"""
AI Chat Route — powers the FloatingAIAssistant on the frontend.
Single endpoint + streaming SSE endpoint. No mock responses.
"""

import json
import logging
import re
from typing import List, Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from google.genai import types
from pydantic import BaseModel, Field

from tcf_ai_service import _gemini_generate

logger = logging.getLogger("ai_chat")
router = APIRouter()

MAX_HISTORY_MESSAGES = 16
MAX_MESSAGE_CHARS = 2000

BANNED_PHRASES = [
    "great question",
    "more context",
    "could you clarify",
    "provide more details",
    "can you give more",
]

SYSTEM_PROMPT = """You are an expert French and English language tutor for TCF Canada candidates.

CRITICAL LANGUAGE RULE: Always respond in the SAME LANGUAGE the user writes in.
- If the user writes in French → answer entirely in French.
- If the user writes in English → answer entirely in English.
- If the user mixes languages → match the dominant language of their message.
- Never switch languages unless the user explicitly asks you to.

Formatting rules (the chat renders simple Markdown only):
- Use **bold**, short paragraphs, "- " bullet lists, "1. " numbered lists and "### " headings when useful.
- NEVER use LaTeX or $...$ math notation. Write chemistry and math with Unicode: CO₂, H₂O, m², 10⁶, ×, →.
- The "$" sign is only for money (e.g. 5 $).

Rules:
- Always answer directly
- Translate immediately when asked
- Explain grammar clearly with examples
- Help with vocabulary and pronunciation
- Do NOT ask for more context unless absolutely necessary
- Assume the most likely intent from the user, using the earlier conversation when it helps
- Be concise but useful
- Give examples when helpful

You support:
- translation (French ↔ English)
- grammar explanations
- pronunciation guidance
- vocabulary building
- TCF/TEF exam preparation
- general French and English learning
"""

_FRENCH_HINTS = re.compile(
    r"[àâçéèêëîïôûùüÿœæ]|\b(le|la|les|des|une|est|que|qui|pour|avec|dans|je|tu|vous|nous|c'est|comment|"
    r"pourquoi|quelle?s?|quoi|où|bonjour|merci|est-ce)\b",
    re.IGNORECASE,
)
_ENGLISH_HINTS = re.compile(
    r"\b(the|is|are|what|how|why|which|does|do|can|could|would|should|in|of|and|to|my|your|please|"
    r"translate|mean|means|difference|between)\b",
    re.IGNORECASE,
)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AIChatRequest(BaseModel):
    message: str
    history: List[ChatTurn] = Field(default_factory=list)


class AIChatResponse(BaseModel):
    response: str


def _contains_banned_phrase(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in BANNED_PHRASES)


def detect_language(text: str) -> str | None:
    """Best-effort 'fr' / 'en' guess for the user's latest message; None when unclear."""
    french = len(_FRENCH_HINTS.findall(text))
    english = len(_ENGLISH_HINTS.findall(text))
    if french > english:
        return "fr"
    if english > french:
        return "en"
    return None


def build_contents(message: str, history: List[ChatTurn]) -> list:
    """Last MAX_HISTORY_MESSAGES turns (non-empty, trimmed) followed by the new user message."""
    turns = [t for t in history if t.content.strip()][-MAX_HISTORY_MESSAGES:]
    contents = [
        types.Content(
            role="user" if t.role == "user" else "model",
            parts=[types.Part(text=t.content.strip()[:MAX_MESSAGE_CHARS])],
        )
        for t in turns
    ]
    contents.append(types.Content(role="user", parts=[types.Part(text=message.strip()[:MAX_MESSAGE_CHARS])]))
    return contents


def build_system_instruction(message: str) -> str:
    language = detect_language(message)
    if language == "fr":
        return SYSTEM_PROMPT + "\nThe user's latest message is in French: answer entirely in French."
    if language == "en":
        return SYSTEM_PROMPT + "\nThe user's latest message is in English: answer entirely in English."
    return SYSTEM_PROMPT


def _call_gemini(message: str, history: List[ChatTurn]) -> str:
    system = build_system_instruction(message)
    contents = build_contents(message, history)
    text = ""
    for attempt in range(3):
        resp = _gemini_generate(contents, system_instruction=system, temperature=0.5)
        text = (resp.text or "").strip()
        if not _contains_banned_phrase(text):
            return text
        logger.warning("Banned phrase in response (attempt %d), retrying", attempt + 1)
        system += (
            "\n\nIMPORTANT: Answer DIRECTLY. Do NOT say 'great question', "
            "'more context', or ask for clarification. Give the answer now."
        )
    return text


_UNAVAILABLE = "Je suis désolé, le service est temporairement indisponible. / Sorry, the service is temporarily unavailable. Please try again in a moment."


@router.post("/api/ai/chat", response_model=AIChatResponse)
def ai_chat(payload: AIChatRequest) -> AIChatResponse:
    if not payload.message.strip():
        return AIChatResponse(response="Please type a question.")
    try:
        return AIChatResponse(response=_call_gemini(payload.message, payload.history))
    except Exception as exc:
        logger.error("AI chat error: %s", exc)
        return AIChatResponse(response=_UNAVAILABLE)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/api/ai/chat/stream")
def ai_chat_stream(payload: AIChatRequest) -> StreamingResponse:
    """Server-Sent Events streaming endpoint — tokens appear as they are generated."""

    def _generate():
        if not payload.message.strip():
            yield _sse({"token": "Please type a question."})
            yield "data: [DONE]\n\n"
            return
        try:
            stream = _gemini_generate(
                build_contents(payload.message, payload.history),
                stream=True,
                system_instruction=build_system_instruction(payload.message),
                temperature=0.5,
            )
            for chunk in stream:
                token = getattr(chunk, "text", None)
                if token:
                    yield _sse({"token": token})
        except Exception as exc:
            logger.error("AI chat stream error: %s", exc)
            yield _sse({"error": _UNAVAILABLE})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
