"""
Pre-generated speaking openings and vocabulary sets.

Openings: each pooled item is one complete session start (topic + examiner line + audio), served once.
Vocabulary: pooled sets of words per (language, level, topic); words already shown to the same session,
or recently to anyone at that level, are filtered out before serving.
"""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict, deque
from typing import Deque, Dict, List, Optional, Tuple

from gemini_service import MAX_VOCAB_COUNT, gemini_service
from pregen_pool import PregenPool
from tcf_ai_service import generate_tcf_speaking_opening, generate_tcf_speaking_reply

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

def _produce_opening(task_type: str) -> dict:
    with _lock:
        avoid = list(_recent_topics[task_type])
    for _ in range(3):
        opening = generate_tcf_speaking_opening(task_type, avoid)
        fp = _fingerprint(str(opening["session_topic"]))
        with _lock:
            if fp in _topic_fingerprints[task_type]:
                continue
            _topic_fingerprints[task_type].append(fp)
            _recent_topics[task_type].append(str(opening["session_topic"]))
        return opening
    raise RuntimeError("Could not produce a new speaking topic.")


opening_pool: PregenPool = PregenPool(
    "speaking_openings", _produce_opening, target=5, warm_keys=SPEAKING_TASK_TYPES
)


def take_opening(task_type: str, mode: str, hints: bool, session_id: Optional[str]) -> dict:
    """A ready session opening (instant when the pool has one), else generated now."""
    opening = opening_pool.take(task_type)
    if opening is not None:
        return dict(opening)
    reply = generate_tcf_speaking_reply(
        message="__START__", history=[], task_type=task_type, mode=mode, hints=hints, session_id=session_id
    )
    with _lock:
        _recent_topics[task_type].append(str(reply.get("session_topic", "")))
        _topic_fingerprints[task_type].append(_fingerprint(str(reply.get("session_topic", ""))))
    return reply


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


vocab_pool: PregenPool = PregenPool(
    "vocabulary_sets",
    _produce_vocab_set,
    target=3,
    warm_keys=tuple(("fr", level, "") for level in ("A1", "A2", "B1", "B2", "C1", "C2")),
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

    def _fresh(words: List[dict]) -> List[dict]:
        with _lock:
            recent = {w.lower() for w in _recent_for(lang, lvl)}
        taken = {str(i.get("word", "")).strip().lower() for i in chosen}
        out = []
        for item in words:
            w = str(item.get("word", "")).strip().lower()
            if w and w not in recent and w not in seen_session and w not in taken:
                taken.add(w)
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
        extra = gemini_service.generate_vocabulary(
            level=lvl, count=count - len(chosen), topic=topic, language=lang, exclude=exclude
        )
        chosen.extend(_fresh(extra))

    chosen = chosen[:count]
    with _lock:
        recent = _recent_for(lang, lvl)
        for item in chosen:
            word = str(item.get("word", "")).strip().lower()
            recent.append(word)
            seen_session.add(word)
    return chosen
