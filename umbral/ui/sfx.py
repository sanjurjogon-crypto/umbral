from __future__ import annotations

import io
import math
import os
import struct
import wave
from functools import lru_cache

try:
    import winsound
except ImportError:  # pragma: no cover - non-Windows
    winsound = None  # type: ignore[assignment]

_SOUNDS_ENABLED = True


def is_sounds_enabled() -> bool:
    return _SOUNDS_ENABLED


def set_sounds_enabled(enabled: bool) -> None:
    global _SOUNDS_ENABLED
    _SOUNDS_ENABLED = bool(enabled)


def _render_wav(samples: list[float], sample_rate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        pcm = bytearray()
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            pcm.extend(struct.pack("<h", int(clamped * 32767)))
        wf.writeframes(bytes(pcm))
    return buf.getvalue()


@lru_cache(maxsize=8)
def _build_sound(kind: str) -> bytes:
    sr = 22050
    if kind == "step":
        n = int(sr * 0.036)
        samples = []
        for i in range(n):
            t = i / sr
            env = math.exp(-t * 95.0) * min(1.0, i / (sr * 0.003))
            freq = 460.0 - 150.0 * (i / max(1, n))
            samples.append(0.11 * env * math.sin(2.0 * math.pi * freq * t))
        return _render_wav(samples, sr)
    if kind == "flip":
        n = int(sr * 0.085)
        samples = []
        for i in range(n):
            t = i / sr
            env = math.sin(math.pi * (i / max(1, n))) ** 1.3
            freq = 260.0 + 240.0 * (i / max(1, n))
            samples.append(0.12 * env * math.sin(2.0 * math.pi * freq * t))
        return _render_wav(samples, sr)
    if kind == "launch":
        n = int(sr * 0.19)
        samples = []
        for i in range(n):
            t = i / sr
            env1 = math.exp(-t * 18.0) * min(1.0, i / (sr * 0.006))
            env2 = math.exp(-max(0.0, t - 0.045) * 16.0) if t >= 0.045 else 0.0
            s = 0.09 * env1 * math.sin(2.0 * math.pi * 440.0 * t)
            s += 0.09 * env2 * math.sin(2.0 * math.pi * 659.25 * t)
            samples.append(s)
        return _render_wav(samples, sr)
    return b""


def play_ui_sound(kind: str) -> None:
    if not _SOUNDS_ENABLED or winsound is None:
        return
    if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        return
    wav = _build_sound(kind)
    if not wav:
        return
    try:
        winsound.PlaySound(
            wav,
            winsound.SND_MEMORY | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
        )
    except RuntimeError:
        pass
