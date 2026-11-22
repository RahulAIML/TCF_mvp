"""
TTS Service — voice registry, generation, and file persistence.

Provider chain: Gemini TTS first, ElevenLabs as the fallback; every file is an MP3.
Languages: French, English, Spanish, Portuguese (see LANGUAGES / VOICE_REGISTRY).
"""

import io
import logging
import os
import threading
import time
import uuid
import wave
from typing import TypedDict

import requests
from dotenv import load_dotenv

import audio_clean

load_dotenv()

logger = logging.getLogger("tts_service")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
_ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
_ELEVENLABS_OUTPUT_FORMAT = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_22050_32")

_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
_GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")

AUDIO_STORAGE_PATH = os.getenv("AUDIO_STORAGE_PATH", "data/audio")

MAX_TEXT_LENGTH = 10000  # characters — caps ElevenLabs cost per request

# ---------------------------------------------------------------------------
# Languages and voice registry
# ---------------------------------------------------------------------------
# Four languages are supported: French, English, Spanish and Portuguese.
# Both providers use multilingual voices (ElevenLabs eleven_multilingual_v2 and
# Gemini prebuilt voices speak the language of the text they are given), so each
# language gets the same four voices (2 male, 2 female). A voice id is
# "<locale>-<gender>-<n>", e.g. "es-ES-female-1". The French ids are unchanged.
# To add a voice: add a row to _BASE_VOICES (every language gets it) and, to
# add a language, a row to LANGUAGES. Set active=False to hide one.
# Each voice has its own env var so it never collides with the existing
# ELEVENLABS_VOICE_ID_FR used by the pronunciation/vocabulary modules.

class VoiceConfig(TypedDict):
    id: str
    label: str
    language: str
    gender: str
    active: bool
    elevenlabs_voice_id: str
    gemini_voice_name: str


# code -> (locale used in voice ids, name shown to people)
LANGUAGES: dict[str, tuple[str, str]] = {
    "fr": ("fr-FR", "French"),
    "en": ("en-US", "English"),
    "es": ("es-ES", "Spanish"),
    "pt": ("pt-BR", "Portuguese"),
}
DEFAULT_LANGUAGE = "fr"

# (gender, number, env var, default ElevenLabs voice id, Gemini voice name)
_BASE_VOICES: list[tuple[str, int, str, str, str]] = [
    # pNInz6obpgDQGcFmaJgB = Adam (male)
    ("male", 1, "ELEVENLABS_VOICE_ID_TTS_M1", "pNInz6obpgDQGcFmaJgB", "Fenrir"),
    # ErXwobaYiN019PkySvjV = Antoni (warm male voice)
    ("male", 2, "ELEVENLABS_VOICE_ID_TTS_M2", "ErXwobaYiN019PkySvjV", "Puck"),
    # 21m00Tcm4TlvDq8ikWAM = Rachel (clear, natural female)
    ("female", 1, "ELEVENLABS_VOICE_ID_TTS_F1", "21m00Tcm4TlvDq8ikWAM", "Aoede"),
    # AZnzlk1XvdvUeBnXmlld = Domi (strong, expressive female)
    ("female", 2, "ELEVENLABS_VOICE_ID_TTS_F2", "AZnzlk1XvdvUeBnXmlld", "Leda"),
]


def _build_registry() -> dict[str, VoiceConfig]:
    registry: dict[str, VoiceConfig] = {}
    for code, (locale, language_name) in LANGUAGES.items():
        for gender, number, env_var, el_default, gemini_name in _BASE_VOICES:
            voice_id = f"{locale}-{gender}-{number}"
            suffix = "" if number == 1 else f" {number}"
            registry[voice_id] = {
                "id": voice_id,
                "label": f"{language_name} {gender.capitalize()}{suffix}",
                "language": code,
                "gender": gender,
                "active": True,
                "elevenlabs_voice_id": os.getenv(env_var, el_default),
                "gemini_voice_name": gemini_name,
            }
    return registry


VOICE_REGISTRY: dict[str, VoiceConfig] = _build_registry()


