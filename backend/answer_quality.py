"""
Answer-option quality shared by listening and reading generators.

- Prompt rules that keep distractors in the same register, length and stance as the right answer.
- A blind-guess guard: a second model call sees only the question and the options; if it can pick the right
  answer confidently without the document, the item is rejected.
- A deterministic length check (the right answer must not stand out by length).
- Rotating question focus per level and a stem history, so question wording varies.
- A large first-name pool with rotation, so the same people do not keep coming back.
"""
from __future__ import annotations

import logging
import random
import re
import threading
import unicodedata
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

LETTERS = ("A", "B", "C", "D")
LlmJson = Callable[[str, float], Dict[str, Any]]

# ── Prompt rules for options ────────────────────────────────────────────────────

_STRONG_RULE = (
    "Les QUATRE options ont le même registre, une longueur comparable (±25 %) et le même ton. "
    "Si la bonne réponse est critique, nuancée, sceptique ou ironique, au moins DEUX distracteurs sont tout aussi "
    "critiques ou nuancés, mais faux sur l'objet, le degré, la cause ou le raisonnement. Aucun distracteur naïf, "
    "absolu (« toujours », « totalement », « aucun ») ou ouvertement positif face à une bonne réponse critique. "
    "Aucune option ne doit pouvoir être choisie sans avoir compris le document : un candidat qui ne lit/n'écoute "
    "pas le document ne doit avoir qu'une chance sur quatre."
)

OPTION_RULES: Dict[str, str] = {
    "A1": "Options très courtes et de même forme (par exemple quatre heures, quatre prix ou quatre lieux).",
    "A2": "Options courtes, de même forme et de même longueur ; chacune reprend un détail réellement mentionné.",
    "B1": "Les quatre options ont la même structure grammaticale et une longueur comparable (±25 %) ; "
          "aucune option ne doit pouvoir être choisie sans le document.",
    "B2": _STRONG_RULE,
    "C1": _STRONG_RULE,
    "C2": _STRONG_RULE,
}

# ── Question focus rotation ─────────────────────────────────────────────────────

QUESTION_FOCUS: Dict[str, List[str]] = {
    "A1": ["une heure ou un horaire", "un prix ou une quantité", "un lieu", "un objet ou une action demandée",
           "un jour ou une date", "la personne concernée"],
    "A2": ["un horaire ou une date", "un lieu", "une raison simple", "une consigne pratique",
           "un changement annoncé", "un prix ou une quantité", "ce qu'une personne doit faire"],
    "B1": ["l'idée principale", "la décision prise", "l'intention d'un locuteur", "la raison d'un choix",
           "une étape ou une consigne", "le problème rencontré", "la proposition faite", "ce qui va se passer ensuite"],
    "B2": ["l'opinion d'un locuteur sur un point précis", "l'argument avancé", "la cause d'une situation",
           "la conséquence d'une décision", "la réserve ou l'objection formulée", "l'attitude envers un fait",
           "le point de désaccord", "la solution recommandée"],
    "C1": ["un sens implicite", "une nuance ou une concession", "l'intention du locuteur",
           "l'enchaînement du raisonnement", "le sens d'une expression dans son contexte", "la critique formulée",
           "un présupposé", "la fonction d'un exemple cité"],
    "C2": ["le ton (ironie, scepticisme, nostalgie...)", "un sous-entendu", "l'intention de l'auteur",
           "une nuance ou une concession", "une conséquence suggérée sans être dite",
           "le sens d'une expression dans son contexte", "le reproche formulé", "une hypothèse ou une condition",
           "la comparaison de deux positions", "la fonction d'un exemple ou d'une anecdote"],
}

_bag_lock = threading.Lock()
_focus_bags: Dict[str, List[str]] = {}


def next_focus(bucket: str, level: str) -> str:
    """Shuffled rotation: every focus of the level is used once before any repeats."""
    with _bag_lock:
        bag = _focus_bags.get(bucket)
        if not bag:
            bag = list(QUESTION_FOCUS[level])
            random.shuffle(bag)
            _focus_bags[bucket] = bag
        return bag.pop()


# ── Stem variety ────────────────────────────────────────────────────────────────

BANNED_STEM_PHRASES = ("position reelle",)
STEM_WORDS = 5


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.replace("’", "'")).strip()


def stem_key(question: str) -> str:
    return " ".join(_fold(question).split()[:STEM_WORDS])


