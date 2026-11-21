"""Writing and Phrase Helper HTTP routes: SSE format, parallel submit, friendly errors (Gemini mocked)."""
import json
import threading
import time
from types import SimpleNamespace

import tcf_ai_service as svc
from routers import tcf_writing_routes as routes

EVAL = """NIVEAU: B1
STRUCTURE: 6
GRAMMAIRE: 5
COHERENCE: 6
VOCABULAIRE: 5
POINTS A AMELIORER:
- Ajoutez un connecteur.
VERSION AMELIOREE:
Texte amélioré.
"""

LONG = " ".join(["mot"] * 130)


def _events(response) -> list:
    out = []
    for line in response.text.splitlines():
        if not line.startswith("data: "):
            continue
        raw = line[6:]
        out.append(raw if raw == "[DONE]" else json.loads(raw))
    return out


def _submit_payload():
    return {
        "session_id": "s-1", "mode": "exam",
        "task1_prompt": "c1", "task2_prompt": "c2", "task3_prompt": "c3",
        "task1_text": LONG, "task2_text": LONG, "task3_text": LONG,
    }


def test_submit_stream_runs_tasks_in_parallel_and_saves(client, monkeypatch):
    active, peak, lock = [0], [0], threading.Lock()

    def slow_tokens(task, prompt, text):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.3)
        with lock:
            active[0] -= 1
        for line in EVAL.splitlines(keepends=True):
            yield line

    monkeypatch.setattr(routes, "stream_writing_evaluation_tokens", slow_tokens)
    r = client.post("/tcf/writing/submit/stream", json=_submit_payload())
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _events(r)
    assert events[-1] == "[DONE]"
    done_tasks = {e["task"] for e in events if isinstance(e, dict) and "evaluation" in e}
    assert done_tasks == {"task1", "task2", "task3"}
    assert any(isinstance(e, dict) and e.get("token") for e in events)
    assert {"saved": True} in events
    assert peak[0] == 3, "tasks were not evaluated concurrently"


def test_submit_stream_reports_task_error_without_breaking_others(client, monkeypatch):
    def tokens(task, prompt, text):
        if task == "task2":
            raise RuntimeError("Gemini generate_content failed: boom")
        yield EVAL

    monkeypatch.setattr(routes, "stream_writing_evaluation_tokens", tokens)
    events = _events(client.post("/tcf/writing/submit/stream", json=_submit_payload()))
    errors = [e for e in events if isinstance(e, dict) and "error" in e]
    assert len(errors) == 1 and errors[0]["task"] == "task2"
    assert "Gemini" not in errors[0]["error"]
    assert {"saved": False} in events and events[-1] == "[DONE]"


def test_submit_non_stream_is_parallel(client, monkeypatch):
    def slow_eval(task, prompt, text):
        time.sleep(0.3)
        return {"level": "B1", "scores": {"structure": 6, "grammar": 5, "coherence": 6, "vocab": 5},
                "feedback": ["ok"], "improved_version": ""}

    monkeypatch.setattr(routes, "evaluate_tcf_writing_task", slow_eval)
    start = time.time()
    r = client.post("/tcf/writing/submit", json=_submit_payload())
    assert r.status_code == 200, r.text
    assert time.time() - start < 0.85
    assert r.json()["task3"]["level"] == "B1"


def test_evaluate_stream_emits_tokens_then_evaluation(client, monkeypatch):
    monkeypatch.setattr(svc, "API_KEY", "test")
    monkeypatch.setattr(svc, "_gemini_generate",
                        lambda c, stream=False, **k: [SimpleNamespace(text=EVAL[:20]), SimpleNamespace(text=EVAL[20:])])
    r = client.post("/tcf/evaluate-writing/stream",
                    json={"task_type": "task2", "prompt": "c", "response_text": LONG})
    events = _events(r)
    assert events[0]["token"] == EVAL[:20]
    final = [e for e in events if isinstance(e, dict) and "evaluation" in e][0]["evaluation"]
    assert final["scores"]["grammar"] == 5 and events[-1] == "[DONE]"


def test_step_stream_parses_feedback(client, monkeypatch):
    monkeypatch.setattr(svc, "API_KEY", "test")
    monkeypatch.setattr(svc, "_gemini_generate", lambda c, stream=False, **k: [
        SimpleNamespace(text="- Peut-être ajouter « Chère Marie ».\nVERSION AMELIOREE:\nChère Marie, …")])
    r = client.post("/tcf/evaluate-writing-step/stream",
                    json={"task_type": "task1", "step": "Situation", "prompt": "c", "text": "Bonjour"})
    feedback = [e for e in _events(r) if isinstance(e, dict) and "feedback" in e][0]["feedback"]
    assert feedback["feedback"] == ["Peut-être ajouter « Chère Marie »."]
    assert feedback["improved_version"] == "Chère Marie, …"


def test_generation_failure_returns_friendly_503(client, monkeypatch):
    def boom(session_id=None):
        raise RuntimeError("Gemini generate_content failed: quota")

    monkeypatch.setattr(routes, "generate_tcf_writing_tasks", boom)
    r = client.post("/tcf/generate-writing-tasks", json={"session_id": "x"})
    assert r.status_code == 503 and "Gemini" not in r.text


def test_assistant_stream_error_is_friendly(client, monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("Gemini generate_content failed: 500")
        yield  # pragma: no cover

    monkeypatch.setattr(routes, "stream_assist_tcf_writing", broken)
    events = _events(client.post("/tcf/writing/assistant/stream", json={"message": "x", "action": "grammar"}))
    assert "error" in events[0] and "Gemini" not in events[0]["error"] and events[-1] == "[DONE]"


def test_explain_and_translate_stream(client, monkeypatch):
    monkeypatch.setattr(svc, "API_KEY", "test")
    seen = []

    def fake(contents, stream=False, **k):
        seen.append(contents)
        return [SimpleNamespace(text="**Sens** : "), SimpleNamespace(text="progressivement.")]

    monkeypatch.setattr(svc, "_gemini_generate", fake)
    events = _events(client.post("/explain-text/stream", json={"text": "au fur et à mesure"}))
    assert [e["token"] for e in events[:-1]] == ["**Sens** : ", "progressivement."]
    events = _events(client.post("/translate/stream", json={"text": "Hello", "direction": "en-fr"}))
    assert events[-1] == "[DONE]"
    assert "to natural French" in seen[-1]
