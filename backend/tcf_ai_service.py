"""
TCF Canada AI Service
=====================
Standalone AI service for the TCF Canada exam platform.
  - Reading: 39 questions, 4 CEFR-levelled parts (A1->C2)
  - Listening: 39 questions, progressive A1->C2 difficulty, with TTS audio
  - Writing: 3 tasks (short message, description, opinion+justification)
  - Speaking: 3 task types (basic_interaction, role_play, opinion)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import threading
import uuid
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Tuple

from dotenv import load_dotenv
from google import genai as genai_client
from google.genai import types

import answer_balance
import content_bank
import content_dedupe as dedupe
import topic_bank
from content_bank import DurablePool
from learner import active_learner
from schemas import TcfExamQuestion, ListeningQuestionResponse

load_dotenv()

logger = logging.getLogger("tcf.tts")

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")
ELEVENLABS_OUTPUT_FORMAT = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_22050_32")
ELEVENLABS_OPTIMIZE_LATENCY = int(os.getenv("ELEVENLABS_OPTIMIZE_LATENCY", "4"))
AUDIO_STORAGE_PATH = os.getenv(
    "AUDIO_STORAGE_PATH",
    os.path.join(os.path.dirname(__file__), "data", "audio")
)

# Low thinking keeps generation latency down; set GEMINI_THINKING_LEVEL=off to disable.
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "low").strip().lower()
_thinking_enabled = GEMINI_THINKING_LEVEL not in ("", "off", "none")
_shared_client: "genai_client.Client | None" = None


def _gemini_client() -> "genai_client.Client":
    global _shared_client
    if not API_KEY:
        raise RuntimeError("Missing API key. Set GEMINI_API_KEY in backend/.env.")
    if _shared_client is None:
        timeout_ms = int(os.getenv("GEMINI_TIMEOUT_MS", "120000"))
        _shared_client = genai_client.Client(
            api_key=API_KEY,
            http_options=types.HttpOptions(timeout=timeout_ms),
        )
    return _shared_client


def _gen_config(**kwargs: Any) -> "types.GenerateContentConfig":
    if _thinking_enabled:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=GEMINI_THINKING_LEVEL)
    return types.GenerateContentConfig(**kwargs)


def _gemini_generate(contents: Any, stream: bool = False, **config_kwargs: Any) -> Any:
    """generate_content with the shared client; drops thinking_config once if the model rejects it.

    Timeouts, 429s and 5xx are retried. A request the model rejects for content is not.
    """
    import resilience

    def once() -> Any:
        global _thinking_enabled
        method = _gemini_client().models.generate_content_stream if stream else _gemini_client().models.generate_content
        try:
            return method(model=MODEL_NAME, contents=contents, config=_gen_config(**config_kwargs))
        except Exception as error:
            if _thinking_enabled and "think" in str(error).lower():
                logging.getLogger(__name__).warning("Model rejected thinking_config (%s); disabling it.", error)
                _thinking_enabled = False
                return method(model=MODEL_NAME, contents=contents, config=_gen_config(**config_kwargs))
            raise

    return resilience.retry(once, attempts=4, base=0.4, cap=8.0)

# ── Shared scenario pools (reused for variety) ──────────────────────────────

DOMAINS = [
    "culture et arts",
    "voyage et géographie",
    "histoire",
    "vie quotidienne",
    "sciences et innovation",
    "santé et bien-être",
    "éducation",
    "travail et carrières",
    "environnement",
    "gastronomie"
]

SCENARIO_PLACES = [
    "Montréal", "Québec", "Ottawa", "Toronto", "Vancouver",
    "Lyon", "Marseille", "Toulouse", "Nantes", "Bordeaux"
]

SCENARIO_CONTEXTS = [
    "un centre communautaire",
    "une école municipale",
    "une bibliothèque",
    "une entreprise locale",
    "un service public",
    "une association culturelle",
    "un marché de quartier",
    "un hôpital",
    "un bureau administratif",
    "un parc urbain"
]

# Real examiner names used to avoid AI generating "[placeholder]" names
TCF_EXAMINER_NAMES = list(topic_bank.EXAMINERS)

def _pick_examiner(session_id: str | None) -> tuple[str, str]:
    """A name from the large pool. The same learner does not draw a name they just heard."""
    avoid: list[str] = []
    try:
        from learner import current_learner
        who = current_learner()
        if who:
            avoid = content_bank.recent_labels(who, "speaking_examiner", 12)
    except Exception:
        avoid = []
    name, title = topic_bank.pick_examiner(avoid)
    try:
        from learner import current_learner
        who = current_learner()
        if who:
            content_bank.remember(who, "speaking_examiner", dedupe.fingerprint(name), None, label=name)
    except Exception:
        pass
    return name, title


# TCF Canada expression orale, 3 tasks:
#   Tâche 1 — entretien dirigé (2 min, no preparation): the examiner asks the candidate about themselves.
#   Tâche 2 — exercice en interaction (2 min prep + 3 min 30): the examiner plays a role, the CANDIDATE asks
#             questions to obtain information.
#   Tâche 3 — expression d'un point de vue (4 min 30, no preparation): the candidate defends an opinion.
TCF_BASIC_INTERACTIONS = [
    "Présentation personnelle : parcours, famille et situation actuelle du candidat.",
    "Vie professionnelle ou études : métier, tâches quotidiennes, projets de carrière.",
    "Lieu de vie : ville ou quartier du candidat, ce qu'il apprécie et ce qu'il changerait.",
    "Loisirs et temps libre : activités préférées, sport, lectures, sorties.",
    "Projet d'installation au Canada : motivations, attentes et préparatifs.",
    "Habitudes du quotidien : journée type, alimentation, déplacements.",
    "Voyages et vacances : un voyage marquant et les destinations rêvées.",
    "Apprentissage du français : raisons, difficultés et méthodes du candidat.",
]

TCF_ROLE_PLAYS = [
    "Vous voulez vous inscrire à un cours de natation pour adultes. L'examinateur joue l'employé du centre sportif : posez-lui des questions (horaires, tarifs, niveau, matériel).",
    "Vous cherchez un appartement à louer. L'examinateur joue le propriétaire : renseignez-vous sur le logement, le loyer, les charges et la date de disponibilité.",
    "Vous souhaitez adopter un chien dans un refuge. L'examinateur joue le bénévole : informez-vous sur les conditions, les frais et le suivi.",
    "Vous voulez organiser une fête dans une salle municipale. L'examinateur joue l'agent de la mairie : demandez la capacité, le prix, les règles et la réservation.",
    "Un collègue organise un voyage d'équipe. L'examinateur joue ce collègue : posez des questions sur la destination, le programme, le budget et l'hébergement.",
    "Vous voulez suivre une formation en informatique le soir. L'examinateur joue le conseiller du centre : renseignez-vous sur le contenu, la durée, le prix et le certificat.",
    "Vous venez d'arriver dans un nouveau quartier. L'examinateur joue votre voisin : posez des questions sur les commerces, les transports et les activités du quartier.",
    "Vous voulez louer une voiture pour un week-end. L'examinateur joue l'agent de location : informez-vous sur les modèles, l'assurance, le kilométrage et le dépôt.",
]

TCF_OPINION_TOPICS = [
    "Le télétravail devrait-il devenir la norme pour tous les emplois de bureau ?",
    "Faut-il interdire les voitures dans le centre des grandes villes ?",
    "Les réseaux sociaux rapprochent-ils vraiment les gens ?",
    "Les transports en commun devraient-ils être entièrement gratuits ?",
    "Faut-il apprendre une deuxième langue dès l'école maternelle ?",
    "Les enfants devraient-ils avoir un téléphone portable avant 13 ans ?",
    "Vaut-il mieux vivre en ville ou à la campagne ?",
    "Faut-il limiter le tourisme dans les sites naturels les plus visités ?",
]

_SPEAKING_TASK_BRIEFS = {
    "basic_interaction": (
        "Tâche 1 du TCF Canada — entretien dirigé (2 minutes, sans préparation). "
        "Tu poses des questions simples et directes sur la vie du candidat (lui-même, sa famille, son travail, "
        "ses loisirs, sa ville, ses projets). Le candidat parle de lui ; toi tu poses une question à la fois."
    ),
    "role_play": (
        "Tâche 2 du TCF Canada — exercice en interaction (3 minutes 30). "
        "Tu JOUES le rôle indiqué dans la situation. C'est le CANDIDAT qui pose les questions pour obtenir des "
        "informations ; toi tu réponds de façon réaliste et précise (prix, horaires, conditions), puis tu l'invites "
        "brièvement à poursuivre (« Vous avez d'autres questions ? »). Ne pose pas de questions personnelles."
    ),
    "opinion": (
        "Tâche 3 du TCF Canada — expression d'un point de vue (4 minutes 30, sans préparation). "
        "Le candidat doit présenter et défendre son opinion avec des arguments et des exemples. Tu relances "
        "avec un contre-argument ou une demande de justification ou d'exemple."
    ),
}

_SPEAKING_STOPWORDS = {
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
    "le", "la", "les", "un", "une", "des", "de", "du", "au", "aux",
    "et", "ou", "mais", "en", "a", "à", "est", "suis", "sont",
    "etre", "être", "avoir", "pas", "ne", "non", "oui", "merci",
    "bonjour", "salut", "daccord", "ok", "okay"
}


# ── Deduplication caches (separate from other services) ─────────────────────


_last_domain: str | None = None


# ── Helpers ─────────────────────────────────────────────────────────────────

def _ensure_api_key() -> None:
    if not API_KEY:
        raise RuntimeError(
            "Missing API key. Set GEMINI_API_KEY in backend/.env."
        )


def _ensure_elevenlabs_config() -> None:
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("Missing ELEVENLABS_API_KEY for ElevenLabs TTS.")
    if not ELEVENLABS_VOICE_ID:
        raise RuntimeError("Missing ELEVENLABS_VOICE_ID for ElevenLabs TTS.")


def _generate_tts_audio(script: str, question_number: int, session_id: str | None) -> str:
    """Single-voice audio (speaking examiner replies). ElevenLabs within the shared cap, Gemini as fallback."""
    import tts_service

    os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)
    data: bytes
    ext = "mp3"
    if ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID:
        try:
            response = tts_service.elevenlabs_post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
                {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
                {
                    "text": script,
                    "model_id": "eleven_multilingual_v2",
                    "optimize_streaming_latency": ELEVENLABS_OPTIMIZE_LATENCY,
                    "output_format": ELEVENLABS_OUTPUT_FORMAT,
                },
                timeout=(5, 40),
            )
            data = tts_service.polish_mp3(response.content)
        except Exception as error:
            logger.warning("ElevenLabs TTS failed: %s. Falling back to Gemini TTS.", error)
            result = tts_service.synthesize_gemini(script, "fr-FR-female-1")
            data, ext = result["data"], result["extension"]
    else:
        result = tts_service.synthesize_gemini(script, "fr-FR-female-1")
        data, ext = result["data"], result["extension"]

    import audio_store
    file_name = f"tcf_audio_{question_number}_{session_id or 'global'}_{uuid.uuid4().hex[:8]}.{ext}"
    mime = "audio/wav" if ext == "wav" else "audio/mpeg"
    return audio_store.save(file_name, data, mime)


def _freshness_token() -> str:
    return uuid.uuid4().hex[:8]


def _scenario_from_seed(seed: str) -> Tuple[str, str]:
    rng = random.Random(seed)
    return rng.choice(SCENARIO_PLACES), rng.choice(SCENARIO_CONTEXTS)


def _pick_domain() -> str:
    global _last_domain
    choices = [d for d in DOMAINS if d != _last_domain]
    if not choices:
        choices = DOMAINS[:]
    selected = random.choice(choices)
    _last_domain = selected
    return selected


def _extract_json(text: str) -> Dict[str, Any]:
    import json
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", stripped)
    if not match:
        raise ValueError("Could not find JSON object in Gemini response.")
    return json.loads(match.group(0))


def _generate_json(prompt: str, temperature: float = 0.7) -> Dict[str, Any]:
    _ensure_api_key()
    try:
        response = _gemini_generate(prompt, temperature=temperature, response_mime_type="application/json")
    except Exception as error:
        raise RuntimeError(f"Gemini generate_content failed: {error}") from error
    if not getattr(response, "text", None):
        raise RuntimeError("Gemini returned an empty response.")
    return _extract_json(response.text)


def _generate_text(prompt: str, temperature: float = 0.4) -> str:
    _ensure_api_key()
    try:
        response = _gemini_generate(prompt, temperature=temperature)
    except Exception as error:
        raise RuntimeError(f"Gemini generate_content failed: {error}") from error
    if not getattr(response, "text", None):
        raise RuntimeError("Gemini returned an empty response.")
    return str(response.text).strip()


def _normalize_option(option: str, index: int) -> str:
    letters = ["A", "B", "C", "D"]
    clean = option.strip()
    if re.match(r"^[A-D][).:\-\s]+", clean, flags=re.IGNORECASE):
        return clean
    return f"{letters[index]}. {clean}"


def _normalize_listening_question(payload: Dict[str, Any]) -> Dict[str, Any]:
    options_raw = payload.get("options", [])
    options = [str(item) for item in options_raw][:4]
    while len(options) < 4:
        options.append("Option manquante")
    options = [_normalize_option(opt, i) for i, opt in enumerate(options)]
    raw_answer = str(payload.get("correct_answer", "")).strip().upper()
    match = re.match(r"([A-D])", raw_answer)
    normalized_answer = match.group(1) if match else "A"
    return {
        "script": str(payload.get("script", "")).strip(),
        "question": str(payload.get("question", "")).strip(),
        "options": options,
        "correct_answer": normalized_answer,
        "explanation": str(payload.get("explanation", "")).strip()
    }


def _fingerprint(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()




def _infer_cefr_from_question_number(question_number: int) -> str:
    from listening_service import level_for_question
    return level_for_question(question_number)


def _shuffle_answer_options(normalized: dict) -> dict:
    """Randomly reassign which position (A/B/C/D) holds the correct answer."""
    letters = ["A", "B", "C", "D"]
    options = normalized["options"][:]
    correct_letter = normalized["correct_answer"]

    correct_idx = letters.index(correct_letter)
    correct_text = options[correct_idx].split(". ", 1)[-1] if ". " in options[correct_idx] else options[correct_idx]

    texts = [opt.split(". ", 1)[-1] if ". " in opt else opt for opt in options]
    random.shuffle(texts)

    new_options = [f"{letters[i]}. {texts[i]}" for i in range(4)]
    new_correct_idx = texts.index(correct_text)
    new_correct_letter = letters[new_correct_idx]

    normalized["options"] = new_options
    normalized["correct_answer"] = new_correct_letter
    return normalized


def generate_tcf_listening_question(
    question_number: int,
    session_id: str | None = None,
    defer_audio: bool = False,
    target_level: str | None = None,
) -> ListeningQuestionResponse:
    """One unique TCF Canada listening question (see listening_service)."""
    from listening_service import get_question
    return get_question(question_number, session_id, defer_audio, target_level)


# ── Writing (official TCF Canada format) ────────────────────────────────────

WRITING_TASK_SPECS: dict[str, dict[str, Any]] = {
    "task1": {
        "label": "Tâche 1 — Message (décrire, raconter, expliquer)",
        "min_words": 60,
        "max_words": 120,
        "criteria": (
            "transmettre clairement les informations demandées au(x) destinataire(s), décrire / raconter / "
            "expliquer, registre adapté (tutoiement ou vouvoiement), formules d'ouverture et de clôture, "
            "correction de base"
        ),
    },
    "task2": {
        "label": "Tâche 2 — Article, courrier ou note (compte rendu ou récit + opinion argumentée)",
        "min_words": 120,
        "max_words": 150,
        "criteria": (
            "rendre compte d'un événement ou d'une expérience, exprimer et justifier une opinion avec des "
            "arguments, cohérence et cohésion (connecteurs), vocabulaire et structures adaptés au genre"
        ),
    },
    "task3": {
        "label": "Tâche 3 — Comparer deux points de vue puis prendre position",
        "min_words": 120,
        "max_words": 180,
        "criteria": (
            "synthétiser et comparer les deux points de vue des documents (40 à 60 mots) en reformulant sans "
            "recopier, puis défendre une position argumentée (80 à 120 mots), connecteurs logiques, richesse "
            "et précision lexicales, structures complexes maîtrisées"
        ),
    },
}

_WRITING_DEFAULT_SPEC: dict[str, Any] = {
    "label": "Tâche d'expression écrite",
    "min_words": 60,
    "max_words": 180,
    "criteria": "accomplissement de la tâche, cohérence, vocabulaire, correction grammaticale",
}

WRITING_THEMES = [
    "le logement et la colocation", "les transports en commun", "le travail à distance",
    "le bénévolat dans la communauté", "l'alimentation locale", "les réseaux sociaux",
    "l'apprentissage des langues", "le sport amateur", "les vacances en famille",
    "la vie de quartier", "les bibliothèques publiques", "le recyclage et les déchets",
    "les fêtes et traditions", "l'accueil des nouveaux arrivants", "la santé au travail",
    "les études à l'âge adulte", "le commerce en ligne", "les animaux de compagnie",
    "l'hiver canadien", "les parcs et espaces verts", "la sécurité routière",
    "le cinéma et les séries", "les jeux vidéo", "la consommation d'énergie",
    "les petits commerces", "le tourisme local", "la lecture chez les jeunes",
    "les horaires de travail", "le partage de voitures", "les jardins communautaires",
    "la musique en direct", "les objets de seconde main", "le téléphone à l'école",
    "les cours en ligne", "la cuisine maison", "les déménagements",
]

_writing_lock = threading.Lock()
_writing_recent_themes: deque[str] = deque(maxlen=18)
_writing_prompt_history: deque[str] = deque(maxlen=2000)
_writing_served_by_session: dict[str, deque[str]] = {}

_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-•*–—]|\d{1,2}[.)])\s+")
_INLINE_BULLET_SPLIT_RE = re.compile(r"\s+-\s+(?=[A-ZÀ-ÖØ-Ý«\"])")


def _count_words(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if w])


def _split_feedback(value: Any) -> list[str]:
    """Split model feedback into points without breaking hyphenated words (peut-être, est-ce)."""
    if isinstance(value, list):
        raw_items = [str(item) for item in value]
    else:
        raw_items = []
        for line in str(value or "").splitlines():
            stripped = line.strip()
            if stripped.startswith(("-", "•", "*")) and _INLINE_BULLET_SPLIT_RE.search(stripped):
                raw_items.extend(_INLINE_BULLET_SPLIT_RE.split(stripped))
            else:
                raw_items.append(line)
    items: list[str] = []
    for item in raw_items:
        clean = _BULLET_PREFIX_RE.sub("", item).strip()
        if clean:
            items.append(clean)
    return items


def _pick_writing_themes(count: int = 3) -> list[str]:
    with _writing_lock:
        recent = list(_writing_recent_themes)
    try:
        user_recent = content_bank.recent_labels(active_learner(), "writing_theme", 40)
    except Exception:
        user_recent = []
    chosen = topic_bank.pick_writing_themes(count, list(recent) + user_recent)
    with _writing_lock:
        _writing_recent_themes.extend(chosen)
    from learner import current_learner
    who = current_learner()
    if who:
        for theme in chosen:
            content_bank.remember(who, "writing_theme", dedupe.fingerprint(theme), None, label=theme[:240])
    return chosen


def _writing_tasks_prompt(themes: list[str]) -> str:
    import variety
    from learner import current_learner
    who = current_learner()
    form1 = variety.choose("writing_task1", variety.WRITING_TASK1_FORMS, who)
    form2 = variety.choose("writing_task2", variety.WRITING_TASK2_FORMS, who)
    return f"""Tu es concepteur officiel d'épreuves d'expression écrite du TCF Canada (France Éducation international).
