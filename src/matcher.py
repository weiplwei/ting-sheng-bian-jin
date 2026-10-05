"""Multi-offset template matcher: noise-tolerant cosine + adaptive threshold."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .dsp import feature_from_audio


def _l2_rows(a: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(a, axis=1, keepdims=True) + 1e-8
    return a / n


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    va = a.reshape(-1).astype(np.float64)
    vb = b.reshape(-1).astype(np.float64)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def pearson_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation of flattened features (mean-centered cosine)."""
    va = a.reshape(-1).astype(np.float64)
    vb = b.reshape(-1).astype(np.float64)
    if va.size == 0 or vb.size == 0 or va.size != vb.size:
        return 0.0
    va = va - va.mean()
    vb = vb - vb.mean()
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def frame_profile_sim(a: np.ndarray, b: np.ndarray) -> float:
    t = min(a.shape[0], b.shape[0])
    if t == 0:
        return 0.0
    aa = _l2_rows(a[:t].astype(np.float64))
    bb = _l2_rows(b[:t].astype(np.float64))
    return float(np.mean(np.sum(aa * bb, axis=1)))


def energy_envelope(feat: np.ndarray) -> np.ndarray:
    """1-D per-frame energy envelope for timing correlation."""
    if feat.size == 0:
        return np.zeros(0, dtype=np.float64)
    return np.linalg.norm(feat, axis=1).astype(np.float64)


def envelope_ncc(a: np.ndarray, b: np.ndarray) -> float:
    """Normalized cross-correlation of two envelopes (timing check)."""
    if a.size == 0 or b.size == 0:
        return -1.0
    n = min(a.size, b.size)
    aa = a[:n] - a[:n].mean()
    bb = b[:n] - b[:n].mean()
    na = np.linalg.norm(aa)
    nb = np.linalg.norm(bb)
    if na < 1e-12 or nb < 1e-12:
        return -1.0
    return float(np.dot(aa, bb) / (na * nb))