class StemHistory:
    """Recent question openings per bucket; window=0 disables the check."""

    def __init__(self, window: int = 30) -> None:
        self.window = window
        self._lock = threading.Lock()
        self._stems: Dict[str, Deque[str]] = {}

    def problem(self, bucket: str, question: str) -> Optional[str]:
        folded = _fold(question)
        for phrase in BANNED_STEM_PHRASES:
            if phrase in folded:
                return f"banned stem phrase: {phrase}"
        if self.window <= 0:
            return None
        key = stem_key(question)
        with self._lock:
            if key and key in self._stems.get(bucket, ()):
                return f"question opening used recently: {key}"
        return None

    def recent(self, bucket: str, n: int = 8) -> List[str]:
        with self._lock:
            return list(self._stems.get(bucket, ()))[-n:]

    def record(self, bucket: str, question: str) -> None:
        if self.window <= 0:
            return
        with self._lock:
            self._stems.setdefault(bucket, deque(maxlen=self.window)).append(stem_key(question))


# ── Length outlier ──────────────────────────────────────────────────────────────

LENGTH_RATIO = 1.3
CHECKED_LEVELS = ("B1", "B2", "C1", "C2")


def length_problem(options: Sequence[str], correct_index: int) -> Optional[str]:
    lengths = [len(o.strip()) for o in options]
    right = lengths[correct_index]
    others = [n for i, n in enumerate(lengths) if i != correct_index]
    if not others or min(others) == 0:
        return None
    if right > max(others) * LENGTH_RATIO:
        return "correct option is much longer than every distractor"
    if right * LENGTH_RATIO < min(others):
        return "correct option is much shorter than every distractor"
    return None


# ── Blind-guess guard ───────────────────────────────────────────────────────────

BLIND_CONFIDENCE = 0.5


def _blind_prompt(question: str, options: Sequence[str]) -> str:
    listing = "\n".join(f"{LETTERS[i]}. {o}" for i, o in enumerate(options))
    return f"""Tu passes un QCM de français SANS avoir accès au document (ni texte ni audio).
Choisis l'option la plus probable en te fondant uniquement sur la formulation : ton, nuance, longueur,
précision, bon sens. Indique honnêtement ta confiance (0 = pur hasard, 1 = certitude).

Question : {question}
{listing}

Réponds en JSON uniquement : {{"guess": "A", "confidence": 0.0}}"""


def blind_guess(llm: LlmJson, question: str, options: Sequence[str]) -> Optional[Tuple[str, float]]:
    """(letter, confidence) from a model that never sees the document, or None if the call is unusable."""
    try:
        data = llm(_blind_prompt(question, options), 0.0)
        letter = str(data.get("guess", "")).strip().upper()[:1]
        confidence = float(data.get("confidence"))
    except Exception as error:  # noqa: BLE001 - the guard must never block generation on its own failure
        logger.info("Blind-guess check unavailable: %s", error)
        return None
    if letter not in LETTERS:
        return None
    return letter, max(0.0, min(1.0, confidence))


def blind_problem(llm: LlmJson, question: str, options: Sequence[str], correct_index: int) -> Optional[str]:
    result = blind_guess(llm, question, options)
    if result is None:
        return None
    letter, confidence = result
    if letter == LETTERS[correct_index] and confidence >= BLIND_CONFIDENCE:
        return f"answer guessable without the document (confidence {confidence:.2f})"
    return None


def _batch_blind_prompt(items: Sequence[Tuple[str, Sequence[str]]]) -> str:
    blocks = []
    for n, (question, options) in enumerate(items, start=1):
        listing = "\n".join(f"   {LETTERS[i]}. {o}" for i, o in enumerate(options))
        blocks.append(f"Q{n}. {question}\n{listing}")
    joined = "\n".join(blocks)
    return f"""Tu passes un QCM de français SANS avoir accès au document. Pour chaque item ci-dessous, choisis
l'option la plus probable en te fondant uniquement sur la formulation, et indique ta confiance (0 à 1).

{joined}

Réponds en JSON uniquement : {{"guesses": [{{"guess": "A", "confidence": 0.0}}, ...]}} (un élément par item, dans l'ordre)."""


