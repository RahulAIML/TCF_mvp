"""
TCF Canada — Compréhension orale (listening) generation.

Level calibration follows the official TCF Canada candidate manual (39 items, increasing difficulty,
each document heard once) — see the research notes in the repository history.
Every question is unique: a global fingerprint history, a near-duplicate check on the script, a recent
theme history per level, and per-session served sets. Ready questions (with their audio) are kept in a
background pool per level so a request is served instantly.
"""
from __future__ import annotations

import logging
import os
import random
import re
import threading
import uuid
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

import answer_balance
import content_bank
import content_dedupe as dedupe
import quality_guard
import topic_bank
import tts_service
from learner import active_learner
from schemas import ListeningQuestionResponse

logger = logging.getLogger("tcf.listening")

LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
LETTERS = ("A", "B", "C", "D")

# Official item order: easiest first. Question number -> CEFR band.
LEVEL_RANGES: Dict[str, Tuple[int, int]] = {
    "A1": (1, 4),
    "A2": (5, 10),
    "B1": (11, 19),
    "B2": (20, 29),
    "C1": (30, 35),
    "C2": (36, 39),
}

LISTENING_SPECS: Dict[str, Dict[str, str]] = {
    "A1": {
        "word_count": "10 à 20 mots (5 à 10 secondes)",
        "words": (8, 30),
        "complexity": (
            "Débit lent. Mots très fréquents (salutations, nombres, heures, prix, lieux, objets du quotidien). "
            "Une seule idée, phrases de 3 à 7 mots, présent uniquement."
        ),
        "answer_difficulty": "repérage d'un mot ou d'une information explicite unique (prix, heure, lieu, objet)",
        "distractors": "les distracteurs diffèrent de la bonne réponse par un seul élément clé (un autre nombre, une autre heure, un autre objet)",
    },
    "A2": {
        "word_count": "30 à 50 mots (15 à 25 secondes)",
        "words": (22, 65),
        "complexity": (
            "Débit lent à modéré. Vocabulaire fréquent de la vie quotidienne. Présent, passé composé, futur proche. "
            "Phrases courtes reliées par et, mais, parce que."
        ),
        "answer_difficulty": "repérage d'une information explicite précise parmi plusieurs détails mentionnés",
        "distractors": "les distracteurs reprennent d'autres détails réellement mentionnés dans le document (autre jour, autre lieu, autre personne)",
    },
    "B1": {
        "word_count": "60 à 90 mots (25 à 40 secondes)",
        "words": (45, 115),
        "complexity": (
            "Débit standard, registre neutre. Situations familières (travail, loisirs, services). "
            "Connecteurs simples, imparfait, conditionnel présent."
        ),
        "answer_difficulty": "idée principale, décision ou intention d'un locuteur, explicitement exprimée",
        "distractors": "les distracteurs sont plausibles mais contredits par un passage précis du document",
    },
    "B2": {
        "word_count": "100 à 140 mots (40 à 60 secondes)",
        "words": (80, 170),
        "complexity": (
            "Débit normal, registre courant à soutenu. Opinions argumentées, quelques expressions idiomatiques, "
            "subjonctif, discours rapporté."
        ),
        "answer_difficulty": "opinion, attitude ou argument d'un locuteur ; cause ou conséquence partiellement reformulée",
        "distractors": "les distracteurs sont partiellement vrais, ou attribuent une idée au mauvais locuteur, ou confondent cause et conséquence",
    },
    "C1": {
        "word_count": "130 à 160 mots (environ 1 minute)",
        "words": (105, 195),
        "complexity": (
            "Débit naturel. Sujets abstraits ou de société. Vocabulaire riche mais naturel, implicite fréquent, "
            "nuances et concessions."
        ),
        "answer_difficulty": "sens implicite, nuance ou intention du locuteur ; raisonnement non formulé littéralement",
        "distractors": "les distracteurs sont des reformulations qui exagèrent, généralisent ou déforment légèrement la pensée du locuteur",
    },
    "C2": {
        "word_count": "150 à 180 mots (60 à 75 secondes)",
        "words": (120, 215),
        "complexity": (
            "Débit naturel rapide, langue authentique (chronique, débat, documentaire). Ironie, sous-entendus, "
            "registre soutenu NATUREL — celui d'un journaliste cultivé à la radio, jamais celui d'une thèse de "
            "philosophie. INTERDIT : jargon académique ou inventé (ex. « herméneutique », « épistémologique », "
            "« aporie », « paradigme », « dialectique », « ontologique », « praxis », « en rupture de ban »)."
        ),
        "answer_difficulty": "ton, ironie, implication ou position réelle de l'auteur",
        "distractors": "les distracteurs sont des paraphrases subtilement inexactes (nuance, degré de certitude ou intention mal rendus)",
    },
}

