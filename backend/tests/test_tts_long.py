import re
import time
import uuid

import pytest

import audio_store
import tts_jobs
import tts_service as ts


def _frame(i: int) -> bytes:
    """One valid MPEG-1 Layer III frame (417 bytes) so the joiner sees real frames."""
    return b"\xff\xfb\x90\x00" + bytes([i % 250 + 1]) * 413


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ── Splitting ────────────────────────────────────────────────────────────────

def test_short_text_is_one_piece():
    assert ts.split_for_speech("Bonjour tout le monde.") == ["Bonjour tout le monde."]
    assert ts.split_for_speech("   ") == []


def test_forty_thousand_characters_split_into_bounded_pieces_without_losing_text():
    sentence = "Chaque matin, nous marchons ensemble jusqu'à l'école du village voisin. "
    text = (sentence * 700)[:40000]
    pieces = ts.split_for_speech(text)
    assert all(0 < len(p) <= ts.TTS_CHUNK_CHARS for p in pieces)
    assert 40000 / ts.TTS_CHUNK_CHARS <= len(pieces) <= 40000 / ts.TTS_CHUNK_CHARS * 1.25
    assert _norm(" ".join(pieces)) == _norm(text)


def test_pieces_end_at_sentence_boundaries_when_possible():
    text = " ".join(f"Phrase numéro {i} qui parle du quartier et de ses habitants." for i in range(120))
    pieces = ts.split_for_speech(text, 500)
    assert all(p.endswith(".") for p in pieces)


def test_a_sentence_without_punctuation_is_still_cut_at_spaces():
    text = " ".join(["mot"] * 2000)
    pieces = ts.split_for_speech(text, 300)
    assert all(len(p) <= 300 for p in pieces)
    assert _norm(" ".join(pieces)) == _norm(text)


def test_paragraph_breaks_do_not_lose_text():
    text = ("Premier paragraphe. " * 60) + "\n\n" + ("Second paragraphe. " * 60)
    pieces = ts.split_for_speech(text, 400)
    assert _norm(" ".join(pieces)) == _norm(text)


def test_page_limit_is_forty_thousand_and_the_single_request_limit_is_unchanged():
    assert ts.MAX_LONG_TEXT_LENGTH == 40000
    assert ts.MAX_TEXT_LENGTH == 10000


# ── Long synthesis ───────────────────────────────────────────────────────────

@pytest.fixture()
def fast(monkeypatch):
    monkeypatch.setattr(ts.time, "sleep", lambda _s: None)


def _long_text(pieces=5):
    return " ".join(f"Voici la phrase {i}, assez longue pour remplir un morceau. " * 30 for i in range(pieces))


def test_long_text_is_voiced_piece_by_piece_and_joined(monkeypatch, fast):
    calls = []

    def fake(text, voice, polish=True):
        calls.append(len(text))
        return {"data": _frame(len(calls)), "extension": "mp3", "mime_type": "audio/mpeg", "provider": "gemini"}

    monkeypatch.setattr(ts, "_generate_via_gemini", fake)
    progress = []
    result = ts.synthesize_long(_long_text(), "fr-FR-male-1", lambda d, t: progress.append((d, t)))
    assert len(calls) > 1 and all(n <= ts.TTS_CHUNK_CHARS for n in calls)
    assert len(result["data"]) == len(calls) * 417
    assert progress[-1] == (len(calls), len(calls))
    assert [d for d, _ in progress] == sorted(d for d, _ in progress)


def test_a_failing_piece_is_retried_once_before_giving_up_on_a_provider(monkeypatch, fast):
    attempts = {"n": 0}

    def flaky(text, voice, polish=True):
        attempts["n"] += 1
        if attempts["n"] == 2:
            raise RuntimeError("provider blip")
        return {"data": _frame(attempts["n"]), "extension": "mp3", "mime_type": "audio/mpeg", "provider": "gemini"}

    monkeypatch.setattr(ts, "_generate_via_gemini", flaky)
    result = ts.synthesize_long(_long_text(3), "fr-FR-male-1")
    assert result["provider"] == "gemini" and len(result["data"]) >= 3 * 417


