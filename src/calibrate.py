"""Build matcher + auto-calibrate thresholds from cross-scores."""
from __future__ import annotations

import numpy as np

from . import wavio
from .dsp import feature_from_audio
from .landmark import constellation_hashes
from .library import load_items
from .matcher import Matcher, Template, match_score

def build_item_feats(items: list[dict]) -> dict[str, list[np.ndarray]]:
    out: dict[str, list[np.ndarray]] = {}
    for it in items:
        feats = []
        for s in it.get("samples", []):
            x, sr = wavio.read_wav(s["file"])
            if x is None or len(x) < 256:
                continue
            feats.append(feature_from_audio(x, sr))
        out[it["id"]] = feats
    return out


def build_item_hashes(items: list[dict]) -> dict[str, list[frozenset]]:
    out: dict[str, list[frozenset]] = {}
    for it in items:
        hs = []
        for s in it.get("samples", []):
            x, sr = wavio.read_wav(s["file"])
            if x is None or len(x) < 256:
                continue
            hs.append(constellation_hashes(x, sr))
        out[it["id"]] = hs
    return out


def cross_matrix(
    items: list[dict],
    feats: dict[str, list[np.ndarray]],
    hashes: dict[str, list[frozenset]] | None = None,
) -> np.ndarray:
    n = len(items)
    ids = [it["id"] for it in items]
    mat = np.zeros((n, n), dtype=np.float64)
    for i, ida in enumerate(ids):
        for j, idb in enumerate(ids):
            if not feats.get(ida) or not feats.get(idb):
                mat[i, j] = -1.0
                continue
            if i == j:
                mat[i, j] = 1.0
                continue
            best = -1.0
            for a_i, a in enumerate(feats[ida]):
                for b_i, b in enumerate(feats[idb]):
                    mel = match_score(a, b)
                    land = None
                    if hashes:
                        ha = hashes.get(ida, [])
                        hb = hashes.get(idb, [])
                        if a_i < len(ha) and b_i < len(hb):
                            from .landmark import constellation_score

                            land = constellation_score(ha[a_i], hb[b_i])
                    from .matcher import combine_scores

                    sc = combine_scores(mel, land)
                    if sc > best:
                        best = sc
            mat[i, j] = best
    return mat


def calibrate_thresholds(
    items: list[dict],
    feats: dict[str, list[np.ndarray]],
    hashes: dict[str, list[frozenset]] | None = None,
    pad: float = 0.15,
) -> dict[str, float]:
    """threshold_i = max(max_cross + pad, 0.85), clamped to [0.85, 0.96]."""
    mat = cross_matrix(items, feats, hashes)
    out: dict[str, float] = {}
    for i, it in enumerate(items):
        others = [mat[i, j] for j in range(len(items)) if j != i and mat[i, j] > -1]
        max_cross = max(others) if others else 0.5
        thr = float(min(0.96, max(0.85, max_cross + pad)))
        out[it["id"]] = thr
    return out


def build_calibrated_matcher(
    pad: float = 0.15,
    margin_min: float = 0.12,
    homophone_margin_min: float = 0.15,
) -> tuple[Matcher, dict]:
    items = load_items()
    feats = build_item_feats(items)
    hashes = build_item_hashes(items)
    thr_map = calibrate_thresholds(items, feats, hashes=hashes, pad=pad)
    m = Matcher(margin_min=margin_min, homophone_margin_min=homophone_margin_min)
    for it in items:
        f = feats.get(it["id"]) or []
        if not f:
            continue
        m.add_template(
            Template(
                item_id=it["id"],
                name=it["name"],
                feats=f,
                hashes=hashes.get(it["id"]) or [],
                threshold=thr_map[it["id"]],
                cooldown_ms=int(it.get("cooldownMs", 400)),
                tags=list(it.get("tags", [])),
            )
        )
    meta = {
        "items": items,
        "thresholds": thr_map,
        "cross": cross_matrix(items, feats, hashes).tolist(),
    }
    return m, meta


def print_report(meta: dict) -> None:
    items = meta["items"]
    thr = meta["thresholds"]
    cross = meta["cross"]
    print("=== calibrated thresholds ===")
    for it in items:
        print(f"  {it['name'][:20]:20s}  thr={thr[it['id']]:.2f}  (was {it.get('threshold', 0.75):.2f})")
    print("\n=== worst confusions (score >= 0.55) ===")
    pairs = []
    for i, a in enumerate(items):
        for j, b in enumerate(items):
            if j <= i:
                continue
            s = cross[i][j]
            if s >= 0.55:
                pairs.append((s, a["name"], b["name"]))
    for s, a, b in sorted(pairs, reverse=True):
        print(f"  {s:.2f}  {a}  ↔  {b}")
