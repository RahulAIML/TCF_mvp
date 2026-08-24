"""
TTS Service — voice registry, generation, and file persistence.

Provider chain: ElevenLabs (primary) → Gemini TTS (fallback).
Add new voices by extending VOICE_REGISTRY; set active=True to expose them.
"""

import io
import logging
import os
import uuid
import wave
from typing import TypedDict

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("tts_service")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
_ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
_ELEVENLABS_OUTPUT_FORMAT = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_22050_32")

_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
_GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")

AUDIO_STORAGE_PATH = os.getenv("AUDIO_STORAGE_PATH", "data/audio")

MAX_TEXT_LENGTH = 2000  # characters — caps ElevenLabs cost per request

# ---------------------------------------------------------------------------
# Voice registry
# ---------------------------------------------------------------------------
# To add a new voice: append an entry and set active=True.
# "elevenlabs_voice_id" uses env var so it can be overridden per-deployment.

class VoiceConfig(TypedDict):
    id: str
    label: str
    language: str
    gender: str
    active: bool
    elevenlabs_voice_id: str
    gemini_voice_name: str


VOICE_REGISTRY: dict[str, VoiceConfig] = {
    # ── Active ────────────────────────────────────────────────────────────
    "fr-FR-male-1": {
        "id": "fr-FR-male-1",
        "label": "French Male",
        "language": "fr",
        "gender": "male",
        "active": True,
        "elevenlabs_voice_id": os.getenv("ELEVENLABS_VOICE_ID_FR", "EXAVITQu4vr4xnSDxMaL"),
        "gemini_voice_name": "Kore",
    },
    # ── Additional voices — set ELEVENLABS_VOICE_ID_FR_* to override ────
    # Falls back to Gemini TTS when the env var is not set.
    "fr-FR-male-2": {
        "id": "fr-FR-male-2",
        "label": "French Male 2",
        "language": "fr",
        "gender": "male",
        "active": True,
        "elevenlabs_voice_id": os.getenv("ELEVENLABS_VOICE_ID_FR_M2", ""),
        "gemini_voice_name": "Fenrir",
    },
    "fr-FR-female-1": {
        "id": "fr-FR-female-1",
        "label": "French Female",
        "language": "fr",
        "gender": "female",
        "active": True,
        "elevenlabs_voice_id": os.getenv("ELEVENLABS_VOICE_ID_FR_F1", ""),
        "gemini_voice_name": "Aoede",
    },
    "fr-FR-female-2": {
        "id": "fr-FR-female-2",
        "label": "French Female 2",
        "language": "fr",
        "gender": "female",
        "active": True,
        "elevenlabs_voice_id": os.getenv("ELEVENLABS_VOICE_ID_FR_F2", ""),
        "gemini_voice_name": "Leda",
    },
}


def list_active_voices() -> list[dict]:
    return [
        {"id": v["id"], "label": v["label"], "language": v["language"], "gender": v["gender"]}
        for v in VOICE_REGISTRY.values()
        if v["active"]
    ]


def get_voice(voice_id: str) -> VoiceConfig:
    voice = VOICE_REGISTRY.get(voice_id)
    if not voice or not voice["active"]:
        raise ValueError(f"Unknown or inactive voice: {voice_id!r}")
    return voice


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

_SESSION = requests.Session()


def _save_mp3(audio_bytes: bytes, voice_id: str) -> str:
    os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)
    safe_id = voice_id.replace("/", "_")
    file_name = f"tts_{safe_id}_{uuid.uuid4().hex[:8]}.mp3"
    file_path = os.path.join(AUDIO_STORAGE_PATH, file_name)
    with open(file_path, "wb") as f:
        f.write(audio_bytes)
    return f"/audio/{file_name}"


def _save_wav_as_mp3_named(pcm_bytes: bytes, voice_id: str) -> str:
    """Wrap raw PCM in WAV container and save (Gemini returns PCM)."""
    os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)
    safe_id = voice_id.replace("/", "_")
    file_name = f"tts_{safe_id}_{uuid.uuid4().hex[:8]}.wav"
    file_path = os.path.join(AUDIO_STORAGE_PATH, file_name)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm_bytes)
    with open(file_path, "wb") as f:
        f.write(buf.getvalue())
    return f"/audio/{file_name}"


def _generate_via_elevenlabs(text: str, voice: VoiceConfig) -> str:
    if not _ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not configured.")
    el_voice_id = voice["elevenlabs_voice_id"]
    if not el_voice_id:
        raise RuntimeError(f"No ElevenLabs voice ID configured for {voice['id']!r}.")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{el_voice_id}"
    payload = {
        "text": text,
        "model_id": _ELEVENLABS_MODEL,
        "output_format": _ELEVENLABS_OUTPUT_FORMAT,
    }
    headers = {"xi-api-key": _ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    logger.info("ElevenLabs TTS: voice=%s chars=%s", voice["id"], len(text))
    resp = _SESSION.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return _save_mp3(resp.content, voice["id"])


def _generate_via_gemini(text: str, voice: VoiceConfig) -> str:
    if not _GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not configured.")
    try:
        from google import genai as genai_client
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai package not installed.") from exc

    client = genai_client.Client(api_key=_GEMINI_API_KEY)
    logger.info("Gemini TTS: voice=%s chars=%s", voice["id"], len(text))
    response = client.models.generate_content(
        model=_GEMINI_TTS_MODEL,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice["gemini_voice_name"]
                    )
                )
            ),
        ),
    )
    pcm_bytes = response.candidates[0].content.parts[0].inline_data.data
    return _save_wav_as_mp3_named(pcm_bytes, voice["id"])


def generate_tts_audio(text: str, voice_id: str) -> str:
    """
    Generate TTS audio for `text` using the requested voice.
    Returns the audio URL (e.g. /audio/tts_fr-FR-male-1_abc123.mp3).
    Raises ValueError for bad input, RuntimeError for provider failure.
    """
    text = text.strip()
    if not text:
        raise ValueError("Text must not be empty.")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"Text exceeds maximum length of {MAX_TEXT_LENGTH} characters.")

    voice = get_voice(voice_id)

    try:
        return _generate_via_elevenlabs(text, voice)
    except Exception as el_err:
        logger.warning("ElevenLabs failed (%s), falling back to Gemini TTS.", el_err)

    return _generate_via_gemini(text, voice)
