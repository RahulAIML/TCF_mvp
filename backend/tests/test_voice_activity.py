import io
import math
import random
import struct
import wave

import audio_mime
from gemini_service import GeminiService


def _wav(samples, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"".join(struct.pack("<h", max(-32768, min(32767, int(s)))) for s in samples))
    return buf.getvalue()


def test_digital_silence_has_no_speech():
    assert audio_mime.has_speech(_wav([0] * 32000), "audio/wav") is False


def test_quiet_room_noise_has_no_speech():
    rng = random.Random(1)
    assert audio_mime.has_speech(_wav([rng.gauss(0, 60) for _ in range(32000)]), "audio/wav") is False


def test_short_click_is_not_speech():
    samples = [0] * 32000
    for i in range(160):  # 10 ms click
        samples[16000 + i] = 20000
    assert audio_mime.has_speech(_wav(samples), "audio/wav") is False


def test_voice_level_audio_is_speech():
    samples = [6000 * math.sin(2 * math.pi * 180 * t / 16000) for t in range(16000)]
    assert audio_mime.has_speech(_wav(samples), "audio/wav") is True


def test_undecodable_format_is_never_discarded(monkeypatch):
    monkeypatch.setattr(audio_mime.shutil, "which", lambda name: None)
    assert audio_mime.has_speech(b"\x1aE\xdf\xa3 not really webm", "audio/webm") is True


def test_silence_never_reaches_the_model(monkeypatch):
    called = []
    monkeypatch.setattr("gemini_service._gemini_generate", lambda *a, **k: called.append(1))
    assert GeminiService.transcribe_bytes(_wav([0] * 32000), "fr", "audio/wav") == ""
    assert called == []
