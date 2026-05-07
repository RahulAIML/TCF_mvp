"""
AI Chat Route — powers the FloatingAIAssistant on the frontend.
Single, direct endpoint. No mock responses.
"""

import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gemini_service import GeminiService

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


@router.post("/ai/chat", response_model=AIChatResponse)
async def ai_chat(payload: AIChatRequest) -> AIChatResponse:
    """Direct AI assistant — always answers, never asks for more context."""
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    import google.generativeai as genai
    import os

    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    model = genai.GenerativeModel(model_name)

    full_prompt = f"{SYSTEM_PROMPT}\n\nUser: {payload.message.strip()}"

    for attempt in range(3):
        try:
            resp = model.generate_content(full_prompt)
            text = resp.text.strip()

            if _contains_banned_phrase(text):
                logger.warning("AI response contained banned phrase (attempt %d), retrying", attempt + 1)
                full_prompt += (
                    "\n\nIMPORTANT: Answer DIRECTLY. Do NOT say 'great question', "
                    "'more context', or ask for clarification. Give the answer now."
                )
                continue

            return AIChatResponse(response=text)
        except Exception as exc:
            logger.error("AI chat error on attempt %d: %s", attempt + 1, exc)
            if attempt == 2:
                raise HTTPException(status_code=500, detail="AI service error. Please try again.")

    # Fallback if all retries produced banned phrases (rare)
    return AIChatResponse(response="Je ne comprends pas. Pouvez-vous reformuler? / I didn't understand. Could you rephrase?")