# (format, is_dialogue). Dialogues are a large share, as in the real exam.
LISTENING_FORMATS: Dict[str, List[Tuple[str, bool]]] = {
    "A1": [
        ("un échange très court entre deux personnes (achat, salutation, direction)", True),
        ("un échange très court entre deux personnes au téléphone (heure, rendez-vous)", True),
        ("une phrase entendue dans une situation simple (magasin, rue, maison)", False),
        ("une annonce très courte d'une seule information", False),
    ],
    "A2": [
        ("un court dialogue dans un commerce ou à un guichet", True),
        ("un message vocal court laissé à un ami ou un collègue", False),
        ("une annonce publique simple (gare, métro, école, magasin)", False),
        ("une conversation simple entre deux voisins", True),
    ],
    "B1": [
        ("un dialogue entre deux amis qui organisent une activité", True),
        ("un message sur répondeur avec des instructions pratiques", False),
        ("une conversation au travail ou dans un service public", True),
        ("une courte émission de radio sur la vie quotidienne au Canada", False),
    ],
    "B2": [
        ("une interview radio d'un professionnel par un journaliste", True),
        ("un auditeur qui donne son avis à l'animateur d'une émission de radio", True),
        ("une conversation téléphonique entre collègues sur un problème", True),
        ("un court reportage d'actualité locale", False),
        ("une discussion entre deux personnes aux avis différents", True),
    ],
    "C1": [
        ("un débat entre deux intervenants sur un enjeu de société", True),
        ("un entretien approfondi d'un expert par un journaliste", True),
        ("une émission culturelle avec un animateur et un invité", True),
        ("un exposé sur un sujet abstrait", False),
    ],
    "C2": [
        ("une chronique radio argumentée ou ironique", False),
        ("un extrait de documentaire", False),
        ("une conférence enregistrée", False),
        ("un débat d'idées entre deux spécialistes", True),
    ],
}

DOMAINS = list(dict.fromkeys([
    "vie quotidienne", "logement", "transports", "travail", "santé", "éducation", "consommation",
    "loisirs et culture", "environnement", "alimentation", "technologie", "vie de quartier",
    "administration et services publics", "voyage", "sport", "immigration et intégration",
] + [d.split(",")[0] for d in topic_bank.DOMAINS]))
PLACES = list(dict.fromkeys(topic_bank.PLACES))

MALE_NAMES = [
    "Marc", "Thomas", "Pierre", "Julien", "Antoine", "Nicolas", "Luc", "Paul", "Simon", "David",
    "Éric", "François", "Gabriel", "Mathieu", "Étienne", "Jean-François", "Sébastien", "Olivier", "Maxime", "Samuel",
]
FEMALE_NAMES = [
    "Sophie", "Isabelle", "Marie", "Claire", "Léa", "Camille", "Emma", "Nathalie", "Julie", "Laura",
    "Sandrine", "Céline", "Geneviève", "Marie-Ève", "Chloé", "Mélanie", "Audrey", "Amélie", "Valérie", "Noémie",
]
_NAME_GENDER = {**{n: "male" for n in MALE_NAMES}, **{n: "female" for n in FEMALE_NAMES}}

VOICES = {
    "male": ["fr-FR-male-1", "fr-FR-male-2"],
    "female": ["fr-FR-female-1", "fr-FR-female-2"],
}

BANNED_WORDS = (
    "herméneutique", "épistémologi", "aporie", "paradigme", "dialectique", "ontologi", "praxis",
    "rupture de ban", "rhodanien", "colloque singulier",
)

POOL_TARGET = int(os.getenv("LISTENING_POOL_TARGET", "5"))
MAX_ATTEMPTS = 4

# ── Speaker labels ──────────────────────────────────────────────────────────────

