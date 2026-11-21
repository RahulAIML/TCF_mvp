"""Audio format helpers shared by transcription and pronunciation routes."""
from __future__ import annotations

import re

# Formats Gemini accepts for audio input.
GEMINI_AUDIO_MIMES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/aac", "audio/flac"}

_ALIASES = {
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/vnd.wave": "audio/wav",
    "audio/x-m4a": "audio/mp4",
    "audio/m4a": "audio/mp4",
    "video/mp4": "audio/mp4",
    "video/webm": "audio/webm",
    "audio/mp3": "audio/mpeg",
    "audio/x-aac": "audio/aac",
}

_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
}

_FILENAME_MIMES = {ext: mime for mime, ext in _EXTENSIONS.items()}
_FILENAME_MIMES[".m4a"] = "audio/mp4"
_FILENAME_MIMES[".oga"] = "audio/ogg"


def base_mime(content_type: str | None, filename: str | None = None) -> str:
    """
    'audio/mp4;codecs=mp4a.40.2' -> 'audio/mp4'. Unknown or generic types fall back to the
    filename extension, then to audio/webm (what Chrome and Firefox record).
    """
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    mime = _ALIASES.get(mime, mime)
    if mime in GEMINI_AUDIO_MIMES:
        return mime
    if filename:
        match = re.search(r"\.[A-Za-z0-9]+$", filename)
        if match and match.group(0).lower() in _FILENAME_MIMES:
            return _FILENAME_MIMES[match.group(0).lower()]
    return "audio/webm"


def extension_for(mime: str) -> str:
    return _EXTENSIONS.get(base_mime(mime), ".webm")


NO_SPEECH_TOKEN = "<NO_SPEECH>"
NO_SPEECH_MESSAGE = "Aucune parole détectée. Parlez plus près du micro et réessayez."

_NO_SPEECH_RE = re.compile(r"^\W*no[\s_-]*speech\W*$", re.IGNORECASE)


def clean_transcript(raw: str | None) -> str:
    """Map the model's no-speech marker (and blank output) to an empty transcript."""
    text = (raw or "").strip().strip('"').strip()
    if not text or _NO_SPEECH_RE.match(text) or NO_SPEECH_TOKEN.lower() in text.lower():
        return ""
    return text
