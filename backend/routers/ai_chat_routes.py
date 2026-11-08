"""
AI Chat Route — powers the FloatingAIAssistant on the frontend.
Single, direct endpoint. No mock responses.
"""

import logging
import os

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("ai_chat")
router = APIRouter()

BANNED_PHRASES = [
    "great question",
    "more context",
    "could you clarify",
    "provide more details",
    "can you give more",
]

SYSTEM_PROMPT = """You are an expert French and English language tutor.

Rules:
- Always answer directly
- Translate immediately when asked
- Explain grammar clearly with examples
- Help with vocabulary and pronunciation
- Do NOT ask for more context unless absolutely necessary
- Assume the most likely intent from the user
- Be concise but useful
- Give examples when helpful

You support:
- translation (French ↔ English)
- grammar explanations
- pronunciation guidance
- vocabulary building
- TCF/TEF exam preparation
- general French and English learning

Examples:
User: "good morning in french"
You: "Good morning in French is Bonjour. Pronunciation: bohn-ZHOOR. Used any time before noon; after that use Bonsoir."

User: "translate temoignant"
You: "Témoignant means showing, demonstrating, or testifying. Example: Il était témoignant de sa loyauté. (He was demonstrating his loyalty.)"

User: "difference between bonjour and salut"
You: "Bonjour is formal/neutral — safe for anyone. Salut is informal — use it with friends. Never use Salut with strangers or in professional settings."

User: "what is passé composé"
You: "Passé composé is the main past tense for completed actions. Structure: avoir/être + past participle. Examples: J'ai mangé (I ate), Elle est partie (She left). Use être with movement verbs: aller, venir, partir, arriver, entrer, sortir, monter, descendre, rester, naître, mourir."
"""


def _contains_banned_phrase(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in BANNED_PHRASES)


class AIChatRequest(BaseModel):
    message: str


class AIChatResponse(BaseModel):
    response: str


def _call_gemini(message: str) -> str:
    import google.generativeai as genai
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    model = genai.GenerativeModel(model_name)
    full_prompt = f"{SYSTEM_PROMPT}\n\nUser: {message}"
    for attempt in range(3):
        resp = model.generate_content(full_prompt)
        text = resp.text.strip()
        if not _contains_banned_phrase(text):
            return text
        logger.warning("Banned phrase in response (attempt %d), retrying", attempt + 1)
        full_prompt += (
            "\n\nIMPORTANT: Answer DIRECTLY. Do NOT say 'great question', "
            "'more context', or ask for clarification. Give the answer now."
        )
    return text  # return last attempt even if it has a banned phrase


@router.post("/api/ai/chat", response_model=AIChatResponse)
async def ai_chat(payload: AIChatRequest) -> AIChatResponse:
    if not payload.message.strip():
        return AIChatResponse(response="Please type a question.")
    try:
        text = _call_gemini(payload.message.strip())
        return AIChatResponse(response=text)
    except Exception as exc:
        logger.error("AI chat error: %s", exc)
        return AIChatResponse(
            response="Je suis désolé, le service est temporairement indisponible. / Sorry, the service is temporarily unavailable. Please try again in a moment."
        )