Rédige UNE série complète de trois tâches, en français, au format officiel. Contexte canadien bienvenu.

Thèmes imposés (un par tâche, dans cet ordre) : 1) {themes[0]} ; 2) {themes[1]} ; 3) {themes[2]}.

Format officiel à respecter :
- Tâche 1 (60 à 120 mots) : rédiger {form1} adressé à un ou plusieurs destinataires
  nommés, pour décrire, raconter ou expliquer quelque chose. La consigne précise le destinataire et 2 ou 3 éléments
  à inclure.
- Tâche 2 (120 à 150 mots) : rédiger {form2} pour un lecteur précis (journal local,
  blogue, association…) qui rend compte d'un événement ou d'une expérience ET donne une opinion argumentée.
- Tâche 3 (120 à 180 mots) : deux courts documents (60 à 90 mots chacun) présentent deux points de vue OPPOSÉS sur
  le thème. La consigne demande : comparer les deux points de vue (40 à 60 mots), puis donner son opinion
  argumentée (80 à 120 mots). Inclure les deux documents DANS task3_prompt, sous la forme
  "Document 1 : …" puis "Document 2 : …", après la consigne.

Règles :
- Consignes naturelles et réalistes, vouvoiement du candidat, nombre de mots indiqué dans chaque consigne.
- Pas de jargon, situations de la vie courante, professionnelle ou citoyenne.
- Au Canada, les prix sont en dollars canadiens, jamais en francs.
- Sortie : JSON valide uniquement, sans Markdown :
{{
  "task1_prompt": "...",
  "task2_prompt": "...",
  "task3_prompt": "..."
}}
"""


def _generate_writing_task_set() -> dict[str, str]:
    """One brand-new task set: never repeats a prompt already generated by this process."""
    last_error: Exception | None = None
    for _ in range(3):
        themes = _pick_writing_themes()
        try:
            payload = _generate_json(_writing_tasks_prompt(themes), temperature=0.9)
        except Exception as error:
            last_error = error
            continue
        tasks = {key: str(payload.get(key, "")).strip() for key in ("task1_prompt", "task2_prompt", "task3_prompt")}
        if not all(tasks.values()):
            last_error = RuntimeError("Incomplete writing task set.")
            continue
        if "Document 1" not in tasks["task3_prompt"] or "Document 2" not in tasks["task3_prompt"]:
            last_error = RuntimeError("Task 3 is missing its two documents.")
            continue
        fingerprints = [_fingerprint(value) for value in tasks.values()]
        with _writing_lock:
            if any(fp in _writing_prompt_history for fp in fingerprints):
                last_error = RuntimeError("Duplicate writing prompt; regenerating.")
                continue
            _writing_prompt_history.extend(fingerprints)
        return tasks
    raise RuntimeError(f"Writing task generation failed: {last_error}") from last_error


def _writing_fingerprint(tasks: dict[str, str]) -> str:
    return dedupe.fingerprint("\n".join(tasks.get(key, "") for key in ("task1_prompt", "task2_prompt", "task3_prompt")))


_writing_task_pool = DurablePool(
    "writing_tasks",
    lambda _key: _generate_writing_task_set(),
    target=int(os.getenv("PREGEN_WRITING_TARGET", "5")),
    warm_keys=("all",),
    module="writing",
    fingerprint_of=_writing_fingerprint,
    simhash_of=lambda tasks: dedupe.simhash_of("\n".join(tasks.values())),
)


def _writing_session_served(session_id: str | None) -> deque[str]:
    with _writing_lock:
        return _writing_served_by_session.setdefault(session_id or "__anon__", deque(maxlen=200))


def _remember_writing(learner: str, tasks: dict[str, str]) -> None:
    content_bank.remember(learner, "writing", _writing_fingerprint(tasks), dedupe.simhash_of("\n".join(tasks.values())))
    for value in tasks.values():
        if _substantial(value):
            content_bank.remember(learner, "writing_task", dedupe.fingerprint(value), dedupe.simhash_of(value), label=value[:240])


def _substantial(text: str) -> bool:
    return len(dedupe.normalize_text(text).split()) >= 12


def _writing_blocked(learner: str, served: deque[str], tasks: dict[str, str]) -> bool:
    key = _writing_fingerprint(tasks)
    if key in served or content_bank.is_seen(learner, "writing", key, dedupe.simhash_of("\n".join(tasks.values()))):
        return True
    for value in tasks.values():
        if _substantial(value) and content_bank.is_seen(
            learner, "writing_task", dedupe.fingerprint(value), dedupe.simhash_of(value)
        ):
            return True
    return False


def generate_tcf_writing_tasks(session_id: str | None = None) -> dict[str, str]:
    """Serve a ready task set from the durable pool, or generate one. A learner never receives a prompt twice."""
    learner = active_learner(session_id)
    served = _writing_session_served(session_id)
    for _ in range(5):
        tasks = _writing_task_pool.take("all")
        if tasks is None:
            break
        if _writing_blocked(learner, served, tasks):
            continue
        served.append(_writing_fingerprint(tasks))
        _remember_writing(learner, tasks)
        return tasks
    last_error: Exception | None = None
    for _ in range(3):
        try:
            tasks = _generate_writing_task_set()
        except Exception as error:
            last_error = error
            continue
        if _writing_blocked(learner, served, tasks):
            last_error = RuntimeError("writing prompts already served")
            continue
        served.append(_writing_fingerprint(tasks))
        _remember_writing(learner, tasks)
        return tasks
    raise RuntimeError(f"No new writing tasks: {last_error}")


def assist_tcf_writing(
    action: str,
    message: str,
    direction: str | None = None,
    context: str | None = None
) -> str:
    clean = message.strip()
    if not clean:
        return "Veuillez fournir un texte pour continuer."
    prompt, temperature = _build_writing_prompt(action, clean, direction, context)
    if temperature == 0.0:
        return prompt
    return _generate_text(prompt, temperature=temperature).strip()


def _build_writing_prompt(action: str, message: str, direction: str | None, context: str | None) -> tuple[str, float]:
    clean = message.strip()
    context_block = f"\nContexte de la consigne :\n{context}\n" if context else ""

    if action == "translate":
        if direction == "en-fr":
            return (
                "Translate the following English text to French. "
                "Output only the French translation - no explanations, no labels.\n\n"
                f"English text:\n{clean}",
                0.2,
            )
        return (
            "Translate the following French text to English. "
            "Output only the English translation - no explanations, no labels.\n\n"
            f"French text:\n{clean}",
            0.2,
        )

    if action == "grammar":
        return (
            f"Tu es correcteur de français. Corrige la grammaire, l'orthographe et la ponctuation.\n"
            f"{context_block}Texte :\n{clean}\n\n"
            "Réponds d'abord avec la version corrigée, puis une courte liste (tirets) des principales corrections. "
            "N'utilise jamais LaTeX.",
            0.2,
        )

    if action == "suggestions":
        return (
            f"Tu es coach TCF Canada en expression écrite. Donne 3 à 5 suggestions concrètes et concises "
            f"pour améliorer la réponse.\n{context_block}Texte :\n{clean}\n\n"
            "Réponds par une liste simple (tirets), sans texte supplémentaire.",
            0.3,
        )

    if action == "example":
        return (
            f"Tu es examinateur TCF Canada. Génère un exemple de réponse claire et naturelle.\n"
            f"{context_block}Consigne ou sujet :\n{clean}\n\n"
            "Contraintes :\n- Respecte le nombre de mots demandé par la consigne (sinon 80 à 140 mots).\n"
            "- Français naturel et cohérent.\n- Pas de titres, pas de puces.\n\n"
            "Réponds uniquement avec l'exemple.",
            0.4,
        )

    return ("Action non prise en charge.", 0.0)


def stream_assist_tcf_writing(
    action: str,
    message: str,
    direction: str | None = None,
    context: str | None = None
):
    clean = message.strip()
    if not clean:
        yield "Veuillez fournir un texte pour continuer."
        return

    prompt, temperature = _build_writing_prompt(action, clean, direction, context)
    if temperature == 0.0:
        yield prompt
        return
    _ensure_api_key()
    for chunk in _gemini_generate(prompt, stream=True, temperature=temperature):
        token = getattr(chunk, "text", None)
        if token:
            yield token


# Evaluation is streamed in a line format so scores appear first and feedback fills in progressively.
_EVAL_SCORE_KEYS = {
    "structure": "STRUCTURE",
    "grammar": "GRAMMAIRE",
    "coherence": "COHERENCE",
    "vocab": "VOCABULAIRE",
}


def _strip_accents_upper(text: str) -> str:
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    ).upper()


def _writing_eval_prompt(task_type: str, prompt_text: str, response_text: str) -> str:
    spec = WRITING_TASK_SPECS.get(task_type, _WRITING_DEFAULT_SPEC)
    words = _count_words(response_text)
    return f"""Tu es correcteur certifié de l'expression écrite du TCF Canada. Tu évalues avec honnêteté et exigence,
