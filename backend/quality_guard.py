"""Reject multiple-choice items a student can answer without reading or listening.

C1/C2 items were guessable when the correct option was the only one that denounced, mocked or
criticised, or when it was much longer than the other three. Prices in francs inside a Canadian
scene are rejected as well. Explanations are not allowed to name an option letter.
"""
from __future__ import annotations

import re
from typing import Iterable, Sequence

_CRITICAL = re.compile(
    r"\b("
    r"d[ée]nonce[a-z]*|raille[a-z]*|fustige[a-z]*|ironise[a-z]*|ironi[a-z]*|"
    r"condamne[a-z]*|d[ée]plore[a-z]*|stigmatise[a-z]*|"
    r"sarcas(?:me|tique)s?|sceptique[a-z]*|"
    r"se moque|tourne en d[ée]rision|critique s[ée]v[èe]rement"
    r")\b",
    re.IGNORECASE,
)
_FRANCS = re.compile(r"\bfrancs\b", re.IGNORECASE)
_CANADA = re.compile(
    r"montr[eé]al|qu[eé]bec|ottawa|toronto|vancouver|canada|gatineau|sherbrooke|"
    r"winnipeg|trois-rivi[eè]res|moncton",
    re.IGNORECASE,
)
_LETTER_CITE = re.compile(
    r"\b(?:l['’]\s*|la\s+|les\s+)?(?:options?|r[ée]ponses?|propositions?|choix|lettres?)\s*\(?\s*([A-D])\s*\)?",
    re.IGNORECASE,
)
_OPTION_PREFIX = re.compile(r"^\s*(?:[A-D][).:\-–]\s*)", re.IGNORECASE)


def option_body(option: str) -> str:
    return _OPTION_PREFIX.sub("", str(option)).strip()


def stance_and_length_rules() -> str:
    return (
        "Les quatre options ont le MÊME degré de nuance et de critique : il est interdit que la bonne "
        "réponse soit la seule à dénoncer, railler, fustiger, ironiser ou déplorer pendant que les autres "
        "restent neutres ou naïves. La bonne réponse n'est pas plus longue que les distracteurs. "
        "Si la scène est au Canada, les prix sont en dollars canadiens, jamais en francs."
    )


def _words(text: str) -> int:
    return len(re.findall(r"\w+", text))


def choice_problems(level: str, options: Sequence[str], correct_letter: str) -> list[str]:
    """Problems that make the key guessable. Empty when the item is acceptable."""
    problems: list[str] = []
    bodies = [option_body(option) for option in list(options)[:4]]
    if len(bodies) != 4 or correct_letter not in "ABCD":
        return problems
    index = "ABCD".index(correct_letter)
    if level in ("C1", "C2"):
        flags = [bool(_CRITICAL.search(body)) for body in bodies]
        if flags[index] and sum(flags) == 1:
            problems.append("only the correct option carries a critical stance")
        lengths = [_words(body) for body in bodies]
        others = [n for i, n in enumerate(lengths) if i != index]
        longest_other = max(others) if others else 0
        if lengths[index] >= longest_other + 5 and lengths[index] > longest_other * 1.45 and lengths[index] >= 8:
            problems.append("correct option is markedly longer than the distractors")
    return problems


def explanation_problems(explanation: str) -> list[str]:
    if _LETTER_CITE.search(explanation or ""):
        return ["explanation cites an option letter"]
    return []


def scrub_letter_citations(explanation: str) -> str:
    """Replace 'la réponse B' with a phrase that does not name a letter."""
    cleaned = _LETTER_CITE.sub("la bonne réponse", explanation or "")
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def anachronism_problems(text: str) -> list[str]:
    if _FRANCS.search(text or "") and _CANADA.search(text or ""):
        return ["francs used in a Canadian scene"]
    return []


def item_problems(level: str, options: Sequence[str], correct_letter: str, explanation: str, *texts: str) -> list[str]:
    problems = choice_problems(level, options, correct_letter)
    problems += explanation_problems(explanation)
    blob = " ".join(texts) + " " + " ".join(option_body(o) for o in options)
    problems += anachronism_problems(blob)
    return problems


def any_text_problems(texts: Iterable[str]) -> list[str]:
    return anachronism_problems(" ".join(texts))
