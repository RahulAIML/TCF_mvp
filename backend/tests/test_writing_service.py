"""Writing generation, evaluation parsing and assistant prompts (Gemini is mocked)."""
import itertools
import time
from types import SimpleNamespace

import pytest

import tcf_ai_service as svc
from pregen_pool import PregenPool


@pytest.fixture(autouse=True)
def _fresh_writing_history():
    svc._writing_prompt_history.clear()
    svc._writing_recent_themes.clear()
    yield
    svc._writing_prompt_history.clear()


def _chunks(text: str, size: int = 7):
    return [SimpleNamespace(text=text[i:i + size]) for i in range(0, len(text), size)]


GOOD_EVAL = """NIVEAU: B1
STRUCTURE: 6
GRAMMAIRE: 5
COHÉRENCE: 6
VOCABULAIRE: 5
POINTS A AMELIORER:
- « je suis allé au parc avec mes amis » : ajoutez un connecteur, par exemple « ensuite ».
- Peut-être préciser la date : « samedi dernier ».
- Est-ce que la formule finale est adaptée ? Utilisez « Bien à vous ».
VERSION AMELIOREE:
Bonjour Marie,
Structure : je vous écris pour vous raconter ma journée.
"""


# ── feedback splitting ──────────────────────────────────────────────────────

def test_split_feedback_keeps_hyphenated_words():
    text = "- Peut-être ajouter un exemple.\n- Est-ce clair ? Reformulez.\n- Utilisez « c'est-à-dire »."
    assert svc._split_feedback(text) == [
        "Peut-être ajouter un exemple.",
        "Est-ce clair ? Reformulez.",
        "Utilisez « c'est-à-dire ».",
    ]


def test_split_feedback_handles_inline_bullets_and_numbering():
    assert svc._split_feedback("- Point un - Deuxième point") == ["Point un", "Deuxième point"]
    assert svc._split_feedback("1. Accord du verbe\n2) Ponctuation") == ["Accord du verbe", "Ponctuation"]
    assert svc._split_feedback(["  - Déjà une liste ", ""]) == ["Déjà une liste"]


# ── evaluation parsing and honesty guards ───────────────────────────────────

def test_parse_streamed_evaluation_complete():
    parsed = svc.parse_writing_evaluation_text(GOOD_EVAL)
    assert parsed["complete"] is True
    assert parsed["level"] == "B1"
    assert parsed["scores"] == {"structure": 6, "grammar": 5, "coherence": 6, "vocab": 5}
    assert len(parsed["feedback"]) == 3
    assert parsed["feedback"][1].startswith("Peut-être")
    # A "Structure :" line inside the improved text must not overwrite the score.
    assert "Structure : je vous écris" in parsed["improved_version"]


def test_parse_partial_stream_is_incomplete():
    parsed = svc.parse_writing_evaluation_text("NIVEAU: B2\nSTRUCTURE: 7\nGRAMM")
    assert parsed["complete"] is False
    assert parsed["scores"]["structure"] == 7
    assert parsed["scores"]["grammar"] is None


def test_short_text_is_capped_and_flagged():
    parsed = svc.parse_writing_evaluation_text(GOOD_EVAL.replace("STRUCTURE: 6", "STRUCTURE: 9"))
    result = svc._apply_writing_guards(parsed, "task1", "Bonjour, je viens samedi. Merci.")
    assert all(score <= 4 for score in result["scores"].values())
    assert result["feedback"][0].startswith("Longueur insuffisante")
    assert result["level"] in ("A1", "A2")


def test_level_consistent_with_scores():
    parsed = svc.parse_writing_evaluation_text(GOOD_EVAL.replace("NIVEAU: B1", "NIVEAU: C2"))
    result = svc._apply_writing_guards(parsed, "task1", " ".join(["mot"] * 80))
    assert result["level"] == "B1"