comme un vrai examinateur : jamais de complaisance, jamais de note généreuse par défaut.

{spec['label']}
Longueur attendue : {spec['min_words']} à {spec['max_words']} mots. Longueur réelle : {words} mots.
Critères officiels : {spec['criteria']}.

Consigne :
{prompt_text}

Production du candidat :
{response_text}

Barème (chaque critère sur 10, ancré sur le CECRL) :
- 0-2 : A1 ou hors sujet ; communication très difficile.
- 3-4 : A2 ; message partiel, erreurs fréquentes qui gênent la compréhension, phrases simples juxtaposées.
- 5-6 : B1 ; tâche globalement réalisée, erreurs régulières mais compréhensible, vocabulaire courant et limité.
- 7-8 : B2 ; tâche bien réalisée, argumentation claire, erreurs peu nombreuses qui ne gênent pas.
- 9 : C1 ; aisance, précision, structures complexes maîtrisées, quasiment pas d'erreurs.
- 10 : C2 uniquement si la production est irréprochable et d'une grande finesse.
Règles d'honnêteté :
- Une production correcte mais ordinaire, sans erreurs graves, vaut 5 à 6 : pas davantage.
- Hors sujet ou consigne non respectée : 0 à 2 sur tous les critères.
- Moins de {spec['min_words']} mots : STRUCTURE au maximum 5.
- Chaque point à améliorer cite un extrait précis du texte et propose une correction.
- Le NIVEAU global est cohérent avec la moyenne des quatre notes.
- Stabilité : applique le barème de façon mécanique. Deux copies identiques reçoivent exactement les mêmes quatre notes.
  N'arrondis pas à la hausse et ne change pas une note d'une correction à l'autre.

