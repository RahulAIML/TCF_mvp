"""
Gemini Service - Centralized AI Processing
Handles transcription, pronunciation evaluation, vocabulary generation, and speaking evaluation.
"""

import base64
import io
import json
import logging
import os
import random
import wave
from typing import Any, Dict, List, Optional

import requests as _requests
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("gemini_service")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

genai.configure(api_key=GEMINI_API_KEY)


class GeminiService:
    """Centralized Gemini API service for TCF platform"""

    @staticmethod
    def transcribe_speech(audio_path: str, language: str = "fr", mime_type: str = "audio/webm") -> str:
        """
        Transcribe audio file to text using Gemini.

        Args:
            audio_path: Path to audio file
            language: Language code (fr, en)

        Returns:
            Transcribed text
        """
        try:
            with open(audio_path, "rb") as audio_file:
                audio_data = audio_file.read()

            model = genai.GenerativeModel(GEMINI_MODEL)

            prompt = (
                f"Transcribe the following {language.upper()} speech accurately and completely. "
                "Return ONLY the transcribed text, no additional commentary."
            )

            safe_mime = mime_type if mime_type in (
                "audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav"
            ) else "audio/webm"
            response = model.generate_content(
                [
                    prompt,
                    {
                        "mime_type": safe_mime,
                        "data": audio_data,
                    },
                ]
            )

            return response.text.strip()
        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}")
            raise

    @staticmethod
    def evaluate_pronunciation(
        expected_text: str,
        audio_path: str,
        language: str = "fr",
        mime_type: str = "audio/webm",
    ) -> Dict[str, Any]:
        """
        Evaluate pronunciation accuracy using Gemini.

        Args:
            expected_text: The expected/correct text
            audio_path: Path to user's audio recording
            language: Language code (fr, en)

        Returns:
            {
                "accuracy": 0-10,
                "clarity": 0-10,
                "mistakes": [str],
                "feedback": str,
                "improved_version": str
            }
        """
        try:
            # First transcribe the audio
            with open(audio_path, "rb") as audio_file:
                audio_data = audio_file.read()

            model = genai.GenerativeModel(GEMINI_MODEL)

            # Transcribe user's speech (use actual mime type from upload)
            transcribe_prompt = (
                f"Transcribe the following {language.upper()} speech. Return ONLY the text."
            )
            # Normalize mime type to one Gemini accepts
            safe_mime = mime_type if mime_type in (
                "audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav"
            ) else "audio/webm"

            transcribe_response = model.generate_content(
                [
                    transcribe_prompt,
                    {
                        "mime_type": safe_mime,
                        "data": audio_data,
                    },
                ]
            )

            user_text = transcribe_response.text.strip()

            # Evaluate pronunciation
            eval_prompt = f"""You are a strict pronunciation evaluator for {language.upper()}.

Expected text: "{expected_text}"
User said: "{user_text}"

Compare them carefully and return a JSON object with:
- accuracy: 0-10 (how close to expected)
- clarity: 0-10 (how clear is pronunciation)
- mistakes: list of specific mispronounced words or phrases
- feedback: brief explanation of issues
- improved_version: corrected pronunciation guide

Return ONLY valid JSON, no other text.

Rules:
- Be strict on accuracy
- Penalize missing words, wrong words, unclear pronunciation
- Give 0 if completely wrong
- Give 10 only if perfect match"""

            eval_response = model.generate_content(eval_prompt)

            # Parse JSON response
            response_text = eval_response.text.strip()
            # Handle potential markdown code blocks
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            result = json.loads(response_text)
            result["user_text"] = user_text

            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse pronunciation evaluation: {str(e)}")
            return {
                "accuracy": 5,
                "clarity": 5,
                "mistakes": ["Unable to evaluate"],
                "feedback": "Technical error during evaluation",
                "improved_version": expected_text,
                "user_text": ""
            }
        except Exception as e:
            logger.error(f"Pronunciation evaluation failed: {str(e)}")
            raise

    @staticmethod
    def evaluate_speaking(
        transcript: str,
        conversation_context: List[Dict[str, str]],
        task_type: str = "basic_interaction"
    ) -> Dict[str, Any]:
        """
        Evaluate speaking response for TCF exam.

        Args:
            transcript: User's spoken response
            conversation_context: Full conversation history
            task_type: Type of speaking task

        Returns:
            {
                "fluency": 0-10,
                "grammar": 0-10,
                "vocabulary": 0-10,
                "relevance": 0-10,
                "overall_score": 0-10,
                "feedback": [str],
                "should_improve": bool
            }
        """
        try:
            # Build conversation summary
            context_str = ""
            for msg in conversation_context[-6:]:  # Last 3 exchanges
                role = "Examiner" if msg.get("role") == "examiner" else "User"
                context_str += f"{role}: {msg.get('content', '')}\n"

            model = genai.GenerativeModel(GEMINI_MODEL)

            eval_prompt = f"""You are a TCF speaking evaluator. Assess this response:

Task type: {task_type}
Conversation context:
{context_str}

User's response: "{transcript}"

Evaluate on:
1. Fluency (0-10): smooth delivery, natural pacing
2. Grammar (0-10): correct sentence structure, tense usage
3. Vocabulary (0-10): appropriate and varied word choice
4. Relevance (0-10): answers question, stays on topic

Return JSON:
{{
    "fluency": <0-10>,
    "grammar": <0-10>,
    "vocabulary": <0-10>,
    "relevance": <0-10>,
    "overall_score": <0-10>,
    "feedback": ["point1", "point2", "point3"],
    "should_improve": <bool>
}}

Rules:
- Empty response = all scores 0
- Wrong language = low scores
- Irrelevant answer = low relevance
- Return ONLY JSON"""

            response = model.generate_content(eval_prompt)
            response_text = response.text.strip()

            # Handle markdown code blocks
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            result = json.loads(response_text)
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse speaking evaluation: {str(e)}")
            return {
                "fluency": 0,
                "grammar": 0,
                "vocabulary": 0,
                "relevance": 0,
                "overall_score": 0,
                "feedback": ["Evaluation error"],
                "should_improve": True
            }
        except Exception as e:
            logger.error(f"Speaking evaluation failed: {str(e)}")
            raise

    @staticmethod
    def generate_vocabulary(
        level: str = "A2",
        count: int = 5,
        topic: Optional[str] = None,
        language: str = "fr"
    ) -> List[Dict[str, str]]:
        """
        Generate vocabulary words for a given level.

        Args:
            level: CEFR level (A1, A2, B1, B2, C1, C2)
            count: Number of words to generate
            topic: Optional topic (cooking, travel, work, etc.)
            language: Language code (fr, en)

        Returns:
            List of vocab items: [{"word": str, "meaning": str, "example": str, "phonetic": str}]
        """
        try:
            model = genai.GenerativeModel(GEMINI_MODEL)

            topic_str = f" on the topic of '{topic}'" if topic else ""
            seed = random.randint(1000, 9999)

            vocab_prompt = f"""Generate {count} useful {language.upper()} vocabulary words at CEFR level {level}{topic_str}.
Session seed: {seed} — choose a DIFFERENT random selection of words each time.

Return as JSON array:
[
  {{
    "word": "{language.upper()} word or phrase",
    "meaning": "English meaning (clear and concise)",
    "example": "{language.upper()} example sentence using the word",
    "example_translation": "English translation of the example",
    "phonetic": "IPA or simplified pronunciation guide"
  }}
]

Rules:
- {count} words total, all different from each other
- Appropriate for CEFR {level} (not too easy, not too hard)
- Real words actually used by native speakers
- Vary your selection — avoid common textbook words like bonjour, merci, etc.
- Return ONLY the JSON array, no markdown, no extra text"""

            response = model.generate_content(vocab_prompt)
            response_text = response.text.strip()

            # Handle markdown code blocks
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            vocab_list = json.loads(response_text)
            return vocab_list
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse vocabulary generation: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Vocabulary generation failed: {str(e)}")
            raise

    @staticmethod
    def evaluate_ai_response(user_message: str) -> str:
        """
        Generate AI assistant response (already improved with direct answers).

        Args:
            user_message: User's question

        Returns:
            Assistant response
        """
        try:
            model = genai.GenerativeModel(GEMINI_MODEL)

            system_prompt = """You are an expert French language tutor specialized in TCF and TEF exams.

Rules:
1. ALWAYS answer directly - never ask for clarification first
2. For vocabulary: give translation + pronunciation + example
3. For grammar: explain simply with examples
4. For writing: give corrected version + explanation
5. Keep answers short by default, expand only if asked
6. Tone: clear, helpful, teacher-like

Never start with:
- "That's a great question"
- "Can you give more context?"
- "Could you provide more details?"

Always provide direct answers."""

            response = model.generate_content(
                f"{system_prompt}\n\nUser question: {user_message}"
            )

            return response.text.strip()
        except Exception as e:
            logger.error(f"AI response generation failed: {str(e)}")
            return "I encountered an error processing your question. Please try again."


    @staticmethod
    def generate_tts(text: str, language: str = "fr") -> Optional[bytes]:
        """
        Generate TTS audio via Gemini 2.5 Flash TTS preview.
        Returns WAV bytes (PCM wrapped), or None on failure.
        Used as fallback when ElevenLabs is unavailable.
        """
        try:
            lang_label = "French" if language == "fr" else "English"
            url = (
                "https://generativelanguage.googleapis.com/v1beta/"
                f"models/gemini-2.5-flash-preview-tts:generateContent"
                f"?key={GEMINI_API_KEY}"
            )
            payload = {
                "contents": [
                    {"parts": [{"text": f"Say this {lang_label} text clearly and naturally at normal speed: {text}"}]}
                ],
                "generationConfig": {
                    "response_modalities": ["AUDIO"],
                    "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {
                                "voice_name": "Aoede"
                            }
                        }
                    }
                }
            }
            resp = _requests.post(url, json=payload, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            inline = data["candidates"][0]["content"]["parts"][0]["inlineData"]
            pcm_bytes = base64.b64decode(inline["data"])

            # Wrap raw PCM (24 kHz, 16-bit, mono) in a WAV container
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(pcm_bytes)
            return buf.getvalue()
        except Exception as exc:
            logger.error(f"Gemini TTS failed: {exc}")
            return None


# Export service instance for use in routes
gemini_service = GeminiService()
