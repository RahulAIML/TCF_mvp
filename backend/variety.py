"""Per-learner rotation of formats and voice pairs.

Choices are stored on the seen-set (one small row each). Nothing is generated in the background,
and the lists themselves are a few dozen strings.
"""
from __future__ import annotations

import hashlib
import logging
import random
import time

import content_bank
from learner import active_learner, current_learner

logger = logging.getLogger("tcf.variety")

# Listening voice pairs. Each pair is two public French voices whose pitch and accent already differ.
LISTENING_PAIRS: list[tuple[str, str]] = [
    ("fr-FR-male-1", "fr-FR-female-2"),  # deep France + bright Quebec
    ("fr-FR-male-2", "fr-FR-female-1"),  # bright Quebec + deep France
    ("fr-FR-male-1", "fr-FR-female-1"),  # both deep, different gender
    ("fr-FR-male-2", "fr-FR-female-2"),  # both bright, different gender
    ("fr-FR-male-1", "fr-FR-male-2"),    # two men, opposite pitch
    ("fr-FR-female-1", "fr-FR-female-2"),  # two women, opposite pitch
]

WRITING_TASK1_FORMS = ["un courriel", "un mot", "une invitation", "un message"]
WRITING_TASK2_FORMS = ["un article", "un courrier", "une note", "un billet de blogue"]

SPEAKING_SITUATIONS = {
    "basic_interaction": [
        "se présenter à un voisin",
        "parler d'une journée type",
        "raconter un loisir",
        "décrire son logement",
    ],
    "role_play": [
        "un guichet de mairie",
        "une clinique",
        "une agence de location",
        "un commerce de quartier",
    ],
    "opinion": [
        "un choix de société",
        "une habitude du quotidien",
        "un service public",
        "une question de travail",
    ],
}

VOCAB_TOPICS = [
    "la ville", "le travail", "la santé", "les études", "l'alimentation",
    "les transports", "le logement", "la nature", "les loisirs", "l'administration",
]

GRAMMAR_FOCI = [
    "l'accord du participe passé",
    "le choix entre imparfait et passé composé",
    "une préposition (à, de, en, dans)",
    "le pronom relatif (qui, que, dont)",
    "l'accord de l'adjectif",
    "un temps du futur ou du conditionnel",
]


def _learner(learner: str | None) -> str:
    if learner:
        return learner
    return current_learner() or active_learner()


def recent(module: str, learner: str | None = None, limit: int = 8) -> list[str]:
    try:
        return content_bank.recent_labels(_learner(learner), f"variety:{module}", limit)
    except Exception:
        logger.warning("Could not read recent variety choices for %s", module)
        return []


def choose(module: str, options: list[str], learner: str | None = None) -> str:
    """Next option for this learner. The previous choice is skipped, and the same one is never used three times running."""
    if not options:
        raise ValueError(f"No choices for {module}")
    who = _learner(learner)
    history = recent(module, who, 8)
    last = history[0] if history else None
    pool = [item for item in options if item != last] or list(options)
    if len(history) >= 2 and history[0] == history[1]:
        pool = [item for item in options if item != history[0]] or pool
    picked = random.choice(pool)
    _remember(module, who, picked)
    return picked


def _remember(module: str, learner: str, label: str) -> None:
    stamp = f"{module}|{label}|{time.time_ns()}|{random.randrange(1_000_000)}"
    fingerprint = hashlib.sha256(stamp.encode("utf-8")).hexdigest()
    try:
        content_bank.remember(learner, f"variety:{module}", fingerprint, None, label=label[:240])
    except Exception:
        logger.warning("Could not record variety choice %s", module)


def pair_key(left: str, right: str) -> str:
    return "|".join(sorted((left, right)))


def _voice_gender(voice_id: str) -> str:
    parts = voice_id.split("-")
    return parts[2] if len(parts) >= 3 else ""


def _adult_pairs(speakers_same_gender: bool | None, gender: str | None) -> list[tuple[str, str]]:
    """Pairs drawn from the French adult pool, so a dialogue is not stuck on the first four voices."""
    import tts_service
    voices = tts_service.list_active_voices("fr")
    males = [v["id"] for v in voices if v["gender"] == "male"]
    females = [v["id"] for v in voices if v["gender"] == "female"]
    if speakers_same_gender is True and gender == "female":
        pool_a, pool_b = females, females
    elif speakers_same_gender is True:
        pool_a, pool_b = males, males
    elif speakers_same_gender is False:
        return [(m, f) for m in males for f in females] or list(LISTENING_PAIRS)
    else:
        return [(m, f) for m in males for f in females] or list(LISTENING_PAIRS)
    return [(a, b) for i, a in enumerate(pool_a) for b in pool_b[i + 1 :]] or list(LISTENING_PAIRS)


def listening_pair(
    speakers_same_gender: bool | None,
    learner: str | None = None,
    gender: str | None = None,
) -> tuple[str, str]:
    """A voice pair this learner did not just hear. Same-gender dialogues stay on a same-gender pair."""
    options = _adult_pairs(speakers_same_gender, gender)
    if speakers_same_gender is True:
        options = [pair for pair in options if _voice_gender(pair[0]) == _voice_gender(pair[1])] or options
    elif speakers_same_gender is False:
        options = [pair for pair in options if _voice_gender(pair[0]) != _voice_gender(pair[1])] or options
    labels = [pair_key(*pair) for pair in options]
    picked = choose("listening_pair", labels, learner)
    for pair in options:
        if pair_key(*pair) == picked:
            order_label = picked + ":0"
            if recent("listening_pair_order", learner, 1)[:1] == [order_label]:
                _remember("listening_pair_order", _learner(learner), picked + ":1")
                return pair[1], pair[0]
            _remember("listening_pair_order", _learner(learner), order_label)
            return pair
    return options[0]