def normalize_language(language: str | None) -> str | None:
    """'fr', 'FR', 'fr-FR', 'French', 'français' ... -> 'fr'; None if it is not a supported language."""
    if not language or not str(language).strip():
        return None
    raw = str(language).strip().lower().replace("_", "-")
    if raw in LANGUAGES:
        return raw
    primary = raw.split("-")[0]
    if primary in LANGUAGES:
        return primary
    names = {
        "french": "fr", "francais": "fr", "français": "fr",
        "english": "en", "anglais": "en", "inglés": "en", "ingles": "en", "inglês": "en", "ingles": "en",
        "spanish": "es", "espanol": "es", "español": "es", "espagnol": "es", "espanhol": "es",
        "portuguese": "pt", "portugues": "pt", "português": "pt", "portugais": "pt",
    }
    return names.get(raw)


def list_languages() -> list[dict]:
    return [
        {"code": code, "locale": locale, "name": name, "voices": len(list_active_voices(code))}
        for code, (locale, name) in LANGUAGES.items()
        if list_active_voices(code)
    ]


def list_active_voices(language: str | None = None) -> list[dict]:
    wanted = normalize_language(language) if language else None
    if language and wanted is None:
        return []
    return [
        {"id": v["id"], "label": v["label"], "language": v["language"], "gender": v["gender"]}
        for v in VOICE_REGISTRY.values()
        if v["active"] and (wanted is None or v["language"] == wanted)
    ]


def get_voice(voice_id: str) -> VoiceConfig:
    voice = VOICE_REGISTRY.get(voice_id)
    if not voice or not voice["active"]:
        raise ValueError(f"Unknown or inactive voice: {voice_id!r}")
    return voice


def resolve_voice(language: str | None = None, voice_id: str | None = None, gender: str | None = None) -> VoiceConfig:
    """
    The voice to use for a request that names a language, a voice, or both.
    - voice only: that voice (its language is the voice's language);
    - language only: the first active voice of that language (the requested gender first, if given);
    - both: the voice, which must belong to that language.
    Raises ValueError with a message that says what IS available.
    """
    lang = normalize_language(language) if language else None
    if language and lang is None:
        supported = ", ".join(f"{c} ({n})" for c, (_l, n) in LANGUAGES.items())
        raise ValueError(f"Unsupported language {language!r}. Supported: {supported}.")

    if voice_id:
        voice = VOICE_REGISTRY.get(voice_id)
        if not voice or not voice["active"]:
            options = ", ".join(v["id"] for v in list_active_voices(lang))
            raise ValueError(f"Unknown voice {voice_id!r}. Available{' for ' + lang if lang else ''}: {options}.")
        if lang and voice["language"] != lang:
            options = ", ".join(v["id"] for v in list_active_voices(lang))
            raise ValueError(f"Voice {voice_id!r} is a {voice['language']} voice, not {lang}. Voices for {lang}: {options}.")
        return voice

    lang = lang or DEFAULT_LANGUAGE
    candidates = [v for v in VOICE_REGISTRY.values() if v["active"] and v["language"] == lang]
    if gender:
        g = str(gender).strip().lower()
        if g not in ("male", "female"):
            raise ValueError("gender must be 'male' or 'female'.")
        preferred = [v for v in candidates if v["gender"] == g]
        candidates = preferred or candidates
    if not candidates:
        raise ValueError(f"No voice is available for language {lang!r}.")
    return candidates[0]


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

_SESSION = requests.Session()

GEMINI_SAMPLE_RATE = 24000  # Gemini TTS returns 16-bit mono PCM at 24 kHz

# ElevenLabs rejects requests above the plan's concurrency limit (HTTP 429), so every caller shares this cap.
ELEVENLABS_SLOTS = threading.BoundedSemaphore(max(1, int(os.getenv("ELEVENLABS_MAX_CONCURRENCY", "4"))))


def elevenlabs_post(url: str, headers: dict, payload: dict, timeout) -> requests.Response:
    """POST to ElevenLabs within the shared concurrency cap, retrying 429/5xx with backoff."""
    delay = 1.0
    for attempt in range(4):
        with ELEVENLABS_SLOTS:
            resp = _SESSION.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 429 and resp.status_code < 500:
            resp.raise_for_status()
            return resp
        if attempt == 3:
            resp.raise_for_status()
        logger.warning("ElevenLabs HTTP %s, retrying in %.0fs", resp.status_code, delay)
        time.sleep(delay)
        delay *= 2
    raise RuntimeError("unreachable")


