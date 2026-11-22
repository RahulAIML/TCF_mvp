"""Normalized fingerprints and near-duplicate signatures for served practice content.

Exact repeats use a SHA-256 of the normalized text. Longer items also get a 64-bit simhash of
word shingles so a light paraphrase is treated as the same item. Short items (a single vocabulary
word, a short topic line) are compared exactly: simhash on a handful of tokens is too noisy.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata

_ARTICLES = ("le", "la", "les", "un", "une", "des", "du", "de", "d", "l")
_WORD = re.compile(r"[a-z0-9]+")
_NEAR_MIN_TOKENS = 24


def normalize_text(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(_WORD.findall(folded.lower()))


def normalize_vocab(word: str) -> str:
    """Lowercase, strip accents and a leading article so 'le chat' and 'chat' are one word."""
    tokens = normalize_text(word).split()
    if tokens and tokens[0] in _ARTICLES:
        tokens = tokens[1:]
    return " ".join(tokens) or normalize_text(word)


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def vocab_fingerprint(word: str) -> str:
    return hashlib.sha256(normalize_vocab(word).encode("utf-8")).hexdigest()


def simhash_of(text: str) -> str | None:
    """Hex simhash for a long text, or None when the text is too short to compare safely."""
    tokens = normalize_text(text).split()
    if len(tokens) < _NEAR_MIN_TOKENS:
        return None
    shingles = [" ".join(tokens[i:i + 3]) for i in range(len(tokens) - 2)]
    bits = [0] * 64
    for shingle in shingles:
        digest = int(hashlib.md5(shingle.encode("utf-8")).hexdigest(), 16)
        for i in range(64):
            bits[i] += 1 if (digest >> i) & 1 else -1
    value = 0
    for i, weight in enumerate(bits):
        if weight > 0:
            value |= 1 << i
    return f"{value:016x}"


def hamming(left: str | None, right: str | None) -> int | None:
    if not left or not right:
        return None
    return (int(left, 16) ^ int(right, 16)).bit_count()


def near_duplicate(left: str | None, right: str | None, threshold: int | None = None) -> bool:
    distance = hamming(left, right)
    if distance is None:
        return False
    limit = threshold if threshold is not None else int(os.getenv("NEAR_DUP_HAMMING", "5"))
    return distance <= limit
