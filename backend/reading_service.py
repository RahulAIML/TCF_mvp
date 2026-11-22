"""
Reading comprehension (compréhension écrite) generation for TCF Canada.

- Six single CEFR levels; exam items ascend A1 (Q1) to C2 (Q39) like the official test.
- Every item is served at most once: pooled items are popped, every generated text is
  fingerprinted, near-duplicate texts and recent topics are rejected, and each session
  keeps the set of items it has already seen.
- The correct answer position is assigned before generation and enforced afterwards, and
  explanations never cite option letters, so the explanation always matches the key.
"""
from __future__ import annotations

import logging
import os
import random
import re
import threading
import unicodedata
from collections import OrderedDict, deque
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

import answer_balance
import content_bank
import pregen_pool
import content_dedupe as dedupe
import quality_guard
import topic_bank
import tcf_ai_service as ai
from learner import active_learner
from schemas import PassageQuizResponse, PassageResponse, TcfExamQuestion

logger = logging.getLogger(__name__)

LETTERS = ["A", "B", "C", "D"]
READING_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
PASSAGE_LEVELS = ["A2", "B1", "B2", "C1", "C2"]

# Official item order: easiest first. Q-ranges per level (boundaries after Q10 follow the common TCF split).
READING_LEVEL_RANGES: Dict[str, Tuple[int, int]] = {
    "A1": (1, 4),
    "A2": (5, 10),
    "B1": (11, 19),
    "B2": (20, 29),
    "C1": (30, 35),
    "C2": (36, 39),
}

MAX_ATTEMPTS = 3

_NO_JARGON = (
    "Style recherché mais NATUREL, comme un vrai texte publié : n'invente aucun jargon et n'accumule pas "
    "de termes rares ou académiques (pas de « aporie », « herméneutique », « épistémologie », « paradigme »)."
)

READING_SPECS: Dict[str, Dict[str, Any]] = {
    "A1": {
        "question_type": "reading_a1",
        "documents": [
            "un panneau ou une affiche très simple",
            "un court SMS ou une note entre amis",
            "une petite annonce très simple",
            "un horaire d'ouverture affiché",
        ],
        "words": (15, 30),
        "language": "Phrases très courtes (3 à 8 mots), présent uniquement, vocabulaire très fréquent "
                    "(nombres, jours, heures, prix, lieux, objets du quotidien).",
        "focus": "repérer UNE information explicite (heure, jour, lieu, prix, interdiction, objet)",
        "question_style": "question très courte et directe, options de 1 à 5 mots",
    },
    "A2": {
        "question_type": "reading_a2",
        "documents": [
            "un menu ou une carte de restaurant",
            "un horaire ou un programme d'activités",
            "une publicité ou un dépliant",
            "un courriel amical simple",
            "une petite annonce (logement, objet à vendre, cours)",
        ],
        "words": (30, 60),
        "language": "Phrases simples reliées par et, mais, parce que ; présent, passé composé, futur proche ; "
                    "vocabulaire courant de la vie quotidienne.",
        "focus": "repérer une information précise parmi plusieurs détails mentionnés",
        "question_style": "question simple, options courtes",
    },
    "B1": {
        "question_type": "reading_b1",
        "documents": [
            "une lettre ou un courriel personnel",
            "un avis pratique (règlement, consignes d'un service)",
            "un courriel professionnel simple",
            "un court article de journal local",
        ],
        "words": (70, 110),
        "language": "Registre neutre, connecteurs logiques simples (donc, pourtant, alors que), imparfait, "
                    "conditionnel présent ; situations familières (travail, loisirs, services).",
        "focus": "comprendre l'idée principale, l'intention de l'auteur ou l'enchaînement des actions, "
                 "exprimés explicitement dans le texte",
        "question_style": "question claire, options d'une phrase",
    },
    "B2": {
        "question_type": "reading_b2",
        "documents": [
            "un article d'opinion dans la presse",
            "un compte rendu ou un rapport",
            "une lettre de réclamation argumentée",
            "un article de presse sur un enjeu de société",
        ],
        "words": (120, 170),
        "language": "Registre courant à soutenu, argumentation structurée, subjonctif, discours rapporté, "
                    "quelques expressions idiomatiques.",
        "focus": "identifier l'opinion ou la position de l'auteur, une cause ou une conséquence reformulée",
        "question_style": "options reformulées (pas de copie mot pour mot du texte)",
    },
    "C1": {
        "question_type": "reading_c1",
        "documents": [
            "un long article informatif destiné au grand public cultivé",
            "un éditorial argumenté",
            "un extrait d'essai",
            "une analyse de presse",
        ],
        "words": (170, 220),
        "language": "Vocabulaire riche mais naturel, phrases complexes, concessions et nuances, implicite fréquent. "
                    + _NO_JARGON,
        "focus": "saisir un sens implicite, une nuance, l'intention de l'auteur ou un raisonnement qui n'est pas "
                 "formulé littéralement",
        "question_style": "options reformulées, proches les unes des autres",
    },
    "C2": {
        "question_type": "reading_c2",
        "documents": [
            "un extrait littéraire (roman ou récit)",
            "un extrait de chronique ou d'essai",
            "une critique culturelle",
            "un texte d'opinion au style personnel",
        ],
        "words": (200, 250),
        "language": "Langue littéraire ou journalistique authentique : ironie, sous-entendus, images, style "
                    "personnel. " + _NO_JARGON,
        "focus": "percevoir le ton (ironie, scepticisme, nostalgie), l'implicite ou la position réelle de l'auteur",
        "question_style": "options subtilement différentes ; une seule est exacte",
    },
}

