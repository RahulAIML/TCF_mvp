"""AI Learn: instant local scoring, French feedback, streaming, served-once exercise batches."""
import json
import threading
import time

import pytest

import tcf_ai_service
from routers import learn_routes
from routers.learn_routes import ExerciseBatchCache, content_id_for


def _no_ai(*_args, **_kwargs):
  raise AssertionError("objective exercises must not call the model")


@pytest.fixture()
def forbid_ai(monkeypatch):
  monkeypatch.setattr(tcf_ai_service, "_generate_json", _no_ai)


# ── Local MCQ / sentence scoring ────────────────────────────────────────────

@pytest.mark.parametrize("user_answer,expected,correct", [
  ("B", "B", True),
  ("b", "B. Le train", True),
  ("B. Le train", "B", True),
  ("C", "B", False),
  ("A) Oui", "A", True),
])
def test_mcq_is_scored_locally(forbid_ai, user_answer, expected, correct):
  started = time.perf_counter()
  result = tcf_ai_service.evaluate_learn_answer("mcq", "Q ?", expected, user_answer, explanation="Parce que.")
  assert time.perf_counter() - started < 0.05
  assert result["is_correct"] is correct
  assert result["score"] == (10 if correct else 0)
  assert result["explanation"] == "Parce que."


def test_wrong_mcq_feedback_is_french_and_names_the_answer(forbid_ai):
  result = tcf_ai_service.evaluate_learn_answer("mcq", "Q ?", "D", "A")
  assert result["feedback"] == ["Réponse incorrecte. La bonne réponse est D."]
  text = " ".join(result["feedback"]).lower()
  assert "the correct answer" not in text and "incorrect." not in text


def test_sentence_correction_ignores_case_and_punctuation(forbid_ai):
  ok = tcf_ai_service.evaluate_learn_answer("sentence_correction", "Corrigez", "Je suis allé au marché.", "je suis allé au marché")
  bad = tcf_ai_service.evaluate_learn_answer("sentence_correction", "Corrigez", "Je suis allé au marché.", "Je suis aller au marché.")
  assert ok["is_correct"] and ok["score"] == 10
  assert not bad["is_correct"] and bad["score"] == 0
  assert "Réponse attendue : Je suis allé au marché." in bad["feedback"]


def test_blank_answer_never_reaches_the_model(forbid_ai):
  result = tcf_ai_service.evaluate_learn_answer("writing_task", "Écrivez", "modèle", "   ")
  assert result["score"] == 0 and result["feedback"] == ["Aucune réponse fournie."]


def test_open_ended_uses_model_and_splits_feedback_on_lines_not_hyphens(monkeypatch):
  prompts = []

  def fake(prompt, temperature=0.7):
    prompts.append(prompt)
    return {"overall_score": 7, "grammar": 6, "feedback": "- Peut-être ajouter un exemple.\n- Est-ce clair ?", "explanation": "Bien."}

  monkeypatch.setattr(tcf_ai_service, "_generate_json", fake)
  result = tcf_ai_service.evaluate_learn_answer("writing_task", "Écrivez", "", "Mon texte en français.")
  assert result["score"] == 7 and result["is_correct"]
  assert result["feedback"] == ["Peut-être ajouter un exemple.", "Est-ce clair ?"]
  assert "UNIQUEMENT en français" in prompts[0]


# ── Exercise uniqueness ─────────────────────────────────────────────────────

def test_repeated_questions_are_dropped():
  exercises = [{"type": "mcq", "question": "Quel est le sujet ?"}, {"type": "mcq", "question": "Où se passe l'histoire ?"}]
  kept = tcf_ai_service._drop_repeated(exercises, ["quel est le sujet?"])
  assert [e["question"] for e in kept] == ["Où se passe l'histoire ?"]


# ── Served-once prefetched batch ────────────────────────────────────────────

def _batch(prefix):
  return [
    {"type": "mcq", "question": f"{prefix} q1", "options": ["A. a", "B. b", "C. c", "D. d"], "correct_answer": "A"},
    {"type": "sentence_correction", "question": f"{prefix} q2", "correct_answer": "x"},
  ]


def test_prefetched_batch_is_served_once_and_excludes_seen_questions():
  calls = []
  lock = threading.Lock()

  def producer(topic, level, summary, exclude):
    with lock:
      calls.append(list(exclude))
      return _batch(f"lot{len(calls)}")

  cache = ExerciseBatchCache(producer)
  cache.remember("c1", ["première question"])
  cache.schedule("c1", "Sujet", "B1", "Résumé")
  first = cache.take("c1", timeout=5)
  assert [e["question"] for e in first] == ["lot1 q1", "lot1 q2"]
  assert calls[0] == ["première question"], "producer must receive already-asked questions"
  assert cache.take("c1", timeout=0.1) is None, "a batch must never be served twice"


