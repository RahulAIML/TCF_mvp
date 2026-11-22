"""Listening generation: calibration bands, answer/explanation agreement, dialogue parsing, uniqueness, pool, audio."""
import itertools
import os
import random
from collections import Counter

import pytest

import listening_service as ls
import tcf_ai_service


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def fresh_history(monkeypatch):
    monkeypatch.setattr(ls, "HISTORY", ls._History())


_counter = itertools.count()


def _words(n, seed):
    vocab = ["maison", "travail", "train", "matin", "ville", "parc", "billet", "école", "marché", "voisin",
             "musique", "projet", "réunion", "bureau", "voyage", "repas", "quartier", "centre", "piscine", "jardin"]
    rng = random.Random(seed)
    return " ".join(rng.choice(vocab) + str(rng.randint(0, 9999)) for _ in range(n))


def _monologue_payload(level="B1", correct="C", explanation="Le locuteur dit qu'il part à huit heures.", theme=None):
    lo, hi = ls.LISTENING_SPECS[level]["words"]
    n = next(_counter)
    return {
        "theme": theme or f"thème {n}",
        "script": _words((lo + hi) // 2, n),
        "question": f"Que dit le locuteur ? {n}",
        "options": [f"Option un {n}", f"Option deux {n}", f"Option trois {n}", f"Option quatre {n}"],
        "correct_answer": correct,
        "explanation": explanation,
    }


def _dialogue_payload(names, level="B1", correct="A"):
    lo, hi = ls.LISTENING_SPECS[level]["words"]
    n = next(_counter)
    per_line = max(3, (lo + hi) // 2 // 4)
    a, b = names
    script = "\n".join([
        f"{a} : {_words(per_line, n)}",
        f"{b} : {_words(per_line, n + 1)}",
        f"{a} : {_words(per_line, n + 2)}",
        f"{b} : {_words(per_line, n + 3)}",
    ])
    return {
        "theme": f"dialogue {n}",
        "script": script,
        "question": f"Que décide {b} ? {n}",
        "options": [f"Choix {i} {n}" for i in range(4)],
        "correct_answer": correct,
        "explanation": f"{b} explique qu'elle préfère attendre.",
    }


# ── Calibration bands ────────────────────────────────────────────────────────

@pytest.mark.parametrize("number,level", [
    (1, "A1"), (4, "A1"), (5, "A2"), (10, "A2"), (11, "B1"), (19, "B1"),
    (20, "B2"), (29, "B2"), (30, "C1"), (35, "C1"), (36, "C2"), (39, "C2"),
])
def test_six_band_mapping_is_ascending(number, level):
    assert ls.level_for_question(number) == level
    assert tcf_ai_service._infer_cefr_from_question_number(number) == level


def test_every_level_has_specs_formats_and_dialogues():
    for level in ls.LEVELS:
        assert level in ls.LISTENING_SPECS and level in ls.LISTENING_FORMATS
        assert any(is_dialogue for _f, is_dialogue in ls.LISTENING_FORMATS[level])


# ── Speaker parsing ──────────────────────────────────────────────────────────

def test_detects_accented_and_hyphenated_names():
    script = "Marie-Ève : Tu viens ce soir ?\nÉric : Oui, vers huit heures.\nMarie-Ève : Parfait."
    assert ls.detect_speakers(script) == ["Marie-Ève", "Éric"]
    assert ls.detect_speakers(script, ["Marie-Ève", "Éric"]) == ["Marie-Ève", "Éric"]


def test_dash_prefix_and_role_in_parentheses():
    script = "— Jean-François (journaliste) : Bonjour.\n— Geneviève : Bonjour à vous."
    assert ls.detect_speakers(script) == ["Jean-François", "Geneviève"]


def test_colons_in_a_monologue_are_not_speakers():
    script = (
        "Attention : la piscine municipale ferme plus tôt aujourd'hui.\n"
        "Horaires : de 9 h à 17 h.\n"
        "Information importante : le vestiaire est fermé.\n"
        "Il est 8 heures : les cours commencent."
    )
    assert ls.detect_speakers(script) == []


def test_single_label_is_not_a_dialogue():
    assert ls.detect_speakers("Animateur : Bonjour à tous et bienvenue.") == []


def test_mostly_unlabelled_text_is_not_a_dialogue():
    script = "Paul : bonjour\nMarie : salut\n" + "\n".join(f"Ligne de texte {i}." for i in range(8))
    assert ls.detect_speakers(script) == []
    assert ls.detect_speakers(script, ["Paul", "Marie"]) == ["Paul", "Marie"]


def test_segments_keep_leading_narration_and_continuation_lines():
    script = "Dans un café de Montréal.\nLuc : Un café, s'il te plaît.\nsuite de la phrase\nEmma : Tout de suite."
    segs = ls.dialogue_segments(script, ["Luc", "Emma"])
    assert segs[0] == (None, "Dans un café de Montréal.")
    assert segs[1] == ("Luc", "Un café, s'il te plaît. suite de la phrase")
    assert segs[2] == ("Emma", "Tout de suite.")


def test_two_speakers_on_one_line_are_both_heard():
    script = "François : Allô, c'est toi ? Paul : Oui, j'arrive dans dix minutes."
    assert ls.detect_speakers(script) == ["François", "Paul"]
    segments = ls.dialogue_segments(script, ["François", "Paul"])
    assert [name for name, _text in segments] == ["François", "Paul"]
    spoken = " ".join(text for _name, text in segments)
    assert "François :" not in spoken and "Paul :" not in spoken
    assert "Allô" in spoken and "j'arrive" in spoken


def test_two_male_names_get_two_different_male_voices():
    import tts_service
    for names in (["François", "Paul"], ["Antoine", "Simon"]):
        voices = ls.assign_voices(names)
        assert voices[names[0]].startswith("fr-FR-male")
        assert voices[names[1]].startswith("fr-FR-male")
        assert voices[names[0]] != voices[names[1]]
        first = tts_service.get_voice(voices[names[0]])
        second = tts_service.get_voice(voices[names[1]])
        assert first["gemini_voice_name"] != second["gemini_voice_name"]
        assert first["elevenlabs_voice_id"] != second["elevenlabs_voice_id"]
        assert {first["gemini_voice_name"], second["gemini_voice_name"]} == {"Charon", "Puck"}


def test_dialogue_audio_has_one_segment_per_speaker(monkeypatch, tmp_path):
    calls = []

    def fake(text, voice, polish=True):
        calls.append((text, voice))
        # A real MP3 so the turn mixer can decode it. Pitch differs per voice.
        rate = 660 if voice.endswith("2") else 440
        return {"data": _tone(rate), "extension": "mp3", "mime_type": "audio/mpeg", "provider": "test"}

    monkeypatch.setattr(ls.tts_service, "synthesize_elevenlabs", fake)
    monkeypatch.setattr(ls, "_audio_dir", lambda: str(tmp_path))
    url = ls.synthesize_listening_audio("François : Bonjour tout le monde. Paul : Bonsoir à vous deux.")
    assert len(calls) == 2
    assert calls[0][1] != calls[1][1]
    assert all(call[1].startswith("fr-FR-male") for call in calls)
    assert all(":" not in call[0] for call in calls)
    import audio_store
    loaded = audio_store.load(url)
    assert loaded is not None
    decoded = _decode_mp3(loaded[0])
    # Two tones plus the pause between them: longer than either turn alone.
    assert len(decoded) > 24000 * 0.5


def test_a_missing_audio_file_is_served_from_the_database(client):
    import audio_store
    url = audio_store.save("tcf_listening_persist.mp3", b"ID3" + b"\x11" * 80, "audio/mpeg")
    os.remove(audio_store._path("tcf_listening_persist.mp3"))
    response = client.get(url)
    assert response.status_code == 200
    assert response.content.startswith(b"ID3")
    assert client.get("/audio/does-not-exist.mp3").status_code == 404


def test_a_dead_audio_url_is_never_returned(monkeypatch):
    import audio_store
    item = ls.ListeningQuestionResponse(
        question_id="dead", level="B1", script="François : Bonjour. Paul : Salut.",
        audio_url="/audio/tcf_listening_gone.mp3", question="Qui parle ?",
        options=["A. a", "B. b", "C. c", "D. d"], correct_answer="A", explanation="ok",
        speakers=["François", "Paul"],
    )
    fresh = audio_store.save("tcf_listening_replaced.mp3", b"ID3fresh", "audio/mpeg")
    monkeypatch.setattr(ls, "synthesize_listening_audio", lambda script, speakers=None: fresh)
    deferred = ls._deliver(item, defer_audio=True)
    assert deferred.audio_url is None
    ready = ls._deliver(item, defer_audio=False)
    assert ready.audio_url == fresh
    assert audio_store.available(ready.audio_url)


def test_a_monologue_stays_one_voice_and_drops_a_lone_label(monkeypatch, tmp_path):
    calls = []

    def fake(text, voice):
        calls.append((text, voice))
        return {"data": _tone(440), "extension": "mp3", "mime_type": "audio/mpeg", "provider": "test"}

    monkeypatch.setattr(ls.tts_service, "synthesize", fake)
    monkeypatch.setattr(ls, "_audio_dir", lambda: str(tmp_path))
    ls.synthesize_listening_audio("Animateur : Bonjour à tous et bienvenue à l'émission.")
    assert len(calls) == 1
    assert "Animateur" not in calls[0][0]
    assert "Bonjour" in calls[0][0]


def _tone(freq, seconds=0.35, rate=24000):
    import lameenc
    import math
    enc = lameenc.Encoder()
    enc.set_bit_rate(64)
    enc.set_in_sample_rate(rate)
    enc.set_channels(1)
    enc.set_quality(5)
    samples = bytearray()
    for i in range(int(rate * seconds)):
        value = int(8000 * math.sin(2 * math.pi * freq * i / rate))
        samples += int(value).to_bytes(2, "little", signed=True)
    return bytes(enc.encode(bytes(samples))) + bytes(enc.flush())


def _decode_mp3(data):
    import miniaudio
    decoded = miniaudio.decode(data, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=24000)
    return decoded.samples


def test_voices_are_distinct_and_match_gender():
    for _ in range(50):
        voices = ls.assign_voices(["Marc", "Sophie", "Nicolas"])
        assert voices["Marc"].startswith("fr-FR-male")
        assert voices["Sophie"].startswith("fr-FR-female")
        assert len({voices["Marc"], voices["Sophie"], voices["Nicolas"]}) == 3


# ── Answer / explanation agreement ───────────────────────────────────────────

def test_wrong_letter_from_model_is_moved_to_target_slot():
    payload = _monologue_payload(correct="A")
    right_text = payload["options"][0]
    item = ls._validate(payload, "B1", False, ("Marc", "Sophie"), "D")
    assert item["correct_answer"] == "D"
    assert item["options"][3] == f"D. {right_text}"
    assert sorted(o[3:] for o in item["options"]) == sorted(payload["options"])


def test_letter_references_are_removed_from_explanations():
    payload = _monologue_payload(explanation="La réponse C est juste car le locuteur part tôt ; l'option B est fausse (A).")
    item = ls._validate(payload, "B1", False, ("Marc", "Sophie"), "C")
    assert not any(f" {l} " in f" {item['explanation']} " for l in "ABCD")


def test_positional_references_are_rejected():
    payload = _monologue_payload(explanation="La première option est la bonne.")
    with pytest.raises(ls.InvalidQuestion):
        ls._validate(payload, "B1", False, ("Marc", "Sophie"), "A")


def test_option_labels_from_model_are_normalised():
    payload = _monologue_payload()
    payload["options"] = ["A) Prendre le train", "B. Rester", "c: Partir", "(D) Attendre"]
    item = ls._validate(payload, "B1", False, ("Marc", "Sophie"), "B")
    assert item["options"][0].startswith("A. ") and "A)" not in item["options"][0]
    assert all(o[3:] in ("Prendre le train", "Rester", "Partir", "Attendre") for o in item["options"])


@pytest.mark.parametrize("bad", [
    {"options": ["x", "x", "y", "z"]},
    {"options": ["x", "y", "z"]},
    {"options": ["x", "y", "z", ""]},
    {"script": ""},
])
def test_malformed_questions_are_rejected(bad):
    payload = {**_monologue_payload(), **bad}
    with pytest.raises(ls.InvalidQuestion):
        ls._validate(payload, "B1", False, ("Marc", "Sophie"), "A")


def test_c2_jargon_is_rejected():
    payload = _monologue_payload(level="C2")
    payload["script"] = payload["script"] + " une herméneutique du colloque singulier"
    with pytest.raises(ls.InvalidQuestion):
        ls._validate(payload, "C2", False, ("Marc", "Sophie"), "A")


def test_length_outside_level_band_is_rejected():
    payload = _monologue_payload(level="A1")
    payload["script"] = _words(120, 1)
    with pytest.raises(ls.InvalidQuestion):
        ls._validate(payload, "A1", False, ("Marc", "Sophie"), "A")


def test_dialogue_without_both_named_speakers_is_rejected():
    payload = _dialogue_payload(("Marc", "Sophie"))
    payload["script"] = payload["script"].replace("Sophie :", "— ")
    with pytest.raises(ls.InvalidQuestion):
        ls._validate(payload, "B1", True, ("Marc", "Sophie"), "A")


def test_valid_dialogue_keeps_speakers():
    item = ls._validate(_dialogue_payload(("Marc", "Sophie")), "B1", True, ("Marc", "Sophie"), "A")
    assert item["speakers"] == ["Marc", "Sophie"]


def test_monologue_with_lone_label_has_label_removed():
    payload = _monologue_payload()
    payload["script"] = "Animatrice : " + payload["script"]
    item = ls._validate(payload, "B1", False, ("Marc", "Sophie"), "A")
    assert not item["script"].startswith("Animatrice")


def _patch_generator(monkeypatch, make_payload):
    def fake_generate_json(prompt, temperature=0.7):
        target = prompt.split("placée en position ")[1][0]
        level = prompt.split("Niveau CECRL visé : ")[1][:2]
        if "DIALOGUE entre exactement deux personnes, " in prompt:
            names = prompt.split("DIALOGUE entre exactement deux personnes, ")[1].split(", avec")[0].split(" et ")
            return make_payload(level, target, (names[0].strip(), names[1].strip()))
        return make_payload(level, target, None)
    monkeypatch.setattr(tcf_ai_service, "_generate_json", fake_generate_json)


def test_correct_letter_distribution_is_uniform(monkeypatch):
    def make(level, target, names):
        wrong = random.choice("ABCD")  # the model ignores the requested slot
        if names:
            return _dialogue_payload(names, level, wrong)
        return _monologue_payload(level, wrong)
    _patch_generator(monkeypatch, make)
    letters = Counter(ls.build_question("B2", with_audio=False).correct_answer for _ in range(400))
    for letter in "ABCD":
        assert 0.17 < letters[letter] / 400 < 0.33, letters


def test_explanation_never_disagrees_with_answer(monkeypatch):
    def make(level, target, names):
        payload = _dialogue_payload(names, level, "B") if names else _monologue_payload(level, "B")
        payload["explanation"] = "La réponse B est correcte : " + payload["explanation"]
        return payload
    _patch_generator(monkeypatch, make)
    for _ in range(60):
        q = ls.build_question(random.choice(ls.LEVELS[2:]), with_audio=False)
        for letter in "ABCD":
            assert f"réponse {letter}" not in q.explanation


# ── Uniqueness ───────────────────────────────────────────────────────────────

def test_identical_question_is_never_produced_twice(monkeypatch):
    fixed = _monologue_payload("B1")
    _patch_generator(monkeypatch, lambda level, target, names: dict(fixed, correct_answer=target))
    monkeypatch.setattr(ls, "LISTENING_FORMATS", {**ls.LISTENING_FORMATS, "B1": [("un message", False)]})
    ls.build_question("B1", with_audio=False)
    with pytest.raises(RuntimeError):
        ls.build_question("B1", with_audio=False)


def test_near_duplicate_script_is_rejected():
    script = _words(80, 42)
    ls.HISTORY.record("fp1", script, "B1", "thème")
    altered = script.replace(script.split()[0], "différent")
    assert ls.HISTORY.is_duplicate("fp2", altered, "B1", "autre thème") == "near-duplicate script"


def test_recent_theme_is_rejected():
    ls.HISTORY.record("fp1", _words(50, 1), "B1", "Fermeture de la piscine")
    assert "theme" in ls.HISTORY.is_duplicate("fp2", _words(50, 2), "B1", "fermeture de la piscine")


def test_many_generated_questions_are_all_unique(monkeypatch):
    def make(level, target, names):
        return _dialogue_payload(names, level, target) if names else _monologue_payload(level, target)
    _patch_generator(monkeypatch, make)
    ids = [ls.build_question(lvl, with_audio=False).question_id for lvl in ls.LEVELS[2:] for _ in range(25)]
    assert len(ids) == len(set(ids))


class _FakePool:
    def __init__(self, items):
        self.items = list(items)

    def take(self, key):
        return self.items.pop(0) if self.items else None


def _question(qid):
    return tcf_ai_service.ListeningQuestionResponse(
        question_id=qid, level="B1", script=f"script {qid}", question="q", options=["A. a", "B. b", "C. c", "D. d"],
        correct_answer="A", explanation="e",
    )


def test_pool_items_are_served_once_and_never_twice_to_a_session(monkeypatch):
    repeated = _question("same")
    monkeypatch.setattr(ls, "POOL", _FakePool([repeated, repeated, _question("other")]))
    first = ls.get_question(15, session_id="s1", target_level="B1")
    second = ls.get_question(15, session_id="s1", target_level="B1")
    assert first.question_id == "same" and second.question_id == "other"


def test_empty_pool_falls_back_to_generation(monkeypatch):
    monkeypatch.setattr(ls, "POOL", _FakePool([]))
    _patch_generator(monkeypatch, lambda level, target, names: _dialogue_payload(names, level, target) if names else _monologue_payload(level, target))
    q = ls.get_question(36, session_id="s2")
    assert q.level == "C2" and q.audio_url is None


# ── Audio ────────────────────────────────────────────────────────────────────

def _mp3(seconds=0.3):
    import lameenc
    enc = lameenc.Encoder()
    enc.set_bit_rate(32)
    enc.set_in_sample_rate(22050)
    enc.set_channels(1)
    enc.set_quality(7)
    pcm = b"\x00\x00" * int(22050 * seconds)
    return bytes(enc.encode(pcm)) + bytes(enc.flush())


def _count_frames(data):
    i = frames = 0
    while i < len(data) - 4:
        n = ls._frame_length(data[i:i + 4])
        if not n:
            return None
        frames += 1
        i += n
    return frames


def test_joined_mp3_is_one_clean_frame_stream():
    pytest.importorskip("lameenc")
    info_frame = bytearray(_mp3(0.1)[:104])
    info_frame[36:40] = b"Info"
    id3 = b"ID3\x03\x00\x00\x00\x00\x00\x05" + b"\x00" * 5
    seg1 = id3 + bytes(info_frame) + _mp3(0.3)
    seg2 = _mp3(0.3) + b"TAG" + b"\x00" * 125
    joined = ls.join_mp3([seg1, seg2])
    assert joined[:2] == b"\xff\xf3" or joined[0] == 0xFF
    assert b"Info" not in joined and b"ID3" not in joined and b"TAG" not in joined
    assert _count_frames(joined) is not None


def test_dialogue_audio_uses_one_voice_per_speaker(monkeypatch):
    calls = []

    def fake_el(text, voice):
        calls.append(("el", voice))
        return {"data": _mp3(0.1), "extension": "mp3", "mime_type": "audio/mpeg", "provider": "elevenlabs"}

    monkeypatch.setattr(ls.tts_service, "synthesize_elevenlabs", fake_el)
    url = ls.synthesize_listening_audio("Marc : Bonjour.\nSophie : Salut.\nMarc : Ça va ?", ["Marc", "Sophie"])
    assert url.startswith("/audio/") and url.endswith(".mp3")
    assert [c[1].split("-")[2] for c in calls] == ["male", "female", "male"]
    assert calls[0][1] == calls[2][1]


def test_dialogue_falls_back_entirely_to_gemini_without_mixing(monkeypatch):
    providers = []

    def flaky_el(text, voice):
        if "Salut" in text:
            raise RuntimeError("429")
        providers.append("el")
        return {"data": _mp3(0.1), "extension": "mp3", "mime_type": "audio/mpeg", "provider": "elevenlabs"}

    def gemini(text, voice):
        providers.append("gemini")
        return {"data": _mp3(0.1), "extension": "mp3", "mime_type": "audio/mpeg", "provider": "gemini"}

    monkeypatch.setattr(ls.tts_service, "synthesize_elevenlabs", flaky_el)
    monkeypatch.setattr(ls.tts_service, "synthesize_gemini", gemini)
    ls.synthesize_listening_audio("Marc : Bonjour à la bibliothèque.\nSophie : Salut Marc.\nMarc : Ça va ce matin ?", ["Marc", "Sophie"])
    assert providers.count("gemini") == 3


def test_monologue_uses_a_random_registry_voice(monkeypatch):
    voices = set()

    def fake_synth(text, voice):
        voices.add(voice)
        return {"data": _mp3(0.1), "extension": "mp3", "mime_type": "audio/mpeg", "provider": "gemini"}

    monkeypatch.setattr(ls.tts_service, "synthesize", fake_synth)
    for i in range(40):
        ls.synthesize_listening_audio(f"Attention : la piscine numéro {i} ferme à 17 heures aujourd'hui.")
    assert len(voices) >= 3 and all(v.startswith("fr-FR-") for v in voices)


# ── Routes ───────────────────────────────────────────────────────────────────

def test_question_route_returns_friendly_503(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("Gemini generate_content failed: quota")
    monkeypatch.setattr(ls, "get_question", boom)
    r = client.post("/tcf/generate-listening-question", json={"question_number": 3, "defer_audio": True})
    assert r.status_code == 503
    assert "Gemini" not in r.json()["detail"]


def test_audio_route_passes_speakers(client, monkeypatch):
    seen = {}

    def fake(script, speakers):
        seen["speakers"] = speakers
        return "/audio/x.mp3"
    monkeypatch.setattr(ls, "synthesize_listening_audio", fake)
    r = client.post("/tcf/generate-listening-audio", json={"script": "Marc : a\nSophie : b", "speakers": ["Marc", "Sophie"]})
    assert r.status_code == 200 and r.json()["audio_url"] == "/audio/x.mp3"
    assert seen["speakers"] == ["Marc", "Sophie"]


def test_question_route_serves_pool_item(client, monkeypatch):
    monkeypatch.setattr(ls, "POOL", _FakePool([_question("pooled")]))
    r = client.post("/tcf/generate-listening-question",
                    json={"question_number": 12, "defer_audio": True, "target_level": "b1", "session_id": "abc"})
    assert r.status_code == 200 and r.json()["question_id"] == "pooled"
