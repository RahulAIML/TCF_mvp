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


def split_into_turns(samples: np.ndarray, turn_count: int, rate: int = 24000) -> list[np.ndarray]:
    """Cut the file at the longest silences so there is one piece per synthesised turn.

    A sentence can contain a short stop. The pause we insert between speakers is longer, so the
    longest gaps are the turn boundaries even when a turn itself is not one continuous phrase.
    """
    if turn_count < 2:
        return [samples]
    frame = int(rate * 0.02)
    rms = np.array([
        np.sqrt(np.mean(samples[i:i + frame] ** 2))
        for i in range(0, max(frame, len(samples) - frame), frame)
    ])
    speech = float(np.percentile(rms, 75)) if len(rms) else 0.0
    quiet = rms < max(0.012, speech * 0.25)
    runs: list[tuple[int, int]] = []
    i = 0
    while i < len(quiet):
        if not quiet[i]:
            i += 1
            continue
        j = i
        while j < len(quiet) and quiet[j]:
            j += 1
        # Ignore the fade at the very start and the tail after the last word.
        if j - i >= 8 and i > 2 and j < len(quiet) - 2:
            runs.append((j - i, i))
        i = j
    runs.sort(reverse=True)
    chosen = sorted(runs[:turn_count - 1], key=lambda run: run[1])
    if len(chosen) < turn_count - 1:
        raise ValueError(f"only {len(chosen)} pauses for {turn_count} turns")
    cuts = [((start + length // 2) * frame) for length, start in chosen]
    bounds = [0, *cuts, len(samples)]
    pieces = [samples[bounds[k]:bounds[k + 1]] for k in range(turn_count)]
    if any(len(piece) < int(rate * 0.25) for piece in pieces):
        raise ValueError(f"a turn was too short after splitting {turn_count} turns")
    return pieces


def sides_for_speakers(samples: np.ndarray, turns: list[dict], rate: int = 24000) -> tuple[np.ndarray, np.ndarray]:
    """One waveform per speaker. A mid-file cut mixes both people when a dialogue has more than two turns."""
    speakers = [str(turn.get("speaker") or turn.get("voice_id") or index) for index, turn in enumerate(turns)]
    if len(set(speakers)) < 2:
        raise ValueError("the file does not name two speakers")
    pieces = split_into_turns(samples, len(speakers), rate)
    grouped: dict[str, list[np.ndarray]] = {}
    for piece, speaker in zip(pieces, speakers):
        grouped.setdefault(speaker, []).append(piece)
    names = list(grouped)
    return np.concatenate(grouped[names[0]]), np.concatenate(grouped[names[1]])


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
