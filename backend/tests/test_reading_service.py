import random
import re
import string
import time
from collections import Counter

import pytest

import reading_service as rs


def _word(rng: random.Random) -> str:
    return "".join(rng.choice(string.ascii_lowercase) for _ in range(7))


class FakeLLM:
    """Returns valid reading payloads with unique text; `answer` controls the letter the model claims."""

    def __init__(self, answer=None, explanation=None, text_words=None):
        self.rng = random.Random(42)
        self.answer = answer
        self.explanation = explanation
        self.text_words = text_words
        self.prompts = []

    def __call__(self, prompt, temperature):
        self.prompts.append(prompt)
        target = re.search(r'"correct_answer": "([A-D])"', prompt)
        letter = self.answer or (target.group(1) if target else "A")
        low_high = re.search(r"Longueur du (?:document|texte) : (\d+) à (\d+) mots", prompt)
        n = self.text_words or (int(low_high.group(1)) + 5 if low_high else 60)
        text = " ".join(_word(self.rng) for _ in range(n))
        options = [f"option {_word(self.rng)}" for _ in range(4)]
        if "questions" in prompt and "10 questions" in prompt:
            return {
                "title": "Titre",
                "passage": text,
                "topic": _word(self.rng),
                "questions": [
                    {"question": f"q{i}", "options": [f"o{i}{j} {_word(self.rng)}" for j in range(4)],
                     "correct_answer": "A", "explanation": "Selon le texte, l'option A est juste."}
                    for i in range(10)
                ],
            }
        return {
            "text": text,
            "question": "Que dit le document ?",
            "options": options,
            "correct_answer": letter,
            "explanation": self.explanation or "Le texte le dit clairement.",
            "topic": _word(self.rng),
        }


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(rs, "_registry", rs.UniquenessRegistry())
    monkeypatch.setattr(rs, "_served", rs.SessionServed())
    monkeypatch.setattr(rs, "_exam_cache", rs.OrderedDict())
    # Keep tests deterministic and offline: never use the background pool.
    monkeypatch.setattr(rs._READING_POOL, "take", lambda key: None)
    monkeypatch.setattr(rs._QUIZ_POOL, "take", lambda key: None)
    fake = FakeLLM()
    monkeypatch.setattr(rs, "_llm_json", fake)
    return fake


# ── Level mapping ────────────────────────────────────────────────────────────

def test_every_question_number_maps_to_exactly_one_ascending_level():
    levels = [rs.level_for_question(q) for q in range(1, 40)]
    assert levels[0] == "A1" and levels[-1] == "C2"
    order = rs.READING_LEVELS
    assert [order.index(l) for l in levels] == sorted(order.index(l) for l in levels), "levels must ascend"
    assert set(levels) == set(order), "all six levels appear in the 39-question exam"
    assert Counter(levels) == {"A1": 4, "A2": 6, "B1": 9, "B2": 10, "C1": 6, "C2": 4}


def test_each_level_has_its_own_spec_and_question_type():
    types = {rs.READING_SPECS[l]["question_type"] for l in rs.READING_LEVELS}
    assert len(types) == 6
    for level in ("C1", "C2"):
        assert "jargon" in rs.READING_SPECS[level]["language"]


# ── Routing by target level ──────────────────────────────────────────────────

def test_target_level_overrides_question_number(fresh_state):
    q = rs.get_reading_question(1, session_id="s1", target_level="C2")
    assert q.question_type == "reading_c2"
    assert "Niveau : C2" in fresh_state.prompts[-1]


def test_exam_level_follows_question_number(fresh_state):
    assert rs.get_reading_question(2, "s1").question_type == "reading_a1"
    assert rs.get_reading_question(25, "s1").question_type == "reading_b2"
    assert rs.get_reading_question(39, "s1").question_type == "reading_c2"


def test_invalid_target_level_falls_back_to_question_number():
    assert rs.get_reading_question(12, "s1", target_level="Z9").question_type == "reading_b1"


