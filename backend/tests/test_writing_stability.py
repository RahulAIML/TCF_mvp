"""Identical writing submissions must always get identical evaluations (Mario: B1, B2, B1 for the same text)."""
import itertools
from types import SimpleNamespace

import pytest

import tcf_ai_service as svc


@pytest.fixture(autouse=True)
def _clean_cache():
    svc._writing_eval_cache.clear()
    yield
    svc._writing_eval_cache.clear()


def _eval_text(score: int) -> str:
    return (f"NIVEAU: B2\nSTRUCTURE: {score}\nGRAMMAIRE: {score}\nCOHÉRENCE: {score}\nVOCABULAIRE: {score}\n"
            "POINTS A AMELIORER:\n- « bonjour » : ajoutez une virgule.\nVERSION AMELIOREE:\nBonjour, Marie.\n")


def _chunks(text):
    return [SimpleNamespace(text=text[i:i + 9]) for i in range(0, len(text), 9)]


TEXT = " ".join(["mot"] * 90)


def _varying_model(monkeypatch):
    scores = itertools.cycle([6, 8, 5, 9])
    calls = []

    def fake_generate(contents, stream=False, **kwargs):
        calls.append(kwargs)
        text = _eval_text(next(scores))
        return _chunks(text) if stream else SimpleNamespace(text=text)

    monkeypatch.setattr(svc, "API_KEY", "test")
    monkeypatch.setattr(svc, "_gemini_generate", fake_generate)
    return calls


def test_same_text_gets_the_same_result_even_if_the_model_varies(monkeypatch):
    calls = _varying_model(monkeypatch)
    results = [svc.evaluate_tcf_writing_task("task1", "Écrivez à Marie.", TEXT) for _ in range(4)]
    assert all(r == results[0] for r in results)
    assert len(calls) == 1, "identical submission was re-scored by the model"


def test_whitespace_differences_are_the_same_submission(monkeypatch):
    calls = _varying_model(monkeypatch)
    a = svc.evaluate_tcf_writing_task("task1", "Écrivez à Marie.", TEXT)
    b = svc.evaluate_tcf_writing_task("task1", "Écrivez  à Marie. ", "  " + TEXT.replace(" ", "\n", 3) + "\n")
    assert a == b and len(calls) == 1


def test_different_text_or_task_is_scored_separately(monkeypatch):
    calls = _varying_model(monkeypatch)
    svc.evaluate_tcf_writing_task("task1", "Consigne", TEXT)
    svc.evaluate_tcf_writing_task("task1", "Consigne", TEXT + " encore")
    svc.evaluate_tcf_writing_task("task2", "Consigne", " ".join(["mot"] * 130))
    assert len(calls) == 3


def test_model_is_called_deterministically(monkeypatch):
    calls = _varying_model(monkeypatch)
    svc.evaluate_tcf_writing_task("task1", "Consigne", TEXT)
    assert calls[0]["temperature"] == 0.0 and calls[0]["seed"] == svc._EVAL_SEED


def test_stream_replay_matches_first_stream(monkeypatch):
    _varying_model(monkeypatch)
    first_text = "".join(svc.stream_writing_evaluation_tokens("task1", "Consigne", TEXT))
    first = svc.finalize_writing_evaluation(first_text, "task1", "Consigne", TEXT)
    replay_text = "".join(svc.stream_writing_evaluation_tokens("task1", "Consigne", TEXT))
    replay = svc.finalize_writing_evaluation(replay_text, "task1", "Consigne", TEXT)
    assert replay_text == first_text and replay == first


@pytest.mark.parametrize("score,level", [(0, "A1"), (2, "A1"), (3, "A2"), (4, "A2"), (5, "B1"), (6, "B1"),
                                         (7, "B2"), (8, "B2"), (9, "C1"), (10, "C2")])
def test_level_comes_only_from_the_scores(score, level):
    parsed = svc.parse_writing_evaluation_text(_eval_text(score).replace("NIVEAU: B2", "NIVEAU: C2"))
    assert svc._apply_writing_guards(parsed, "task1", TEXT)["level"] == level


def test_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(svc, "_WRITING_EVAL_CACHE_MAX", 3)
    _varying_model(monkeypatch)
    for i in range(6):
        svc.evaluate_tcf_writing_task("task1", "Consigne", TEXT + f" {i}")
    assert len(svc._writing_eval_cache) == 3


def _sse_parts(raw: str):
    import json
    tokens, final = [], None
    for line in raw.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        event = json.loads(line[6:])
        if "token" in event:
            tokens.append(event["token"])
        if "evaluation" in event:
            final = event["evaluation"]
    return "".join(tokens), final


def test_routes_replay_identical_stream(client, monkeypatch):
    _varying_model(monkeypatch)
    body = {"task_type": "task1", "prompt": "Écrivez à Marie.", "response_text": TEXT}
    first_text, first_eval = _sse_parts(client.post("/tcf/evaluate-writing/stream", json=body).text)
    second_text, second_eval = _sse_parts(client.post("/tcf/evaluate-writing/stream", json=body).text)
    plain = client.post("/tcf/evaluate-writing", json=body).json()
    assert first_text == second_text
    assert first_eval == second_eval == plain


def test_stream_never_shows_the_models_own_level(monkeypatch):
    _varying_model(monkeypatch)
    streamed = "".join(svc.stream_writing_evaluation_tokens("task1", "Consigne", TEXT))
    assert "NIVEAU" not in streamed and "STRUCTURE: 6" in streamed
    final = svc.finalize_writing_evaluation(streamed, "task1", "Consigne", TEXT)
    assert final["level"] == "B1"  # computed from scores of 6, not the model's "B2"
