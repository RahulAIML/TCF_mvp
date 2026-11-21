"""AI chat: history handling, language matching, SSE format (Gemini mocked)."""
import json
from types import SimpleNamespace

from routers import ai_chat_routes as chat


def _events(response):
    return [
        line[6:] if line[6:] == "[DONE]" else json.loads(line[6:])
        for line in response.text.splitlines() if line.startswith("data: ")
    ]


def test_detect_language():
    assert chat.detect_language("Quelle est la différence entre « bonjour » et « salut » ?") == "fr"
    assert chat.detect_language("What is the difference between bonjour and salut?") == "en"


def test_history_is_trimmed_and_mapped_to_roles():
    history = [chat.ChatTurn(role="user" if i % 2 == 0 else "assistant", content=f"m{i}") for i in range(30)]
    history.append(chat.ChatTurn(role="assistant", content="   "))
    contents = chat.build_contents("dernière question", history)
    assert len(contents) == chat.MAX_HISTORY_MESSAGES + 1
    assert contents[-1].role == "user" and contents[-1].parts[0].text == "dernière question"
    assert contents[0].parts[0].text == "m14"
    assert {c.role for c in contents} == {"user", "model"}


def test_long_messages_are_truncated():
    contents = chat.build_contents("x" * 5000, [])
    assert len(contents[0].parts[0].text) == chat.MAX_MESSAGE_CHARS


def test_system_prompt_forbids_latex_and_sets_language():
    system = chat.build_system_instruction("Pourquoi le CO2 réchauffe-t-il la planète ?")
    assert "NEVER use LaTeX" in system and "CO₂" in system
    assert system.endswith("answer entirely in French.")


def test_stream_sends_history_and_emits_sse(client, monkeypatch):
    captured = {}

    def fake_generate(contents, stream=False, **kwargs):
        captured["contents"] = contents
        captured["system"] = kwargs.get("system_instruction")
        return [SimpleNamespace(text="Bonjour "), SimpleNamespace(text="!")]

    monkeypatch.setattr(chat, "_gemini_generate", fake_generate)
    r = client.post("/api/ai/chat/stream", json={
        "message": "Et un autre exemple ?",
        "history": [{"role": "user", "content": "Explique le subjonctif"},
                    {"role": "assistant", "content": "Le subjonctif exprime…"}],
    })
    events = _events(r)
    assert [e["token"] for e in events[:-1]] == ["Bonjour ", "!"] and events[-1] == "[DONE]"
    assert len(captured["contents"]) == 3
    assert "French" in captured["system"]


def test_stream_error_is_friendly(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("Gemini generate_content failed: 429")

    monkeypatch.setattr(chat, "_gemini_generate", boom)
    events = _events(client.post("/api/ai/chat/stream", json={"message": "hello"}))
    assert "error" in events[0] and "429" not in events[0]["error"] and events[-1] == "[DONE]"


def test_request_without_history_still_valid(client, monkeypatch):
    monkeypatch.setattr(chat, "_gemini_generate", lambda *a, **k: SimpleNamespace(text="Réponse directe."))
    r = client.post("/api/ai/chat", json={"message": "Bonjour, ça va ?"})
    assert r.status_code == 200 and r.json()["response"] == "Réponse directe."
