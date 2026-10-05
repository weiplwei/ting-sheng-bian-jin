"""Shazam-style constellation / landmark fingerprint (discriminative)."""
from __future__ import annotations

import numpy as np

from .dsp import N_FFT, HOP, SR, extract_event, highpass_fft, stft_power

# landmark params
PEAK_AMP = 4          # peaks per frame kept
FANOUT = 5            # pair each peak with next N
MIN_DT = 2            # frames
MAX_DT = 24           # frames
BAND_HZ = 80.0        # quantize freq to this (for hash robustness)


def _find_peaks(power: np.ndarray, top_k: int = PEAK_AMP) -> list[tuple[int, int, float]]:
    """Return list of (frame, freq_bin, energy) local maxima."""
    peaks: list[tuple[int, int, float]] = []
    n_frames, n_bins = power.shape
    for t in range(n_frames):
        row = power[t]
        # cheap top-k
        if n_bins <= top_k:
            idxs = range(n_bins)
        else:
            idxs = np.argpartition(row, -top_k)[-top_k:]
        for f in idxs:
            f = int(f)
            e = float(row[f])
            if e <= 0:
                continue
            # local max in 3x3
            f0, f1 = max(0, f - 1), min(n_bins, f + 2)
            t0, t1 = max(0, t - 1), min(n_frames, t + 2)
            if e >= power[t0:t1, f0:f1].max() - 1e-9:
                peaks.append((t, f, e))
    peaks.sort(key=lambda x: x[2], reverse=True)
    return peaks


def _quant_freq(f_bin: int, sr: int, n_fft: int) -> int:
    hz = f_bin * sr / n_fft
    return int(hz // BAND_HZ)


def constellation_hashes(
    x: np.ndarray,
    sr: int = SR,
    highpass_hz: float = 120.0,
    event_slice: tuple[int, int] | None = None,
) -> frozenset[tuple[int, int, int]]:
    """Landmark hashes: (f1_q, f2_q, dt) for peak pairs."""
    if event_slice is None:
        event_slice = extract_event(x, sr)
    seg = x[event_slice[0] : event_slice[1]]
    if seg.size < 256:
        seg = x
    seg = highpass_fft(seg, highpass_hz, sr)
    power = stft_power(seg)
    # emphasize peaks relative to frame median (noise-robust)
    med = np.median(power, axis=1, keepdims=True) + 1e-12
    power = power / med

    peaks = _find_peaks(power, top_k=PEAK_AMP)
    peaks.sort(key=lambda p: (p[0], p[1]))  # by time

    hashes: set[tuple[int, int, int]] = set()
    n = len(peaks)
    for i in range(n):
        t1, f1, _ = peaks[i]
        paired = 0
        for j in range(i + 1, n):
            if paired >= FANOUT:
                break
            t2, f2, _ = peaks[j]
            dt = t2 - t1
            if dt < MIN_DT:
                continue
            if dt > MAX_DT:
                break
            q1, q2 = _quant_freq(f1, sr, N_FFT), _quant_freq(f2, sr, N_FFT)
            if q1 == q2:
                continue
            hashes.add((q1, q2, dt))
            paired += 1
    return frozenset(hashes)


def constellation_score(
    live: frozenset[tuple[int, int, int]],
    tpl: frozenset[tuple[int, int, int]],
) -> float:
    """Score in [0,1]: Jaccard-like with bonus for high absolute overlap."""
    if not live or not tpl:
        return -1.0
    inter = len(live & tpl)
    union = len(live | tpl)
    if inter == 0:
        return 0.0
    jaccard = inter / union
    # coverage of the shorter set
    cover = inter / min(len(live), len(tpl))
    return float(0.45 * jaccard + 0.55 * cover)


def match_constellation(
    live_x: np.ndarray,
    tpl_hashes_list: list[frozenset[tuple[int, int, int]]],
    sr: int = SR,
    highpass_hz: float = 120.0,
) -> float:
    live_h = constellation_hashes(live_x, sr, highpass_hz)
    if not live_h or not tpl_hashes_list:
        return -1.0
    return max(constellation_score(live_h, th) for th in tpl_hashes_list)