def test_recording_restarts_whole_on_the_other_provider_never_mixing(monkeypatch, fast):
    monkeypatch.setattr(ts, "_ELEVENLABS_API_KEY", "key")
    used = []

    def broken_gemini(text, voice, polish=True):
        used.append("gemini")
        if len([u for u in used if u == "gemini"]) >= 3:
            raise RuntimeError("gemini down")
        return {"data": _frame(1), "extension": "mp3", "mime_type": "audio/mpeg", "provider": "gemini"}

    def eleven(text, voice, polish=True):
        used.append("elevenlabs")
        return {"data": _frame(9), "extension": "mp3", "mime_type": "audio/mpeg", "provider": "elevenlabs"}

    monkeypatch.setattr(ts, "_generate_via_gemini", broken_gemini)
    monkeypatch.setattr(ts, "_generate_via_elevenlabs", eleven)
    pieces = len(ts.split_for_speech(_long_text(6)))
    result = ts.synthesize_long(_long_text(6), "fr-FR-male-1")
    assert result["provider"] == "elevenlabs"
    assert used.count("elevenlabs") == pieces, "every piece of the final recording came from one provider"
    assert len(result["data"]) == pieces * 417


def test_error_when_every_provider_fails(monkeypatch, fast):
    def down(text, voice, polish=True):
        raise RuntimeError("down")

    monkeypatch.setattr(ts, "_generate_via_gemini", down)
    with pytest.raises(RuntimeError, match="Audio generation failed"):
        ts.synthesize_long(_long_text(2), "fr-FR-male-1")


def test_text_over_the_limit_is_rejected():
    with pytest.raises(ValueError):
        ts.synthesize_long("a" * 40001, "fr-FR-male-1")


# ── Jobs survive a restart ───────────────────────────────────────────────────

def test_finished_job_is_readable_after_a_restart(app):
    job_id = uuid.uuid4().hex
    tts_jobs.create(job_id, 3, 4500)
    tts_jobs.update(job_id, status="done", audio_url="/audio/x.mp3", done_parts=3)
    tts_jobs._live.clear()  # a restart forgets memory
    job = tts_jobs.get(job_id)
    assert job["status"] == "done" and job["audio_url"] == "/audio/x.mp3" and job["done_parts"] == 3


def test_running_job_is_reported_interrupted_after_a_restart(app):
    job_id = uuid.uuid4().hex
    tts_jobs.create(job_id, 5, 9000)
    tts_jobs.update(job_id, done_parts=2)
    assert tts_jobs.get(job_id)["status"] == "pending"
    tts_jobs._live.clear()
    job = tts_jobs.get(job_id)
    assert job["status"] == "error" and job["error"] == tts_jobs.INTERRUPTED
    assert tts_jobs.get(job_id)["status"] == "error", "the verdict is stored"


def test_unknown_job_is_none(app):
    assert tts_jobs.get("does-not-exist") is None


def test_long_lane_refuses_when_the_line_is_full(monkeypatch):
    monkeypatch.setattr(tts_jobs, "_long_waiting", tts_jobs._MAX_LONG_WAITING)
    with pytest.raises(tts_jobs.LongBusy):
        tts_jobs.submit_long(lambda: None)


# ── API ──────────────────────────────────────────────────────────────────────