Réponds EXACTEMENT dans ce format, en français, sans Markdown, sans LaTeX, sans rien avant ni après :
NIVEAU: <A1|A2|B1|B2|C1|C2>
STRUCTURE: <0-10>
GRAMMAIRE: <0-10>
COHERENCE: <0-10>
VOCABULAIRE: <0-10>
POINTS A AMELIORER:
- <3 à 6 points concrets>
VERSION AMELIOREE:
<version améliorée du texte, entre {spec['min_words']} et {spec['max_words']} mots>
"""


# Overall CEFR level is computed only from the four criterion scores (average out of 10), never taken from
# the model's own label, so the same scores always give the same level:
#   < 3 → A1 · 3–4.99 → A2 · 5–6.99 → B1 · 7–8.49 → B2 · 8.5–9.49 → C1 · ≥ 9.5 → C2
def _level_from_average(average: float) -> str:
    if average < 3:
        return "A1"
    if average < 5:
        return "A2"
    if average < 7:
        return "B1"
    if average < 8.5:
        return "B2"
    if average < 9.5:
        return "C1"
    return "C2"


def _evaluation_from_json(payload: dict) -> dict[str, Any] | None:
    scores = {
        "structure": payload.get("structure"),
        "grammar": payload.get("grammaire", payload.get("grammar")),
        "coherence": payload.get("coherence"),
        "vocab": payload.get("vocabulaire", payload.get("vocab")),
    }
    parsed_scores: dict[str, int | None] = {}
    for key, value in scores.items():
        if value is None or value == "":
            parsed_scores[key] = None
            continue
        try:
            parsed_scores[key] = max(0, min(10, round(float(value))))
        except (TypeError, ValueError):
            parsed_scores[key] = None
    level = str(payload.get("niveau") or payload.get("level") or "").strip().upper()
    if level not in _LEVELS:
        level = None
    feedback = payload.get("feedback") or payload.get("points") or []
    return {
        "level": level,
        "scores": parsed_scores,
        "feedback": _split_feedback(feedback),
        "improved_version": str(payload.get("improved_version") or payload.get("version_amelioree") or "").strip(),
        "complete": level is not None and all(v is not None for v in parsed_scores.values()),
    }


def parse_writing_evaluation_text(text: str) -> dict[str, Any]:
    """Parse the streamed line format, or a JSON object. `complete` tells if all scores were found."""
    stripped = (text or "").strip()
    if stripped.startswith("{"):
        import json
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            parsed = _evaluation_from_json(payload)
            if parsed and parsed["complete"]:
                return parsed
    level: str | None = None
    scores: dict[str, int | None] = {key: None for key in _EVAL_SCORE_KEYS}
    feedback_lines: list[str] = []
    improved_lines: list[str] = []
    section = ""
    for line in text.splitlines():
        if section == "improved":
            improved_lines.append(line)
            continue
        upper = _strip_accents_upper(line.strip())
        header = re.match(r"^([A-Z ]+?)\s*:\s*(.*)$", upper)
        if header:
            name, rest = header.group(1).strip(), header.group(2).strip()
            if name == "NIVEAU":
                found = re.search(r"\b(A1|A2|B1|B2|C1|C2)\b", rest)
                level = found.group(1) if found else level
                section = ""
                continue
            matched_score = next((k for k, label in _EVAL_SCORE_KEYS.items() if name == label), None)
            if matched_score:
                number = re.search(r"\d+(?:[.,]\d+)?", rest)
                if number:
                    scores[matched_score] = max(0, min(10, round(float(number.group(0).replace(",", ".")))))
                section = ""
                continue
            if name.startswith("POINTS"):
                section = "feedback"
                continue
            if name.startswith("VERSION AMELIOREE"):
                section = "improved"
                original_rest = line.split(":", 1)[1].strip() if ":" in line else ""
                if original_rest:
                    improved_lines.append(original_rest)
                continue
        if section == "feedback":
            feedback_lines.append(line)
    return {
        "level": level,
        "scores": scores,
        "feedback": _split_feedback("\n".join(feedback_lines)),
        "improved_version": "\n".join(improved_lines).strip(),
        # The level is computed from the scores, so only the four scores are required.
        "complete": all(v is not None for v in scores.values()),
    }


def _empty_writing_evaluation() -> dict[str, object]:
    return {
        "level": "A1",
        "scores": {key: 0 for key in _EVAL_SCORE_KEYS},
        "feedback": ["Aucune production : rédigez votre réponse avant de demander une évaluation."],
        "improved_version": "",
    }


def _apply_writing_guards(result: dict[str, Any], task_type: str, response_text: str) -> dict[str, object]:
    spec = WRITING_TASK_SPECS.get(task_type, _WRITING_DEFAULT_SPEC)
    scores = {key: int(result["scores"].get(key) or 0) for key in _EVAL_SCORE_KEYS}
    words = _count_words(response_text)
    if words < spec["min_words"] * 0.5:
        scores = {key: min(value, 4) for key, value in scores.items()}
    elif words < spec["min_words"]:
        scores["structure"] = min(scores["structure"], 5)
    level = _level_from_average(sum(scores.values()) / len(scores))
    feedback = [str(item) for item in result.get("feedback") or []]
    if words < spec["min_words"]:
        feedback.insert(0, f"Longueur insuffisante : {words} mots pour {spec['min_words']} à {spec['max_words']} attendus.")
    elif words > spec["max_words"] * 1.2:
        feedback.insert(0, f"Texte trop long : {words} mots pour {spec['min_words']} à {spec['max_words']} attendus.")
    return {
        "level": level,
        "scores": scores,
        "feedback": feedback,
        "improved_version": str(result.get("improved_version") or "").strip(),
    }


_EVAL_SEED = 1729
_WRITING_EVAL_TEMPERATURE = float(os.getenv("WRITING_EVAL_TEMPERATURE", "0"))


def stream_writing_evaluation_tokens(task_type: str, prompt_text: str, response_text: str):
    """
    Streams the evaluation text. The same submission always gets the same evaluation: an identical
    (task, prompt, text) replays the cached result; otherwise sampling is deterministic (temperature 0, fixed seed).
    """
    if not response_text.strip():
        return
    cached = content_bank.get_writing_eval(content_bank.writing_eval_key(task_type, prompt_text, response_text))
    if cached and cached.get("raw_text"):
        yield from _without_model_level([cached["raw_text"]])
        return
    _ensure_api_key()
    chunks = _gemini_generate(
        _writing_eval_prompt(task_type, prompt_text, response_text),
        stream=True,
        temperature=_WRITING_EVAL_TEMPERATURE,
        seed=_EVAL_SEED,
    )
    yield from _without_model_level(getattr(chunk, "text", None) or "" for chunk in chunks)


_MODEL_LEVEL_LINE = re.compile(r"^\s*NIVEAU\s*:", re.IGNORECASE)


def _without_model_level(tokens):
    """Line-buffered pass-through that drops the model's own NIVEAU line: the level shown is always the one
    computed from the scores, so the student never sees one level while streaming and another at the end."""
    pending = ""
    for token in tokens:
        pending += token
        while "\n" in pending:
            line, pending = pending.split("\n", 1)
            if not _MODEL_LEVEL_LINE.match(line):
                yield line + "\n"
    if pending and not _MODEL_LEVEL_LINE.match(pending):
        yield pending


def finalize_writing_evaluation(
    streamed_text: str, task_type: str, prompt_text: str, response_text: str
) -> dict[str, object]:
    """Normalize the streamed evaluation; one non-streamed retry if the stream was malformed.

    The first successful score for a given task, prompt and response is stored and reused, so a
    second correction of the same text cannot drift from B1 to B2.
    """
    if not response_text.strip():
        return _empty_writing_evaluation()
    cache_key = content_bank.writing_eval_key(task_type, prompt_text, response_text)
    cached = content_bank.get_writing_eval(cache_key)
    if cached and cached.get("result"):
        return cached["result"]
    parsed = parse_writing_evaluation_text(streamed_text)
    raw_text = streamed_text
    if not parsed["complete"]:
        raw_text = _gemini_text_deterministic(_writing_eval_prompt(task_type, prompt_text, response_text))
        retry = parse_writing_evaluation_text(raw_text)
        if not retry["complete"]:
            raise RuntimeError("Writing evaluation could not be parsed.")
        parsed = retry
    result = _apply_writing_guards(parsed, task_type, response_text)
    content_bank.put_writing_eval(cache_key, raw_text, result)
    return result


def _gemini_text_deterministic(prompt: str) -> str:
    _ensure_api_key()
    response = _gemini_generate(prompt, temperature=_WRITING_EVAL_TEMPERATURE, seed=_EVAL_SEED)
    text = getattr(response, "text", None)
    if not text:
        raise RuntimeError("Gemini returned an empty response.")
    return str(text).strip()


def evaluate_tcf_writing_task(
    task_type: str,
    prompt_text: str,
    response_text: str
) -> dict[str, object]:
    """Evaluate a TCF Canada writing submission. task_type: 'task1' | 'task2' | 'task3'."""
    if not response_text.strip():
        return _empty_writing_evaluation()
    text = "".join(stream_writing_evaluation_tokens(task_type, prompt_text, response_text))
    return finalize_writing_evaluation(text, task_type, prompt_text, response_text)


def _writing_step_prompt(task_type: str, step: str, prompt_text: str, text: str) -> str:
    spec = WRITING_TASK_SPECS.get(task_type, _WRITING_DEFAULT_SPEC)
    return f"""Tu es coach TCF Canada en expression écrite. Donne un retour honnête et précis sur une étape de rédaction.

