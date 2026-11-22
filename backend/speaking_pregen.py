"""
Pre-generated speaking openings and vocabulary sets.

Openings: each pooled item is one complete session start (topic + examiner line + audio), served once.
Vocabulary: pooled sets of words per (language, level, topic); words already shown to the same session,
or recently to anyone at that level, are filtered out before serving.
"""
from __future__ import annotations

import hashlib
import logging
import os
import random
import threading
from collections import OrderedDict, deque
from typing import Deque, Dict, List, Optional, Tuple

import content_bank
import content_dedupe as dedupe
import topic_bank
from content_bank import DurablePool
from gemini_service import MAX_VOCAB_COUNT, gemini_service
from learner import active_learner
from tcf_ai_service import TCF_EXAMINER_NAMES, generate_tcf_speaking_opening, generate_tcf_speaking_reply

SPEAKING_TASK_TYPES = ("basic_interaction", "role_play", "opinion")
VOCAB_SET_SIZE = 15
_RECENT_TOPICS = 300
_RECENT_WORDS_PER_LEVEL = 500
_MAX_SESSIONS = 2000

_lock = threading.Lock()
_recent_topics: Dict[str, Deque[str]] = {t: deque(maxlen=_RECENT_TOPICS) for t in SPEAKING_TASK_TYPES}
_topic_fingerprints: Dict[str, Deque[str]] = {t: deque(maxlen=_RECENT_TOPICS) for t in SPEAKING_TASK_TYPES}
_recent_words: Dict[Tuple[str, str], Deque[str]] = {}
_session_words: "OrderedDict[str, set[str]]" = OrderedDict()


