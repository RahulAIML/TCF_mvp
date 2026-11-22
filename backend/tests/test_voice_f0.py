"""The pitch gate accepts an adult tone and rejects a childlike or an elderly one."""
import math
import struct

from qa.voice_f0 import in_adult_range, median_f0


def _tone(freq: float, rate: int = 16000, seconds: float = 0.6) -> bytes:
    pcm = bytearray()
    for i in range(int(rate * seconds)):
        value = int(8000 * math.sin(2 * math.pi * freq * i / rate))
        pcm += struct.pack("<h", value)
    return bytes(pcm)


def test_a_male_tone_and_a_female_tone_land_in_range():
    male = median_f0(_tone(120), 16000)
    female = median_f0(_tone(200), 16000)
    assert male is not None and 100 < male < 140
    assert female is not None and 175 < female < 230
    assert in_adult_range("male", male)
    assert in_adult_range("female", female)


def test_a_child_pitch_and_an_elderly_pitch_are_rejected():
    assert in_adult_range("male", 280) is False
    assert in_adult_range("female", 320) is False
    assert in_adult_range("male", 70) is False
    assert in_adult_range("female", 140) is False