_NAME_PART = r"(?:[A-ZÀ-ÝÉÈ][a-zà-ÿ'’]+|[A-ZÀ-Ý]{2,})"
# A label may sit at the start of a line OR later on the same line ("François : … Paul : …").
SPEAKER_LABEL_RE = re.compile(
    rf"(?:[-–—]\s*)?({_NAME_PART}(?:[- ]{_NAME_PART})?)\s*(?:\([^)]{{0,40}}\))?\s*:\s*"
)
# Labels that are announcement headings, never people.
_NOT_SPEAKERS = {
    "Attention", "Horaires", "Horaire", "Note", "Remarque", "Information", "Informations", "Rappel", "Adresse",
    "Prix", "Tarif", "Tarifs", "Date", "Lieu", "Objet", "Ouverture", "Fermeture", "Téléphone", "Important",
    "Avis", "Annonce", "Message", "Question", "Réponse", "Exemple", "Bienvenue", "Inscription", "Contact",
}


def _speaker_lines(script: str) -> List[Tuple[Optional[str], str]]:
    """Split a script into (speaker or None, text) pieces. Several labels on one line each become a turn."""
    out: List[Tuple[Optional[str], str]] = []
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        marks = [m for m in SPEAKER_LABEL_RE.finditer(line) if m.group(1) not in _NOT_SPEAKERS]
        if not marks:
            out.append((None, line))
            continue
        if marks[0].start() > 0:
            prefix = line[:marks[0].start()].strip()
            if prefix:
                out.append((None, prefix))
        for index, mark in enumerate(marks):
            end = marks[index + 1].start() if index + 1 < len(marks) else len(line)
            text = line[mark.end():end].strip()
            out.append((mark.group(1), text))
    return out


def detect_speakers(script: str, known: Optional[List[str]] = None) -> List[str]:
    """
    Speaker names in order of appearance, or [] when the script is not a dialogue.
    With `known` names, only those count. Without them, a script is a dialogue only when at least two distinct
    labels exist and labelled lines make up most of the script (so "Horaires : 9 h" in an announcement is not a
    speaker).
    """
    lines = _speaker_lines(script)
    names: List[str] = []
    labelled = 0
    for speaker, _text in lines:
        if speaker and (known is None or speaker in known):
            labelled += 1
            if speaker not in names:
                names.append(speaker)
    if len(names) < 2:
        return []
    if known is None and labelled < 0.6 * len(lines):
        return []
    return names