# ── Caching / uniqueness ─────────────────────────────────────────────────────

def test_exam_question_is_stable_within_a_session_for_resume():
    first = rs.get_reading_question(7, session_id="exam-1")
    again = rs.get_reading_question(7, session_id="exam-1")
    assert first == again


def test_no_cache_is_shared_across_sessions_or_anonymous_users():
    a = rs.get_reading_question(7, session_id="user-a")
    b = rs.get_reading_question(7, session_id="user-b")
    anon1 = rs.get_reading_question(7)
    anon2 = rs.get_reading_question(7)
    texts = {a.text, b.text, anon1.text, anon2.text}
    assert len(texts) == 4


def test_practice_never_repeats_even_for_the_same_question_number():
    seen = {rs.get_reading_question(5, session_id="p", target_level="A2").text for _ in range(15)}
    assert len(seen) == 15


def test_duplicate_and_near_duplicate_texts_are_rejected():
    reg = rs.UniquenessRegistry()
    text = "La bibliotheque municipale ouvre ses portes samedi matin pour une journee familiale gratuite"
    assert reg.check_and_register("q:B1", text, "bibliotheque familiale")
    assert not reg.check_and_register("q:B1", text, "autre")
    near = text.replace("samedi", "dimanche")
    assert not reg.check_and_register("q:B1", near, "autre sujet")
    assert not reg.check_and_register("q:B1", "Un texte completement different sur la cuisine", "bibliotheque familiale")


def test_pool_items_are_not_reserved_twice_for_one_session(monkeypatch):
    item = rs.produce_reading_question("B1")
    served_twice = iter([item, item, None, None])
    monkeypatch.setattr(rs._READING_POOL, "take", lambda key: next(served_twice))
    first = rs.get_reading_question(12, session_id="sess", target_level="B1")
    second = rs.get_reading_question(12, session_id="sess", target_level="B1")
    assert first.text == item.text
    assert second.text != item.text


def test_exam_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(rs, "_EXAM_CACHE_MAX", 5)
    for i in range(12):
        rs.get_reading_question(3, session_id=f"s{i}")
    assert len(rs._exam_cache) == 5


# ── Answer key integrity ─────────────────────────────────────────────────────

def test_answer_moved_to_target_letter_when_model_disagrees(monkeypatch):
    monkeypatch.setattr(rs.answer_balance, "next_letter", lambda bucket: "D")
    fake = FakeLLM(answer="A", explanation="L'option A est correcte car le texte le précise.")
    monkeypatch.setattr(rs, "_llm_json", fake)
    q = rs.produce_reading_question("B2")
    assert q.correct_answer == "D"
    assert q.options[3].startswith("D. ")
    assert not re.search(r"\b(option|réponse)\s+[A-D]\b", q.explanation, re.I)
    assert "la bonne réponse" in q.explanation


def test_correct_option_text_survives_the_swap():
    payload = {
        "question": "Q ?",
        "options": ["A. juste", "B) faux un", "faux deux", "faux trois"],
        "correct_answer": "A",
        "explanation": "La réponse A est la bonne, pas la réponse C.",
    }
    block = rs._validate_choice_block(payload, "C")
    assert block["correct_answer"] == "C"
    assert block["options"][2] == "C. juste"
    assert block["options"][0] == "A. faux deux"
    assert "réponse A" not in block["explanation"] and "réponse C" not in block["explanation"]


def test_answer_letters_are_uniformly_distributed():
    counts = Counter(rs.produce_reading_question("A2").correct_answer for _ in range(400))
    for letter in rs.LETTERS:
        assert 70 <= counts[letter] <= 130, counts


@pytest.mark.parametrize("bad", [
    {"options": ["a", "b", "c"]},
    {"options": ["a", "a", "b", "c"]},
    {"correct_answer": "E"},
    {"explanation": ""},
])
def test_invalid_choice_blocks_are_rejected(bad):
    payload = {"question": "Q", "options": ["a", "b", "c", "d"], "correct_answer": "B", "explanation": "x"}
    payload.update(bad)
    with pytest.raises(ValueError):
        rs._validate_choice_block(payload, "A")