PASSAGE_SPECS: Dict[str, Dict[str, Any]] = {
    "A2": {"words": (120, 150), "language": READING_SPECS["A2"]["language"],
           "focus": "informations explicites et détails pratiques"},
    "B1": {"words": (170, 210), "language": READING_SPECS["B1"]["language"],
           "focus": "idée principale, détails importants, intentions explicites"},
    "B2": {"words": (210, 250), "language": READING_SPECS["B2"]["language"],
           "focus": "opinions, arguments, causes et conséquences"},
    "C1": {"words": (240, 290), "language": READING_SPECS["C1"]["language"],
           "focus": "implicite, nuances, intention et raisonnement de l'auteur"},
    "C2": {"words": (260, 310), "language": READING_SPECS["C2"]["language"],
           "focus": "ton, ironie, implicite et position réelle de l'auteur"},
}


# ── Level helpers ────────────────────────────────────────────────────────────

def level_for_question(question_number: int) -> str:
    for level, (start, end) in READING_LEVEL_RANGES.items():
        if start <= question_number <= end:
            return level
    return "A1" if question_number < 1 else "C2"


def normalize_level(level: Optional[str], allowed: List[str] = READING_LEVELS) -> Optional[str]:
    if not level:
        return None
    clean = level.strip().upper()
    return clean if clean in allowed else None


# ── Text utilities ───────────────────────────────────────────────────────────

_PREFIX_RE = re.compile(r"^\s*(?:\(?[A-Da-d]\s*[).:\-–]\s+)")
_LETTER_CITATION_RE = re.compile(
    r"\b(?:l['’]\s*|la\s+|les\s+)?(option|réponse|reponse|proposition|choix|lettre)s?\s+\(?([A-D])\)?(?![\w'])",
    flags=re.IGNORECASE,
)


def _strip_prefix(option: str) -> str:
    return _PREFIX_RE.sub("", str(option)).strip()


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _content_words(text: str) -> Set[str]:
    return set(re.findall(r"[a-z]{4,}", _strip_accents(text.lower())))


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def sanitize_explanation(explanation: str, correct_letter: str) -> str:
    """Remove references to option letters so an explanation can never contradict the answer key."""

    def repl(match: re.Match) -> str:
        return "la bonne réponse" if match.group(2).upper() == correct_letter else "cette proposition"

    cleaned = _LETTER_CITATION_RE.sub(repl, explanation)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def place_correct_option(options: List[str], correct_index: int, target_index: int) -> Tuple[List[str], int]:
    """Swap so the correct option sits at target_index; distractor order is otherwise preserved."""
    if correct_index == target_index:
        return list(options), target_index
    moved = list(options)
    moved[correct_index], moved[target_index] = moved[target_index], moved[correct_index]
    return moved, target_index


def _letter_options(options: List[str]) -> List[str]:
    return [f"{LETTERS[i]}. {text}" for i, text in enumerate(options)]