def best_offset_scores(long: np.ndarray, short: np.ndarray) -> tuple[float, float, float]:
    """Return (cosine, pearson, profile) at the best temporal offset."""
    L, S = long.shape[0], short.shape[0]
    if S == 0 or L == 0:
        return -1.0, -1.0, -1.0
    if L == S:
        return (
            cosine_sim(long, short),
            pearson_sim(long, short),
            frame_profile_sim(long, short),
        )
    best_c, best_p, best_f = -1.0, -1.0, -1.0
    max_off = L - S
    step = 1 if max_off <= 40 else max(1, max_off // 40)
    for off in range(0, max_off + 1, step):
        seg = long[off : off + S]
        c = cosine_sim(seg, short)
        if c > best_c:
            best_c = c
            best_p = pearson_sim(seg, short)
            best_f = frame_profile_sim(seg, short)
        if best_c > 0.98:
            break
    return best_c, best_p, best_f


def split_feats(feat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if feat.shape[0] < 3:
        return feat, feat[:0]
    return feat[:-2], feat[-2:]


def match_score(live_feat: np.ndarray, tpl_feat: np.ndarray) -> float:
    """Noise-tolerant score in [0, 1]-ish (can go slightly negative)."""
    if live_feat.size == 0 or tpl_feat.size == 0:
        return -1.0
    live_frames, live_shape = split_feats(live_feat)
    tpl_frames, tpl_shape = split_feats(tpl_feat)

    if live_frames.shape[0] > 0 and tpl_frames.shape[0] > 0:
        if live_frames.shape[0] > tpl_frames.shape[0]:
            cos_t, pear_t, prof_t = best_offset_scores(live_frames, tpl_frames)
        else:
            cos_t, pear_t, prof_t = best_offset_scores(tpl_frames, live_frames)
        env = envelope_ncc(energy_envelope(live_frames), energy_envelope(tpl_frames))
        env_s = 0.5 * (env + 1.0)
        temporal = 0.58 * cos_t + 0.22 * max(pear_t, 0.0) + 0.12 * max(prof_t, 0.0) + 0.08 * env_s
    else:
        temporal = -1.0

    if live_shape.size and tpl_shape.size:
        timbre = max(cosine_sim(live_shape, tpl_shape), 0.0)
    else:
        timbre = 0.0

    return float(0.82 * temporal + 0.18 * timbre)


def combine_scores(mel: float, landmark: float | None) -> float:
    """Blend mel cosine with constellation agreement.

    Constellation is nearly 0 between different items and high for true
    matches, so it acts as a discriminator. Mel alone is noise-robust.
    """
    if landmark is None:
        return mel
    # landmark in [0,1]; 0.15+ is real agreement, 0.03- is "different sound"
    if landmark >= 0.15:
        return float(min(1.0, mel * 1.06 + 0.10 * landmark))
    if landmark <= 0.04 and mel < 0.98:
        # no landmark agreement — penalize so neighbors don't sneak through
        return float(mel * 0.82)
    return mel


@dataclass
class Template:
    item_id: str
    name: str
    feats: list[np.ndarray] = field(default_factory=list)
    hashes: list[frozenset] = field(default_factory=list)
    threshold: float = 0.85
    cooldown_ms: int = 400
    tags: list[str] = field(default_factory=list)


@dataclass
class MatchResult:
    item_id: str
    name: str
    score: float
    second_score: float
    margin: float
    threshold: float
    effective_threshold: float
    accepted: bool
    reason: str


def noise_snr_db(signal_rms_dbfs: float, noise_rms_dbfs: float) -> float:
    return signal_rms_dbfs - noise_rms_dbfs


def effective_threshold(base_thr: float, snr_db: float | None) -> float:
    """Only slightly relax under noise — never trade accuracy for hits.

    Wrong IDs are worse than misses (user feedback), so we keep the bar
    close to the calibrated threshold even in noise.
    """
    if snr_db is None:
        return base_thr
    snr_db = float(np.clip(snr_db, -10.0, 25.0))
    # -10 dB → 0.88×, 0 dB → 0.93×, 20 dB → 1.0×
    scale = 0.88 + 0.12 * ((snr_db + 10.0) / 35.0)
    return float(base_thr * scale)


class Matcher:
    def __init__(
        self,
        margin_min: float = 0.08,
        homophone_margin_min: float = 0.12,
    ) -> None:
        self.templates: list[Template] = []
        self.margin_min = margin_min
        self.homophone_margin_min = homophone_margin_min
        self._last_hit_ts: dict[str, float] = {}

    def add_template(self, tpl: Template) -> None:
        self.templates.append(tpl)

    def build_from_items(self, items: list[dict], audio_loader) -> None:
        for it in items:
            feats = []
            for s in it.get("samples", []):
                path = s.get("file")
                if not path:
                    continue
                try:
                    x, sr = audio_loader(path)
                except Exception:
                    continue
                if x is None or len(x) < 256:
                    continue
                feats.append(feature_from_audio(x, sr))
            if not feats:
                continue
            self.add_template(
                Template(
                    item_id=it["id"],
                    name=it["name"],
                    feats=feats,
                    threshold=float(it.get("threshold", 0.75)),
                    cooldown_ms=int(it.get("cooldownMs", 400)),
                    tags=list(it.get("tags", [])),
                )
            )

    def score_item(self, live_feat: np.ndarray, tpl: Template) -> float:
        if not tpl.feats:
            return -1.0
        return max(match_score(live_feat, f) for f in tpl.feats)

    def score_item_full(
        self,
        live_feat: np.ndarray,
        live_hashes: frozenset | None,
        tpl: Template,
    ) -> float:
        if not tpl.feats:
            return -1.0
        best = -1.0
        for i, f in enumerate(tpl.feats):
            mel = match_score(live_feat, f)
            land = None
            if live_hashes is not None and i < len(tpl.hashes):
                from .landmark import constellation_score

                land = constellation_score(live_hashes, tpl.hashes[i])
            sc = combine_scores(mel, land)
            if sc > best:
                best = sc
        return best

    def _is_homophone(self, tpl: Template) -> bool:
        return any("同音" in t for t in tpl.tags) or "同音" in tpl.name

    def rank(self, live_feat: np.ndarray, snr_db: float | None = None, live_hashes: frozenset | None = None) -> list[MatchResult]:
        scored: list[tuple[float, Template]] = []
        for tpl in self.templates:
            sc = self.score_item_full(live_feat, live_hashes, tpl)
            scored.append((sc, tpl))
        scored.sort(key=lambda x: x[0], reverse=True)
        results: list[MatchResult] = []
        for i, (score, tpl) in enumerate(scored):
            if i == 0:
                second = scored[1][0] if len(scored) > 1 else -1.0
                margin = score - second
            else:
                second = scored[0][0]
                margin = score - scored[0][0]
            need = self.homophone_margin_min if self._is_homophone(tpl) else self.margin_min
            ethr = effective_threshold(tpl.threshold, snr_db)
            if i == 0:
                accepted = score >= ethr and margin >= need
                if accepted:
                    reason = "ok"
                elif score < ethr:
                    reason = "low_score"
                else:
                    reason = "low_margin"
            else:
                accepted = False
                reason = "not_best"
            results.append(
                MatchResult(
                    item_id=tpl.item_id,
                    name=tpl.name,
                    score=score,
                    second_score=second,
                    margin=margin,
                    threshold=tpl.threshold,
                    effective_threshold=ethr,
                    accepted=accepted,
                    reason=reason,
                )
            )
        return results

    def match(
        self,
        live_feat: np.ndarray,
        now_ms: float | None = None,
        snr_db: float | None = None,
        live_hashes: frozenset | None = None,
    ) -> MatchResult | None:
        import time as _time

        if now_ms is None:
            now_ms = _time.time() * 1000.0
        results = self.rank(live_feat, snr_db=snr_db, live_hashes=live_hashes)
        if not results:
            return None
        best = results[0]
        if not best.accepted:
            return best
        last = self._last_hit_ts.get(best.item_id)
        tpl = next((t for t in self.templates if t.item_id == best.item_id), None)
        cool = tpl.cooldown_ms if tpl else 400
        if last is not None and (now_ms - last) < cool:
            return None
        self._last_hit_ts[best.item_id] = now_ms
        return best