def _wait(client, job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        body = client.get(f"/api/tts/job/{job_id}").json()
        if body["status"] != "pending":
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_short_text_job_completes(client, monkeypatch):
    monkeypatch.setattr("routers.tts_routes.generate_tts_audio", lambda text, voice, progress=None: "/audio/short.mp3")
    r = client.post("/api/tts/generate", json={"text": "Bonjour.", "voice_id": "fr-FR-male-1"})
    assert r.status_code == 200 and r.json()["total_parts"] == 1
    assert _wait(client, r.json()["job_id"])["audio_url"] == "/audio/short.mp3"


def test_long_text_reports_progress_and_finishes(client, monkeypatch):
    def fake(text, voice, progress=None):
        parts = len(ts.split_for_speech(text))
        for i in range(parts):
            progress(i, parts)
        progress(parts, parts)
        return "/audio/long.mp3"

    monkeypatch.setattr("routers.tts_routes.generate_tts_audio", fake)
    text = _long_text(8)
    r = client.post("/api/tts/generate", json={"text": text, "voice_id": "fr-FR-male-1"})
    assert r.status_code == 200 and r.json()["total_parts"] > 1
    done = _wait(client, r.json()["job_id"])
    assert done["status"] == "done" and done["done_parts"] == done["total_parts"]


def test_failed_job_reports_a_friendly_error(client, monkeypatch):
    def boom(text, voice, progress=None):
        raise RuntimeError("Gemini: secret internal detail")

    monkeypatch.setattr("routers.tts_routes.generate_tts_audio", boom)
    r = client.post("/api/tts/generate", json={"text": "Bonjour.", "voice_id": "fr-FR-male-1"})
    body = _wait(client, r.json()["job_id"])
    assert body["status"] == "error" and "secret" not in (body["error"] or "")


def test_forty_thousand_characters_are_accepted_and_more_are_not(client, monkeypatch):
    monkeypatch.setattr("routers.tts_routes.generate_tts_audio", lambda text, voice, progress=None: "/audio/big.mp3")
    ok = client.post("/api/tts/generate", json={"text": "a" * 40000, "voice_id": "fr-FR-male-1"})
    assert ok.status_code == 200
    too_long = client.post("/api/tts/generate", json={"text": "a" * 40001, "voice_id": "fr-FR-male-1"})
    assert too_long.status_code == 422


def test_blank_text_and_unknown_voice_are_rejected(client):
    assert client.post("/api/tts/generate", json={"text": "   ", "voice_id": "fr-FR-male-1"}).status_code == 400
    assert client.post("/api/tts/generate", json={"text": "Bonjour", "voice_id": "nope"}).status_code == 400


def test_unknown_job_is_404(client):
    assert client.get("/api/tts/job/unknown-job").status_code == 404


# ── Audio route ──────────────────────────────────────────────────────────────

def test_audio_head_get_and_download(client):
    name = f"tts_fr-FR-male-1_{uuid.uuid4().hex[:8]}.mp3"
    audio_store.save(name, _frame(3) * 4, "audio/mpeg")
    head = client.head(f"/audio/{name}")
    assert head.status_code == 200 and head.headers["content-type"] == "audio/mpeg"
    get = client.get(f"/audio/{name}")
    assert get.status_code == 200 and len(get.content) == 417 * 4
    assert "content-disposition" not in get.headers
    dl = client.get(f"/audio/{name}?download=1")
    assert dl.headers["content-disposition"] == f'attachment; filename="{name}"'


def test_missing_audio_is_404_for_head_and_get(client):
    assert client.head("/audio/tts_fr-FR-male-1_00000000.mp3").status_code == 404
    assert client.get("/audio/tts_fr-FR-male-1_00000000.mp3").status_code == 404


def test_single_request_synthesis_hands_long_text_to_the_chunked_path(monkeypatch, fast):
    seen = []

    def piece(text, voice, polish=True):
        seen.append(len(text))
        return {"data": _frame(len(seen)), "extension": "mp3", "mime_type": "audio/mpeg", "provider": "gemini"}

    monkeypatch.setattr(ts, "_generate_via_gemini", piece)
    result = ts.synthesize(_long_text(4), "fr-FR-male-1")
    assert len(seen) > 1 and max(seen) <= ts.TTS_CHUNK_CHARS and result["extension"] == "mp3"
