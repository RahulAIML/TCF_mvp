"""Pronunciation prompts: generated when the model is available, otherwise a tracked offline list.

Every phrase that is handed out is recorded for the learner, including the offline fallback, so the
same prompt is not offered again.
"""
from __future__ import annotations

import logging
import os

import content_bank
import content_dedupe as dedupe
from learner import active_learner

logger = logging.getLogger("tcf.pronunciation_prompts")

# Safe offline list. Each entry is also tracked once it is served.
_FALLBACK = {
    "fr": [
        ("A1", "Bonjour, je m'appelle Marie."),
        ("A1", "Merci beaucoup pour votre aide."),
        ("A1", "Je voudrais un café, s'il vous plaît."),
        ("A1", "Où est la station de métro ?"),
        ("A1", "J'habite à Montréal depuis un an."),
        ("A2", "Comment allez-vous aujourd'hui ?"),
        ("A2", "Je prends le bus pour aller au travail."),
        ("A2", "Nous avons réservé une table pour deux."),
        ("A2", "Il fait froid, je mets mon manteau."),
        ("A2", "Est-ce que vous pouvez répéter, s'il vous plaît ?"),
        ("B1", "Je me suis inscrit à un cours du soir."),
        ("B1", "L'environnement du quartier s'est amélioré."),
        ("B1", "Nous devrions réduire nos déchets cette année."),
        ("B1", "Elle a déménagé à Québec le mois dernier."),
        ("B1", "Je cherche un appartement près de l'université."),
        ("B2", "La citoyenneté implique des droits et des devoirs."),
        ("B2", "Le développement durable concerne toute la ville."),
        ("B2", "Il faudrait mieux financer les bibliothèques publiques."),
        ("B2", "Cette décision aura des conséquences sur le quartier."),
        ("C1", "On ne peut pas réduire ce débat à une seule cause."),
        ("C1", "Les habitants revendiquent un meilleur accès aux soins."),
        ("C1", "Sa chronique soulève une question plus large."),
    ],
    "en": [
        ("A1", "Hello, my name is Marie."),
        ("A1", "Thank you very much for your help."),
        ("A1", "I would like a coffee, please."),
        ("A2", "How are you today?"),
        ("A2", "Could you repeat that, please?"),
        ("B1", "I signed up for an evening class."),
        ("B2", "Environmental sustainability matters to the whole city."),
        ("C1", "The decision will have consequences for the neighbourhood."),
    ],
}


def _fallback(language: str, level: str) -> list[str]:
    rows = _FALLBACK.get(language, _FALLBACK["fr"])
    preferred = [text for lvl, text in rows if lvl == level]
    rest = [text for lvl, text in rows if lvl != level]
    return preferred + rest


def _generate(language: str, level: str, count: int, avoid: list[str]) -> list[str]:
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("no model configured")
    from gemini_service import _parse_json
    from tcf_ai_service import _gemini_generate
    lang = "French" if language.startswith("fr") else "English"
    blocked = ", ".join(avoid[-40:]) or "none"
    prompt = (
        f"Generate {count} short {lang} sentences a learner can read aloud for pronunciation practice "
        f"at CEFR {level}. Everyday Canadian or francophone life. No francs as currency. "
        f"Do not repeat or closely paraphrase: {blocked}. "
        'Return JSON: {"phrases": ["...", "..."]}.'
    )
    response = _gemini_generate(prompt, temperature=0.8, response_mime_type="application/json")
    payload = _parse_json(getattr(response, "text", "") or "{}")
    phrases = payload.get("phrases") if isinstance(payload, dict) else payload
    if not isinstance(phrases, list):
        return []
    return [str(item).strip() for item in phrases if str(item).strip()]


def take_prompts(language: str, level: str, count: int, learner: str | None = None) -> list[dict]:
    learner = learner or active_learner()
    language = (language or "fr").split("-")[0].lower()
    level = (level or "A2").upper()
    count = max(1, min(12, int(count)))
    avoid = content_bank.recent_labels(learner, "pronunciation", 80)
    produced: list[str] = []
    try:
        produced = _generate(language, level, count + 4, avoid)
    except Exception as error:
        logger.info("Pronunciation prompt generation fell back to the offline list: %s", error)
    candidates = produced + _fallback(language, level)
    chosen: list[dict] = []
    seen_norm: set[str] = set()
    for phrase in candidates:
        norm = dedupe.normalize_text(phrase)
        if not norm or norm in seen_norm:
            continue
        fp = dedupe.fingerprint(phrase)
        if content_bank.is_seen(learner, "pronunciation", fp, dedupe.simhash_of(phrase)):
            continue
        content_bank.remember(learner, "pronunciation", fp, dedupe.simhash_of(phrase), label=phrase[:240])
        seen_norm.add(norm)
        chosen.append({"text": phrase, "level": level, "language": language})
        if len(chosen) >= count:
            break
    if not chosen:
        raise RuntimeError("No new pronunciation prompts for this learner.")
    return chosen


def remember_prompt(text: str, language: str = "fr", learner: str | None = None) -> None:
    """Record a phrase the client showed from its own fallback, so it is not served again."""
    learner = learner or active_learner()
    phrase = (text or "").strip()
    if not phrase:
        return
    content_bank.remember(
        learner, "pronunciation", dedupe.fingerprint(phrase), dedupe.simhash_of(phrase), label=phrase[:240],
    )