def _spoken_turn(text: str, speakers: List[str]) -> str:
    """Drop any speaker label that survived inside a turn, so the voice never says the name as a label."""
    cleaned = text
    for name in speakers:
        cleaned = re.sub(rf"(?:^|\s){re.escape(name)}\s*:\s*", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _monologue_text(script: str) -> str:
    """One voice. A lone 'Animateur :' label is not spoken; announcement lines ('Horaires :') are kept."""
    parts: List[str] = []
    for speaker, text in _speaker_lines(script):
        if speaker:
            parts.append(text)
        else:
            parts.append(text)
    return re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()


def dialogue_segments(script: str, speakers: List[str]) -> List[Tuple[Optional[str], str]]:
    """Consecutive (speaker, text) segments. Text before the first label is a narrator segment (speaker None)."""
    segments: List[Tuple[Optional[str], str]] = []
    current: Optional[str] = None
    buf: List[str] = []
    for speaker, text in _speaker_lines(script):
        if speaker in speakers:
            if buf:
                segments.append((current, " ".join(buf)))
            current, buf = speaker, ([text] if text else [])
        else:
            buf.append(text if speaker is None else f"{speaker} : {text}")
    if buf:
        segments.append((current, " ".join(buf)))
    return [(s, t.strip()) for s, t in segments if t.strip()]


def assign_voices(speakers: List[str]) -> Dict[Optional[str], str]:
    """A distinct voice per speaker that matches the name's gender when known; the narrator gets an unused one."""
    pools = {g: random.sample(v, len(v)) for g, v in VOICES.items()}
    all_voices = [v for vs in VOICES.values() for v in vs]
    used: List[str] = []
    mapping: Dict[Optional[str], str] = {}

    def take(gender: Optional[str]) -> str:
        if gender in pools:
            for v in pools[gender]:
                if v not in used:
                    return v
        for v in random.sample(all_voices, len(all_voices)):
            if v not in used:
                return v
        return random.choice(all_voices)

    for name in speakers:
        voice = take(_NAME_GENDER.get(name))
        used.append(voice)
        mapping[name] = voice
    mapping[None] = take(None)
    return mapping


# ── MP3 joining ─────────────────────────────────────────────────────────────────

_MP3_BITRATES = {
    (1, 3): [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    (2, 3): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_MP3_SAMPLE_RATES = {1: [44100, 48000, 32000], 2: [22050, 24000, 16000], 25: [11025, 12000, 8000]}


def _frame_length(header: bytes) -> int:
    if len(header) < 4 or header[0] != 0xFF or (header[1] & 0xE0) != 0xE0:
        return 0
    version_bits = (header[1] >> 3) & 0x3
    layer_bits = (header[1] >> 1) & 0x3
    if layer_bits != 1 or version_bits == 1:  # Layer III only
        return 0
    version = {3: 1, 2: 2, 0: 25}[version_bits]
    bitrate_idx = (header[2] >> 4) & 0xF
    sr_idx = (header[2] >> 2) & 0x3
    if bitrate_idx in (0, 15) or sr_idx == 3:
        return 0
    bitrate = _MP3_BITRATES[(1 if version == 1 else 2, 3)][bitrate_idx] * 1000
    sample_rate = _MP3_SAMPLE_RATES[version][sr_idx]
    padding = (header[2] >> 1) & 0x1
    coefficient = 144 if version == 1 else 72
    return coefficient * bitrate // sample_rate + padding


def strip_mp3_metadata(data: bytes) -> bytes:
    """
    Remove ID3 tags and the Xing/Info/VBRI header frame. Joined segments then form one plain stream whose duration
    browsers compute correctly (a leftover Info frame makes players report only the first segment's length).
    """
    start = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
        start = 10 + size + (10 if data[5] & 0x10 else 0)
    end = len(data) - 128 if len(data) >= 128 and data[-128:-125] == b"TAG" else len(data)
    # Find the first frame sync from `start`.
    i = start
    while i < end - 4 and _frame_length(data[i:i + 4]) == 0:
        i += 1
    if i >= end - 4:
        return data[start:end]
    first_len = _frame_length(data[i:i + 4])
    first_frame = data[i:i + first_len]
    if b"Xing" in first_frame or b"Info" in first_frame or b"VBRI" in first_frame:
        i += first_len
    return data[i:end]


def join_mp3(parts: List[bytes]) -> bytes:
    return b"".join(strip_mp3_metadata(p) for p in parts)


def _mix_turns(parts: List[bytes], pause_ms: int = 280) -> bytes:
    """One MP3: each turn, then a short silence, so the browser plays every voice and the joins do not click.

    Decoding to PCM and encoding once avoids a second MP3 header that some players treat as the end of the file
    (the listener then hears only the first speaker).
    """
    import shutil
    import subprocess
    import tempfile
    if len(parts) == 1:
        return parts[0]
    if shutil.which("ffmpeg") is None:
        return join_mp3(parts)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            pcm_parts: List[bytes] = []
            for index, data in enumerate(parts):
                src = os.path.join(tmp, f"turn{index}.bin")
                pcm_path = os.path.join(tmp, f"turn{index}.pcm")
                with open(src, "wb") as handle:
                    handle.write(data)
                decoded = subprocess.run(
                    ["ffmpeg", "-y", "-v", "error", "-i", src, "-f", "s16le", "-ac", "1", "-ar", "24000", pcm_path],
                    capture_output=True,
                )
                if decoded.returncode != 0 or not os.path.exists(pcm_path):
                    return join_mp3(parts)
                with open(pcm_path, "rb") as handle:
                    pcm_parts.append(handle.read())
            gap = b"\x00\x00" * int(24000 * pause_ms / 1000)
            raw_path = os.path.join(tmp, "all.pcm")
            out_path = os.path.join(tmp, "out.mp3")
            with open(raw_path, "wb") as handle:
                handle.write(gap.join(pcm_parts))
            encoded = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", raw_path,
                 "-codec:a", "libmp3lame", "-b:a", "64k", out_path],
                capture_output=True,
            )
            if encoded.returncode != 0 or not os.path.exists(out_path):
                return join_mp3(parts)
            with open(out_path, "rb") as handle:
                return handle.read()
    except Exception as error:
        logger.warning("Turn mix failed (%s); joining the MP3s directly.", error)
        return join_mp3(parts)


# ── Audio ───────────────────────────────────────────────────────────────────────

def _audio_dir() -> str:
    from tcf_ai_service import AUDIO_STORAGE_PATH
    os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)
    return AUDIO_STORAGE_PATH