{spec['label']}
Étape : {step}
Consigne :
{prompt_text}

Brouillon du candidat pour cette étape :
{text}

Réponds EXACTEMENT dans ce format, en français, sans Markdown ni LaTeX :
- <2 à 4 points concis : cite l'extrait concerné et propose la correction>
VERSION AMELIOREE:
<version légèrement améliorée de cette étape>
"""


def stream_writing_step_feedback(task_type: str, step: str, prompt_text: str, text: str):
    if not text.strip():
        yield "- Écrivez quelques phrases pour cette étape avant de demander un retour."
        return
    _ensure_api_key()
    for chunk in _gemini_generate(_writing_step_prompt(task_type, step, prompt_text, text), stream=True, temperature=0.3):
        token = getattr(chunk, "text", None)
        if token:
            yield token


def parse_writing_step_feedback(text: str) -> dict[str, object]:
    parts = re.split(r"(?im)^\s*VERSION\s+AM[ÉE]LIOR[ÉE]E\s*:\s*", text, maxsplit=1)
    feedback = _split_feedback(parts[0])
    improved = parts[1].strip() if len(parts) > 1 else ""
    return {"feedback": feedback, "improved_version": improved}


def evaluate_tcf_writing_step(
    task_type: str,
    step: str,
    prompt_text: str,
    text: str
) -> dict[str, object]:
    result = parse_writing_step_feedback("".join(stream_writing_step_feedback(task_type, step, prompt_text, text)))
    if not result["feedback"]:
        result["feedback"] = ["Retour indisponible pour cette étape. Réessayez dans un instant."]
    return result


def _speaking_candidate_text(history: list[dict[str, str]]) -> str:
    return " ".join(
        str(item.get("content", "")).strip()
        for item in history
        if item.get("role") == "user"
    ).strip()


def _speaking_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", text.lower())


def _is_speaking_low_response(text: str) -> tuple[bool, str]:
    tokens = _speaking_tokens(text)
    if not tokens:
        return True, "empty"
    if len(tokens) < 5:
        return True, "too_short"
    content_words = [w for w in tokens if w not in _SPEAKING_STOPWORDS and len(w) > 2]
    if len(content_words) < 2:
        return True, "irrelevant"
    return False, ""


_SPEAKING_TOPIC_LISTS = {
    "basic_interaction": TCF_BASIC_INTERACTIONS,
    "role_play": TCF_ROLE_PLAYS,
    "opinion": TCF_OPINION_TOPICS,
}


def _resolve_examiner(examiner_name: str | None, session_id: str | None) -> tuple[str, str]:
    if examiner_name:
        for name, title in TCF_EXAMINER_NAMES:
            if name == examiner_name:
                return name, title
    return _pick_examiner(session_id)


def _build_speaking_prompt(
    message: str,
    history: list[dict[str, str]],
    task_type: str,
    mode: str,
    hints: bool,
    session_id: str | None,
    session_topic: str | None,
    examiner_name: str | None = None,
) -> tuple[str, str, str]:
    """Return (prompt, chosen_topic, examiner_name) for the examiner's next turn."""
    chosen_topic = session_topic if session_topic else topic_bank.speaking_topic(task_type)
    task_brief = _SPEAKING_TASK_BRIEFS.get(task_type, _SPEAKING_TASK_BRIEFS["opinion"])
    name, title = _resolve_examiner(examiner_name, session_id)

    is_start = message == "__START__"
    message_text = "" if is_start else message

    history_text = "\n".join(
        f"{'Candidat' if m['role'] == 'user' else name}: {m['content']}"
        for m in history
    )
    asked_questions = [m["content"] for m in history if m.get("role") == "assistant"]
    asked_block = (
        "\n\nRépliques déjà prononcées (NE PAS RÉPÉTER) :\n" +
        "\n".join(f"- {q[:120]}" for q in asked_questions[-6:])
        if asked_questions else ""
    )
    hint_instruction = (
        "\nSi le candidat semble bloqué, glisse une piste courte et discrète."
        if hints else ""
    )
    exam_instruction = (
        "\nMode examen : reste neutre et formel, n'aide pas le candidat et ne le corrige pas."
        if mode == "exam" else ""
    )

    if is_start:
        if task_type == "role_play":
            task_opening = (
                f"Ouvre l'échange : salue le candidat en te présentant (« Bonjour, je m'appelle {name}. »), "
                f"rappelle la situation en une phrase ({chosen_topic}) puis indique que tu joues ton rôle et "
                "invite-le à te poser ses questions."
            )
        else:
            task_opening = (
                f"Ouvre l'échange : « Bonjour, je m'appelle {name}, je suis votre {title} aujourd'hui. » "
                f"Puis pose UNE seule question claire pour lancer le sujet : {chosen_topic}"
            )
    elif task_type == "role_play":
        task_opening = (
            "Continue la conversation dans ton rôle. Réponds précisément à la DERNIÈRE question du candidat "
            "avec des informations réalistes et cohérentes avec ce que tu as déjà dit."
        )
    else:
        task_opening = (
            "Continue la conversation. Pose UNE question de suivi précise basée sur la DERNIÈRE réponse du candidat. "
            "Si la réponse est courte ou vague, demande une précision ou un exemple. "
            "Si la réponse est bonne, approfondis un aspect du sujet."
        )

    prompt = f"""Tu es {name}, {title} TCF Canada.
{task_brief}
Sujet de la session : {chosen_topic}
{exam_instruction}
{hint_instruction}

RÈGLES ABSOLUES :
- Utilise toujours ton vrai nom : {name}. Jamais de crochets ni de placeholders comme [nom].
- Ne répète jamais une réplique déjà prononcée.
- Reste strictement sur le sujet de la session.
- 1 à 2 phrases maximum, ton naturel et humain, français standard.
{asked_block}

{task_opening}

Historique :
{history_text}

Candidat : {message_text}

Réponds uniquement en tant que {name} (1-2 phrases). Texte brut uniquement, sans guillemets autour de ta réponse.
"""
    return prompt, chosen_topic, name