class AudioResult(TypedDict):
    data: bytes
    extension: str   # "mp3" (or "wav" only if no MP3 encoder is installed)
    mime_type: str
    provider: str


def polish_mp3(mp3: bytes) -> bytes:
    """
    Decode an MP3, strip a full-scale noise burst at either end, fade, and encode again.
    The burst is in the provider's audio (and sometimes survives the first encode). Re-encoding
    after the PCM cleaner is what makes the file the learner hears end in silence.
    If ffmpeg is missing or fails, the original bytes are returned.
    """
    if not mp3 or not audio_clean.enabled():
        return mp3
    import shutil
    import subprocess
    import tempfile
    if shutil.which("ffmpeg") is None:
        return mp3
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.mp3")
            pcm_path = os.path.join(tmp, "in.pcm")
            out = os.path.join(tmp, "out.mp3")
            with open(src, "wb") as handle:
                handle.write(mp3)
            decoded = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", src, "-f", "s16le", "-ac", "1", "-ar", str(GEMINI_SAMPLE_RATE), pcm_path],
                check=False, capture_output=True,
            )
            if decoded.returncode != 0 or not os.path.exists(pcm_path):
                return mp3
            with open(pcm_path, "rb") as handle:
                pcm = handle.read()
            cleaned, _report = audio_clean.clean_pcm(pcm, GEMINI_SAMPLE_RATE)
            with open(pcm_path, "wb") as handle:
                handle.write(cleaned)
            encoded = subprocess.run(
                ["ffmpeg", "-v", "error", "-f", "s16le", "-ar", str(GEMINI_SAMPLE_RATE), "-ac", "1",
                 "-i", pcm_path, "-codec:a", "libmp3lame", "-b:a", "64k", "-y", out],
                check=False, capture_output=True,
            )
            if encoded.returncode != 0 or not os.path.exists(out):
                return mp3
            with open(out, "rb") as handle:
                return handle.read() or mp3
    except Exception as exc:
        logger.warning("MP3 polish skipped: %s", exc)
        return mp3


def _pcm_to_mp3(pcm_bytes: bytes) -> bytes | None:
    """Encode Gemini's raw PCM as MP3 so every file the platform produces is a real MP3. None if no encoder."""
    try:
        import lameenc
    except ImportError:
        logger.warning("lameenc is not installed: Gemini audio will be saved as WAV, not MP3.")
        return None
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(64)
    encoder.set_in_sample_rate(GEMINI_SAMPLE_RATE)
    encoder.set_channels(1)
    encoder.set_quality(2)
    return bytes(encoder.encode(pcm_bytes)) + bytes(encoder.flush())