def _save(data: bytes, ext: str) -> str:
    file_name = f"tcf_listening_{uuid.uuid4().hex[:12]}.{ext}"
    with open(os.path.join(_audio_dir(), file_name), "wb") as f:
        f.write(data)
    return f"/audio/{file_name}"


def _synthesize_segments(jobs: List[Tuple[str, str]], synth) -> List[Dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=min(3, max(1, len(jobs)))) as pool:
        return list(pool.map(lambda job: synth(job[0], job[1]), jobs))


def synthesize_listening_audio(script: str, speakers: Optional[List[str]] = None) -> str:
    """
    Audio for a listening script. Dialogues: one voice per speaker, synthesised per segment with ElevenLabs; if any
    segment fails, the whole dialogue is redone with Gemini voices of the same genders (providers are never mixed in
    one file — their MP3 sample rates differ). Monologues: one random French voice (Gemini, ElevenLabs fallback).
    """
    names = detect_speakers(script, speakers or None) if speakers else detect_speakers(script)
    if not names:
        voice = random.choice([v for vs in VOICES.values() for v in vs])
        spoken = _monologue_text(script)
        result = tts_service.synthesize(spoken or script, voice)
        return _save(result["data"], result["extension"])

    voices = assign_voices(names)
    segments = dialogue_segments(script, names)
    # Never send the "Name :" label to the synthesizer.
    jobs = [(_spoken_turn(text, names), voices.get(speaker) or voices[None]) for speaker, text in segments]
    jobs = [(text, voice) for text, voice in jobs if text]
    if len({voice for _text, voice in jobs}) < 2 and len(names) >= 2:
        logger.warning("Dialogue voices collapsed to one id: %s", voices)
    try:
        results = _synthesize_segments(jobs, tts_service.synthesize_elevenlabs)
    except Exception as el_error:
        logger.warning("Dialogue ElevenLabs synthesis failed (%s); regenerating with Gemini voices.", el_error)
        results = _synthesize_segments(jobs, tts_service.synthesize_gemini)
    ext = results[0]["extension"]
    if ext == "mp3":
        data = _mix_turns([r["data"] for r in results])
    else:  # WAV only when no MP3 encoder: re-wrap PCM into a single file
        import io
        import wave
        frames = b""
        params = None
        for r in results:
            with wave.open(io.BytesIO(r["data"]), "rb") as wf:
                params = wf.getparams()
                frames += wf.readframes(wf.getnframes())
        buf = io.BytesIO()
        with wave.open(buf, "wb") as out:
            out.setparams(params)
            out.writeframes(frames)
        data = buf.getvalue()
    logger.info("Dialogue audio: %d segments, voices=%s", len(jobs), voices)
    return _save(data, ext)


# ── Uniqueness ──────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    text = text.lower()
    text = re.sub(r"^[^:\n]{1,30}:\s*", "", text, flags=re.M)  # drop speaker labels
    return re.sub(r"[^\wà-ÿ]+", " ", text).strip()


def _shingles(text: str) -> Set[str]:
    words = _norm(text).split()
    return {" ".join(words[i:i + 3]) for i in range(max(0, len(words) - 2))}