def _validate_choice_block(payload: Dict[str, Any], target_letter: str) -> Dict[str, Any]:
    """Validate question/options/answer/explanation and enforce the pre-assigned answer position."""
    question = str(payload.get("question", "")).strip()
    raw_options = payload.get("options") or []
    options = [_strip_prefix(o) for o in raw_options][:4]
    if not question:
        raise ValueError("missing question")
    if len(options) != 4 or any(not o for o in options):
        raise ValueError("need exactly 4 non-empty options")
    if len({o.lower() for o in options}) != 4:
        raise ValueError("options are not distinct")
    match = re.match(r"\s*([A-D])", str(payload.get("correct_answer", "")).upper())
    if not match:
        raise ValueError("invalid correct_answer")
    model_letter = match.group(1)
    correct_index = LETTERS.index(model_letter)
    target_index = LETTERS.index(target_letter)
    options, final_index = place_correct_option(options, correct_index, target_index)
    final_letter = LETTERS[final_index]
    # Letters in the explanation refer to the model's original order, so judge them against model_letter.
    explanation = sanitize_explanation(str(payload.get("explanation", "")).strip(), model_letter)
    if not explanation:
        raise ValueError("missing explanation")
    return {
        "question": question,
        "options": _letter_options(options),
        "correct_answer": final_letter,
        "explanation": explanation,
    }


# ── Uniqueness registry ──────────────────────────────────────────────────────

class UniquenessRegistry:
    """Global memory of generated texts: exact fingerprints, near-duplicate detection, recent topics."""

    def __init__(self, max_items: int = 3000, similarity_threshold: float = 0.55) -> None:
        self._lock = threading.Lock()
        self._fps: Set[str] = set()
        self._fp_order: Deque[str] = deque()
        self._recent_words: Dict[str, Deque[Set[str]]] = {}
        self._recent_topics: Dict[str, Deque[str]] = {}
        self._max_items = max_items
        self._threshold = similarity_threshold

    def check_and_register(self, bucket: str, text: str, topic: str = "") -> bool:
        """Atomically register `text` if it is new; return False for duplicates or near-duplicates."""
        fp = ai._fingerprint(text)
        words = _content_words(text)
        topic_key = _strip_accents(topic.lower()).strip()
        with self._lock:
            if fp in self._fps:
                return False
            recent = self._recent_words.setdefault(bucket, deque(maxlen=300))
            if any(_jaccard(words, other) >= self._threshold for other in recent):
                return False
            topics = self._recent_topics.setdefault(bucket, deque(maxlen=30))
            if topic_key and topic_key in topics:
                return False
            self._fps.add(fp)
            self._fp_order.append(fp)
            if len(self._fp_order) > self._max_items:
                self._fps.discard(self._fp_order.popleft())
            recent.append(words)
            if topic_key:
                topics.append(topic_key)
            return True

    def recent_topics(self, bucket: str, limit: int = 12) -> List[str]:
        with self._lock:
            return list(self._recent_topics.get(bucket, ()))[-limit:]


_registry = UniquenessRegistry()


class SessionServed:
    """Per-session set of served item fingerprints (bounded number of sessions)."""

    def __init__(self, max_sessions: int = 2000) -> None:
        self._lock = threading.Lock()
        self._sessions: "OrderedDict[str, Set[str]]" = OrderedDict()
        self._max = max_sessions

    def seen(self, session_id: Optional[str], fp: str) -> bool:
        if not session_id:
            return False
        with self._lock:
            return fp in self._sessions.get(session_id, set())

    def add(self, session_id: Optional[str], fp: str) -> None:
        if not session_id:
            return
        with self._lock:
            served = self._sessions.pop(session_id, set())
            served.add(fp)
            self._sessions[session_id] = served
            while len(self._sessions) > self._max:
                self._sessions.popitem(last=False)


_served = SessionServed()

# Exam questions stay stable per (session, question number) so a resumed exam shows the same items.
_EXAM_CACHE_MAX = 5000
_exam_cache: "OrderedDict[str, TcfExamQuestion]" = OrderedDict()
_exam_cache_lock = threading.Lock()


def _exam_cache_get(key: str) -> Optional[TcfExamQuestion]:
    with _exam_cache_lock:
        item = _exam_cache.get(key)
        if item is not None:
            _exam_cache.move_to_end(key)
        return item


