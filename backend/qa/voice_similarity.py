"""Compare the two speakers in a live listening dialogue.

Splits the MP3 on the silence we insert between turns, embeds each side, and prints the cosine
similarity. Same-speaker pairs on this encoder usually sit above 0.80; clearly different voices sit lower.

    python -m qa.voice_similarity https://tcf-mvp.onrender.com --count 30

Exits 1 if the median similarity is above --fail-at (default 0.80).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

import numpy as np

FAIL_AT = 0.80


def _post(base: str, path: str, body: dict, timeout: float = 120) -> dict:
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Learner-Id": "voice-qa-learner-1111"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode())


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def _decode(mp3: bytes, rate: int = 24000) -> np.ndarray:
    import miniaudio
    decoded = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=rate)
    return np.frombuffer(decoded.samples, dtype="<i2").astype(np.float32) / 32768.0


def speech_segments(samples: np.ndarray, rate: int = 24000) -> list[np.ndarray]:
    """Pieces of speech separated by the pause between turns.

    The inserted pause is 650 ms, so a real turn gap is longer than a stop inside a sentence.
    """
    frame = int(rate * 0.02)
    if len(samples) < frame * 10:
        return [samples]
    rms = np.array([
        np.sqrt(np.mean(samples[i:i + frame] ** 2))
        for i in range(0, len(samples) - frame, frame)
    ])
    speech = float(np.percentile(rms, 75))
    quiet = rms < max(0.015, speech * 0.22)
    gap_frames = 20  # 0.40 s
    segments: list[np.ndarray] = []
    start = 0
    i = 0
    while i < len(quiet):
        if not quiet[i]:
            i += 1
            continue
        j = i
        while j < len(quiet) and quiet[j]:
            j += 1
        if j - i >= gap_frames and i > start:
            piece = samples[start * frame:i * frame]
            if len(piece) > int(rate * 0.55):
                segments.append(piece)
            start = j
        i = j
    tail = samples[start * frame:]
    if len(tail) > int(rate * 0.55):
        segments.append(tail)
    return segments or [samples]


def sides_for_speakers(samples: np.ndarray, turns: list[dict], rate: int = 24000) -> tuple[np.ndarray, np.ndarray]:
    """One waveform per speaker. A mid-file cut mixes both people when a dialogue has more than two turns."""
    segments = speech_segments(samples, rate)
    speakers = [turn.get("speaker") or turn.get("voice_id") or str(index) for index, turn in enumerate(turns)]
    if len(segments) == len(speakers) and len(set(speakers)) >= 2:
        grouped: dict[str, list[np.ndarray]] = {}
        for segment, speaker in zip(segments, speakers):
            grouped.setdefault(str(speaker), []).append(segment)
        names = list(grouped)
        return np.concatenate(grouped[names[0]]), np.concatenate(grouped[names[1]])
    # Only trust a score when each turn was separated. Averaging leftover pieces makes two different
    # voices look like one person.
    raise ValueError(f"could not isolate the two speakers ({len(segments)} segments for {len(speakers) or 'unknown'} turns)")


def _encoder():
    from resemblyzer import VoiceEncoder
    return VoiceEncoder()


def embed(encoder, samples: np.ndarray, rate: int = 24000) -> np.ndarray:
    # resemblyzer expects 16 kHz float audio.
    if rate != 16000:
        duration = len(samples) / rate
        target = int(duration * 16000)
        samples = np.interp(np.linspace(0, len(samples) - 1, target), np.arange(len(samples)), samples).astype(np.float32)
    return encoder.embed_utterance(samples)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", nargs="?", default="https://tcf-mvp.onrender.com")
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--fail-at", type=float, default=FAIL_AT)
    args = parser.parse_args()
    encoder = _encoder()
    levels = ["A1", "A2", "B1", "B2", "C1", "C2"]
    same_gender = [
        ("Antoine", "Simon", "male"),
        ("Marie", "Sophie", "female"),
        ("François", "Paul", "male"),
        ("Claire", "Léa", "female"),
    ]
    rows = []
    for i in range(args.count):
        level = levels[i % len(levels)]
        number = {"A1": 2, "A2": 7, "B1": 15, "B2": 24, "C1": 32, "C2": 37}[level]
        speakers: list[str] = []
        script = ""
        try:
            question = _post(args.base, "/tcf/generate-listening-question", {
                "question_number": number, "target_level": level, "defer_audio": True,
                "session_id": f"voice-qa-{i}",
            })
            speakers = question.get("speakers") or []
            script = question.get("script") or ""
        except Exception as error:
            print(f"{i:02d} {level} QUESTION FAIL {error}", flush=True)
        if len(speakers) < 2:
            a, b, _kind = same_gender[i % len(same_gender)]
            speakers = [a, b]
            script = (
                f"{a} : Bonjour, c'est l'appel numéro {i}, comment allez-vous aujourd'hui à Montréal ?\n"
                f"{b} : Très bien merci, je vais prendre le métro vers le centre-ville à {8 + (i % 5)} heures."
            )
            print(f"{i:02d} {level} crafted {speakers}", flush=True)
        try:
            audio = _post(args.base, "/tcf/generate-listening-audio", {
                "script": script, "speakers": speakers,
            })
            raw = _get(args.base.rstrip("/") + audio["audio_url"])
            left, right = sides_for_speakers(_decode(raw), audio.get("voices") or [])
            score = cosine(embed(encoder, left), embed(encoder, right))
        except Exception as error:
            print(f"{i:02d} {level} AUDIO FAIL {error}")
            continue
        heard = ",".join(
            f"{turn.get('speaker')}:{turn.get('provider_voice')}@{turn.get('pitch_semitones')}"
            for turn in (audio.get("voices") or [])
        )
        print(f"{i:02d} {level} speakers={speakers} voices={heard} similarity={score:.3f}", flush=True)
        rows.append((level, speakers, score))
    if not rows:
        print("no dialogues measured")
        return 1
    values = [row[2] for row in rows]
    median = float(np.median(values))
    print(f"\n{len(rows)} dialogues  median={median:.3f}  max={max(values):.3f}  fail-at={args.fail_at}")
    high = [row for row in rows if row[2] > args.fail_at]
    for level, speakers, score in high:
        print(f"  HIGH {level} {speakers} {score:.3f}")
    return 1 if median > args.fail_at else 0


if __name__ == "__main__":
    sys.exit(main())