class _History:
    """Thread-safe uniqueness store shared by the pool producers and request threads."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.fingerprints: "OrderedDict[str, None]" = OrderedDict()
        self.recent_shingles: Deque[Tuple[str, Set[str]]] = deque(maxlen=400)
        self.recent_themes: Dict[str, Deque[str]] = {lvl: deque(maxlen=40) for lvl in LEVELS}
        self.sessions: "OrderedDict[str, Set[str]]" = OrderedDict()

    def themes(self, level: str) -> List[str]:
        with self.lock:
            return list(self.recent_themes[level])

    def is_duplicate(self, fingerprint: str, script: str, level: str, theme: str) -> Optional[str]:
        shingles = _shingles(script)
        theme_key = _norm(theme)
        with self.lock:
            if fingerprint in self.fingerprints:
                return "exact duplicate"
            if theme_key and theme_key in {_norm(t) for t in self.recent_themes[level]}:
                return f"theme already used recently: {theme}"
            for _fp, other in self.recent_shingles:
                if shingles and other:
                    overlap = len(shingles & other) / max(1, len(shingles | other))
                    if overlap > 0.45:
                        return "near-duplicate script"
        return None

    def record(self, fingerprint: str, script: str, level: str, theme: str) -> None:
        with self.lock:
            self.fingerprints[fingerprint] = None
            while len(self.fingerprints) > 5000:
                self.fingerprints.popitem(last=False)
            self.recent_shingles.append((fingerprint, _shingles(script)))
            if theme:
                self.recent_themes[level].append(theme)

    def seen_by(self, session_id: Optional[str], fingerprint: str) -> bool:
        if not session_id:
            return False
        with self.lock:
            return fingerprint in self.sessions.get(session_id, set())

    def mark_served(self, session_id: Optional[str], fingerprint: str) -> None:
        if not session_id:
            return
        with self.lock:
            served = self.sessions.pop(session_id, set())
            served.add(fingerprint)
            self.sessions[session_id] = served
            while len(self.sessions) > 2000:
                self.sessions.popitem(last=False)


HISTORY = _History()


# ── Generation ──────────────────────────────────────────────────────────────────

def level_for_question(question_number: int) -> str:
    for level, (lo, hi) in LEVEL_RANGES.items():
        if lo <= question_number <= hi:
            return level
    return "C2" if question_number > 39 else "A1"


def _pick_names() -> Tuple[str, str]:
    if random.random() < 0.7:
        a, b = random.choice(MALE_NAMES), random.choice(FEMALE_NAMES)
        return (a, b) if random.random() < 0.5 else (b, a)
    pool = MALE_NAMES if random.random() < 0.5 else FEMALE_NAMES
    a, b = random.sample(pool, 2)
    return a, b


def _clean_option(text: str) -> str:
    return re.sub(r"^\s*\(?[A-Da-d]\s*[).:\-–]\s*", "", str(text)).strip()


_LETTER_REF_RE = re.compile(
    r"\b(?:l['’]\s*|la\s+|les\s+)?(?:options?|réponses?|propositions?|choix|lettres?)\s*\(?\s*[A-D]\s*\)?(?![\w])",
    re.IGNORECASE,
)
_ORDINAL_REF_RE = re.compile(
    r"\b(?:premi[eè]re?|deuxi[eè]me|second[e]?|troisi[eè]me|quatri[eè]me|derni[eè]re?)\s+(?:option|réponse|proposition)",
    re.IGNORECASE,
)


def strip_letter_references(explanation: str) -> str:
    cleaned = _LETTER_REF_RE.sub("cette réponse", explanation)
    cleaned = re.sub(r"\(\s*[A-D]\s*\)", "", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _build_prompt(level: str, question_number: int, fmt: str, is_dialogue: bool, names: Tuple[str, str],
                  target_letter: str, avoid_themes: List[str]) -> str:
    spec = LISTENING_SPECS[level]
    domain = random.choice(DOMAINS)
    place = random.choice(PLACES)
    if is_dialogue:
        a, b = names
        script_rules = (
            f"Le script est un DIALOGUE entre exactement deux personnes, {a} et {b}, avec des répliques alternées.\n"
            f"Chaque réplique est sur sa propre ligne et commence par le prénom suivi de « : » "
            f"(exemple : « {a} : ... » puis « {b} : ... »). Aucune autre ligne, aucune narration, aucun tiret.\n"
            f"Si le format implique un rôle (journaliste, animateur, client...), {a} ou {b} tient ce rôle.\n"
            f"Les répliques doivent sonner spontanées et authentiques."
        )
    else:
        script_rules = (
            "Le script est un MONOLOGUE d'une seule voix, sans étiquette de locuteur (pas de « Nom : »), "
            "sans dialogue et sans interpeller une personne qui ne parle pas."
        )
    avoid = "; ".join(avoid_themes[-12:]) or "aucun"
    return f"""Tu es concepteur d'épreuves officielles du TCF Canada (compréhension orale). Génère UNE question.

