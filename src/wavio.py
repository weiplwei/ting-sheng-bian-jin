"""Minimal WAV mono float32 reader/writer (stdlib only)."""
from __future__ import annotations

import struct
import wave
from pathlib import Path

import numpy as np


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Return (mono float32 in [-1, 1], sample_rate)."""
    with wave.open(str(path), "rb") as w:
        n = w.getnframes()
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        raw = w.readframes(n)

    if sw == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        # try 32-bit int first; if values look like float, reinterpret
        as_i4 = np.frombuffer(raw, dtype="<i4")
        if np.max(np.abs(as_i4)) > 8:  # not float-scale
            data = as_i4.astype(np.float32) / 2147483648.0
        else:
            data = np.frombuffer(raw, dtype="<f4").copy()
    elif sw == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        as_i4 = (
            b[:, 0].astype(np.int32)
            | (b[:, 1].astype(np.int32) << 8)
            | (b[:, 2].astype(np.int32) << 16)
        )
        as_i4 = np.where(as_i4 & 0x800000, as_i4 | ~0xFFFFFF, as_i4)
        data = as_i4.astype(np.float32) / 8388608.0
    else:
        raise ValueError(f"unsupported sample width {sw}")

    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return np.ascontiguousarray(data, dtype=np.float32), sr


def write_wav(path: str | Path, data: np.ndarray, sr: int) -> None:
    data = np.clip(data, -1.0, 1.0)
    pcm = (data * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
