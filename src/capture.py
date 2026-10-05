"""WASAPI loopback capture via soundcard (optional) + WAV file source."""
from __future__ import annotations

from typing import Iterator, Protocol

import numpy as np

from . import wavio


class AudioSource(Protocol):
    def read(self, frames: int) -> np.ndarray: ...
    def close(self) -> None: ...


class WavSource:
    """Offline source: yields the whole file in chunks (then silence)."""

    def __init__(self, path: str, sr: int = 48000) -> None:
        data, file_sr = wavio.read_wav(path)
        if file_sr != sr:
            data = _resample_linear(data, file_sr, sr)
        self.data = data
        self.sr = sr
        self.pos = 0
        self.finished = False

    def read(self, frames: int) -> np.ndarray:
        if self.pos >= len(self.data):
            self.finished = True
            return np.zeros(frames, dtype=np.float32)
        end = min(len(self.data), self.pos + frames)
        chunk = self.data[self.pos : end]
        self.pos = end
        if self.pos >= len(self.data):
            self.finished = True
        if chunk.size < frames:
            chunk = np.pad(chunk, (0, frames - chunk.size))
        return chunk.astype(np.float32)

    def close(self) -> None:
        pass


class LoopbackSource:
    """System loopback via the `soundcard` package (WASAPI on Windows)."""

    def __init__(self, sr: int = 48000, device_name: str | None = None) -> None:
        import soundcard as sc  # lazy

        self._sc = sc
        self.sr = sr
        if device_name:
            speaker = None
            for s in sc.all_speakers():
                if device_name.lower() in s.name.lower():
                    speaker = s
                    break
            if speaker is None:
                raise RuntimeError(f"speaker not found: {device_name}")
        else:
            speaker = sc.default_speaker()
        # soundcard loopback: get_microphone(name, include_loopback=True)
        mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        self._rec = mic.recorder(samplerate=sr, channels=1)
        self._rec.__enter__()
        self._closed = False

    def read(self, frames: int) -> np.ndarray:
        data = self._rec.record(numframes=frames)
        # soundcard returns (frames, channels)
        if data.ndim > 1:
            data = data.mean(axis=1)
        return np.ascontiguousarray(data, dtype=np.float32)

    def close(self) -> None:
        if not self._closed:
            try:
                self._rec.__exit__(None, None, None)
            except Exception:
                pass
            self._closed = True


def _resample_linear(x: np.ndarray, sr0: int, sr1: int) -> np.ndarray:
    if sr0 == sr1 or x.size == 0:
        return x
    n1 = int(round(x.size * sr1 / sr0))
    t0 = np.linspace(0.0, 1.0, num=x.size, endpoint=False)
    t1 = np.linspace(0.0, 1.0, num=n1, endpoint=False)
    return np.interp(t1, t0, x).astype(np.float32)


def open_source(
    kind: str = "loopback",
    path: str | None = None,
    device: str | None = None,
    sr: int = 48000,
) -> AudioSource:
    if kind == "wav":
        if not path:
            raise ValueError("wav source needs path")
        return WavSource(path, sr=sr)
    return LoopbackSource(sr=sr, device_name=device)


def iter_blocks(source: AudioSource, frames: int) -> Iterator[np.ndarray]:
    while True:
        block = source.read(frames)
        yield block
