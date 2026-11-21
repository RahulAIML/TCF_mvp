"""AI Learn exercises: five small model calls in parallel, streamed progress, honest fallbacks."""
import json
import threading
import time

import tcf_ai_service
from routers import learn_routes


def _fake_slot_json(delay=0.0, bad_types=(), fail_first=()):
    lock = threading.Lock()
    calls = {"n": 0, "per_type": {}}

    def fake(prompt, temperature=0.7):
        exercise_type = next(t for t in ("sentence_correction", "speaking_prompt", "writing_task", "mcq")
                             if f'"type": "{t}"' in prompt)
        with lock:
            calls["n"] += 1
            seen = calls["per_type"][exercise_type] = calls["per_type"].get(exercise_type, 0) + 1
        time.sleep(delay)
        if exercise_type in bad_types or (exercise_type in fail_first and seen == 1):
            return {"nonsense": True}
        question = f"{exercise_type} {seen} {prompt.count('DIFFÉRENTE')} {time.time_ns()}"
        item = {"type": "wrong-type-from-model", "question": question, "correct_answer": "x", "explanation": "e"}
        if exercise_type == "mcq":
            item.update(options=["A. a", "B. b", "C. c", "D. d"], correct_answer="C")
        if exercise_type == "sentence_correction":
            item.update(incorrect="Il mange des pomme.")
        return item

    return fake, calls


def test_five_exercises_generated_in_parallel_in_order(monkeypatch):
    fake, calls = _fake_slot_json(delay=0.4)
    monkeypatch.setattr(tcf_ai_service, "_generate_json", fake)
    ready = []
    start = time.time()
    exercises = tcf_ai_service.generate_learn_exercises("Un texte.", on_ready=lambda i, ex: ready.append(i))
    elapsed = time.time() - start
    assert elapsed < 1.2, f"slots ran one after another ({elapsed:.2f}s)"
    assert [e["type"] for e in exercises] == ["mcq", "sentence_correction", "writing_task", "speaking_prompt", "writing_task"]
    assert sorted(ready) == [0, 1, 2, 3, 4] and calls["n"] == 5


def test_invalid_exercise_is_retried_once(monkeypatch):
    fake, calls = _fake_slot_json(fail_first=("mcq",))
    monkeypatch.setattr(tcf_ai_service, "_generate_json", fake)
    exercises = tcf_ai_service.generate_learn_exercises("Un texte.")
    assert exercises[0]["type"] == "mcq" and calls["per_type"]["mcq"] == 2


def test_persistently_invalid_exercise_is_dropped_not_faked(monkeypatch):
    fake, _ = _fake_slot_json(bad_types=("speaking_prompt",))
    monkeypatch.setattr(tcf_ai_service, "_generate_json", fake)
    exercises = tcf_ai_service.generate_learn_exercises("Un texte.")
    assert [e["type"] for e in exercises] == ["mcq", "sentence_correction", "writing_task", "writing_task"]


def test_already_asked_questions_are_never_repeated(monkeypatch):
    # Every slot returns the same already-asked question (sentence corrections are identified by question + sentence).
    monkeypatch.setattr(tcf_ai_service, "_generate_json",
                        lambda prompt, temperature=0.7: {"type": "x", "question": "Même question", "correct_answer": "A",
                                                         "options": ["A. a", "B. b", "C. c", "D. d"], "incorrect": "y"})
    exercises = tcf_ai_service.generate_more_exercises(
        "Vélo", "B1", "Résumé", exclude_questions=["Même question", "Même questiony"])
    assert exercises == []


def test_one_set_never_contains_the_same_question_twice(monkeypatch):
    monkeypatch.setattr(tcf_ai_service, "_generate_json",
                        lambda prompt, temperature=0.7: {"type": "x", "question": "Identique", "correct_answer": "A"})
    exercises = tcf_ai_service.generate_learn_exercises("Un texte.")
    assert [e["question"] for e in exercises] == ["Identique"]


def test_analysis_stream_reports_progress_then_full_list(client, monkeypatch):
    fake, _ = _fake_slot_json(delay=0.05)
    monkeypatch.setattr(tcf_ai_service, "_generate_json", fake)
    monkeypatch.setattr(learn_routes, "generate_learn_overview", lambda text: {
        "topic": "Vélo", "level": "B1", "summary": "Résumé.", "key_points": ["a"], "vocabulary": [],
    })
    monkeypatch.setattr(learn_routes._batches, "schedule", lambda *a, **k: None)
    r = client.post("/learn/analyze/stream", json={"text": "Un texte en français assez long."})
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    progress = [e["ready"] for e in events if e["type"] == "progress"]
    assert progress == [1, 2, 3, 4, 5]
    kinds = [e["type"] for e in events]
    assert kinds.index("exercises") > kinds.index("progress") and kinds[-1] == "done"
    assert len(next(e for e in events if e["type"] == "exercises")["exercises"]) == 5
