"""Noise-robust log-mel features + event anchoring (numpy only)."""
from __future__ import annotations

import numpy as np

SR = 48000
N_FFT = 2048
HOP = 512
N_MELS = 64
FMIN = 40.0
FMAX = 16000.0
EPS = 1e-8


def _hz_to_mel(hz: np.ndarray | float) -> np.ndarray | float:
    return 2595.0 * np.log10(1.0 + np.asarray(hz) / 700.0)


def _mel_to_hz(mel: np.ndarray | float) -> np.ndarray | float:
    return 700.0 * (10.0 ** (np.asarray(mel) / 2595.0) - 1.0)


def mel_filterbank(sr: int = SR, n_fft: int = N_FFT, n_mels: int = N_MELS,
                   fmin: float = FMIN, fmax: float = FMAX) -> np.ndarray:
    n_bins = n_fft // 2 + 1
    fft_freqs = np.linspace(0.0, sr / 2.0, n_bins)
    mel_points = np.linspace(_hz_to_mel(fmin), _hz_to_mel(fmax), n_mels + 2)
    hz_points = _mel_to_hz(mel_points)
    fb = np.zeros((n_mels, n_bins), dtype=np.float32)
    for i in range(n_mels):
        left, center, right = hz_points[i], hz_points[i + 1], hz_points[i + 2]
        up = (fft_freqs - left) / max(center - left, 1e-6)
        down = (right - fft_freqs) / max(right - center, 1e-6)
        fb[i] = np.maximum(0.0, np.minimum(up, down))
    enorm = 2.0 / (hz_points[2:] - hz_points[:-2])
    fb *= enorm[:, None].astype(np.float32)
    return fb


_MEL_FB: dict[tuple[int, int, int, int, int], np.ndarray] = {}


def get_mel_fb(sr: int = SR) -> np.ndarray:
    key = (sr, N_FFT, N_MELS, int(FMIN), int(FMAX))
    if key not in _MEL_FB:
        _MEL_FB[key] = mel_filterbank(sr, N_FFT, N_MELS, FMIN, FMAX)
    return _MEL_FB[key]


def highpass_fft(x: np.ndarray, cutoff_hz: float = 120.0, sr: int = SR) -> np.ndarray:
    if cutoff_hz <= 0:
        return x
    n = len(x)
    if n < 8:
        return x
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    ratio = np.where(freqs > 0, freqs / cutoff_hz, 0.0)
    gain = (ratio**2 / (1.0 + ratio**2)).astype(np.float32)
    spec = spec * gain
    return np.fft.irfft(spec, n=n).astype(np.float32)


