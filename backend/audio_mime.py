"""Audio format helpers shared by transcription and pronunciation routes."""
from __future__ import annotations

import array
import io
import re
import shutil
import subprocess
import sys
import wave

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


# ── Voice activity: never send silence to the model (it invents speech from silence) ──

_FRAME_SECONDS = 0.03
_VOICE_FRAME_RMS = 0.02      # ~ -34 dBFS: normal speech frames are well above this
_MIN_VOICE_SECONDS = 0.3


def _voiced_seconds(samples: "array.array", sample_rate: int, full_scale: float) -> float:
    frame = max(1, int(sample_rate * _FRAME_SECONDS))
    voiced = 0
    for start in range(0, len(samples) - frame + 1, frame):
        chunk = samples[start:start + frame]
        rms = (sum(s * s for s in chunk) / frame) ** 0.5 / full_scale
        if rms >= _VOICE_FRAME_RMS:
            voiced += 1
    return voiced * _FRAME_SECONDS


def _pcm16(raw: bytes) -> "array.array":
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def _decode_wav(data: bytes) -> "tuple[array.array, int] | None":
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            if wf.getsampwidth() != 2:
                return None
            channels, rate = wf.getnchannels(), wf.getframerate()
            samples = _pcm16(wf.readframes(wf.getnframes()))
    except (wave.Error, EOFError):
        return None
    if channels > 1:
        samples = samples[::channels]
    return samples, rate


def _decode_with_ffmpeg(data: bytes) -> "tuple[array.array, int] | None":
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        out = subprocess.run(
            [ffmpeg, "-v", "quiet", "-i", "pipe:0", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"],
            input=data, capture_output=True, timeout=15, check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    return _pcm16(out), 16000


def has_speech(data: bytes, mime: str | None) -> bool:
    """
    False only when the recording is decodable and contains under 0.3 s of voice-level audio.
    Undecodable formats return True (unknown), so real speech is never discarded.
    """
    if not data:
        return False
    decoded = _decode_wav(data) if base_mime(mime) == "audio/wav" else None
    if decoded is None:
        decoded = _decode_with_ffmpeg(data)
    if decoded is None:
        return True
    samples, rate = decoded
    return _voiced_seconds(samples, rate, 32768.0) >= _MIN_VOICE_SECONDS
