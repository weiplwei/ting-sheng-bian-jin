"""Validate calibrated matcher: self, leave-one-out, noise, confusion."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import wavio
from src.calibrate import build_calibrated_matcher, print_report
from src.dsp import feature_from_audio
from src.landmark import constellation_hashes


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


def main() -> None:
    m, meta = build_calibrated_matcher()
    items = meta["items"]
    print_report(meta)

    print("\n1) SELF-MATCH (must be correct top1 + accepted)")
    ok = 0
    total = 0
    for it in items:
        for s in it.get("samples", []):
            x, sr = wavio.read_wav(s["file"])
            feat = feature_from_audio(x, sr)
            live_hashes = constellation_hashes(x, sr)
            rank = m.rank(feat, live_hashes=live_hashes)
            best = rank[0]
            total += 1
            good = best.item_id == it["id"] and best.accepted
            ok += int(good)
            mark = "OK " if good else "BAD"
            print(
                f"  [{mark}] {it['name'][:16]:16s} score={best.score:.3f} "
                f"top={best.name[:12]:12s} Δ={best.margin:.3f} thr={best.effective_threshold:.2f} {best.reason}"
            )
    print(f"  self accepted-accuracy: {ok}/{total}\n")

    print("2) NOISE (top1 correct?)")
    rng = np.random.default_rng(42)
    for snr in (20, 10, 5, 0):
        hits = 0
        acc_hits = 0
        scores = []
        total = 0
        for it in items:
            for s in it.get("samples", []):
                x, sr = wavio.read_wav(s["file"])
                noisy = add_noise(x, snr, rng)
                feat = feature_from_audio(noisy, sr)
                live_hashes = constellation_hashes(noisy, sr)
                best = m.rank(feat, live_hashes=live_hashes)[0]
                total += 1
                scores.append(best.score)
                if best.item_id == it["id"]:
                    hits += 1
                if best.item_id == it["id"] and best.accepted:
                    acc_hits += 1
        print(
            f"  SNR {snr:4d}dB  top1={hits}/{total}  accepted={acc_hits}/{total}  "
            f"mean={np.mean(scores):.3f}"
        )

    print("\n3) LIVE-style: feed each sample through LiveEngine")
    from src.live import LiveConfig, LiveEngine

    eng_hits = 0
    eng_wrong = 0
    eng_miss = 0
    for it in items:
        for s in it.get("samples", []):
            x, sr = wavio.read_wav(s["file"])
            eng = LiveEngine(m, LiveConfig(sr=sr))
            hop = int(sr * 0.02)
            found = None
            for i in range(0, len(x) + hop * 20, hop):
                b = x[i : i + hop] if i < len(x) else np.zeros(hop, dtype=np.float32)
                if b.size < hop:
                    b = np.pad(b, (0, hop - b.size))
                for r in eng.feed(b):
                    if r.accepted:
                        found = r
            if found is None:
                eng_miss += 1
                print(f"  MISS {it['name'][:16]}")
            elif found.item_id == it["id"]:
                eng_hits += 1
                print(f"  HIT  {it['name'][:16]:16s} {found.score:.3f}")
            else:
                eng_wrong += 1
                print(f"  WRONG {it['name'][:16]:16s} → {found.name} {found.score:.3f}")
    print(f"\n  live-engine: hit={eng_hits} wrong={eng_wrong} miss={eng_miss}")


if __name__ == "__main__":
    main()
