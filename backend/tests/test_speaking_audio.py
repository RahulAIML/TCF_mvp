"""Speaking, pronunciation, vocabulary and TTS-route behaviour with Gemini/ElevenLabs mocked out."""
import io
import itertools
import json
import time
import types as pytypes
import wave

import pytest

import audio_mime
import gemini_service
import speaking_pregen
from audio_mime import NO_SPEECH_MESSAGE, base_mime, clean_transcript, extension_for
from guest import is_guest


def _silent_wav(seconds: float = 1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


def _sse_events(body: str) -> list:
    events = []
    for line in body.splitlines():
        if line.startswith("data: ") and line != "data: [DONE]":
            events.append(json.loads(line[6:]))
    return events


class _FakeResponse:
    def __init__(self, text):
        self.text = text


# ── audio format normalisation ──────────────────────────────────────────────

@pytest.mark.parametrize("content_type,filename,expected", [
    ("audio/mp4;codecs=mp4a.40.2", None, "audio/mp4"),
    ("AUDIO/WEBM;codecs=opus", None, "audio/webm"),
    ("audio/x-wav", None, "audio/wav"),
    ("audio/x-m4a", None, "audio/mp4"),
    ("application/octet-stream", "recording.m4a", "audio/mp4"),
    ("", "voice.ogg", "audio/ogg"),
    (None, None, "audio/webm"),
])
def test_base_mime(content_type, filename, expected):
    assert base_mime(content_type, filename) == expected


def test_extension_follows_mime():
    assert extension_for("audio/mp4;codecs=mp4a.40.2") == ".mp4"
    assert extension_for("audio/ogg;codecs=opus") == ".ogg"


@pytest.mark.parametrize("raw", ["<NO_SPEECH>", " <no_speech> ", "NO_SPEECH", "[NO SPEECH]", "", "   ", '"<NO_SPEECH>"'])
def test_no_speech_marker_becomes_empty_transcript(raw):
    assert clean_transcript(raw) == ""


def test_real_speech_is_kept():
    assert clean_transcript(" Je voudrais un café. ") == "Je voudrais un café."


def test_guest_detection():
    assert is_guest(None)
    assert is_guest(pytypes.SimpleNamespace(email="demo@tcf.local"))
    assert not is_guest(pytypes.SimpleNamespace(email="someone@example.com"))


# ── transcription: silence never produces invented text ─────────────────────

def test_transcribe_silence_returns_no_speech(client, monkeypatch):
    seen = {}

    def fake_generate(contents, **kwargs):
        seen["mime"] = contents[1].inline_data.mime_type
        return _FakeResponse("<NO_SPEECH>")

    monkeypatch.setattr(gemini_service, "_gemini_generate", fake_generate)
    # Exercise the model's no-speech path (the voice-activity gate has its own tests).
    monkeypatch.setattr(gemini_service, "has_speech", lambda data, mime: True)
    r = client.post(
        "/tcf/transcribe-audio",
        files={"audio": ("recording.mp4", _silent_wav(), "audio/mp4;codecs=mp4a.40.2")},
        data={"language": "fr-FR"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transcript"] == "" and body["no_speech"] is True
    assert body["message"] == NO_SPEECH_MESSAGE
    assert seen["mime"] == "audio/mp4", "codec parameters must be stripped before calling Gemini"


def test_transcribe_returns_speech(client, monkeypatch):
    monkeypatch.setattr(gemini_service, "_gemini_generate", lambda contents, **k: _FakeResponse("Bonjour, je m'appelle Ana."))
    r = client.post("/tcf/transcribe-audio", files={"audio": ("r.webm", b"\x1a\x45\xdf\xa3" * 50, "audio/webm;codecs=opus")})
    assert r.status_code == 200
    assert r.json() == {"transcript": "Bonjour, je m'appelle Ana.", "no_speech": False}


def test_transcribe_empty_upload_is_400(client):
    r = client.post("/tcf/transcribe-audio", files={"audio": ("r.webm", b"", "audio/webm")})
    assert r.status_code == 400


def test_transcribe_provider_failure_is_friendly_503(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("Gemini generate_content failed: 500 INTERNAL secret detail")

    monkeypatch.setattr(gemini_service, "_gemini_generate", boom)
    r = client.post("/tcf/transcribe-audio", files={"audio": ("r.webm", b"abc", "audio/webm")})
    assert r.status_code == 503
    assert "Gemini" not in r.json()["detail"] and "secret" not in r.json()["detail"]


# ── pronunciation ───────────────────────────────────────────────────────────

def test_pronunciation_silence_is_not_scored(client, monkeypatch):
    calls = []

    def fake_generate(contents, **kwargs):
        calls.append(kwargs)
        return _FakeResponse("<NO_SPEECH>")

    monkeypatch.setattr(gemini_service, "_gemini_generate", fake_generate)
    # Exercise the model's no-speech path (the voice-activity gate has its own tests).
    monkeypatch.setattr(gemini_service, "has_speech", lambda data, mime: True)
    r = client.post(
        "/api/pronunciation/evaluate",
        data={"target_text": "Bonjour", "language": "fr"},
        files={"audio_file": ("r.wav", _silent_wav(), "audio/wav")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["no_speech"] is True and body["accuracy"] == 0 and body["user_text"] == ""
    assert body["feedback"] == NO_SPEECH_MESSAGE
    assert len(calls) == 1, "no scoring call may be made when nothing was said"


def test_pronunciation_scores_are_clamped(client, monkeypatch):
    responses = iter([
        _FakeResponse("Bonjour madame"),
        _FakeResponse(json.dumps({"accuracy": 14, "clarity": -2, "mistakes": "madame", "feedback": "ok", "improved_version": "Bonjour"})),
    ])
    monkeypatch.setattr(gemini_service, "_gemini_generate", lambda contents, **k: next(responses))
    r = client.post(
        "/api/pronunciation/evaluate",
        data={"target_text": "Bonjour", "language": "fr"},
        files={"audio_file": ("r.webm", b"abc", "audio/webm")},
    )
    body = r.json()
    assert body["accuracy"] == 10 and body["clarity"] == 0 and body["mistakes"] == ["madame"]
    assert body["no_speech"] is False


def test_pronunciation_stream_sends_transcript_tokens_and_scores(client, monkeypatch):
    def fake_generate(contents, stream=False, **kwargs):
        if stream:
            return iter([_FakeResponse("Très "), _FakeResponse("bien.")])
        if isinstance(contents, list):
            return _FakeResponse("Bonjour")
        return _FakeResponse(json.dumps({"accuracy": 9, "clarity": 8, "mistakes": [], "improved_version": "Bonjour"}))

    monkeypatch.setattr(gemini_service, "_gemini_generate", fake_generate)
    r = client.post(
        "/api/pronunciation/evaluate/stream",
        data={"target_text": "Bonjour", "language": "fr"},
        files={"audio_file": ("r.webm", b"abc", "audio/webm")},
    )
    assert r.status_code == 200
    events = _sse_events(r.text)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "transcript" and events[0]["user_text"] == "Bonjour"
    assert "".join(e["token"] for e in events if e["type"] == "token") == "Très bien."
    scores = next(e for e in events if e["type"] == "scores")
    assert scores["accuracy"] == 9 and scores["clarity"] == 8
    assert kinds[-1] == "done"


def test_pronunciation_stream_silence(client, monkeypatch):
    monkeypatch.setattr(gemini_service, "_gemini_generate", lambda contents, **k: _FakeResponse("<NO_SPEECH>"))
    r = client.post(
        "/api/pronunciation/evaluate/stream",
        data={"target_text": "Bonjour"},
        files={"audio_file": ("r.wav", _silent_wav(), "audio/wav")},
    )
    events = _sse_events(r.text)
    assert [e["type"] for e in events] == ["no_speech"]
    assert events[0]["user_text"] == ""


def test_guide_rejects_overlong_text(client):
    assert client.get("/api/pronunciation/guide/" + "a" * 300).status_code == 400


# ── vocabulary ──────────────────────────────────────────────────────────────

def _word_factory():
    counter = itertools.count()

    def fake_generate_vocabulary(level="A2", count=5, topic=None, language="fr", exclude=None):
        excluded = {w.lower() for w in (exclude or [])}
        out = []
        while len(out) < count:
            w = f"mot{next(counter)}"
            if w not in excluded:
                out.append({"word": w, "meaning": "m", "example": "e", "example_translation": None, "phonetic": None})
        return out

    return fake_generate_vocabulary


@pytest.fixture()
def fake_vocab(monkeypatch):
    fake = _word_factory()
    monkeypatch.setattr(speaking_pregen.gemini_service, "generate_vocabulary", fake)
    monkeypatch.setattr(speaking_pregen.vocab_pool, "_producer", lambda key: fake(level=key[1], count=15, language=key[0]))
    monkeypatch.setattr("routers.pronunciation_routes._warm_guides", lambda words, language: None)
    return fake


@pytest.mark.parametrize("requested,expected", [(99, 20), (0, 1), (-3, 1), (7, 7)])
def test_vocabulary_count_is_clamped(client, fake_vocab, requested, expected):
    r = client.post("/api/pronunciation/vocabulary/generate", json={"level": "B1", "count": requested, "session_id": f"clamp-{requested}"})
    assert r.status_code == 200, r.text
    assert r.json()["count"] == expected == len(r.json()["words"])


def test_vocabulary_never_repeats_within_a_session(client, fake_vocab):
    seen = []
    for _ in range(4):
        r = client.post("/api/pronunciation/vocabulary/generate", json={"level": "A2", "count": 8, "session_id": "s-unique"})
        assert r.status_code == 200
        seen += [w["word"] for w in r.json()["words"]]
    assert len(seen) == 32 and len(set(seen)) == 32


def test_vocabulary_pool_serves_each_set_once(fake_vocab):
    key = ("fr", "C1", "")
    speaking_pregen.vocab_pool.fill(key)
    deadline = time.time() + 5
    while time.time() < deadline and speaking_pregen.vocab_pool.stats().get(str(key), {}).get("ready", 0) < 3:
        time.sleep(0.02)
    first = speaking_pregen.take_vocabulary("C1", 5, None, "fr", "pool-a")
    second = speaking_pregen.take_vocabulary("C1", 5, None, "fr", "pool-b")
    assert not {w["word"] for w in first} & {w["word"] for w in second}


def test_guest_vocabulary_is_not_stored(client, fake_vocab):
    from database import SessionLocal
    from guest import DEMO_EMAIL
    from models import User, VocabularyWord
    r = client.post("/api/pronunciation/vocabulary/generate", json={"level": "A1", "count": 3, "session_id": "guest-store"})
    assert r.status_code == 200
    db = SessionLocal()
    try:
        demo = db.query(User).filter(User.email == DEMO_EMAIL).first()
        assert demo is not None
        assert db.query(VocabularyWord).filter(VocabularyWord.user_id == demo.id).count() == 0
    finally:
        db.close()


def test_vocabulary_progress_unknown_word_is_404_not_500(client, signup):
    headers = signup(client, "vocab404@example.com")
    r = client.put("/api/pronunciation/vocabulary/progress", json={"word": "inexistant", "accuracy_score": 5}, headers=headers)
    assert r.status_code == 404
    r = client.get("/api/pronunciation/vocabulary/word/inexistant", headers=headers)
    assert r.status_code == 404


def test_signed_in_vocabulary_is_stored_and_progress_updates(client, signup, fake_vocab):
    headers = signup(client, "vocabstore@example.com")
    r = client.post("/api/pronunciation/vocabulary/generate", json={"level": "B2", "count": 2, "session_id": "signed"}, headers=headers)
    word = r.json()["words"][0]["word"]
    r = client.put("/api/pronunciation/vocabulary/progress", json={"word": word, "accuracy_score": 9, "is_learned": True}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["is_learned"] is True and r.json()["correct_count"] == 1


# ── speaking openings, conversation and evaluation ─────────────────────────

def test_opening_pool_rejects_duplicate_topics_and_serves_once(monkeypatch):
    topics = iter(["Sujet A", "Sujet A", "Sujet B", "Sujet C", "Sujet D", "Sujet E", "Sujet F", "Sujet G"])
    monkeypatch.setattr(
        speaking_pregen, "generate_tcf_speaking_opening",
        lambda task, avoid: {"reply": "Bonjour.", "audio_url": "/audio/x.mp3", "session_topic": next(topics), "examiner_name": "Marie Dupont"},
    )
    served = [speaking_pregen._produce_opening("opinion")["session_topic"] for _ in range(3)]
    assert served == ["Sujet A", "Sujet B", "Sujet C"]


def test_conversation_start_uses_pooled_opening(client, monkeypatch):
    monkeypatch.setattr(
        speaking_pregen.opening_pool, "take",
        lambda key: {"reply": "Bonjour, je m'appelle Marie Dupont.", "audio_url": "/audio/o.mp3", "session_topic": "Votre ville", "examiner_name": "Marie Dupont"},
    )
    r = client.post("/tcf/speaking/opening", json={"task_type": "basic_interaction"})
    assert r.status_code == 200, r.text
    assert r.json()["examiner_name"] == "Marie Dupont" and r.json()["audio_url"] == "/audio/o.mp3"


def test_conversation_stream_sends_text_then_audio(client, monkeypatch):
    def fake_stream(**kwargs):
        assert kwargs["examiner_name"] == "Thomas Rousseau"
        yield "meta", {"session_topic": "Loisirs", "examiner_name": "Thomas Rousseau"}
        yield "token", "Que faites-vous "
        yield "token", "le week-end ?"
        yield "reply", "Que faites-vous le week-end ?"

    monkeypatch.setattr("routers.tcf_speaking_routes.stream_tcf_speaking_reply", fake_stream)
    monkeypatch.setattr("routers.tcf_speaking_routes.speaking_reply_audio", lambda text, sid: "/audio/r.mp3")
    r = client.post("/tcf/conversation/stream", json={
        "message": "J'aime lire.", "history": [{"role": "assistant", "content": "Bonjour"}],
        "task_type": "basic_interaction", "session_topic": "Loisirs", "examiner_name": "Thomas Rousseau",
    })
    events = _sse_events(r.text)
    assert [e["type"] for e in events] == ["meta", "token", "token", "reply", "audio"]
    assert events[3]["reply"] == "Que faites-vous le week-end ?" and events[4]["audio_url"] == "/audio/r.mp3"


def test_conversation_stream_error_is_friendly(client, monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("Gemini exploded")
        yield  # pragma: no cover

    monkeypatch.setattr("routers.tcf_speaking_routes.stream_tcf_speaking_reply", broken)
    r = client.post("/tcf/conversation/stream", json={
        "message": "Oui", "history": [{"role": "assistant", "content": "Bonjour"}], "task_type": "opinion", "session_topic": "x",
    })
    events = _sse_events(r.text)
    assert events[-1]["type"] == "error" and "Gemini" not in events[-1]["message"]


def test_evaluation_stream_short_answer_gets_fixed_low_score(client):
    r = client.post("/tcf/evaluate/stream", json={
        "history": [{"role": "assistant", "content": "Parlez-moi de vous."}, {"role": "user", "content": "Oui."}],
        "task_type": "basic_interaction",
    })
    events = _sse_events(r.text)
    assert events[0]["type"] == "scores" and events[0]["fluency"] == 1 and events[-1]["type"] == "done"


def test_evaluation_stream_scores_and_model_answer(client, monkeypatch):
    monkeypatch.setattr(
        "routers.tcf_speaking_routes.speaking_scores_without_model_answer",
        lambda history, task: {"fluency": 6, "grammar": 5, "vocabulary": 6, "interaction": 7, "feedback": ["a"], "improved_response": "", "cefr_level": "B1"},
    )
    monkeypatch.setattr("routers.tcf_speaking_routes.stream_speaking_model_answer", lambda history, task: iter(["Je ", "pense que..."]))
    history = [
        {"role": "assistant", "content": "Que pensez-vous du télétravail ?"},
        {"role": "user", "content": "Je pense que le télétravail permet de gagner du temps et améliore la concentration au quotidien."},
    ]
    r = client.post("/tcf/evaluate/stream", json={"history": history, "task_type": "opinion"})
    events = _sse_events(r.text)
    scores = next(e for e in events if e["type"] == "scores")
    assert scores["cefr_level"] == "B1" and "improved_response" not in scores
    assert "".join(e["token"] for e in events if e["type"] == "token") == "Je pense que..."
    assert events[-1]["type"] == "done"


def test_enhanced_speaking_router_is_gone(client):
    assert client.post("/tcf/speaking/enhanced/session/init", json={"task_type": "opinion"}).status_code == 404


# ── TTS route validation ────────────────────────────────────────────────────

def test_tts_unknown_voice_is_400(client):
    r = client.post("/api/tts/generate", json={"text": "Bonjour", "voice_id": "xx-XX-robot-9"})
    assert r.status_code == 400