def stft_power(x: np.ndarray, n_fft: int = N_FFT, hop: int = HOP) -> np.ndarray:
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    n_frames = 1 + (len(x) - n_fft) // hop
    window = np.hanning(n_fft).astype(np.float32)
    out = np.empty((n_frames, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_frames):
        seg = x[i * hop : i * hop + n_fft] * window
        spec = np.fft.rfft(seg)
        out[i] = (spec.real**2 + spec.imag**2).astype(np.float32)
    return out


def frame_energy(x: np.ndarray, n_fft: int = N_FFT, hop: int = HOP) -> np.ndarray:
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    n_frames = 1 + (len(x) - n_fft) // hop
    out = np.empty(n_frames, dtype=np.float32)
    for i in range(n_frames):
        seg = x[i * hop : i * hop + n_fft]
        out[i] = float(np.mean(seg.astype(np.float64) ** 2))
    return out


def smooth_energy(energy: np.ndarray, k: int = 5) -> np.ndarray:
    if k <= 1 or len(energy) < 2:
        return energy
    kernel = np.ones(k, dtype=np.float32) / k
    return np.convolve(energy, kernel, mode="same").astype(np.float32)


def spectral_subtract(power: np.ndarray, strength: float = 1.2, floor: float = 0.08) -> np.ndarray:
    """Per-bin Wiener-ish gain using the quietest ~25% frames as noise estimate."""
    if power.size == 0:
        return power
    n = power.shape[0]
    k = max(1, n // 4)
    # order frames by total energy
    totals = power.sum(axis=1)
    order = np.argsort(totals)
    noise = power[order[:k]].mean(axis=0) + EPS
    # over-subtract then floor
    est = np.maximum(power - strength * noise, floor * noise)
    # Wiener-like gain
    gain = est / (est + noise + EPS)
    return (power * gain).astype(np.float32)


def logmel(
    x: np.ndarray,
    sr: int = SR,
    highpass_hz: float = 120.0,
    denoise: bool = True,
) -> np.ndarray:
    x = highpass_fft(x, highpass_hz, sr)
    power = stft_power(x)
    if denoise:
        power = spectral_subtract(power)
    mel = power @ get_mel_fb(sr).T
    return np.log(mel + EPS).astype(np.float32)


def extract_event(
    x: np.ndarray,
    sr: int = SR,
    pad_ms: float = 15.0,
    drop_db: float = 15.0,
    min_ms: float = 120.0,
    max_ms: float = 280.0,
) -> tuple[int, int]:
    """Locate the main sound event as a peak-centered fixed-ish window.

    Anchor is the sample-accurate absolute peak of the waveform so leading
    silence cannot shift the crop (STFT frame peaks quantize and drift).
    """
    n = len(x)
    if n < 256:
        return 0, n

    # sample-accurate anchor
    absx = np.abs(x)
    peak_s = int(np.argmax(absx))
    if absx[peak_s] <= 0:
        return 0, n

    # preferred: slightly more post-peak than pre-peak (attack is short)
    min_len = int(min_ms * sr / 1000.0)
    max_len = int(max_ms * sr / 1000.0)
    target = min(max_len, max(min_len, int(0.22 * sr)))
    pre = int(target * 0.28)
    start = peak_s - pre
    end = start + target
    if start < 0:
        end = min(n, end - start)
        start = 0
    if end > n:
        start = max(0, start - (end - n))
        end = n
    return int(start), int(end)


def cmvn(feat: np.ndarray, active: np.ndarray | None = None) -> np.ndarray:
    if feat.size == 0:
        return feat
    if active is None or not np.any(active):
        active = np.ones(feat.shape[0], dtype=bool)
    ref = feat[active]
    mean = ref.mean(axis=0, keepdims=True)
    std = np.maximum(ref.std(axis=0, keepdims=True), 1e-4)
    return ((feat - mean) / std).astype(np.float32)


def active_mask(energy: np.ndarray, drop_db: float = 22.0) -> np.ndarray:
    if energy.size == 0:
        return np.zeros(0, dtype=bool)
    peak = float(energy.max())
    if peak <= 0:
        return np.zeros(energy.size, dtype=bool)
    thr = peak * (10.0 ** (-drop_db / 10.0))
    return energy >= thr


def band_shape(feat: np.ndarray) -> np.ndarray:
    """Noise-invariant summary: time-averaged band shape, L2-normalized.

    Additive noise mostly lifts the floor; the *shape* of the peak bands
    is more stable than absolute log-mel values.
    """
    if feat.size == 0:
        return feat
    shape = feat.mean(axis=0, keepdims=True)
    # also include temporal peak (most distinctive frames)
    peak_frame = feat[np.argmax(np.linalg.norm(feat, axis=1)) :][
        :1
    ]
    stacked = np.vstack([shape, peak_frame])
    # L2 normalize each row
    norms = np.linalg.norm(stacked, axis=1, keepdims=True) + 1e-8
    return (stacked / norms).astype(np.float32)


def extract_event_candidates(
    x: np.ndarray,
    sr: int = SR,
    n_cand: int = 3,
    min_sep_ms: float = 80.0,
) -> list[tuple[int, int]]:
    """Top-N peak-centered windows (for dirty multi-event clips)."""
    n = len(x)
    if n < 256:
        return [(0, n)]
    absx = np.abs(x).astype(np.float64)
    k = max(1, int(sr * 0.008))
    kernel = np.ones(k) / k
    smooth = np.convolve(absx, kernel, mode="same")
    peaks: list[int] = []
    sep = int(sr * min_sep_ms / 1000.0)
    work = smooth.copy()
    for _ in range(n_cand):
        p = int(np.argmax(work))
        if work[p] <= 0:
            break
        peaks.append(p)
        lo = max(0, p - sep)
        hi = min(n, p + sep)
        work[lo:hi] = 0
    out: list[tuple[int, int]] = []
    for p in peaks:
        target = min(int(0.28 * sr), int(0.22 * sr))
        pre = int(target * 0.28)
        start = p - pre
        end = start + target
        if start < 0:
            end = min(n, end - start)
            start = 0
        if end > n:
            start = max(0, start - (end - n))
            end = n
        out.append((int(start), int(end)))
    return out or [extract_event(x, sr)]


def feature_from_audio(
    x: np.ndarray,
    sr: int = SR,
    highpass_hz: float = 120.0,
    event_slice: tuple[int, int] | None = None,
    denoise: bool = True,
) -> np.ndarray:
    """Event crop → highpass → denoise → log-mel → level norm + band-shape.

    Intentionally does NOT apply per-band CMVN: that normalizes away the
    global spectral shape which is what tells 卡莫纳 from 琥珀 apart.
    Only overall level is removed so loudness/recording gain cannot dominate.
    """
    if event_slice is None:
        event_slice = extract_event(x, sr)
    seg = x[event_slice[0] : event_slice[1]]
    if seg.size < 256:
        seg = x
    feat = logmel(seg, sr, highpass_hz, denoise=denoise)
    # remove overall level only (keep band shape)
    feat = feat - float(feat.mean())
    shape = band_shape(feat)
    return np.vstack([feat, shape]).astype(np.float32)