def test_learn_explanations_do_not_cite_a_letter(monkeypatch):
    monkeypatch.setattr(svc, "_generate_json", lambda *a, **k: [{
        "type": "mcq",
        "question": "Pourquoi le marché ouvre-t-il tôt ?",
        "options": ["A. le soir", "B. le matin", "C. jamais", "D. le lundi"],
        "correct_answer": "B",
        "explanation": "La réponse B est correcte car le texte dit samedi matin.",
    }])
    exercises = svc.generate_more_exercises("le marché", "A2", "Le marché ouvre le samedi matin.")
    assert exercises
    assert "réponse B" not in exercises[0]["explanation"]
    assert "bonne réponse" in exercises[0]["explanation"]


def test_examiner_pool_is_large():
    import topic_bank
    assert len(topic_bank.EXAMINERS) >= 30
    drawn = {topic_bank.pick_examiner()[0] for _ in range(60)}
    assert len(drawn) >= 15


def test_the_same_text_keeps_the_same_scores(monkeypatch):
    """A second correction must not drift (the reported case was B1 6/6/6/5, then B2 8/8/8/7)."""
    calls = []
    answers = iter([GOOD_EVAL, GOOD_EVAL.replace("NIVEAU: B1", "NIVEAU: B2").replace("STRUCTURE: 6", "STRUCTURE: 8")])

    def fake_generate(contents, stream=False, **kwargs):
        calls.append(kwargs.get("temperature"))
        text = next(answers)
        return _chunks(text) if stream else SimpleNamespace(text=text)

    monkeypatch.setattr(svc, "API_KEY", "test")
    monkeypatch.setattr(svc, "_gemini_generate", fake_generate)
    prompt = "Écrivez à un collègue au sujet d'un événement local."
    response = " ".join(["phrase"] * 130)
    first = svc.evaluate_tcf_writing_task("task2", prompt, response)
    second = svc.evaluate_tcf_writing_task("task2", prompt, response)
    assert first == second
    assert first["level"] == "B1"
    assert calls == [0.0]
    assert svc._WRITING_EVAL_TEMPERATURE == 0.0


def test_evaluate_streams_then_parses(monkeypatch):
    calls = []

    def fake_generate(contents, stream=False, **kwargs):
        calls.append(stream)
        return _chunks(GOOD_EVAL) if stream else SimpleNamespace(text=GOOD_EVAL)

    monkeypatch.setattr(svc, "API_KEY", "test")
    monkeypatch.setattr(svc, "_gemini_generate", fake_generate)
    result = svc.evaluate_tcf_writing_task("task1", "Écrivez à Marie.", " ".join(["mot"] * 80))
    assert calls == [True]
    assert result["scores"] == {"structure": 6, "grammar": 5, "coherence": 6, "vocab": 5}
    assert result["level"] == "B1"


def test_evaluate_retries_once_when_stream_malformed(monkeypatch):
    def fake_generate(contents, stream=False, **kwargs):
        return _chunks("Désolé, je ne peux pas.") if stream else SimpleNamespace(text=GOOD_EVAL)

    monkeypatch.setattr(svc, "API_KEY", "test")
    monkeypatch.setattr(svc, "_gemini_generate", fake_generate)
    result = svc.evaluate_tcf_writing_task("task2", "Consigne", " ".join(["mot"] * 130))
    assert result["scores"]["structure"] == 6


def test_empty_text_is_not_sent_to_the_model(monkeypatch):
    monkeypatch.setattr(svc, "_gemini_generate", lambda *a, **k: pytest.fail("model called for empty text"))
    result = svc.evaluate_tcf_writing_task("task3", "Consigne", "   ")
    assert result["scores"] == {"structure": 0, "grammar": 0, "coherence": 0, "vocab": 0}


def test_eval_prompt_uses_official_word_ranges():
    assert "60 à 120 mots" in svc._writing_eval_prompt("task1", "c", "t")
    assert "120 à 150 mots" in svc._writing_eval_prompt("task2", "c", "t")
    prompt3 = svc._writing_eval_prompt("task3", "c", "t")
    assert "120 à 180 mots" in prompt3 and "40 à 60 mots" in prompt3


# ── step feedback ───────────────────────────────────────────────────────────

