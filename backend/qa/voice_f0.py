"""Median speaking pitch, used to reject a childlike or elderly voice.

Adult male speech sits near 85–155 Hz. Adult female speech sits near 165–255 Hz.
"""
from __future__ import annotations

import numpy as np

MALE = (85.0, 155.0)
FEMALE = (165.0, 255.0)


def median_f0(pcm: bytes, sample_rate: int) -> float | None:
    """Median fundamental frequency of the voiced frames, or None when the clip has no pitch."""
    if sample_rate <= 0 or len(pcm) < 4:
        return None
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
    if samples.size < sample_rate // 5:
        return None
    samples = samples - np.mean(samples)
    frame = int(sample_rate * 0.04)
    hop = int(sample_rate * 0.01)
    low = int(sample_rate / 400)
    high = int(sample_rate / 70)
    pitches: list[float] = []
    window = np.hanning(frame)
    for start in range(0, samples.size - frame, hop):
        chunk = samples[start:start + frame] * window
        if np.sqrt(np.mean(chunk * chunk)) < 400:
            continue
        corr = np.correlate(chunk, chunk, mode="full")[frame - 1:]
        if high >= corr.size or corr[0] <= 0:
            continue
        lag = low + int(np.argmax(corr[low:high]))
        if corr[lag] < 0.3 * corr[0]:
            continue
        pitches.append(sample_rate / lag)
    if len(pitches) < 5:
        return None
    return float(np.median(np.asarray(pitches)))


def in_adult_range(gender: str, hertz: float | None) -> bool:
    if hertz is None:
        return False
    low, high = MALE if gender == "male" else FEMALE
    return low <= hertz <= high