def test_take_drops_questions_served_meanwhile():
  cache = ExerciseBatchCache(lambda *a: _batch("lot"))
  cache.schedule("c2", "S", "B1", "R")
  time.sleep(0.2)
  cache.remember("c2", ["lot q1"])
  assert [e["question"] for e in cache.take("c2", timeout=5)] == ["lot q2"]


def test_more_exercises_endpoint_serves_prefetched_batch_instantly(client, monkeypatch):
  produced = []

  def producer(topic, level, summary, exclude):
    produced.append(1)
    return _batch(f"lot{len(produced)}")

  monkeypatch.setattr(learn_routes, "_batches", ExerciseBatchCache(producer))
  body = {"topic": "Le vélo", "level": "B1", "summary": "Un texte."}
  cid = content_id_for(body["topic"], body["level"], body["summary"])
  learn_routes._batches.schedule(cid, body["topic"], body["level"], body["summary"])
  time.sleep(0.2)

  started = time.perf_counter()
  r = client.post("/learn/more-exercises", json={**body, "content_id": cid})
  assert r.status_code == 200, r.text
  assert time.perf_counter() - started < 1.0
  first = [e["question"] for e in r.json()]
  assert first == ["lot1 q1", "lot1 q2"]

  time.sleep(0.2)  # next batch was scheduled after serving
  second = [e["question"] for e in client.post("/learn/more-exercises", json={**body, "content_id": cid}).json()]
  assert second and not set(first) & set(second)


# ── Streaming endpoints ─────────────────────────────────────────────────────

def _events(response):
  return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def test_analyze_stream_emits_overview_exercises_done(client, monkeypatch):
  monkeypatch.setattr(learn_routes, "generate_learn_overview", lambda text: {
    "topic": "Vélo", "level": "B1", "summary": "Résumé.", "key_points": ["a"], "vocabulary": [],
  })
  monkeypatch.setattr(learn_routes, "generate_learn_exercises", lambda text, **kwargs: _batch("x"))
  monkeypatch.setattr(learn_routes, "_batches", ExerciseBatchCache(lambda *a: _batch("next")))
  r = client.post("/learn/analyze/stream", json={"text": "Un texte en français assez long."})
  events = _events(r)
  kinds = [e["type"] for e in events]
  assert set(kinds[:2]) == {"overview", "exercises"} and kinds[-1] == "done"
  assert events[-1]["content_id"] == content_id_for("Vélo", "B1", "Résumé.")


def test_analyze_stream_reports_friendly_error(client, monkeypatch):
  def boom(text):
    raise RuntimeError("Gemini generate_content failed: quota")

  monkeypatch.setattr(learn_routes, "generate_learn_overview", boom)
  monkeypatch.setattr(learn_routes, "generate_learn_exercises", lambda text, **kwargs: _batch("x"))
  events = _events(client.post("/learn/analyze/stream", json={"text": "Un texte en français assez long."}))
  assert events[-1] == {"type": "error", "message": "L'analyse a échoué. Veuillez réessayer."}


def test_evaluate_batch_stream_returns_every_item(client, monkeypatch):
  monkeypatch.setattr(tcf_ai_service, "_generate_json", lambda prompt, temperature=0.7: {"overall_score": 8, "feedback": ["Bien."]})
  items = [
    {"index": 0, "exercise_type": "mcq", "question": "Q", "correct_answer": "A", "user_answer": "A"},
    {"index": 1, "exercise_type": "writing_task", "question": "Écrivez", "correct_answer": "", "user_answer": "Texte."},
    {"index": 2, "exercise_type": "mcq", "question": "Q", "correct_answer": "A", "user_answer": "C"},
  ]
  events = _events(client.post("/learn/evaluate-batch/stream", json={"items": items}))
  results = {e["index"]: e["evaluation"] for e in events if e["type"] == "result"}
  assert set(results) == {0, 1, 2}
  assert results[0]["is_correct"] and results[1]["score"] == 8 and not results[2]["is_correct"]
  assert events[-1]["type"] == "done"


def test_guest_learn_session_is_not_stored(client):
  from database import SessionLocal
  from models import LearnSession

  db = SessionLocal()
  before = db.query(LearnSession).count()
  r = client.post("/learn/session/save", json={"source_type": "text", "topic": "T", "score": 8, "exercises_total": 5, "exercises_completed": 3})
  assert r.status_code == 200 and r.json()["id"] == 0 and r.json()["score"] == 8
  assert db.query(LearnSession).count() == before
  db.close()