Niveau CECRL visé : {level} (question {question_number} sur 39 ; l'épreuve va du plus facile au plus difficile)
Format du document sonore : {fmt}
Domaine : {domain}. Contexte : {place}.
Thèmes déjà utilisés récemment, à NE PAS reprendre : {avoid}

DOCUMENT SONORE (script) :
- {script_rules}
- Longueur : {spec['word_count']}.
- Langue : {spec['complexity']}
- Le document doit être calibré EXACTEMENT au niveau {level} : ni plus facile, ni plus difficile.

QUESTION ET OPTIONS :
- Ce que la question évalue : {spec['answer_difficulty']}.
- 4 options courtes, toutes plausibles et grammaticalement parallèles ; {spec['distractors']}.
- Une seule réponse est juste, et elle se déduit uniquement de l'écoute du document.
- La bonne réponse DOIT être placée en position {target_letter}.
- La question et la bonne réponse portent sur le contenu du document. Ne pas faire parler ni interpeller une
  personne absente du script.

EXPLICATION (en français, 1 à 3 phrases) :
- Justifie la bonne réponse en citant ou reformulant le passage du document qui la prouve.
- {"Désigne les personnes par leur prénom." if is_dialogue else "Désigne la personne qui parle comme « le locuteur » ou « la locutrice » (c'est un monologue)."}
- Ne mentionne JAMAIS de lettre (A, B, C, D) ni la position d'une option.
- {quality_guard.stance_and_length_rules() if level in ("C1", "C2") else "Si la scène est au Canada, les prix sont en dollars, jamais en francs."}

Réponds en JSON valide uniquement :
{{
  "theme": "le sujet précis en 3 à 6 mots",
  "script": "...",
  "question": "...",
  "options": ["...", "...", "...", "..."],
  "correct_answer": "{target_letter}",
  "explanation": "..."
}}
"""


class InvalidQuestion(ValueError):
    pass


def _validate(payload: Dict[str, Any], level: str, is_dialogue: bool, names: Tuple[str, str],
              target_letter: str) -> Dict[str, Any]:
    script = str(payload.get("script", "")).strip()
    question = str(payload.get("question", "")).strip()
    explanation = str(payload.get("explanation", "")).strip()
    theme = str(payload.get("theme", "")).strip()
    raw_options = payload.get("options") or []
    if not script or not question or not explanation:
        raise InvalidQuestion("missing script, question or explanation")
    if not isinstance(raw_options, list) or len(raw_options) != 4:
        raise InvalidQuestion("need exactly 4 options")
    options = [_clean_option(o) for o in raw_options]
    if any(not o or o.lower() == "option manquante" for o in options):
        raise InvalidQuestion("empty option")
    if len({o.lower() for o in options}) < 4:
        raise InvalidQuestion("duplicate options")

    m = re.match(r"\s*([A-D])", str(payload.get("correct_answer", "")).upper())
    if not m:
        raise InvalidQuestion("no correct letter")
    correct_idx = LETTERS.index(m.group(1))
    target_idx = LETTERS.index(target_letter)
    if correct_idx != target_idx:
        # The explanation never refers to positions, so moving the right option to the target slot is safe.
        options[correct_idx], options[target_idx] = options[target_idx], options[correct_idx]

    if _ORDINAL_REF_RE.search(explanation):
        raise InvalidQuestion("explanation refers to an option position")
    explanation = strip_letter_references(explanation)

    lowered = script.lower()
    for word in BANNED_WORDS:
        if word in lowered:
            raise InvalidQuestion(f"jargon: {word}")

    if is_dialogue:
        speakers = detect_speakers(script, list(names))
        if set(names) - set(speakers):
            raise InvalidQuestion(f"dialogue must have labelled lines for {names[0]} and {names[1]}")
        unlabelled = [t for s, t in _speaker_lines(script) if s is None]
        if unlabelled:
            raise InvalidQuestion("dialogue has unlabelled lines")
    else:
        lines = _speaker_lines(script)
        labels = {s for s, _ in lines if s}
        if len(labels) >= 2:
            raise InvalidQuestion("monologue contains several speakers")
        if len(labels) == 1:  # a lone "Animateur :" label would be read aloud
            script = "\n".join(t for _s, t in lines)
        speakers = []

    words = len(_norm(script).split())
    lo, hi = LISTENING_SPECS[level]["words"]
    if not lo <= words <= hi:
        raise InvalidQuestion(f"script length {words} words outside {lo}-{hi} for {level}")

    return {
        "script": script,
        "question": question,
        "options": [f"{LETTERS[i]}. {o}" for i, o in enumerate(options)],
        "correct_answer": target_letter,
        "explanation": explanation,
        "speakers": speakers,
        "theme": theme,
    }


def _fingerprint(script: str, question: str) -> str:
    import hashlib
    return hashlib.sha256(f"{_norm(script)}|{_norm(question)}".encode("utf-8")).hexdigest()


def build_question(level: str, question_number: Optional[int] = None, with_audio: bool = True) -> ListeningQuestionResponse:
    """Generate one validated, unique question for `level` (optionally with its audio)."""
    from tcf_ai_service import _generate_json

    lo, hi = LEVEL_RANGES[level]
    number = question_number if question_number and lo <= question_number <= hi else random.randint(lo, hi)
    fmt, is_dialogue = random.choice(LISTENING_FORMATS[level])
    names = _pick_names()
    last_error: Exception | None = None
    target_letter = answer_balance.next_letter(f"listening:{level}")
    for _attempt in range(MAX_ATTEMPTS):
        prompt = _build_prompt(level, number, fmt, is_dialogue, names, target_letter, HISTORY.themes(level))
        try:
            payload = _generate_json(prompt, temperature=0.9)
            item = _validate(payload, level, is_dialogue, names, target_letter)
        except Exception as error:
            last_error = error
            logger.info("Listening %s attempt rejected: %s", level, error)
            continue
        fp = _fingerprint(item["script"], item["question"])
        reason = HISTORY.is_duplicate(fp, item["script"], level, item["theme"])
        if reason:
            last_error = InvalidQuestion(reason)
            logger.info("Listening %s attempt rejected: %s", level, reason)
            continue
        HISTORY.record(fp, item["script"], level, item["theme"])
        problems = quality_guard.item_problems(
            level, item["options"], item["correct_answer"], item["explanation"], item["script"], item["question"],
        )
        if problems:
            last_error = InvalidQuestion("; ".join(problems))
            logger.info("Listening %s attempt rejected: %s", level, last_error)
            continue
        audio_url = None
        if with_audio:
            try:
                audio_url = synthesize_listening_audio(item["script"], item["speakers"] or None)
            except Exception as error:
                logger.warning("Listening audio failed (question kept, audio on demand): %s", error)
        return ListeningQuestionResponse(
            question_id=fp,
            level=level,
            script=item["script"],
            audio_url=audio_url,
            question=item["question"],
            options=item["options"],
            correct_answer=item["correct_answer"],
            explanation=item["explanation"],
            format_type=fmt,
            speakers=item["speakers"],
        )
    raise RuntimeError(f"Listening question generation failed for {level}: {last_error}")


def _listening_fp(item: ListeningQuestionResponse) -> tuple[str, Optional[str]]:
    return item.question_id, dedupe.simhash_of(item.script)


POOL: content_bank.DurablePool = content_bank.DurablePool(
    "listening",
    producer=lambda level: build_question(str(level), with_audio=True),
    target=POOL_TARGET,
    warm_keys=LEVELS,
    module="listening",
    fingerprint_of=lambda item: item.question_id,
    simhash_of=lambda item: dedupe.simhash_of(item.script),
    load=lambda payload: ListeningQuestionResponse.model_validate(payload),
)


def _listening_blocked(learner: str, session_id: Optional[str], item: ListeningQuestionResponse) -> bool:
    fp, sim = _listening_fp(item)
    return HISTORY.seen_by(session_id, item.question_id) or content_bank.is_seen(learner, "listening", fp, sim)


def _listening_remember(learner: str, session_id: Optional[str], item: ListeningQuestionResponse) -> None:
    fp, sim = _listening_fp(item)
    HISTORY.mark_served(session_id, item.question_id)
    content_bank.remember(learner, "listening", fp, sim, label=item.question[:180])


def get_question(question_number: int, session_id: Optional[str] = None, defer_audio: bool = True,
                 target_level: Optional[str] = None) -> ListeningQuestionResponse:
    """Serve a question from the durable pool when one is ready, otherwise generate one. Never repeats for this learner."""
    learner = active_learner(session_id)
    level = target_level.upper() if target_level and target_level.upper() in LISTENING_SPECS else level_for_question(question_number)
    for _ in range(max(POOL_TARGET, 1) + 3):
        item = POOL.take(level)
        if item is None:
            break
        if _listening_blocked(learner, session_id, item):
            continue
        _listening_remember(learner, session_id, item)
        return item
    last_error: Exception | None = None
    for _ in range(3):
        try:
            item = build_question(level, question_number, with_audio=not defer_audio)
        except Exception as error:
            last_error = error
            continue
        if _listening_blocked(learner, session_id, item):
            last_error = RuntimeError("listening item already served to this learner")
            continue
        _listening_remember(learner, session_id, item)
        return item
    raise RuntimeError(f"No new listening question for {level}: {last_error}")