def _fingerprint(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


# ── Speaking openings ───────────────────────────────────────────────────────

def _topic_blocked(task_type: str, topic: str, learner: str) -> bool:
    # The in-memory fingerprint deque means "already generated into the pool", not "already served".
    return content_bank.is_seen(learner, "speaking_topic", dedupe.fingerprint(topic), dedupe.simhash_of(topic))


def _remember_topic(task_type: str, topic: str, learner: str) -> None:
    fp = _fingerprint(topic)
    with _lock:
        if fp not in _topic_fingerprints[task_type]:
            _topic_fingerprints[task_type].append(fp)
        _recent_topics[task_type].append(topic)
    content_bank.remember(learner, "speaking_topic", dedupe.fingerprint(topic), dedupe.simhash_of(topic), label=topic[:240])


def _produce_opening(task_type: str) -> dict:
    with _lock:
        avoid = list(_recent_topics[task_type])
    try:
        avoid += content_bank.recent_labels(active_learner(), "speaking_topic", 25)
    except Exception:
        pass
    for _ in range(3):
        opening = generate_tcf_speaking_opening(task_type, avoid)
        topic = str(opening["session_topic"])
        fp = _fingerprint(topic)
        with _lock:
            if fp in _topic_fingerprints[task_type]:
                continue
            _topic_fingerprints[task_type].append(fp)
            _recent_topics[task_type].append(topic)
        return opening
    raise RuntimeError("Could not produce a new speaking topic.")


opening_pool = DurablePool(
    "speaking_openings",
    _produce_opening,
    target=int(os.getenv("PREGEN_SPEAKING_TARGET", "2")),
    warm_keys=SPEAKING_TASK_TYPES,
    module="speaking_topic",
    fingerprint_of=lambda item: dedupe.fingerprint(str(item.get("session_topic", ""))),
    simhash_of=lambda item: dedupe.simhash_of(str(item.get("session_topic", ""))),
)


def take_opening(task_type: str, mode: str, hints: bool, session_id: Optional[str]) -> dict:
    """A ready session opening from the durable pool, else a new topic generated now."""
    learner = active_learner(session_id)
    for _ in range(4):
        opening = opening_pool.take(task_type)
        if opening is None:
            break
        topic = str(opening.get("session_topic", ""))
        if topic and _topic_blocked(task_type, topic, learner):
            continue
        if topic:
            _remember_topic(task_type, topic, learner)
        return dict(opening)
    last_error: Exception | None = None
    for _ in range(3):
        avoid = list(_recent_topics[task_type]) + content_bank.recent_labels(learner, "speaking_topic", 25)
        topic = topic_bank.speaking_topic(task_type, avoid)
        if _topic_blocked(task_type, topic, learner):
            continue
        try:
            reply = generate_tcf_speaking_reply(
                message="__START__",
                history=[],
                task_type=task_type,
                mode=mode,
                hints=hints,
                session_id=session_id,
                session_topic=topic,
            )
        except Exception as error:
            last_error = error
            continue
        served_topic = str(reply.get("session_topic") or topic)
        _remember_topic(task_type, served_topic, learner)
        return reply
    # The model is down. A tracked template still lets the learner start, and it is not reused.
    name, _title = random.choice(TCF_EXAMINER_NAMES)
    topic = topic_bank.speaking_topic(task_type, content_bank.recent_labels(learner, "speaking_topic", 40))
    _remember_topic(task_type, topic, learner)
    logging.getLogger("tcf.speaking").warning("Speaking opening used the offline template: %s", last_error)
    if task_type == "role_play":
        reply = f"Bonjour, je m'appelle {name}. {topic}"
    else:
        reply = f"Bonjour, je m'appelle {name}, je suis votre examinateur aujourd'hui. {topic}"
    return {"reply": reply, "audio_url": None, "session_topic": topic, "examiner_name": name}


# ── Vocabulary ──────────────────────────────────────────────────────────────

def _vocab_key(language: str, level: str, topic: Optional[str]) -> Tuple[str, str, str]:
    return ((language or "fr").lower(), (level or "A2").upper(), (topic or "").strip().lower())


def _recent_for(language: str, level: str) -> Deque[str]:
    key = (language, level)
    if key not in _recent_words:
        _recent_words[key] = deque(maxlen=_RECENT_WORDS_PER_LEVEL)
    return _recent_words[key]


def _produce_vocab_set(key: Tuple[str, str, str]) -> List[dict]:
    language, level, topic = key
    with _lock:
        exclude = list(_recent_for(language, level))
    words = gemini_service.generate_vocabulary(
        level=level, count=VOCAB_SET_SIZE, topic=topic or None, language=language, exclude=exclude
    )
    if len(words) < 5:
        raise RuntimeError("Vocabulary generation returned too few words.")
    return words


def _vocab_fingerprint(words: List[dict]) -> str:
    joined = " ".join(sorted(dedupe.normalize_vocab(str(item.get("word", ""))) for item in words))
    return dedupe.fingerprint(joined)


vocab_pool = DurablePool(
    "vocabulary_sets",
    _produce_vocab_set,
    target=3,
    warm_keys=tuple(("fr", level, "") for level in ("A1", "A2", "B1", "B2", "C1", "C2")),
    module="vocabulary_set",
    fingerprint_of=_vocab_fingerprint,
)


def _session_seen(session_id: Optional[str]) -> set:
    if not session_id:
        return set()
    with _lock:
        seen = _session_words.get(session_id)
        if seen is None:
            seen = set()
            _session_words[session_id] = seen
            while len(_session_words) > _MAX_SESSIONS:
                _session_words.popitem(last=False)
        else:
            _session_words.move_to_end(session_id)
        return seen


def take_vocabulary(
    level: str, count: int, topic: Optional[str], language: str, session_id: Optional[str]
) -> List[dict]:
    """`count` words never shown to this session and not shown recently at this level."""
    count = max(1, min(MAX_VOCAB_COUNT, int(count)))
    key = _vocab_key(language, level, topic)
    lang, lvl, _ = key
    seen_session = _session_seen(session_id)

    chosen: List[dict] = []

    learner = active_learner(session_id)

    def _fresh(words: List[dict]) -> List[dict]:
        with _lock:
            recent = {w.lower() for w in _recent_for(lang, lvl)}
        taken = {dedupe.normalize_vocab(str(i.get("word", ""))) for i in chosen}
        out = []
        for item in words:
            w = str(item.get("word", "")).strip()
            norm = dedupe.normalize_vocab(w)
            if not norm or norm in recent or norm in {dedupe.normalize_vocab(s) for s in seen_session} or norm in taken:
                continue
            if content_bank.is_seen(learner, "vocabulary", dedupe.vocab_fingerprint(w)):
                continue
            taken.add(norm)
            out.append(item)
        return out

    for _ in range(3):
        if len(chosen) >= count:
            break
        pooled = vocab_pool.take(key) if count <= VOCAB_SET_SIZE else None
        if pooled is None:
            break
        chosen.extend(_fresh(pooled))

    if len(chosen) < count:
        with _lock:
            exclude = list(_recent_for(lang, lvl))
        exclude += [str(i.get("word", "")) for i in chosen] + list(seen_session)
        exclude += content_bank.recent_labels(learner, "vocabulary", 80)
        extra = gemini_service.generate_vocabulary(
            level=lvl, count=count - len(chosen), topic=topic, language=lang, exclude=exclude
        )
        chosen.extend(_fresh(extra))

    chosen = chosen[:count]
    with _lock:
        recent = _recent_for(lang, lvl)
        for item in chosen:
            word = str(item.get("word", "")).strip()
            norm = dedupe.normalize_vocab(word)
            recent.append(norm)
            seen_session.add(norm)
            content_bank.remember(learner, "vocabulary", dedupe.vocab_fingerprint(word), None, label=norm[:240])
    return chosen