def _exam_cache_put(key: str, item: TcfExamQuestion) -> None:
    with _exam_cache_lock:
        _exam_cache[key] = item
        _exam_cache.move_to_end(key)
        while len(_exam_cache) > _EXAM_CACHE_MAX:
            _exam_cache.popitem(last=False)


def _item_fp(question: TcfExamQuestion) -> str:
    return ai._fingerprint(question.text)


# ── LLM access (patched in tests) ────────────────────────────────────────────

def _llm_json(prompt: str, temperature: float) -> Dict[str, Any]:
    return ai._generate_json(prompt, temperature=temperature)


# ── Single reading question ──────────────────────────────────────────────────

def build_reading_prompt(level: str, question_number: int, target_letter: str, avoid_topics: List[str]) -> str:
    spec = READING_SPECS[level]
    low, high = spec["words"]
    token = ai._freshness_token()
    place, context = topic_bank.place(), random.choice(ai.SCENARIO_CONTEXTS)
    domain = topic_bank.domain()
    import variety
    from learner import current_learner
    document = variety.choose(f"reading_document:{level}", list(spec["documents"]), current_learner())
    avoid = "; ".join(avoid_topics) if avoid_topics else "aucun"
    return f"""Tu es concepteur d'épreuves officielles du TCF Canada (compréhension écrite).
Rédige UNE question de niveau {level} du CECR, STRICTEMENT à ce niveau (ni plus facile, ni plus difficile).

Niveau : {level} (question {question_number} sur 39, les questions vont du plus facile au plus difficile)
Type de document : {document}
Domaine : {domain} ; cadre : {place}, {context} ; contexte canadien ou francophone réaliste
Longueur du document : {low} à {high} mots
Langue attendue : {spec['language']}
Ce que la question évalue : {spec['focus']}
Forme des options : {spec['question_style']}
Sujets déjà utilisés récemment, à NE PAS reprendre : {avoid}
Jeton de fraîcheur : {token} (ne pas l'inclure dans la sortie)

Règles :
- Document authentique et naturel, tel qu'on le trouverait réellement.
- Une seule bonne réponse, sans ambiguïté, justifiable par le texte.
- La bonne réponse DOIT être en position {target_letter} dans la liste des options.
- Les trois distracteurs sont plausibles : chacun s'appuie sur un élément réellement présent dans le texte
  mais le déforme (mauvais détail, mauvaise personne, mauvais moment, généralisation abusive, contresens).
  Aucun distracteur absurde, hors sujet ou évidemment faux.
- Les quatre options ont une longueur et une forme comparables ; ne commence pas les options par une lettre.
- L'explication (en français, 1 à 3 phrases) justifie la bonne réponse à partir du texte et ne mentionne
  JAMAIS de lettre (A, B, C ou D).
- {quality_guard.stance_and_length_rules() if level in ("C1", "C2") else "Si la scène est au Canada, les prix sont en dollars, jamais en francs."}
- "topic" : le sujet du document en 3 à 6 mots.

Sortie : JSON valide uniquement, sans Markdown :
{{
  "text": "...",
  "question": "...",
  "options": ["...", "...", "...", "..."],
  "correct_answer": "{target_letter}",
  "explanation": "...",
  "topic": "..."
}}
"""


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


def produce_reading_question(level: str, question_number: Optional[int] = None) -> TcfExamQuestion:
    """Generate one new, unique reading question at exactly `level` (raises RuntimeError on failure)."""
    spec = READING_SPECS[level]
    start, end = READING_LEVEL_RANGES[level]
    qnum = question_number or random.randint(start, end)
    low, high = spec["words"]
    last_error: Exception | None = None
    target_letter = answer_balance.next_letter(f"reading:{level}")
    for _ in range(MAX_ATTEMPTS):
        prompt = build_reading_prompt(level, qnum, target_letter, _registry.recent_topics(f"q:{level}"))
        try:
            payload = _llm_json(prompt, 0.8)
            text = str(payload.get("text", "")).strip()
            words = _word_count(text)
            if words < max(5, int(low * 0.5)) or words > int(high * 1.8):
                raise ValueError(f"text length {words} words is outside the {level} range")
            block = _validate_choice_block(payload, target_letter)
            question = TcfExamQuestion.model_validate({
                "text": text,
                **block,
                "question_type": spec["question_type"],
            })
            if not _registry.check_and_register(f"q:{level}", text, str(payload.get("topic", ""))):
                raise ValueError("duplicate or near-duplicate text")
            problems = quality_guard.item_problems(
                level, question.options, question.correct_answer, question.explanation, text, question.question,
            )
            if problems:
                raise ValueError("; ".join(problems))
            return question
        except Exception as error:  # noqa: BLE001 - every failure triggers a fresh attempt
            last_error = error
            logger.info("Reading %s attempt failed: %s", level, error)
    raise RuntimeError(f"Reading question generation failed for {level}: {last_error}") from last_error


