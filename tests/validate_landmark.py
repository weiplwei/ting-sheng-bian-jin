"""Evaluate constellation fingerprint on leave-one-out + noise."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import wavio
from src.landmark import constellation_hashes, constellation_score

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


def main() -> None:
    items = __import__("json").loads(
        (ROOT / "data" / "library" / "items.json").read_text(encoding="utf-8")
    )

    print("=== same-item different samples ===")
    for it in items:
        if len(it["samples"]) < 2:
            continue
        hs = []
        for s in it["samples"]:
            x, sr = wavio.read_wav(s["file"])
            hs.append(constellation_hashes(x, sr))
        for i in range(len(hs)):
            for j in range(i + 1, len(hs)):
                inter = len(hs[i] & hs[j])
                sc = constellation_score(hs[i], hs[j])
                print(
                    f"  {it['name'][:12]:12s} s{i}-s{j}  {sc:.3f}  "
                    f"hashes {len(hs[i])}/{len(hs[j])} inter={inter}"
                )

    print("\n=== leave-one-out top1 ===")
    ok_n = bad_n = 0
    for it in items:
        for si, s in enumerate(it["samples"]):
            x, sr = wavio.read_wav(s["file"])
            live = constellation_hashes(x, sr)
            best = (-1.0, "")
            second = (-1.0, "")
            for it2 in items:
                scores = []
                for sj, s2 in enumerate(it2["samples"]):
                    if it2["id"] == it["id"] and sj == si:
                        continue
                    x2, sr2 = wavio.read_wav(s2["file"])
                    h2 = constellation_hashes(x2, sr2)
                    scores.append(constellation_score(live, h2))
                if not scores:
                    continue
                sc = max(scores)
                if sc > best[0]:
                    second = best
                    best = (sc, it2["name"])
                elif sc > second[0]:
                    second = (sc, it2["name"])
            good = best[1] == it["name"]
            ok_n += int(good)
            bad_n += int(not good)
            mark = "OK " if good else "BAD"
            print(
                f"  [{mark}] {it['name'][:14]:14s} hold=s{si}  "
                f"top={best[1][:12]:12s} {best[0]:.3f}  2nd={second[0]:.3f}"
            )
    print(f"  leave-one-out: ok={ok_n} bad={bad_n}")

    print("\n=== noise: self-hash overlap ===")
    rng = np.random.default_rng(42)
    for snr in (20, 10, 5, 0):
        scores, covers = [], []
        top1 = 0
        total = 0
        for it in items:
            for s in it["samples"]:
                x, sr = wavio.read_wav(s["file"])
                clean = constellation_hashes(x, sr)
                noisy = constellation_hashes(add_noise(x, snr, rng), sr)
                sc = constellation_score(noisy, clean)
                scores.append(sc)
                # top1 among items
                best = (-1, "")
                for it2 in items:
                    for s2 in it2["samples"]:
                        x2, sr2 = wavio.read_wav(s2["file"])
                        h2 = constellation_hashes(x2, sr2)
                        v = constellation_score(noisy, h2)
                        if v > best[0]:
                            best = (v, it2["name"])
                total += 1
                if best[1] == it["name"]:
                    top1 += 1
        print(
            f"  SNR {snr:3d}  self_mean={np.mean(scores):.3f}  "
            f"top1={top1}/{total}"
        )


if __name__ == "__main__":
    main()