def batch_blind_flags(llm: LlmJson, items: Sequence[Tuple[str, Sequence[str], int]]) -> List[bool]:
    """One call for many items; True where the answer was guessed confidently without the document."""
    try:
        data = llm(_batch_blind_prompt([(q, o) for q, o, _ in items]), 0.0)
        guesses = data.get("guesses")
        if not isinstance(guesses, list) or len(guesses) < len(items):
            return [False] * len(items)
        flags = []
        for (_, _, correct_index), g in zip(items, guesses):
            letter = str(g.get("guess", "")).strip().upper()[:1]
            confidence = float(g.get("confidence", 0))
            flags.append(letter == LETTERS[correct_index] and confidence >= BLIND_CONFIDENCE)
        return flags
    except Exception as error:  # noqa: BLE001
        logger.info("Batch blind-guess check unavailable: %s", error)
        return [False] * len(items)


def option_problem(level: str, question: str, options: Sequence[str], correct_index: int,
                   llm: Optional[LlmJson]) -> Optional[str]:
    """Length outlier, then blind guess (B1 and above). None when the options are fair."""
    if level not in CHECKED_LEVELS:
        return None
    reason = length_problem(options, correct_index)
    if reason:
        return reason
    if llm is not None:
        return blind_problem(llm, question, options, correct_index)
    return None


def prompt_block(level: str, focus: str, recent_stems: Sequence[str]) -> str:
    avoid = "; ".join(f"« {s}… »" for s in recent_stems) or "aucune"
    return (
        f"- La question porte sur : {focus}. Formule-la de façon naturelle et précise.\n"
        f"- Débuts de question déjà utilisés, à NE PAS reprendre : {avoid}. "
        "N'utilise jamais l'expression « position réelle ».\n"
        f"- {OPTION_RULES[level]}"
    )


# ── First names ─────────────────────────────────────────────────────────────────

MALE_NAMES = [
    "Marc", "Thomas", "Pierre", "Julien", "Antoine", "Nicolas", "Luc", "Paul", "Simon", "David",
    "Éric", "François", "Gabriel", "Mathieu", "Étienne", "Jean-François", "Sébastien", "Olivier", "Maxime", "Samuel",
    "Alexandre", "Benoît", "Charles", "Denis", "Émile", "Félix", "Guillaume", "Hugo", "Jérôme", "Laurent",
    "Martin", "Noah", "Philippe", "Raphaël", "Rémi", "Stéphane", "Tristan", "Vincent", "Xavier", "Yannick",
    "Louis", "Patrice", "Karim", "Mehdi", "Frédéric", "Jacques", "Bruno", "Jonathan",
]
FEMALE_NAMES = [
    "Sophie", "Isabelle", "Marie", "Claire", "Léa", "Camille", "Emma", "Nathalie", "Julie", "Laura",
    "Sandrine", "Céline", "Geneviève", "Marie-Ève", "Chloé", "Mélanie", "Audrey", "Amélie", "Valérie", "Noémie",
    "Annie", "Béatrice", "Catherine", "Diane", "Élise", "Florence", "Gabrielle", "Hélène", "Inès", "Jade",
    "Karine", "Lucie", "Manon", "Nadia", "Océane", "Pascale", "Rosalie", "Sarah", "Sylvie", "Véronique",
    "Zoé", "Josée", "Maude", "Alice", "Charlotte", "Yasmine", "Louise", "Brigitte",
]
NAME_GENDER: Dict[str, str] = {**{n: "male" for n in MALE_NAMES}, **{n: "female" for n in FEMALE_NAMES}}


class NameRotation:
    """Picks names not used in the last `window` picks across all generators."""

    def __init__(self, window: int = 40) -> None:
        self._lock = threading.Lock()
        self._recent: Deque[str] = deque(maxlen=window)

    def _take(self, pool: List[str], exclude: Sequence[str] = ()) -> str:
        fresh = [n for n in pool if n not in self._recent and n not in exclude]
        name = random.choice(fresh or [n for n in pool if n not in exclude])
        self._recent.append(name)
        return name

    def pair(self, mixed_probability: float = 0.7) -> Tuple[str, str]:
        with self._lock:
            if random.random() < mixed_probability:
                a, b = self._take(MALE_NAMES), self._take(FEMALE_NAMES)
                return (a, b) if random.random() < 0.5 else (b, a)
            pool = MALE_NAMES if random.random() < 0.5 else FEMALE_NAMES
            a = self._take(pool)
            return a, self._take(pool, exclude=(a,))

    def recent(self) -> List[str]:
        with self._lock:
            return list(self._recent)


NAMES = NameRotation()