def _reading_ids(question: TcfExamQuestion) -> tuple[str, str | None]:
    return dedupe.fingerprint(question.text), dedupe.simhash_of(question.text)


_READING_POOL = content_bank.DurablePool(
    "reading_question",
    lambda level: produce_reading_question(str(level)),
    target=5,
    warm_keys=tuple(READING_LEVELS),
    module="reading",
    fingerprint_of=lambda item: dedupe.fingerprint(item.text),
    simhash_of=lambda item: dedupe.simhash_of(item.text),
    load=lambda payload: TcfExamQuestion.model_validate(payload),
)


def _offline_reading(level: str) -> TcfExamQuestion:
    """A usable reading item when the model is unavailable. Details vary so the text is not repeated."""
    place = random.choice(["Montréal", "Québec", "Ottawa", "Laval", "Gatineau"])
    hour = random.randint(9, 17)
    day = random.choice(["lundi", "mardi", "mercredi", "jeudi", "vendredi"])
    text = (
        f"La clinique de {place} est ouverte le {day} à partir de {hour} h. "
        f"Les rendez-vous de l'après-midi commencent à {hour + 2} h. "
        "Apportez votre carte d'assurance maladie."
    )
    correct = f"Le {day} à {hour} h."
    distractors = [f"Le {day} à {hour + 2} h.", "Le samedi à 9 h.", f"Tous les jours à {hour + 1} h."]
    letter = answer_balance.next_letter(f"reading:{level}")
    index = "ABCD".index(letter)
    bodies = distractors[:]
    bodies.insert(index, correct)
    return TcfExamQuestion(
        text=text,
        question="Quand la clinique ouvre-t-elle ?",
        options=[f"{'ABCD'[i]}. {bodies[i]}" for i in range(4)],
        correct_answer=letter,  # type: ignore[arg-type]
        explanation=f"Le texte dit que la clinique est ouverte le {day} à partir de {hour} h.",
        question_type=f"reading_{level.lower()}",  # type: ignore[arg-type]
    )


def get_reading_question(
    question_number: int,
    session_id: Optional[str] = None,
    target_level: Optional[str] = None,
) -> TcfExamQuestion:
    """
    Practice (target_level given): always a new item at that level.
    Exam (no target_level): level follows the question number; stable per (session, question number).
    """
    learner = active_learner(session_id)
    level = normalize_level(target_level) or level_for_question(question_number)
    exam_key = f"{session_id}:{question_number}" if session_id and not target_level else None
    if exam_key:
        cached = _exam_cache_get(exam_key)
        if cached is None and session_id:
            stored = content_bank.load_exam(learner, session_id, "reading", str(question_number))
            if stored:
                cached = TcfExamQuestion.model_validate(stored)
                _exam_cache_put(exam_key, cached)
        if cached is not None:
            return cached

    question: Optional[TcfExamQuestion] = None
    for _ in range(6):
        candidate = _READING_POOL.take(level)
        if candidate is None:
            break
        fp, sim = _reading_ids(candidate)
        if _served.seen(session_id, _item_fp(candidate)) or content_bank.is_seen(learner, "reading", fp, sim):
            continue
        question = candidate
        break
    if question is None:
        last_error: Exception | None = None
        for _ in range(3):
            try:
                candidate = produce_reading_question(level, question_number)
            except Exception as error:
                last_error = error
                continue
            fp, sim = _reading_ids(candidate)
            if content_bank.is_seen(learner, "reading", fp, sim):
                last_error = RuntimeError("reading item already served to this learner")
                continue
            question = candidate
            break
        if question is None:
            logger.warning("Reading generation failed for %s (%s); serving an offline item.", level, last_error)
            question = _offline_reading(level)

    fp, sim = _reading_ids(question)
    _served.add(session_id, _item_fp(question))
    content_bank.remember(learner, "reading", fp, sim, label=question.text[:180])
    if exam_key and session_id:
        _exam_cache_put(exam_key, question)
        content_bank.save_exam(learner, session_id, "reading", str(question_number), fp, question.model_dump())
    return question