def _trim_speaking_reply(reply_text: str) -> str:
    reply_text = reply_text.strip().strip('"«» ').strip()
    max_chars = int(os.getenv("SPEAKING_MAX_CHARS", "600"))
    if len(reply_text) > max_chars:
        reply_text = reply_text[:max_chars].rsplit(".", 1)[0] + "."
    return reply_text


def speaking_reply_audio(reply_text: str, session_id: str | None) -> str | None:
    try:
        return _generate_tts_audio(reply_text, 0, session_id)
    except Exception as error:
        logging.getLogger(__name__).warning("Speaking reply TTS failed: %s", error)
        return None


def generate_tcf_speaking_reply(
    message: str,
    history: list[dict[str, str]],
    task_type: str,
    mode: str = "practice",
    hints: bool = False,
    session_id: str | None = None,
    session_topic: str | None = None,
    examiner_name: str | None = None,
) -> dict[str, object]:
    """Examiner reply for TCF Canada speaking. task_type: 'basic_interaction' | 'role_play' | 'opinion'."""
    prompt, chosen_topic, name = _build_speaking_prompt(
        message, history, task_type, mode, hints, session_id, session_topic, examiner_name
    )
    reply_text = _trim_speaking_reply(_generate_text(prompt, temperature=0.75))
    return {
        "reply": reply_text,
        "audio_url": speaking_reply_audio(reply_text, session_id),
        "session_topic": chosen_topic,
        "examiner_name": name,
    }


def stream_tcf_speaking_reply(
    message: str,
    history: list[dict[str, str]],
    task_type: str,
    mode: str = "practice",
    hints: bool = False,
    session_id: str | None = None,
    session_topic: str | None = None,
    examiner_name: str | None = None,
):
    """
    Yield ("meta", {...}) first, then ("token", str) chunks of the examiner reply, then ("reply", full_text).
    Audio is produced by the caller once the full text is known.
    """
    prompt, chosen_topic, name = _build_speaking_prompt(
        message, history, task_type, mode, hints, session_id, session_topic, examiner_name
    )
    yield "meta", {"session_topic": chosen_topic, "examiner_name": name}
    _ensure_api_key()
    parts: list[str] = []
    for chunk in _gemini_generate(prompt, stream=True, temperature=0.75):
        token = getattr(chunk, "text", None)
        if token:
            parts.append(token)
            yield "token", token
    yield "reply", _trim_speaking_reply("".join(parts))


def generate_tcf_speaking_opening(task_type: str, avoid_topics: list[str] | None = None) -> dict[str, object]:
    """
    A fresh session opening for the pre-generation pool: new topic + examiner's first line + audio,
    in one Gemini call. Falls back to the curated topic list when the model output is unusable.
    """
    name, title = _pick_examiner(None)
    brief = _SPEAKING_TASK_BRIEFS.get(task_type, _SPEAKING_TASK_BRIEFS["opinion"])
    import variety
    from learner import current_learner
    situation = variety.choose(
        f"speaking:{task_type}",
        variety.SPEAKING_SITUATIONS.get(task_type, variety.SPEAKING_SITUATIONS["opinion"]),
        current_learner(),
    )
    examples = "\n".join(f"- {topic_bank.speaking_topic(task_type)}" for _ in range(4))
    avoid = ""
    if avoid_topics:
        avoid = "\nSujets déjà utilisés (en choisir un TOUT AUTRE) :\n" + "\n".join(f"- {t[:140]}" for t in avoid_topics[-25:])
    if task_type == "role_play":
        opening_rule = (
            f"opening : salue (« Bonjour, je m'appelle {name}. »), rappelle la situation en une phrase, "
            "dis quel rôle tu joues et invite le candidat à te poser ses questions."
        )
    else:
        opening_rule = (
            f"opening : « Bonjour, je m'appelle {name}, je suis votre {title} aujourd'hui. » "
            "suivi d'UNE seule question claire qui lance le sujet."
        )
    prompt = f"""Tu es {name}, {title} TCF Canada. {brief}

Crée une NOUVELLE situation d'examen réaliste (contexte canadien ou francophone, vie courante, niveau B1-B2).
Forme à privilégier cette fois : {situation}.
dans le même style que ces exemples :
{examples}{avoid}

Réponds en JSON :
{{
  "topic": "la situation ou la question du sujet, en une phrase, en français correct avec accents",
  "opening": "ta première réplique (1-2 phrases)"
}}
Règles : {opening_rule} Pas de crochets ni de placeholders. JSON valide uniquement."""
    payload = _generate_json(prompt, temperature=0.95)
    topic = str(payload.get("topic", "")).strip()
    opening = _trim_speaking_reply(str(payload.get("opening", "")))
    if len(topic) < 15 or len(opening) < 15 or "[" in opening:
        raise RuntimeError("Speaking opening generation returned unusable content.")
    audio_url = speaking_reply_audio(opening, None)
    if not audio_url:
        raise RuntimeError("Speaking opening audio could not be generated.")
    return {"reply": opening, "audio_url": audio_url, "session_topic": topic, "examiner_name": name}


_SPEAKING_LOW_FEEDBACK = {
    "empty": ["Aucune réponse détectée.", "Répondez en phrases complètes."],
    "too_short": ["Votre réponse est trop courte.", "Ajoutez au moins deux idées et un exemple."],
    "irrelevant": ["La réponse est hors sujet ou trop vague.", "Reformulez en répondant directement à la question."],
}

_SPEAKING_TASK_LABELS = {
    "basic_interaction": "Tâche 1 — entretien dirigé (le candidat parle de lui : présentation, vie quotidienne, projets)",
    "role_play": "Tâche 2 — exercice en interaction (le candidat pose des questions pour obtenir des informations)",
    "opinion": "Tâche 3 — expression d'un point de vue (le candidat défend une opinion argumentée)",
}


def speaking_low_response_evaluation(history: list[dict[str, str]]) -> dict[str, object] | None:
    """Fixed low score for empty, very short or off-topic candidate speech (no model call)."""
    is_low, low_reason = _is_speaking_low_response(_speaking_candidate_text(history))
    if not is_low:
        return None
    return {
        "fluency": 1,
        "grammar": 1,
        "vocabulary": 1,
        "interaction": 1,
        "feedback": _SPEAKING_LOW_FEEDBACK.get(low_reason, _SPEAKING_LOW_FEEDBACK["too_short"]),
        "improved_response": "Essayez une réponse plus complète et directement liée au sujet.",
        "cefr_level": "A1",
    }


def _speaking_history_text(history: list[dict[str, str]]) -> str:
    return "\n".join(
        f"{'Candidat' if m['role'] == 'user' else 'Examinateur'}: {m['content']}"
        for m in history
    )


def _speaking_scores(history: list[dict[str, str]], task_type: str, with_improved: bool) -> dict[str, object]:
    task_label = _SPEAKING_TASK_LABELS.get(task_type, task_type)
    improved_field = '  "improved_response": "une meilleure réponse modèle du candidat, en français",\n' if with_improved else ""
    prompt = f"""Tu es évaluateur certifié du TCF Canada pour l'expression orale.

{task_label}

Conversation (transcription automatique de la parole) :
{_speaking_history_text(history)}

Évalue UNIQUEMENT les répliques du candidat, selon la grille du TCF Canada : réalisation de la tâche,
aisance et cohérence, étendue et maîtrise du lexique, correction grammaticale, interaction.
Sois honnête et exigeant : un candidat B1 n'obtient pas 9/10. Note de 0 à 10 :
- 0-2 : A1 ou hors sujet ; 3-4 : A2 ; 5-6 : B1 ; 7-8 : B2 ; 9 : C1 ; 10 : C2.

JSON :
{{
  "fluency": 0-10,
  "grammar": 0-10,
  "vocabulary": 0-10,
  "interaction": 0-10 (réalisation de la tâche et qualité de l'échange),
  "cefr_level": "A1|A2|B1|B2|C1|C2 (niveau global estimé)",
  "feedback": ["3 à 5 remarques concrètes en français, citant des mots du candidat"],
{improved_field}}}
JSON valide uniquement."""
    payload = _generate_json(prompt, temperature=0.2)

    def _clamp(v: object) -> int:
        try:
            return max(0, min(10, int(round(float(v)))))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    feedback = payload.get("feedback", [])
    if isinstance(feedback, str):
        feedback = [item.strip(" -•") for item in feedback.splitlines() if item.strip(" -•")]
    feedback = [str(item).strip() for item in feedback if str(item).strip()]
    level = str(payload.get("cefr_level", "")).strip().upper()[:2]
    return {
        "fluency": _clamp(payload.get("fluency")),
        "grammar": _clamp(payload.get("grammar")),
        "vocabulary": _clamp(payload.get("vocabulary")),
        "interaction": _clamp(payload.get("interaction")),
        "feedback": feedback,
        "improved_response": str(payload.get("improved_response", "")).strip(),
        "cefr_level": level if level in {"A1", "A2", "B1", "B2", "C1", "C2"} else None,
    }


def evaluate_tcf_speaking_conversation(
    history: list[dict[str, str]],
    task_type: str
) -> dict[str, object]:
    """Evaluate a complete TCF Canada speaking session (all candidate turns together)."""
    low = speaking_low_response_evaluation(history)
    if low is not None:
        return low
    return _speaking_scores(history, task_type, with_improved=True)


