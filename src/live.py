"""Onset detection + live event scoring."""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from .dsp import EPS, feature_from_audio
from .matcher import Matcher, MatchResult


@dataclass
class LiveConfig:
    sr: int = 48000
    hop_ms: float = 20.0
    window_ms: float = 40.0
    onset_margin_db: float = 8.0
    noise_floor_dbfs: float = -70.0
    min_event_ms: float = 100.0
    max_event_ms: float = 400.0
    cooldown_ms: float = 400.0
    highpass_hz: float = 120.0
    ring_seconds: float = 3.0


class LiveEngine:
    """Feed PCM blocks; get MatchResults when events fire."""

    def __init__(self, matcher: Matcher, cfg: LiveConfig | None = None) -> None:
        self.matcher = matcher
        self.cfg = cfg or LiveConfig()
        self.sr = self.cfg.sr
        self.hop = max(64, int(self.sr * self.cfg.hop_ms / 1000.0))
        self.win = max(self.hop, int(self.sr * self.cfg.window_ms / 1000.0))
        self.ring_len = int(self.sr * self.cfg.ring_seconds)
        self.ring = np.zeros(self.ring_len, dtype=np.float32)
        self.write_pos = 0
        self.total_samples = 0
        self.pending = np.zeros(0, dtype=np.float32)
        self.noise_rms = 10.0 ** (self.cfg.noise_floor_dbfs / 20.0)
        self.in_event = False
        self.event_start_sample = 0
        self.event_peak_rms = 0.0
        self.event_frames = 0
        self.quiet_frames = 0
        self.last_hit_ms: dict[str, float] = {}
        self._t0 = time.time()
        self.frames_seen = 0
        self.events_seen = 0
        self.hits: list[dict] = []

    def _now_ms(self) -> float:
        return (time.time() - self._t0) * 1000.0

    def feed(self, block: np.ndarray) -> list[MatchResult]:
        if block.size == 0:
            return []
        if block.dtype != np.float32:
            block = block.astype(np.float32)
        self.pending = np.concatenate([self.pending, block]) if self.pending.size else block.copy()
        out: list[MatchResult] = []
        while self.pending.size >= self.hop:
            frame = self.pending[: self.win]
            self._write_ring(frame[: self.hop])
            self.pending = self.pending[self.hop :]
            rms = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)) + EPS)
            self._update_noise(rms)
            self.frames_seen += 1
            result = self._maybe_event(frame, rms)
            if result is not None:
                out.append(result)
        return out

    def _write_ring(self, x: np.ndarray) -> None:
        n = min(x.size, self.ring_len)
        if n <= 0:
            return
        self.ring = np.roll(self.ring, -n)
        self.ring[-n:] = x[-n:]
        self.total_samples += n

    def _update_noise(self, rms: float) -> None:
        if rms < self.noise_rms:
            self.noise_rms = 0.85 * self.noise_rms + 0.15 * rms
        else:
            self.noise_rms = 0.998 * self.noise_rms + 0.002 * rms
        self.noise_rms = max(self.noise_rms, 10.0 ** (self.cfg.noise_floor_dbfs / 20.0))

    def current_snr_db(self, signal_rms: float | None = None) -> float:
        noise_db = 20.0 * np.log10(self.noise_rms + EPS)
        if signal_rms is None:
            if self.ring_len < 256:
                return 20.0
            # high percentile of last 0.5s
            tail = self.ring[-(self.sr // 2) :]
            if tail.size < 16:
                return 20.0
            sig = float(np.sqrt(np.percentile(tail.astype(np.float64) ** 2, 90) + EPS))
        else:
            sig = float(signal_rms)
        return float(20.0 * np.log10(sig + EPS) - noise_db)

    def _maybe_event(self, frame: np.ndarray, rms: float) -> MatchResult | None:
        rms_db = 20.0 * np.log10(rms + EPS)
        noise_db = 20.0 * np.log10(self.noise_rms + EPS)
        snr_frame = rms_db - noise_db
        rising = snr_frame >= self.cfg.onset_margin_db

        if not self.in_event and rising:
            self.in_event = True
            self.event_start_sample = self.total_samples
            self.event_peak_rms = rms
            self.event_frames = 1
            self.quiet_frames = 0
            return None

        if not self.in_event:
            return None

        self.event_frames += 1
        self.event_peak_rms = max(self.event_peak_rms, rms)

        elapsed_ms = self.event_frames * self.cfg.hop_ms
        min_ms = self.cfg.min_event_ms
        max_ms = self.cfg.max_event_ms

        if rising:
            self.quiet_frames = 0
        else:
            self.quiet_frames += 1

        if elapsed_ms < min_ms:
            return None

        # end only after a real tail (hangover) or hard cap
        hangover_ms = 80.0
        hangover_frames = max(1, int(hangover_ms / self.cfg.hop_ms))
        if elapsed_ms >= max_ms or self.quiet_frames >= hangover_frames:
            self.in_event = False
            self.events_seen += 1
            return self._score_event()

        return None

    def _score_event(self) -> MatchResult | None:
        pre = int(0.03 * self.sr)
        ev_len = int(self.cfg.max_event_ms * self.sr / 1000.0)
        since_onset = int(self.event_frames * self.hop)
        lookback = min(self.ring_len, since_onset + pre + ev_len)
        chunk = self.ring[-lookback:]
        if float(np.max(np.abs(chunk))) < 1e-5:
            return None

        from .dsp import extract_event_candidates, feature_from_audio
        from .landmark import constellation_hashes

        # try several peak windows — dirty ambient can hide the real event
        cands = extract_event_candidates(chunk, self.sr, n_cand=3)
        best: MatchResult | None = None
        best_score = -2.0
        snr_db = self.current_snr_db(signal_rms=self.event_peak_rms)
        for ev in cands:
            feat = feature_from_audio(chunk, self.sr, highpass_hz=self.cfg.highpass_hz, event_slice=ev)
            live_hashes = constellation_hashes(
                chunk, self.sr, highpass_hz=self.cfg.highpass_hz, event_slice=ev
            )
            rank = self.matcher.rank(feat, snr_db=snr_db, live_hashes=live_hashes)
            if not rank:
                continue
            top = rank[0]
            key = (1 if top.accepted else 0, top.score)
            prev = (1 if best and best.accepted else 0, best_score) if best else (0, -2.0)
            if key > prev:
                best = top
                best_score = top.score
        if best is None:
            return None
        if best.accepted:
            import time as _time

            last = self.matcher._last_hit_ts.get(best.item_id)
            cool = 400
            tpl = next((t for t in self.matcher.templates if t.item_id == best.item_id), None)
            if tpl:
                cool = tpl.cooldown_ms
            now = _time.time() * 1000.0
            if last is not None and (now - last) < cool:
                return None
            self.matcher._last_hit_ts[best.item_id] = now
            self.hits.append(
                {
                    "item_id": best.item_id,
                    "name": best.name,
                    "score": best.score,
                    "margin": best.margin,
                    "threshold": best.threshold,
                    "effective_threshold": best.effective_threshold,
                    "snr_db": snr_db,
                    "t_ms": now,
                }
            )
        return best
