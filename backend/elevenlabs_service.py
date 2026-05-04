"""
ElevenLabs Service - Text-to-Speech Integration
Generates native pronunciation audio for vocabulary and speaking modules.
"""

import io
import logging
import os
from typing import Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("elevenlabs_service")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID_FR = os.getenv("ELEVENLABS_VOICE_ID_FR", "EXAVITQu4vr4xnSDxMaL")  # French voice
ELEVENLABS_VOICE_ID_EN = os.getenv("ELEVENLABS_VOICE_ID_EN", "21m00Tcm4TlvDq8ikWAM")  # English voice
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
ELEVENLABS_STABILITY = float(os.getenv("ELEVENLABS_STABILITY", "0.5"))
ELEVENLABS_SIMILARITY_BOOST = float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.75"))


class ElevenLabsService:
    """ElevenLabs text-to-speech service for pronunciation"""

    BASE_URL = "https://api.elevenlabs.io/v1"

    @staticmethod
    def get_voice_id(language: str = "fr") -> str:
        """Get appropriate voice ID for language"""
        if language.lower() in ["en", "english"]:
            return ELEVENLABS_VOICE_ID_EN
        return ELEVENLABS_VOICE_ID_FR

    @staticmethod
    def generate_speech(
        text: str,
        language: str = "fr",
        output_format: str = "mp3"
    ) -> Tuple[bytes, str]:
        """
        Generate speech audio from text.

        Args:
            text: Text to convert to speech
            language: Language code (fr, en)
            output_format: Audio format (mp3, wav, pcm)

        Returns:
            (audio_bytes, mime_type)
        """
        try:
            voice_id = ElevenLabsService.get_voice_id(language)

            url = f"{ElevenLabsService.BASE_URL}/text-to-speech/{voice_id}"

            headers = {
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
            }

            data = {
                "text": text,
                "model_id": ELEVENLABS_MODEL,
                "voice_settings": {
                    "stability": ELEVENLABS_STABILITY,
                    "similarity_boost": ELEVENLABS_SIMILARITY_BOOST,
                    "use_speaker_boost": True,
                },
            }

            response = requests.post(url, json=data, headers=headers)
            response.raise_for_status()

            audio_bytes = response.content
            mime_type = "audio/mpeg" if output_format == "mp3" else f"audio/{output_format}"

            return audio_bytes, mime_type
        except requests.exceptions.RequestException as e:
            logger.error(f"ElevenLabs API error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Speech generation failed: {str(e)}")
            raise

    @staticmethod
    def generate_pronunciation_guide(
        word: str,
        language: str = "fr"
    ) -> Optional[bytes]:
        """
        Generate native pronunciation audio for a word.

        Args:
            word: Word to pronounce
            language: Language code

        Returns:
            Audio bytes or None on error
        """
        try:
            audio_bytes, _ = ElevenLabsService.generate_speech(
                word,
                language=language,
                output_format="mp3"
            )
            return audio_bytes
        except Exception as e:
            logger.error(f"Failed to generate pronunciation guide for '{word}': {str(e)}")
            return None

    @staticmethod
    def generate_sentence_audio(
        sentence: str,
        language: str = "fr"
    ) -> Optional[bytes]:
        """
        Generate audio for full sentence.

        Args:
            sentence: Sentence to convert to speech
            language: Language code

        Returns:
            Audio bytes or None on error
        """
        try:
            audio_bytes, _ = ElevenLabsService.generate_speech(
                sentence,
                language=language,
                output_format="mp3"
            )
            return audio_bytes
        except Exception as e:
            logger.error(f"Failed to generate sentence audio: {str(e)}")
            return None

    @staticmethod
    def stream_speech(
        text: str,
        language: str = "fr"
    ) -> Optional[requests.Response]:
        """
        Stream speech audio (for real-time playback).

        Args:
            text: Text to convert
            language: Language code

        Returns:
            Streaming response or None on error
        """
        try:
            voice_id = ElevenLabsService.get_voice_id(language)

            url = f"{ElevenLabsService.BASE_URL}/text-to-speech/{voice_id}/stream"

            headers = {
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
            }

            data = {
                "text": text,
                "model_id": ELEVENLABS_MODEL,
                "voice_settings": {
                    "stability": ELEVENLABS_STABILITY,
                    "similarity_boost": ELEVENLABS_SIMILARITY_BOOST,
                },
            }

            response = requests.post(
                url,
                json=data,
                headers=headers,
                stream=True
            )
            response.raise_for_status()

            return response
        except Exception as e:
            logger.error(f"Speech streaming failed: {str(e)}")
            return None


# Export service instance
elevenlabs_service = ElevenLabsService()
