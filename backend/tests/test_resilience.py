"""Provider blips and an empty pool must still produce a usable item."""
import threading
import time

import pytest

import audio_jobs
import listening_service as ls
import reading_service as rs
import resilience


def test_retry_absorbs_a_rate_limit_then_returns():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("HTTP 429")
        return "ok"

    assert resilience.retry(flaky, attempts=4) == "ok"
    assert calls["n"] == 3


def test_retry_does_not_repeat_a_validation_error():
    calls = {"n": 0}

    def bad():
        calls["n"] += 1
        raise ValueError("duplicate options")

    with pytest.raises(ValueError):
        resilience.retry(bad, attempts=4)
    assert calls["n"] == 1


def test_audio_route_retries_a_provider_429(client, monkeypatch):
    calls = {"n": 0}

    def fake(script, speakers=None, report=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("ElevenLabs HTTP 429")
        if report is not None:
            report.append({"speaker": "Marc", "voice_id": "fr-FR-male-1", "provider": "test", "provider_voice": "Charon", "pitch_semitones": -4})
        return "/audio/ok.mp3"

    monkeypatch.setattr(ls, "synthesize_listening_audio", fake)
    response = client.post(
        "/tcf/generate-listening-audio",
        json={"script": "Marc : Bonjour. Sophie : Salut.", "speakers": ["Marc", "Sophie"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["audio_url"] == "/audio/ok.mp3"
    assert calls["n"] == 3


def test_long_audio_returns_a_job_and_then_the_file(client, monkeypatch):
    monkeypatch.setattr(audio_jobs, "INLINE_WAIT_SECONDS", 0.05)
    release = threading.Event()

    def fake(script, speakers=None, report=None):
        release.wait(2)
        return "/audio/slow.mp3"

    monkeypatch.setattr(ls, "synthesize_listening_audio", fake)
    started = client.post(
        "/tcf/generate-listening-audio",
        json={"script": "Un long entretien qui dépasse le délai du proxy.", "speakers": []},
    )
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["status"] == "pending" and body["job_id"]
    release.set()
    ready = None
    for _ in range(40):
        polled = client.get(f"/tcf/listening-audio-jobs/{body['job_id']}")
        assert polled.status_code == 200
        if polled.json().get("audio_url"):
            ready = polled.json()
            break
        time.sleep(0.05)
    assert ready is not None and ready["audio_url"] == "/audio/slow.mp3"


def test_listening_question_survives_an_empty_pool_and_a_down_provider(monkeypatch):
    monkeypatch.setattr(ls.POOL, "take", lambda level: None)

    def down(*_args, **_kwargs):
        raise RuntimeError("Gemini generate_content failed: 503 UNAVAILABLE")

    monkeypatch.setattr(ls, "build_question", down)
    item = ls.get_question(32, session_id="chaos-listen", defer_audio=True, target_level="C1")
    assert item.level == "C1"
    assert len(item.options) == 4
    assert item.correct_answer in "ABCD"
    assert item.script
    assert item.question


def test_reading_question_survives_an_empty_pool_and_a_down_provider(monkeypatch):
    monkeypatch.setattr(rs._READING_POOL, "take", lambda level: None)

    def down(*_args, **_kwargs):
        raise RuntimeError("Gemini generate_content failed: 500")

    monkeypatch.setattr(rs, "produce_reading_question", down)
    item = rs.get_reading_question(24, session_id="chaos-read", target_level="B2")
    assert len(item.options) == 4
    assert item.correct_answer in "ABCD"
    assert "clinique" in item.text.lower()