def _pcm_to_wav(pcm_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(GEMINI_SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def save_audio(result: AudioResult, voice_id: str, *, long_name: bool = False) -> tuple[str, str]:
    """
    Write the audio under AUDIO_STORAGE_PATH. Returns (file_name, url_path), url_path being "/audio/<file_name>".
    long_name=True uses a full 128-bit random name (files shared outside the app, e.g. through the MCP server).
    """
    os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)
    safe_id = voice_id.replace("/", "_")
    token = uuid.uuid4().hex if long_name else uuid.uuid4().hex[:8]
    file_name = f"tts_{safe_id}_{token}.{result['extension']}"
    with open(os.path.join(AUDIO_STORAGE_PATH, file_name), "wb") as f:
        f.write(result["data"])
    return file_name, f"/audio/{file_name}"


def _generate_via_elevenlabs(text: str, voice: VoiceConfig) -> AudioResult:
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
    resp = elevenlabs_post(url, headers, payload, timeout=(5, 120))
    return {"data": polish_mp3(resp.content), "extension": "mp3", "mime_type": "audio/mpeg", "provider": "elevenlabs"}


def _clean_edges(pcm_bytes: bytes, voice_id: str) -> bytes:
    """
    Remove the loud noise burst Gemini can leave right after the last word, and the click at the start, then fade
    both ends (audio_clean.py). Never fails the generation: on any problem the original audio is used.
    """
    if not audio_clean.enabled():
        return pcm_bytes
    try:
        cleaned, report = audio_clean.clean_pcm(pcm_bytes, GEMINI_SAMPLE_RATE)
        if report.changed:
            logger.info(
                "Audio edges cleaned: voice=%s head -%.0f ms (burst %.0f ms), tail -%.0f ms (burst %.0f ms)",
                voice_id, report.trimmed_head_ms, report.burst_head_ms, report.trimmed_tail_ms, report.burst_tail_ms,
            )
        return cleaned
    except Exception as exc:
        logger.warning("Audio cleaning skipped (%s); using the original audio.", exc)
        return pcm_bytes


_GEMINI_TTS_TIMEOUT_MS = int(os.getenv("GEMINI_TTS_TIMEOUT_MS", "60000"))
_gemini_tts_client = None
_gemini_tts_client_lock = threading.Lock()


def _get_gemini_tts_client():
    """Shared client with a request timeout, so a stalled TTS call can never hang a job forever."""
    global _gemini_tts_client
    from google import genai as genai_client
    from google.genai import types
    with _gemini_tts_client_lock:
        if _gemini_tts_client is None or _gemini_tts_client[0] is not genai_client:
            kwargs = {"api_key": _GEMINI_API_KEY}
            http_options_cls = getattr(types, "HttpOptions", None)
            if http_options_cls is not None:
                kwargs["http_options"] = http_options_cls(timeout=_GEMINI_TTS_TIMEOUT_MS)
            _gemini_tts_client = (genai_client, genai_client.Client(**kwargs))
        return _gemini_tts_client[1]


def _generate_via_gemini(text: str, voice: VoiceConfig) -> AudioResult:
    if not _GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not configured.")
    try:
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai package not installed.") from exc

    client = _get_gemini_tts_client()
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
    pcm_bytes = _clean_edges(pcm_bytes, voice["id"])
    mp3 = _pcm_to_mp3(pcm_bytes)
    if mp3:
        return {"data": polish_mp3(mp3), "extension": "mp3", "mime_type": "audio/mpeg", "provider": "gemini"}
    return {"data": _pcm_to_wav(pcm_bytes), "extension": "wav", "mime_type": "audio/wav", "provider": "gemini"}


def synthesize_elevenlabs(text: str, voice_id: str) -> AudioResult:
    """
    Generate audio via ElevenLabs only — no Gemini fallback.
    Use for cases where a real human-sounding distinct voice is required (e.g. dialogue TTS).
    """
    text = text.strip()
    if not text:
        raise ValueError("Text must not be empty.")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"Text exceeds maximum length of {MAX_TEXT_LENGTH} characters.")
    return _generate_via_elevenlabs(text, get_voice(voice_id))


def synthesize_gemini(text: str, voice_id: str) -> AudioResult:
    """Generate audio via Gemini only (no ElevenLabs fallback) with the voice's Gemini counterpart."""
    text = text.strip()
    if not text:
        raise ValueError("Text must not be empty.")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"Text exceeds maximum length of {MAX_TEXT_LENGTH} characters.")
    return _generate_via_gemini(text, get_voice(voice_id))


def synthesize(text: str, voice_id: str) -> AudioResult:
    """
    Generate the audio for `text` with the requested voice and return it (nothing is written to disk).
    Raises ValueError for bad input, RuntimeError for provider failure.
    """
    text = text.strip()
    if not text:
        raise ValueError("Text must not be empty.")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"Text exceeds maximum length of {MAX_TEXT_LENGTH} characters.")

    voice = get_voice(voice_id)

    try:
        return _generate_via_gemini(text, voice)
    except Exception as gemini_err:
        logger.warning("Gemini TTS failed (%s), falling back to ElevenLabs.", gemini_err)
        try:
            return _generate_via_elevenlabs(text, voice)
        except Exception as el_err:
            raise RuntimeError(f"Audio generation failed (Gemini: {gemini_err}; ElevenLabs: {el_err})") from el_err


def generate_tts_audio(text: str, voice_id: str) -> str:
    """
    Generate TTS audio for `text` using the requested voice.
    Returns the audio URL (e.g. /audio/tts_fr-FR-male-1_abc123.mp3).
    Raises ValueError for bad input, RuntimeError for provider failure.
    """
    result = synthesize(text, voice_id)
    return save_audio(result, voice_id)[1]