# ── Passage + 10-question quiz ───────────────────────────────────────────────

def _quiz_letters(count: int = 10) -> List[str]:
    letters = (LETTERS * ((count // 4) + 1))[:count]
    random.shuffle(letters)
    return letters


def build_quiz_prompt(level: str, letters: List[str], avoid_topics: List[str]) -> str:
    spec = PASSAGE_SPECS[level]
    low, high = spec["words"]
    token = ai._freshness_token()
    place, context = topic_bank.place(), random.choice(ai.SCENARIO_CONTEXTS)
    domain = topic_bank.domain()
    avoid = "; ".join(avoid_topics) if avoid_topics else "aucun"
    letter_plan = ", ".join(f"Q{i + 1}={letter}" for i, letter in enumerate(letters))
    return f"""Tu es concepteur d'épreuves du TCF Canada (compréhension écrite).
Rédige un texte de niveau {level} du CECR, puis 10 questions de compréhension sur ce texte.

Niveau : {level} (strictement)
Domaine : {domain} ; cadre : {place}, {context} ; contexte canadien ou francophone réaliste
Longueur du texte : {low} à {high} mots
Langue attendue : {spec['language']}
Les questions portent sur : {spec['focus']} ; ordre des questions = ordre du texte
Sujets déjà utilisés récemment, à NE PAS reprendre : {avoid}
Position imposée de la bonne réponse : {letter_plan}
Jeton de fraîcheur : {token} (ne pas l'inclure dans la sortie)

Règles :
- Chaque question a une seule bonne réponse justifiable par le texte.
- Les distracteurs reprennent des éléments réellement présents dans le texte mais les déforment ; aucun
  distracteur absurde. Options de longueur comparable, sans lettre au début.
- Chaque explication (1 à 2 phrases, en français) cite l'idée du texte et ne mentionne JAMAIS de lettre.
- Le texte commence par une phrase complète. "topic" : le sujet en 3 à 6 mots.

Sortie : JSON valide uniquement :
{{
  "title": "...",
  "passage": "...",
  "topic": "...",
  "questions": [
    {{"question": "...", "options": ["...", "...", "...", "..."], "correct_answer": "A", "explanation": "..."}}
  ]
}}
"""


def produce_passage_quiz(level: str) -> PassageQuizResponse:
    spec = PASSAGE_SPECS[level]
    low, high = spec["words"]
    last_error: Exception | None = None
    for _ in range(MAX_ATTEMPTS):
        letters = _quiz_letters(10)
        prompt = build_quiz_prompt(level, letters, _registry.recent_topics(f"quiz:{level}"))
        try:
            payload = _llm_json(prompt, 0.8)
            passage = str(payload.get("passage", "")).strip()
            title = str(payload.get("title", "")).strip() or "Texte"
            words = _word_count(passage)
            if words < int(low * 0.6) or words > int(high * 1.6):
                raise ValueError(f"passage length {words} words is outside the {level} range")
            raw_questions = payload.get("questions") or []
            if len(raw_questions) < 10:
                raise ValueError("fewer than 10 questions")
            questions = [_validate_choice_block(q, letters[i]) for i, q in enumerate(raw_questions[:10])]
            quiz = PassageQuizResponse.model_validate({"title": title, "passage": passage, "questions": questions})
            if not _registry.check_and_register(f"quiz:{level}", passage, str(payload.get("topic", ""))):
                raise ValueError("duplicate or near-duplicate passage")
            for block in questions:
                problems = quality_guard.item_problems(
                    level, block["options"], block["correct_answer"], block["explanation"], passage,
                )
                if problems:
                    raise ValueError("; ".join(problems))
            scene_problems = quality_guard.any_text_problems([passage, title])
            if scene_problems:
                raise ValueError("; ".join(scene_problems))
            return quiz
        except Exception as error:  # noqa: BLE001
            last_error = error
            logger.info("Passage quiz %s attempt failed: %s", level, error)
    raise RuntimeError(f"Passage quiz generation failed for {level}: {last_error}") from last_error


_QUIZ_POOL = content_bank.DurablePool(
    "passage_quiz",
    lambda level: produce_passage_quiz(str(level)),
    target=int(os.getenv("PREGEN_QUIZ_TARGET", "2")),
    warm_keys=tuple(PASSAGE_LEVELS),
    module="passage_quiz",
    fingerprint_of=lambda item: dedupe.fingerprint(item.passage),
    simhash_of=lambda item: dedupe.simhash_of(item.passage),
    load=lambda payload: PassageQuizResponse.model_validate(payload),
)


def get_passage_quiz(level: Optional[str] = None, session_id: Optional[str] = None) -> PassageQuizResponse:
    learner = active_learner(session_id)
    chosen = normalize_level(level, PASSAGE_LEVELS) or "B1"
    quiz: Optional[PassageQuizResponse] = None
    for _ in range(4):
        candidate = _QUIZ_POOL.take(chosen)
        if candidate is None:
            break
        fp = dedupe.fingerprint(candidate.passage)
        sim = dedupe.simhash_of(candidate.passage)
        if _served.seen(session_id, ai._fingerprint(candidate.passage)) or content_bank.is_seen(learner, "passage_quiz", fp, sim):
            continue
        quiz = candidate
        break
    if quiz is None:
        last_error: Exception | None = None
        for _ in range(3):
            try:
                candidate = produce_passage_quiz(chosen)
            except Exception as error:
                last_error = error
                continue
            fp = dedupe.fingerprint(candidate.passage)
            if content_bank.is_seen(learner, "passage_quiz", fp, dedupe.simhash_of(candidate.passage)):
                last_error = RuntimeError("passage already served")
                continue
            quiz = candidate
            break
        if quiz is None:
            raise RuntimeError(f"No new passage quiz: {last_error}")
    fp = dedupe.fingerprint(quiz.passage)
    _served.add(session_id, ai._fingerprint(quiz.passage))
    content_bank.remember(learner, "passage_quiz", fp, dedupe.simhash_of(quiz.passage), label=quiz.title[:180])
    return quiz


def generate_passage(level: Optional[str] = None) -> PassageResponse:
    """Stand-alone passage (no quiz), unique like every other reading item."""
    chosen = normalize_level(level, PASSAGE_LEVELS) or "B1"
    spec = PASSAGE_SPECS[chosen]
    low, high = spec["words"]
    last_error: Exception | None = None
    for _ in range(MAX_ATTEMPTS):
        token = ai._freshness_token()
        place, context = topic_bank.place(), random.choice(ai.SCENARIO_CONTEXTS)
        avoid = "; ".join(_registry.recent_topics(f"passage:{chosen}")) or "aucun"
        prompt = f"""Rédige un texte de lecture TCF Canada de niveau {chosen} du CECR.
Longueur : {low} à {high} mots. Langue : {spec['language']}
Domaine : {topic_bank.domain()} ; cadre : {place}, {context}.
Si la scène est au Canada, les prix sont en dollars, jamais en francs.
Sujets à ne pas reprendre : {avoid}. Jeton : {token} (ne pas l'inclure).
Le texte commence par une phrase complète. Sortie JSON uniquement :
{{"title": "...", "passage": "...", "topic": "..."}}
"""
        try:
            payload = _llm_json(prompt, 0.85)
            result = PassageResponse.model_validate({
                "title": str(payload.get("title", "")).strip() or "Texte",
                "passage": str(payload.get("passage", "")).strip(),
            })
            if not result.passage:
                raise ValueError("empty passage")
            if not _registry.check_and_register(f"passage:{chosen}", result.passage, str(payload.get("topic", ""))):
                raise ValueError("duplicate passage")
            scene = quality_guard.any_text_problems([result.passage, result.title])
            if scene:
                raise ValueError("; ".join(scene))
            learner = active_learner()
            fp = dedupe.fingerprint(result.passage)
            if content_bank.is_seen(learner, "passage", fp, dedupe.simhash_of(result.passage)):
                raise ValueError("passage already served to this learner")
            content_bank.remember(learner, "passage", fp, dedupe.simhash_of(result.passage), label=result.title[:180])
            return result
        except Exception as error:  # noqa: BLE001
            last_error = error
    raise RuntimeError(f"Passage generation failed: {last_error}") from last_error