def speaking_scores_without_model_answer(history: list[dict[str, str]], task_type: str) -> dict[str, object]:
    return _speaking_scores(history, task_type, with_improved=False)


def stream_speaking_model_answer(history: list[dict[str, str]], task_type: str):
    """Stream an improved model answer for the candidate's last turns, in French."""
    task_label = _SPEAKING_TASK_LABELS.get(task_type, task_type)
    prompt = f"""Tu es professeur de français et prépares au TCF Canada (expression orale).
{task_label}

Conversation :
{_speaking_history_text(history)}

Écris une réponse modèle de niveau B2 que le candidat aurait pu donner à la DERNIÈRE question de l'examinateur,
en reprenant ses idées mais avec une langue correcte, des connecteurs et un exemple. 4 à 6 phrases, texte brut,
sans titre ni guillemets."""
    _ensure_api_key()
    for chunk in _gemini_generate(prompt, stream=True, temperature=0.5):
        token = getattr(chunk, "text", None)
        if token:
            yield token


# ── Shared utility functions (dictionary, passage, learn) ───────────────────

def explain_text(text: str) -> Dict[str, str]:
    clean = text.strip()
    prompt = f"""Explique ce texte francais clairement pour un apprenant TCF.

Retourne un JSON avec :
meaning
explanation
translation
example

Texte : {clean}

Regles :
- meaning : 1 a 2 phrases simples en francais.
- explanation : explication courte en francais, vocabulaire accessible.
- translation : courte traduction en anglais.
- example : phrase d'exemple simple en francais.
- Sortie : JSON valide uniquement.
"""
    payload = _generate_json(prompt, temperature=0.4)
    return {
        "meaning": str(payload.get("meaning", "")).strip(),
        "explanation": str(payload.get("explanation", "")).strip(),
        "translation": str(payload.get("translation", "")).strip(),
        "example": str(payload.get("example", "")).strip(),
    }


def _translate_prompt(text: str, direction: str = "fr-en") -> str:
    if direction == "en-fr":
        return (
            "Translate the following English text to natural French. "
            "Output only the French translation — no explanations, no labels.\n\n"
            f"English text:\n{text}"
        )
    return (
        "Translate the following French text to English. "
        "Output only the English translation — no explanations, no labels.\n\n"
        f"French text:\n{text}"
    )


def translate_passage(text: str) -> str:
    return _generate_text(_translate_prompt(text.strip()), temperature=0.2).strip()


def stream_translate(text: str, direction: str = "fr-en"):
    clean = text.strip()
    if not clean:
        return
    _ensure_api_key()
    for chunk in _gemini_generate(_translate_prompt(clean, direction), stream=True, temperature=0.2):
        token = getattr(chunk, "text", None)
        if token:
            yield token


def stream_explain_text(text: str):
    """Phrase Helper explanation streamed as short Markdown sections (renders progressively in the UI)."""
    clean = text.strip()
    if not clean:
        return
    prompt = f"""Tu aides un apprenant qui prépare le TCF Canada. Explique ce mot, cette expression ou ce passage français.

Texte : « {clean} »

Réponds EXACTEMENT avec ces quatre sections, dans cet ordre, en Markdown simple, sans LaTeX ni rien d'autre :
**Sens** : 1 à 2 phrases simples en français.
**Explication** : usage, registre et nuance, en français accessible (2 à 3 phrases).
**Traduction** : traduction anglaise courte.
**Exemple** : une phrase d'exemple naturelle en français.
"""
    _ensure_api_key()
    for chunk in _gemini_generate(prompt, stream=True, temperature=0.4):
        token = getattr(chunk, "text", None)
        if token:
            yield token


def explain_word(word: str) -> Any:
    from schemas import WordMeaningResponse
    clean = word.strip()
    prompt = f"""Explique le mot ou l'expression francais pour un apprenant niveau B2.

Retourne un JSON avec :
word
part_of_speech
definition_simple
french_explanation
english_translation
example_sentence
synonyms

Mot ou expression : {clean}

Regles :
- Sorties concises et adaptees aux apprenants.
- example_sentence doit etre en francais.
- synonyms : tableau JSON de 3 a 6 synonymes en francais.
- Le champ "word" doit correspondre exactement a : {clean}
- Sortie : JSON valide uniquement.
"""
    payload = _generate_json(prompt, temperature=0.4)
    synonyms = payload.get("synonyms", [])
    if isinstance(synonyms, str):
        synonyms = [s.strip() for s in synonyms.split(",") if s.strip()]
    payload["synonyms"] = [str(s).strip() for s in synonyms]
    payload["word"] = clean
    try:
        return WordMeaningResponse.model_validate(payload)
    except Exception as error:
        raise RuntimeError(f"Word lookup validation failed: {error}") from error


def generate_tcf_listening_audio(script: str, question_number: int, session_id: str | None = None) -> str:
    """Audio for a listening script (one voice per speaker for dialogues)."""
    from listening_service import synthesize_listening_audio
    return synthesize_listening_audio(script)


def learn_question_fingerprint(question: str) -> str:
    return re.sub(r"[^a-z0-9À-ɏ]", "", (question or "").lower())


