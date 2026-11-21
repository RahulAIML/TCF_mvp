"""
Gemini Service - transcription, pronunciation evaluation, vocabulary generation and fallback TTS.
"""

import base64
import io
import json
import logging
import os
import random
import re
import wave
from typing import Any, Dict, Iterator, List, Optional

import requests as _requests
from google.genai import types
from dotenv import load_dotenv

from audio_mime import NO_SPEECH_MESSAGE, NO_SPEECH_TOKEN, base_mime, clean_transcript, has_speech
from tcf_ai_service import _gemini_generate

load_dotenv()

logger = logging.getLogger("gemini_service")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")

MAX_VOCAB_COUNT = 20

_LANG_NAMES = {"fr": "French", "en": "English", "es": "Spanish", "pt": "Portuguese"}


def _lang_name(language: str) -> str:
    return _LANG_NAMES.get((language or "fr").split("-")[0].lower(), "French")


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_json(text: str) -> Any:
    cleaned = _strip_code_fence(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
        if not match:
            raise
        return json.loads(match.group(0))


def _clamp_score(value: Any) -> float:
    try:
        return round(max(0.0, min(10.0, float(value))), 1)
    except (TypeError, ValueError):
        return 0.0


def no_speech_pronunciation_result(expected_text: str) -> Dict[str, Any]:
    return {
        "accuracy": 0,
        "clarity": 0,
        "mistakes": [],
        "feedback": NO_SPEECH_MESSAGE,
        "improved_version": expected_text,
        "user_text": "",
        "no_speech": True,
    }


class GeminiService:
    """Gemini calls for the speaking, pronunciation and vocabulary modules."""

    @staticmethod
    def transcribe_bytes(audio_data: bytes, language: str = "fr", mime_type: str = "audio/webm") -> str:
        """Verbatim transcript, or "" when the recording has no intelligible speech."""
        if not audio_data or not has_speech(audio_data, mime_type):
            return ""
        prompt = (
            f"Transcribe the {_lang_name(language)} speech in this recording verbatim.\n"
            f"- If there is no intelligible human speech (silence, background noise, breathing, music, "
            f"a click), reply with exactly {NO_SPEECH_TOKEN} and nothing else.\n"
            "- Never guess, complete or invent words that were not clearly spoken.\n"
            "- Return ONLY the transcribed text, no quotes, no commentary."
        )
        response = _gemini_generate(
            [prompt, types.Part.from_bytes(data=audio_data, mime_type=base_mime(mime_type))],
            temperature=0.0,
        )
        return clean_transcript(getattr(response, "text", "") or "")

    @staticmethod
    def transcribe_speech(audio_path: str, language: str = "fr", mime_type: str = "audio/webm") -> str:
        with open(audio_path, "rb") as audio_file:
            return GeminiService.transcribe_bytes(audio_file.read(), language, mime_type)

    @staticmethod
    def _pronunciation_prompt(expected_text: str, user_text: str, language: str, with_feedback: bool) -> str:
        feedback_field = '  "feedback": "2-3 sentences in English explaining the main issues",\n' if with_feedback else ""
        return f"""You are a strict {_lang_name(language)} pronunciation examiner.

Expected text: "{expected_text}"
What the learner said (speech-to-text): "{user_text}"

Return a JSON object:
{{
  "accuracy": 0-10 (how closely the spoken words match the expected text),
  "clarity": 0-10 (how intelligible the speech was, judged from the transcription quality),
  "mistakes": ["each expected word or phrase that was missing, replaced or mispronounced"],
{feedback_field}  "improved_version": "the expected text with a simple pronunciation guide for the difficult words"
}}

Rules:
- Penalise missing, extra or wrong words. 10 only for a perfect match, 0 if unrelated.
- "mistakes" lists words from the EXPECTED text only; empty list if there are none.
- Valid JSON only."""

    @staticmethod
    def pronunciation_scores(expected_text: str, user_text: str, language: str = "fr", with_feedback: bool = True) -> Dict[str, Any]:
        prompt = GeminiService._pronunciation_prompt(expected_text, user_text, language, with_feedback)
        response = _gemini_generate(prompt, temperature=0.2, response_mime_type="application/json")
        try:
            data = _parse_json(getattr(response, "text", "") or "{}")
        except (json.JSONDecodeError, ValueError) as error:
            raise RuntimeError(f"Pronunciation evaluation returned invalid JSON: {error}") from error
        mistakes = data.get("mistakes") or []
        if isinstance(mistakes, str):
            mistakes = [m.strip() for m in mistakes.split(",") if m.strip()]
        return {
            "accuracy": _clamp_score(data.get("accuracy")),
            "clarity": _clamp_score(data.get("clarity")),
            "mistakes": [str(m).strip() for m in mistakes if str(m).strip()],
            "feedback": str(data.get("feedback", "")).strip(),
            "improved_version": str(data.get("improved_version", "") or expected_text).strip(),
            "user_text": user_text,
            "no_speech": False,
        }

    @staticmethod
    def stream_pronunciation_feedback(expected_text: str, user_text: str, language: str = "fr") -> Iterator[str]:
        prompt = f"""You are a friendly but precise {_lang_name(language)} pronunciation coach.
Expected text: "{expected_text}"
What the learner said (speech-to-text): "{user_text}"

In 2 to 3 short sentences of plain English (no markdown, no lists), tell the learner what they got right,
the most important word(s) to fix and exactly how to pronounce them. If it was a perfect match, say so briefly."""
        for chunk in _gemini_generate(prompt, stream=True, temperature=0.3):
            token = getattr(chunk, "text", None)
            if token:
                yield token

    @staticmethod
    def evaluate_pronunciation(
        expected_text: str,
        audio_path: str,
        language: str = "fr",
        mime_type: str = "audio/webm",
    ) -> Dict[str, Any]:
        user_text = GeminiService.transcribe_speech(audio_path, language, mime_type)
        if not user_text:
            return no_speech_pronunciation_result(expected_text)
        return GeminiService.pronunciation_scores(expected_text, user_text, language, with_feedback=True)

    @staticmethod
    def generate_vocabulary(
        level: str = "A2",
        count: int = 5,
        topic: Optional[str] = None,
        language: str = "fr",
        exclude: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """Generate `count` distinct words at a CEFR level, avoiding the `exclude` words."""
        count = max(1, min(MAX_VOCAB_COUNT, int(count)))
        lang = _lang_name(language)
        topic_str = f" on the topic of '{topic}'" if topic else " across varied everyday and professional topics"
        avoid = ""
        if exclude:
            sample = list(dict.fromkeys(w.strip() for w in exclude if w and w.strip()))[-80:]
            avoid = "\nDo NOT use any of these words (already studied): " + ", ".join(sample)
        prompt = f"""Generate {count} useful {lang} vocabulary items at CEFR level {level}{topic_str}.
Variety seed: {random.randint(10000, 99999)}{avoid}

Return a JSON array:
[
  {{
    "word": "{lang} word or short expression (with article for nouns)",
    "meaning": "English meaning, clear and concise",
    "example": "{lang} example sentence that uses the word naturally",
    "example_translation": "English translation of the example",
    "phonetic": "IPA transcription"
  }}
]

Rules:
- Exactly {count} items, all different from each other.
- Genuinely at CEFR {level}: A1/A2 everyday high-frequency words, B1/B2 common abstract and work vocabulary,
  C1/C2 precise, idiomatic or formal vocabulary that native speakers actually use (no invented or archaic words).
- Avoid trivial textbook words (bonjour, merci, oui, chat, chien) above A1.
- JSON only."""
        response = _gemini_generate(prompt, temperature=0.9, response_mime_type="application/json")
        try:
            data = _parse_json(getattr(response, "text", "") or "[]")
        except (json.JSONDecodeError, ValueError):
            logger.error("Vocabulary generation returned invalid JSON")
            return []
        if isinstance(data, dict):
            data = data.get("words") or data.get("items") or []
        excluded = {w.strip().lower() for w in (exclude or [])}
        seen: set[str] = set()
        items: List[Dict[str, str]] = []
        for raw in data if isinstance(data, list) else []:
            if not isinstance(raw, dict):
                continue
            word = str(raw.get("word", "")).strip()
            key = word.lower()
            if not word or key in seen or key in excluded:
                continue
            seen.add(key)
            items.append({
                "word": word,
                "meaning": str(raw.get("meaning", "")).strip(),
                "example": str(raw.get("example", "")).strip(),
                "example_translation": str(raw.get("example_translation", "") or "").strip() or None,
                "phonetic": str(raw.get("phonetic", "") or "").strip() or None,
            })
        return items[:count]

    @staticmethod
    def generate_tts(text: str, language: str = "fr") -> Optional[bytes]:
        """Gemini TTS fallback for the pronunciation guide. WAV bytes, or None on failure."""
        if not GEMINI_API_KEY:
            return None
        try:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/"
                f"models/{GEMINI_TTS_MODEL}:generateContent"
            )
            payload = {
                "contents": [
                    {"parts": [{"text": f"Say this {_lang_name(language)} text clearly and naturally at normal speed: {text}"}]}
                ],
                "generationConfig": {
                    "response_modalities": ["AUDIO"],
                    "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": "Aoede"}}},
                },
            }
            resp = _requests.post(url, json=payload, headers={"x-goog-api-key": GEMINI_API_KEY}, timeout=20)
            resp.raise_for_status()
            inline = resp.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
            pcm_bytes = base64.b64decode(inline["data"])
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(pcm_bytes)
            return buf.getvalue()
        except Exception as exc:
            logger.error("Gemini TTS failed: %s", exc)
            return None


gemini_service = GeminiService()
