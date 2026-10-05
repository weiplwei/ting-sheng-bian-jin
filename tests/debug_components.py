"""Debug score components under noise."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import wavio
from src.dsp import extract_event, feature_from_audio, logmel, cmvn, band_shape, frame_energy, active_mask
from src.matcher import split_feats, best_offset_score, dtw_similarity, cosine_sim

ROOT = Path(__file__).resolve().parents[1]


def add_noise(x, snr_db, rng):
    sig_pow = float(np.mean(x.astype(np.float64) ** 2)) + 1e-12
    noise = rng.standard_normal(len(x)).astype(np.float32)
    spec = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(len(noise), 1.0 / 48000.0)
    weight = 1.0 / (1.0 + (freqs / 300.0))
    noise = np.fft.irfft(spec * weight, n=len(noise)).astype(np.float32)
    noise_pow = float(np.mean(noise.astype(np.float64) ** 2)) + 1e-12
    target = sig_pow / (10.0 ** (snr_db / 10.0))
    noise *= float(np.sqrt(target / noise_pow))
    return (x + noise).astype(np.float32)


def components(live_f, tpl_f):
    lf, ls = split_feats(live_f)
    tf, ts = split_feats(tpl_f)
    if lf.shape[0] > tf.shape[0]:
        cos_t = best_offset_score(lf, tf)
    else:
        cos_t = best_offset_score(tf, lf)
    dtw_t = dtw_similarity(lf[:40], tf[:40])
    timbre = cosine_sim(ls, ts) if ls.size and ts.size else 0.0
    return cos_t, dtw_t, timbre


def main():
    # pick a short clean sample and a 3s dirty one
    samples = list((ROOT / "data" / "library" / "_raw" / "items").glob("*/samples/0001.wav"))
    samples = sorted(samples)
    # use 卡莫纳 (short clean) and 花瓶 (3s)
    clean = None
    dirty = None
    for p in samples:
        import json
        meta = json.loads((p.parent.parent / "meta.json").read_text(encoding="utf-8"))
        if "卡莫纳" in meta["name"] and clean is None:
            clean = p
        if "花瓶" in meta["name"] and dirty is None:
            dirty = p
    print("clean", clean)
    print("dirty", dirty)
    rng = np.random.default_rng(0)

    for label, path in [("clean-short", clean), ("dirty-3s", dirty)]:
        x, sr = wavio.read_wav(path)
        ev = extract_event(x, sr)
        print(f"\n=== {label} len={len(x)/sr:.2f}s event={ev[0]/sr:.3f}-{ev[1]/sr:.3f}s ===")
        tpl = feature_from_audio(x, sr)
        for snr in (40, 20, 10, 0):
            noisy = add_noise(x, snr, rng)
            evn = extract_event(noisy, sr)
            live = feature_from_audio(noisy, sr, event_slice=evn)
            # also try matching with original event slice
            live_orig = feature_from_audio(noisy, sr, event_slice=ev)
            cos_t, dtw_t, timbre = components(live, tpl)
            cos_t2, dtw_t2, timbre2 = components(live_orig, tpl)
            print(
                f"  SNR {snr:3d} | auto-ev cos={cos_t:.3f} dtw={dtw_t:.3f} tim={timbre:.3f} "
                f"| fixed-ev cos={cos_t2:.3f} dtw={dtw_t2:.3f} tim={timbre2:.3f} "
                f"| ev_shift={(evn[0]-ev[0])/sr*1000:.0f}ms"
            )


if __name__ == "__main__":
    main()