def test_generation_gives_up_after_three_attempts(monkeypatch):
    calls = []

    def broken(prompt, temperature):
        calls.append(1)
        raise RuntimeError("model down")

    monkeypatch.setattr(rs, "_llm_json", broken)
    with pytest.raises(RuntimeError):
        rs.produce_reading_question("C1")
    assert len(calls) == rs.MAX_ATTEMPTS == 3


def test_text_far_outside_level_length_is_rejected(monkeypatch):
    monkeypatch.setattr(rs, "_llm_json", FakeLLM(text_words=400))
    with pytest.raises(RuntimeError):
        rs.produce_reading_question("A1")


# ── Passage quiz ─────────────────────────────────────────────────────────────

def test_passage_quiz_enforces_planned_letters_and_level(fresh_state):
    quiz = rs.get_passage_quiz("C1", session_id="pa")
    assert len(quiz.questions) == 10
    letters = Counter(q.correct_answer for q in quiz.questions)
    assert len(letters) >= 3, letters
    for q in quiz.questions:
        assert "option A" not in q.explanation
    assert "Niveau : C1" in fresh_state.prompts[-1]


def test_passage_quiz_defaults_to_b1_and_rejects_unknown_level(fresh_state):
    rs.get_passage_quiz("A1")
    assert "Niveau : B1" in fresh_state.prompts[-1]


# ── Pool integration ─────────────────────────────────────────────────────────

def test_real_pool_serves_unique_items(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(rs, "_llm_json", fake)
    pool = rs.pregen_pool.PregenPool("t_reading", lambda level: rs.produce_reading_question(level), target=5)
    pool.fill("B2")
    deadline = time.time() + 5
    while time.time() < deadline and pool.stats().get("B2", {}).get("ready", 0) < 5:
        time.sleep(0.02)
    items = [pool.take("B2") for _ in range(5)]
    assert all(items)
    assert len({i.text for i in items}) == 5


# ── HTTP routes ──────────────────────────────────────────────────────────────

def test_route_passes_target_level_and_validates(client):
    r = client.post("/tcf/generate-question", json={"question_number": 3, "session_id": "x", "target_level": "C1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["question_type"] == "reading_c1" and body["question_number"] == 3
    bad = client.post("/tcf/generate-question", json={"question_number": 3, "target_level": "Z1"})
    assert bad.status_code == 422


def test_route_hides_generator_errors(client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("Gemini generate_content failed: secret stack")

    monkeypatch.setattr(rs, "produce_reading_question", boom)
    r = client.post("/tcf/generate-question", json={"question_number": 3})
    assert r.status_code == 503
    assert "Gemini" not in r.text and "Réessayez" in r.text.replace("réessayer", "Réessayez")


def test_passage_quiz_route_accepts_level_and_empty_body(client):
    r = client.post("/generate-passage-quiz", json={"level": "B2", "session_id": "pq"})
    assert r.status_code == 200, r.text
    assert len(r.json()["questions"]) == 10
    r2 = client.post("/generate-passage-quiz")
    assert r2.status_code == 200, r2.text


def test_guest_can_submit_reading_exam(client):
    r = client.post("/tcf/submit-exam", json={
        "started_at": "2026-11-22T10:00:00Z",
        "completed_at": "2026-11-22T10:30:00Z",
        "answers": {"1": "A", "2": ""},
        "questions": [
            {"question_number": 1, "correct_answer": "A", "question_type": "reading_a1", "explanation": "x"},
            {"question_number": 2, "correct_answer": "B", "question_type": "reading_a1", "explanation": "y"},
        ],
    })
    assert r.status_code == 200, r.text
    assert r.json()["score"] == 1 and r.json()["attempted"] == 1