def test_step_feedback_parse():
    result = svc.parse_writing_step_feedback(
        "- Ajoutez « Chère Marie ».\n- Peut-être une date.\nVERSION AMÉLIORÉE:\nChère Marie, je t'écris…"
    )
    assert result == {
        "feedback": ["Ajoutez « Chère Marie ».", "Peut-être une date."],
        "improved_version": "Chère Marie, je t'écris…",
    }


# ── assistant prompts (encoding) ────────────────────────────────────────────

@pytest.mark.parametrize("action", ["grammar", "suggestions", "example", "translate"])
def test_assistant_prompts_have_no_mojibake(action):
    prompt, temperature = svc._build_writing_prompt(action, "Je suis allé à l'école.", "fr-en", "Consigne")
    assert "Ã" not in prompt and "â€" not in prompt
    assert temperature > 0


def test_non_streaming_assistant_reuses_shared_prompt(monkeypatch):
    seen = {}

    def fake_text(prompt, temperature=0.4):
        seen["prompt"] = prompt
        return "Texte corrigé"

    monkeypatch.setattr(svc, "_generate_text", fake_text)
    assert svc.assist_tcf_writing("grammar", "je suis allé") == "Texte corrigé"
    assert seen["prompt"] == svc._build_writing_prompt("grammar", "je suis allé", None, None)[0]
    assert svc.assist_tcf_writing("unknown", "x") == "Action non prise en charge."


# ── task generation: uniqueness and pool ────────────────────────────────────

def _fake_task_payloads():
    counter = itertools.count()

    def fake_json(prompt, temperature=0.7):
        n = next(counter)
        return {
            "task1_prompt": f"Écrivez un message à Paul ({n}).",
            "task2_prompt": f"Rédigez un article ({n}).",
            "task3_prompt": f"Comparez. Document 1 : pour ({n}). Document 2 : contre ({n}).",
        }

    return fake_json


def test_generated_sets_never_repeat(monkeypatch):
    monkeypatch.setattr(svc, "_generate_json", _fake_task_payloads())
    sets = [svc._generate_writing_task_set() for _ in range(20)]
    flat = [value for s in sets for value in s.values()]
    assert len(flat) == len(set(flat))


def test_duplicate_from_model_is_regenerated(monkeypatch):
    fixed = {
        "task1_prompt": "Message identique.",
        "task2_prompt": "Article identique.",
        "task3_prompt": "Comparez. Document 1 : a. Document 2 : b.",
    }
    fresh = _fake_task_payloads()
    responses = iter([fixed, fixed, None])

    def fake_json(prompt, temperature=0.7):
        nxt = next(responses)
        return nxt if nxt is not None else fresh(prompt)

    monkeypatch.setattr(svc, "_generate_json", fake_json)
    first = svc._generate_writing_task_set()
    second = svc._generate_writing_task_set()
    assert first != second


def test_task3_without_documents_is_rejected(monkeypatch):
    monkeypatch.setattr(svc, "_generate_json", lambda p, temperature=0.7: {
        "task1_prompt": "a", "task2_prompt": "b", "task3_prompt": "Donnez votre avis."})
    with pytest.raises(RuntimeError):
        svc._generate_writing_task_set()


def test_pool_serves_each_set_once_per_session(monkeypatch):
    counter = itertools.count()
    pool = PregenPool("t_writing", lambda _k: {"task1_prompt": f"t1-{next(counter)}", "task2_prompt": "x",
                                                "task3_prompt": "Document 1 Document 2"}, target=3)
    monkeypatch.setattr(svc, "_writing_task_pool", pool)
    monkeypatch.setattr(svc, "_generate_writing_task_set", lambda: pytest.fail("pool should have been used"))
    pool.fill("all")
    deadline = time.time() + 3
    while pool.stats().get("all", {}).get("ready", 0) < 3 and time.time() < deadline:
        time.sleep(0.01)
    served = [svc.generate_tcf_writing_tasks("session-A")["task1_prompt"] for _ in range(3)]
    assert len(set(served)) == 3


def test_themes_rotate():
    seen = set()
    for _ in range(6):
        seen.update(svc._pick_writing_themes())
    assert len(seen) == 18