def _extract_exercise_list(payload: Any) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("exercises", "items", "data"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def _exclusion_block(exclude_questions: "list[str] | tuple[str, ...]") -> str:
    recent = [q.strip() for q in exclude_questions if q and q.strip()][-40:]
    if not recent:
        return "Questions déjà posées : aucune."
    return "Questions déjà posées (à ne pas répéter) :\n" + "\n".join(f"- {q[:160]}" for q in recent)


def _drop_repeated(exercises: list[Dict[str, Any]], exclude_questions) -> list[Dict[str, Any]]:
    seen = {learn_question_fingerprint(q) for q in exclude_questions if q}
    unique: list[Dict[str, Any]] = []
    for ex in exercises:
        fp = learn_question_fingerprint(str(ex.get("question", "")) + str(ex.get("incorrect", "")))
        if fp and fp not in seen:
            seen.add(fp)
            unique.append(ex)
    return unique


def generate_learn_overview(text: str) -> Dict[str, Any]:
    """Fast first phase of the analysis: topic, level, summary, key points, vocabulary."""
    prompt = f"""Tu es un tuteur TCF Canada. Analyse ce texte français.

Texte :
{text.strip()}

Retourne un JSON :
{{
  "topic": "sujet en quelques mots",
  "level": "A1, A2, B1, B2, C1 ou C2",
  "summary": "résumé en 2-3 phrases",
  "key_points": ["point 1", "point 2", "point 3"],
  "vocabulary": [{{"word": "...", "definition": "...", "example": "..."}}]
}}

Règles : tout en français ; 3 à 5 points clés ; 3 à 5 mots de vocabulaire avec définition et exemple. JSON valide uniquement."""
    payload = _generate_json(prompt, temperature=0.5)
    vocab = payload.get("vocabulary", [])
    vocab = [
        {"word": str(v.get("word", "")).strip(), "definition": str(v.get("definition", "")).strip(), "example": str(v.get("example", "")).strip()}
        for v in vocab if isinstance(v, dict) and str(v.get("word", "")).strip()
    ] if isinstance(vocab, list) else []
    return {
        "topic": str(payload.get("topic", "")).strip(),
        "level": str(payload.get("level", "B1")).strip() or "B1",
        "summary": str(payload.get("summary", "")).strip(),
        "key_points": [str(p).strip() for p in payload.get("key_points", []) if str(p).strip()],
        "vocabulary": vocab,
    }


# ── Exercise generation: one small model call per exercise, all five in parallel ──
# A single call writing all five exercises took ~20 s; five small calls finish in about the time of one.

def _scrub_learn_exercises(exercises: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    import quality_guard
    cleaned: list[Dict[str, Any]] = []
    for exercise in exercises:
        item = dict(exercise)
        if item.get("explanation"):
            item["explanation"] = quality_guard.scrub_letter_citations(str(item["explanation"]))
        cleaned.append(item)
    return cleaned


def _grammar_focus() -> str:
    import variety
    from learner import current_learner
    return variety.choose("grammar", variety.GRAMMAR_FOCI, current_learner())

_LEARN_SLOT_EXECUTOR = ThreadPoolExecutor(max_workers=12, thread_name_prefix="learn-slot")

_LEARN_SLOTS: list[tuple[str, str]] = [
    ("mcq", "Un QCM de compréhension avec 4 options ; la bonne réponse est sur la lettre {letter} ; "
            "les 3 distracteurs sont plausibles et s'appuient sur des détails réels."),
    ("sentence_correction", "Une phrase liée au thème contenant UNE seule faute de grammaire ou d'orthographe "
                            "(accord, conjugaison, préposition…)."),
    ("writing_task", "Une consigne d'écriture courte (3 à 4 phrases) qui fait réutiliser les idées du thème."),
    ("speaking_prompt", "Une consigne orale (1 à 2 minutes) qui demande un avis personnel argumenté."),
    ("writing_task", "Une consigne d'écriture DIFFÉRENTE de la précédente : un courriel ou un message de 4 à 5 "
                     "phrases adressé à une personne précise."),
]


def _learn_slot_example(exercise_type: str, letter: str) -> str:
    examples = {
        "mcq": {"type": "mcq", "question": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
                "correct_answer": letter, "explanation": "..."},
        "sentence_correction": {"type": "sentence_correction", "question": "Corrigez cette phrase",
                                "incorrect": "...", "correct_answer": "...", "explanation": "..."},
        "writing_task": {"type": "writing_task", "question": "...", "correct_answer": "réponse modèle",
                         "explanation": "ce qui est attendu"},
        "speaking_prompt": {"type": "speaking_prompt", "question": "...", "correct_answer": "points clés attendus",
                            "explanation": "critères d'évaluation"},
    }
    return json.dumps(examples[exercise_type], ensure_ascii=False)


def _valid_slot(exercise_type: str, payload: Any) -> Dict[str, Any] | None:
    item = payload
    if isinstance(payload, list):
        item = next((x for x in payload if isinstance(x, dict)), None)
    elif isinstance(payload, dict) and not str(payload.get("question", "")).strip():
        item = next((x for x in _extract_exercise_list(payload) if isinstance(x, dict)), None)
    if not isinstance(item, dict) or not str(item.get("question", "")).strip():
        return None
    item = dict(item)
    item["type"] = exercise_type
    if exercise_type == "mcq":
        options = item.get("options")
        if not isinstance(options, list) or len(options) != 4 or not _letter_of(str(item.get("correct_answer", ""))):
            return None
    if exercise_type == "sentence_correction" and not str(item.get("incorrect", "")).strip():
        return None
    return item


def _grammar_clause(exercise_type: str) -> str:
    return f"La phrase à corriger porte sur {_grammar_focus()}.\n" if exercise_type == "sentence_correction" else ""


def _generate_learn_slot(index: int, source: str, level_rule: str, exclude_questions, temperature: float) -> Dict[str, Any] | None:
    exercise_type, instruction = _LEARN_SLOTS[index]
    letter = answer_balance.next_letter("learn") if exercise_type == "mcq" else ""
    prompt = f"""Tu es un tuteur TCF Canada. Rédige UN SEUL exercice en français.

{source}

Exercice demandé : {instruction.format(letter=letter)}
{_grammar_clause(exercise_type)}{level_rule}
{_exclusion_block(exclude_questions)}

Réponds avec UN objet JSON exactement de cette forme, en français, sans rien d'autre :
{_learn_slot_example(exercise_type, letter)}"""
    for _attempt in range(2):
        try:
            item = _valid_slot(exercise_type, _generate_json(prompt, temperature=temperature))
        except Exception as error:
            logging.getLogger(__name__).info("learn exercise slot %s failed: %s", index, error)
            continue
        if item:
            return item
    return None


def _generate_learn_set(source: str, level_rule: str, exclude_questions, temperature: float, on_ready=None) -> list[Dict[str, Any]]:
    from concurrent.futures import as_completed

    exclude = list(exclude_questions or ())
    futures = {
        _LEARN_SLOT_EXECUTOR.submit(_generate_learn_slot, i, source, level_rule, exclude, temperature): i
        for i in range(len(_LEARN_SLOTS))
    }
    results: list[Dict[str, Any] | None] = [None] * len(_LEARN_SLOTS)
    for future in as_completed(futures):
        index = futures[future]
        results[index] = future.result()
        if results[index] is not None and on_ready is not None:
            on_ready(index, results[index])
    return _scrub_learn_exercises(_drop_repeated([ex for ex in results if ex], exclude))


def generate_learn_exercises(text: str, exclude_questions=(), on_ready=None) -> list[Dict[str, Any]]:
    """Five exercises grounded in the source text; `on_ready(index, exercise)` fires as each one is ready."""
    source = f"Texte source (l'exercice porte sur ce texte) :\n{text.strip()}"
    return _generate_learn_set(source, "", exclude_questions, 0.7, on_ready)


def analyze_learn_content(text: str) -> Dict[str, Any]:
    """Overview and exercises are generated in parallel."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        overview_f = pool.submit(generate_learn_overview, text)
        exercises_f = pool.submit(generate_learn_exercises, text)
        result = overview_f.result()
        result["exercises"] = exercises_f.result()
    return result


def generate_more_exercises(topic: str, level: str, summary: str, exclude_questions=()) -> list[Dict[str, Any]]:
    source = f"Sujet : {topic}\nRésumé du texte étudié : {summary}"
    return _generate_learn_set(source, f"Adapte la difficulté au niveau {level}. Exercice NOUVEAU.", exclude_questions, 0.8)


def _letter_of(answer: str) -> str:
    match = re.match(r"\s*([A-Da-d])(?:[).:\-\s]|$)", answer or "")
    return match.group(1).upper() if match else ""


def _normalize_sentence(s: str) -> str:
    return re.sub(r"[^a-z0-9À-ɏ]", "", (s or "").lower())


def _uniform_result(score: int, is_correct: bool, feedback: list[str], improved: str, explanation: str) -> Dict[str, Any]:
    return {
        "score": score, "grammar": score, "vocabulary": score, "structure": score, "fluency": score,
        "is_correct": is_correct, "feedback": feedback, "improved_answer": improved, "explanation": explanation,
    }


def evaluate_learn_answer(
    exercise_type: str,
    question: str,
    correct_answer: str,
    user_answer: str,
    context: str = "",
    explanation: str | None = None,
) -> Dict[str, Any]:
    """
    Objective exercises (mcq, fill_blank, sentence_correction) are scored locally and instantly.
    Open-ended tasks (writing_task, speaking_prompt) are evaluated by the model. All feedback is in French.
    """
    expected = (correct_answer or "").strip()
    given_explanation = (explanation or "").strip()

    if not user_answer or not user_answer.strip():
        return _uniform_result(
            0, False, ["Aucune réponse fournie."], expected,
            f"Vous n'avez pas répondu. Réponse attendue : {expected}" if expected else "Vous n'avez pas répondu.",
        )

    if exercise_type == "mcq":
        expected_letter = _letter_of(expected)
        is_correct = bool(expected_letter) and _letter_of(user_answer) == expected_letter
        feedback = ["Bonne réponse."] if is_correct else [f"Réponse incorrecte. La bonne réponse est {expected_letter or expected}."]
        return _uniform_result(10 if is_correct else 0, is_correct, feedback, expected, given_explanation)

    if exercise_type in ("fill_blank", "sentence_correction"):
        is_correct = _normalize_sentence(user_answer) == _normalize_sentence(expected)
        feedback = ["Bonne réponse."] if is_correct else [
            "Réponse incorrecte.",
            f"Votre réponse : {user_answer.strip()}",
            f"Réponse attendue : {expected}",
        ]
        return _uniform_result(10 if is_correct else 0, is_correct, feedback, expected, given_explanation)

    def _clamp(v: object) -> int:
        try:
            return max(0, min(10, int(float(v))))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    task_label = "production orale (transcription)" if exercise_type == "speaking_prompt" else "production écrite"
    prompt = f"""Tu es un correcteur strict du TCF Canada. Évalue cette {task_label} d'un apprenant.

Consigne : {question}
Contexte : {context}
Réponse de l'apprenant : {user_answer}

Règles :
- Réponds UNIQUEMENT en français.
- Sois exigeant : pas d'éloge générique ; une réponse hors sujet ou très courte reçoit une note basse.
- grammar, vocabulary, structure, fluency : 0 à 10 chacun selon la qualité réelle.
- overall_score : 0 à 10.
- feedback : 2 à 4 points d'amélioration concrets, chacun une phrase complète.
- improved_answer : une version modèle de la réponse.
- explanation : ce qui est réussi et ce qui manque.

JSON valide uniquement :
{{"overall_score": 0, "grammar": 0, "vocabulary": 0, "structure": 0, "fluency": 0, "feedback": ["..."], "improved_answer": "...", "explanation": "..."}}"""
    ai = _generate_json(prompt, temperature=0.2)
    feedback_raw = ai.get("feedback", [])
    if isinstance(feedback_raw, str):
        feedback_raw = [line.strip(" -•\t") for line in feedback_raw.splitlines()]
    feedback = [str(f).strip() for f in feedback_raw if str(f).strip()] or ["Aucun commentaire disponible."]
    score = _clamp(ai.get("overall_score", ai.get("score", 0)))
    return {
        "score": score,
        "grammar": _clamp(ai.get("grammar", score)),
        "vocabulary": _clamp(ai.get("vocabulary", score)),
        "structure": _clamp(ai.get("structure", score)),
        "fluency": _clamp(ai.get("fluency", score)),
        "is_correct": score >= 6,
        "feedback": feedback,
        "improved_answer": str(ai.get("improved_answer", "")).strip() or expected,
        "explanation": str(ai.get("explanation", "")).strip(),
    }


def extract_text_from_image_bytes(raw: bytes, content_type: str) -> str:
    """Extract text from an image using Gemini vision."""
    _ensure_api_key()
    mime = content_type or "image/jpeg"
    try:
        response = _gemini_generate(
            [
                types.Part.from_bytes(data=raw, mime_type=mime),
                "Extract all readable text from this image. Output plain text only."
            ],
            temperature=0.1,
        )
        return str(response.text).strip() if getattr(response, "text", None) else ""
    except Exception as error:
        raise RuntimeError(f"Image text extraction failed: {error}") from error

