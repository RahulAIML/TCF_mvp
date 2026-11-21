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
import logging
import os
import random
import re
import threading
import uuid
from collections import deque
from typing import Any, Dict, Tuple

from dotenv import load_dotenv
from google import genai as genai_client
from google.genai import types

from pregen_pool import PregenPool
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
        _shared_client = genai_client.Client(api_key=API_KEY)
    return _shared_client


def _gen_config(**kwargs: Any) -> "types.GenerateContentConfig":
    if _thinking_enabled:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=GEMINI_THINKING_LEVEL)
    return types.GenerateContentConfig(**kwargs)


def _gemini_generate(contents: Any, stream: bool = False, **config_kwargs: Any) -> Any:
    """generate_content with the shared client; drops thinking_config once if the model rejects it."""
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
TCF_EXAMINER_NAMES = [
    ("Marie Dupont", "examinatrice"),
    ("Sophie Martin", "examinatrice"),
    ("Claire Lefebvre", "examinatrice"),
    ("Isabelle Moreau", "examinatrice"),
    ("Nathalie Petit", "examinatrice"),
    ("Jean-Pierre Bernard", "examinateur"),
    ("Thomas Rousseau", "examinateur"),
    ("Michel Laurent", "examinateur"),
]

def _pick_examiner(session_id: str | None) -> tuple[str, str]:
    """Return (name, title) deterministic per session, random otherwise."""
    import hashlib
    if session_id:
        idx = int(hashlib.md5(session_id.encode()).hexdigest(), 16) % len(TCF_EXAMINER_NAMES)
        return TCF_EXAMINER_NAMES[idx]
    return random.choice(TCF_EXAMINER_NAMES)


TCF_BASIC_INTERACTIONS = [
    "Vous rencontrez un voisin dans l'escalier. Presentez-vous et engagez une conversation polie.",
    "Vous appelez un cabinet medical pour prendre rendez-vous. L'assistant repond.",
    "Vous etes a la caisse d'un supermarche et il manque un article dans votre sac.",
    "Vous demandez des informations a un agent d'accueil dans une mairie.",
]

TCF_ROLE_PLAYS = [
    "Vous etes agent immobilier et parlez a un locataire qui souhaite louer un appartement.",
    "Vous etes recruteur et menez un entretien pour un poste a temps partiel.",
    "Vous etes responsable d'un centre culturel et expliquez une inscription.",
    "Vous etes receptionniste d'hotel et repondez aux questions d'un client.",
]

TCF_OPINION_TOPICS = [
    "Le teletravail est-il benefique pour tous les travailleurs ?",
    "Faut-il interdire les voitures en centre-ville pour reduire la pollution ?",
    "Les reseaux sociaux ont-ils un impact globalement positif sur la societe ?",
    "Devrait-on rendre les transports en commun entierement gratuits ?",
]

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
            data = response.content
        except Exception as error:
            logger.warning("ElevenLabs TTS failed: %s. Falling back to Gemini TTS.", error)
            result = tts_service.synthesize_gemini(script, "fr-FR-female-1")
            data, ext = result["data"], result["extension"]
    else:
        result = tts_service.synthesize_gemini(script, "fr-FR-female-1")
        data, ext = result["data"], result["extension"]

    file_name = f"tcf_audio_{question_number}_{session_id or 'global'}_{uuid.uuid4().hex[:8]}.{ext}"
    with open(os.path.join(AUDIO_STORAGE_PATH, file_name), "wb") as audio_file:
        audio_file.write(data)
    return f"/audio/{file_name}"


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
        fresh = [t for t in WRITING_THEMES if t not in _writing_recent_themes]
        if len(fresh) < count:
            fresh = list(WRITING_THEMES)
        chosen = random.sample(fresh, count)
        _writing_recent_themes.extend(chosen)
    return chosen


def _writing_tasks_prompt(themes: list[str]) -> str:
    return f"""Tu es concepteur officiel d'épreuves d'expression écrite du TCF Canada (France Éducation international).
Rédige UNE série complète de trois tâches, en français, au format officiel. Contexte canadien bienvenu.

Thèmes imposés (un par tâche, dans cet ordre) : 1) {themes[0]} ; 2) {themes[1]} ; 3) {themes[2]}.

Format officiel à respecter :
- Tâche 1 (60 à 120 mots) : rédiger un MESSAGE (courriel, mot, invitation…) adressé à un ou plusieurs destinataires
  nommés, pour décrire, raconter ou expliquer quelque chose. La consigne précise le destinataire et 2 ou 3 éléments
  à inclure.
- Tâche 2 (120 à 150 mots) : rédiger un ARTICLE, un COURRIER ou une NOTE pour un lecteur précis (journal local,
  blogue, association…) qui rend compte d'un événement ou d'une expérience ET donne une opinion argumentée.
- Tâche 3 (120 à 180 mots) : deux courts documents (60 à 90 mots chacun) présentent deux points de vue OPPOSÉS sur
  le thème. La consigne demande : comparer les deux points de vue (40 à 60 mots), puis donner son opinion
  argumentée (80 à 120 mots). Inclure les deux documents DANS task3_prompt, sous la forme
  "Document 1 : …" puis "Document 2 : …", après la consigne.

Règles :
- Consignes naturelles et réalistes, vouvoiement du candidat, nombre de mots indiqué dans chaque consigne.
- Pas de jargon, situations de la vie courante, professionnelle ou citoyenne.
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


_writing_task_pool: PregenPool[dict[str, str]] = PregenPool(
    "writing_tasks",
    lambda _key: _generate_writing_task_set(),
    target=int(os.getenv("PREGEN_WRITING_TARGET", "5")),
    warm_keys=("all",),
)


def _writing_session_served(session_id: str | None) -> deque[str]:
    with _writing_lock:
        return _writing_served_by_session.setdefault(session_id or "__anon__", deque(maxlen=200))


def generate_tcf_writing_tasks(session_id: str | None = None) -> dict[str, str]:
    """Serve a ready task set from the pre-generated pool (instant); generate one live only if the pool is empty."""
    served = _writing_session_served(session_id)
    for _ in range(5):
        tasks = _writing_task_pool.take("all")
        if tasks is None:
            break
        key = _fingerprint("".join(tasks.values()))
        if key in served:
            continue
        served.append(key)
        return tasks
    tasks = _generate_writing_task_set()
    served.append(_fingerprint("".join(tasks.values())))
    return tasks


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
_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
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


def parse_writing_evaluation_text(text: str) -> dict[str, Any]:
    """Parse the streamed line format. Missing parts are None/empty; `complete` tells if all scores were found."""
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
        "complete": level is not None and all(v is not None for v in scores.values()),
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
    average = sum(scores.values()) / len(scores)
    computed = _level_from_average(average)
    level = result.get("level")
    # Never above what the scores justify; a slightly stricter model judgement (one band lower) is kept.
    if level not in _LEVELS or not (0 <= _LEVELS.index(computed) - _LEVELS.index(level) <= 1):
        level = computed
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


def stream_writing_evaluation_tokens(task_type: str, prompt_text: str, response_text: str):
    if not response_text.strip():
        return
    _ensure_api_key()
    for chunk in _gemini_generate(
        _writing_eval_prompt(task_type, prompt_text, response_text), stream=True, temperature=0.2
    ):
        token = getattr(chunk, "text", None)
        if token:
            yield token


def finalize_writing_evaluation(
    streamed_text: str, task_type: str, prompt_text: str, response_text: str
) -> dict[str, object]:
    """Normalize the streamed evaluation; one non-streamed retry if the stream was malformed."""
    if not response_text.strip():
        return _empty_writing_evaluation()
    parsed = parse_writing_evaluation_text(streamed_text)
    if not parsed["complete"]:
        retry_text = _generate_text(_writing_eval_prompt(task_type, prompt_text, response_text), temperature=0.1)
        retry = parse_writing_evaluation_text(retry_text)
        if not retry["complete"]:
            raise RuntimeError("Writing evaluation could not be parsed.")
        parsed = retry
    return _apply_writing_guards(parsed, task_type, response_text)


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


def generate_tcf_speaking_reply(
    message: str,
    history: list[dict[str, str]],
    task_type: str,
    mode: str = "practice",
    hints: bool = False,
    session_id: str | None = None,
    session_topic: str | None = None
) -> dict[str, object]:
    """
    Generate an AI examiner reply for TCF Canada speaking.
    task_type: 'basic_interaction' | 'role_play' | 'opinion'
    session_topic: locked topic for the session (passed back from first reply)
    """
    chosen_topic: str
    if task_type == "basic_interaction":
        chosen_topic = session_topic if session_topic else random.choice(TCF_BASIC_INTERACTIONS)
        system_context = (
            f"Tu es examinateur TCF Canada. Scénario : {chosen_topic} "
            "Engage une interaction basique et naturelle, réponses courtes."
        )
    elif task_type == "role_play":
        chosen_topic = session_topic if session_topic else random.choice(TCF_ROLE_PLAYS)
        system_context = (
            f"Tu es examinateur TCF Canada. Jeu de rôle : {chosen_topic} "
            "Joue le rôle indiqué, pose des questions pertinentes."
        )
    else:  # opinion
        chosen_topic = session_topic if session_topic else random.choice(TCF_OPINION_TOPICS)
        system_context = (
            f"Tu es examinateur TCF Canada. Sujet d'opinion : {chosen_topic} "
            "Stimule la discussion, demande des justifications."
        )

    # Real examiner identity — never use placeholder names
    examiner_name, examiner_title = _pick_examiner(session_id)

    is_start = message == "__START__"
    message_text = "" if is_start else message

    history_text = "\n".join(
        f"{'Candidat' if m['role'] == 'user' else examiner_name}: {m['content']}"
        for m in history
    )

    # Build all previously asked questions to prevent repetition
    asked_questions = [
        m["content"] for m in history if m.get("role") == "assistant"
    ]
    asked_block = (
        "\n\nQuestions déjà posées (NE PAS RÉPÉTER) :\n" +
        "\n".join(f"- {q[:120]}" for q in asked_questions[-6:])
        if asked_questions else ""
    )

    hint_instruction = (
        "\nSi le candidat semble bloqué, donne un indice court et discret."
        if hints else ""
    )
    exam_instruction = (
        "\nMode examen : reste neutre et formel, n'aide pas le candidat."
        if mode == "exam" else ""
    )

    if is_start:
        task_opening = (
            f"Ouvre l'échange en te présentant : "
            f"\"Bonjour, je m'appelle {examiner_name}, je suis votre {examiner_title} aujourd'hui.\" "
            f"Puis pose UNE seule question claire pour lancer le sujet : {chosen_topic}"
        )
    else:
        task_opening = (
            "Continue la conversation. "
            "Pose UNE question de suivi précise basée sur la DERNIÈRE réponse du candidat. "
            "Si la réponse est courte ou vague, demande une clarification ou un exemple. "
            "Si la réponse est bonne, approfondis avec un aspect plus précis du sujet."
        )

    prompt = f"""Tu es {examiner_name}, {examiner_title} TCF Canada.
Sujet de la session : {chosen_topic}
{exam_instruction}
{hint_instruction}

RÈGLES ABSOLUES :
- TOUJOURS utiliser ton vrai nom : {examiner_name}
- JAMAIS de crochets ou de placeholders comme [nom], [prénom], etc.
- JAMAIS répéter une question déjà posée
- Rester STRICTEMENT sur le sujet de la session
- Répondre en 1 à 2 phrases maximum
- Ton naturel et humain, pas de formules répétitives
{asked_block}

{task_opening}

Historique :
{history_text}

Candidat : {message_text}

Réponds uniquement en tant que {examiner_name} (1-2 phrases). Texte brut uniquement, pas de guillemets autour de ta réponse.
"""

    reply_text = _generate_text(prompt, temperature=0.75)

    # Trim to safe length
    max_chars = int(os.getenv("SPEAKING_MAX_CHARS", "600"))
    if len(reply_text) > max_chars:
        reply_text = reply_text[:max_chars].rsplit(".", 1)[0] + "."

    audio_url = None
    try:
        audio_url = _generate_tts_audio(reply_text, 0, session_id)
    except Exception:
        pass

    return {"reply": reply_text, "audio_url": audio_url, "session_topic": chosen_topic}


def evaluate_tcf_speaking_conversation(
    history: list[dict[str, str]],
    task_type: str
) -> dict[str, object]:
    """
    Evaluate a complete TCF Canada speaking session.
    """
    # Use ALL candidate turns combined for quality check — a short final reply
    # should not zero-score an otherwise full conversation.
    candidate_text = _speaking_candidate_text(history)
    is_low, low_reason = _is_speaking_low_response(candidate_text)
    if is_low:
        feedback_map = {
            "empty": [
                "Aucune réponse détectée.",
                "Répondez en phrases complètes."
            ],
            "too_short": [
                "Votre réponse est trop courte.",
                "Ajoutez au moins deux idées et un exemple."
            ],
            "irrelevant": [
                "La réponse est hors sujet ou trop vague.",
                "Reformulez en répondant directement à la question."
            ],
        }
        feedback = feedback_map.get(low_reason, feedback_map["too_short"])
        return {
            "fluency": 1,
            "grammar": 1,
            "vocabulary": 1,
            "interaction": 1,
            "feedback": feedback,
            "improved_response": "Essayez une réponse plus complète et directement liée au sujet."
        }

    history_text = "\n".join(
        f"{'Candidat' if m['role'] == 'user' else 'Examinateur'}: {m['content']}"
        for m in history
    )
    task_label = {
        "basic_interaction": "Interaction de base",
        "role_play": "Jeu de rôle",
        "opinion": "Expression d'opinion",
    }.get(task_type, task_type)

    prompt = f"""Tu es evaluateur TCF Canada pour l'expression orale.

Type de tache : {task_label}

Conversation :
{history_text}

evalue UNIQUEMENT les repliques du candidat. Notation stricte sur :
- Fluency (aisance)
- Grammar (grammaire)
- Relevance (pertinence)
- Completeness (completude)

Retourne un JSON avec :
{{
  "fluency": 0-10,
  "grammar": 0-10,
  "vocabulary": 0-10,
  "interaction": 0-10,
  "feedback": ["..."],
  "improved_response": "..."
}}

EXEMPLE DE SORTIE (ne pas reproduire cet exemple) :
{{
  "fluency": 7,
  "grammar": 6,
  "vocabulary": 6,
  "interaction": 7,
  "feedback": ["Clarifier vos idees", "Utiliser plus de connecteurs"],
  "improved_response": "..."
}}

  Regles :
  - Scores entiers 0 a 10.
  - 3 a 5 points de feedback concrets.
  - Si la reponse est faible, courte ou hors sujet, donne des scores entre 0 et 2.
  - "vocabulary" doit refleter la pertinence.
  - "interaction" doit refleter la completude de la reponse.
  - improved_response : exemple d'une meilleure reponse du candidat.
  - Sortie : JSON valide uniquement.
"""

    payload = _generate_json(prompt, temperature=0.3)

    def _clamp(v: object) -> int:
        try:
            return max(0, min(10, int(float(v))))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    feedback = payload.get("feedback", [])
    if isinstance(feedback, str):
        feedback = [item.strip() for item in feedback.split("-") if item.strip()]
    feedback = [str(item).strip() for item in feedback if str(item).strip()]

    return {
        "fluency": _clamp(payload.get("fluency")),
        "grammar": _clamp(payload.get("grammar")),
        "vocabulary": _clamp(payload.get("vocabulary")),
        "interaction": _clamp(payload.get("interaction")),
        "feedback": feedback,
        "improved_response": str(payload.get("improved_response", "")).strip(),
    }


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


_LEARN_EXERCISE_ORDER = ["mcq", "sentence_correction", "writing_task", "speaking_prompt", "writing_task"]

_LEARN_EXERCISES_TEMPLATE = """[
  {{
    "type": "mcq",
    "question": "Question de compréhension {about}",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "correct_answer": "A, B, C ou D",
    "explanation": "Pourquoi cette réponse est correcte, en français"
  }},
  {{
    "type": "sentence_correction",
    "question": "Corrigez cette phrase",
    "incorrect": "Une phrase avec UNE faute de grammaire ou d'orthographe",
    "correct_answer": "La phrase corrigée",
    "explanation": "Explication de la correction, en français"
  }},
  {{
    "type": "writing_task",
    "question": "Consigne d'écriture courte (3-4 phrases) {about}",
    "correct_answer": "Exemple de réponse modèle",
    "explanation": "Ce qui est attendu"
  }},
  {{
    "type": "speaking_prompt",
    "question": "Consigne orale (1-2 minutes) {about}",
    "correct_answer": "Points clés attendus",
    "explanation": "Critères d'évaluation"
  }},
  {{
    "type": "writing_task",
    "question": "Seconde consigne d'écriture (4-5 phrases), différente de la première",
    "correct_answer": "Exemple de réponse modèle",
    "explanation": "Ce qui est attendu"
  }}
]"""

_LEARN_RULES = """Règles STRICTES :
- Exactement 5 exercices dans cet ordre : mcq, sentence_correction, writing_task, speaking_prompt, writing_task.
- Tout le contenu est en français.
- Pour le QCM, place la bonne réponse sur la lettre {letter} ; les 3 distracteurs doivent être plausibles.
- Ne réutilise AUCUNE des questions déjà posées listées ci-dessous, ni une reformulation proche.
- Sortie : JSON valide uniquement."""


def learn_question_fingerprint(question: str) -> str:
    return re.sub(r"[^a-z0-9À-ɏ]", "", (question or "").lower())


def _order_learn_exercises(raw_list: list) -> list[Dict[str, Any]]:
    """Return the 5 exercises in the required type order; [] if the model output is unusable."""
    by_type: Dict[str, list] = {}
    for ex in raw_list:
        if isinstance(ex, dict) and str(ex.get("question", "")).strip():
            by_type.setdefault(str(ex.get("type", "")), []).append(ex)
    ordered: list = []
    used: Dict[str, int] = {}
    for rtype in _LEARN_EXERCISE_ORDER:
        bucket = by_type.get(rtype, [])
        idx = used.get(rtype, 0)
        if idx < len(bucket):
            ordered.append(bucket[idx])
            used[rtype] = idx + 1
    return ordered if len(ordered) == 5 else [ex for ex in raw_list if isinstance(ex, dict)][:5]


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


def generate_learn_exercises(text: str, exclude_questions=()) -> list[Dict[str, Any]]:
    """Second phase of the analysis: 5 exercises grounded in the source text."""
    prompt = f"""Tu es un tuteur TCF Canada. Génère exactement 5 exercices d'apprentissage basés sur ce texte.

Texte :
{text.strip()}

Retourne un JSON : tableau de 5 exercices au format :
{_LEARN_EXERCISES_TEMPLATE.format(about="sur le texte")}

{_LEARN_RULES.format(letter=random.choice("ABCD"))}
{_exclusion_block(exclude_questions)}"""
    exercises = _order_learn_exercises(_extract_exercise_list(_generate_json(prompt, temperature=0.7)))
    return _drop_repeated(exercises, exclude_questions)


def analyze_learn_content(text: str) -> Dict[str, Any]:
    """Overview and exercises are generated in parallel."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        overview_f = pool.submit(generate_learn_overview, text)
        exercises_f = pool.submit(generate_learn_exercises, text)
        result = overview_f.result()
        result["exercises"] = exercises_f.result()
    return result


def generate_more_exercises(topic: str, level: str, summary: str, exclude_questions=()) -> list[Dict[str, Any]]:
    prompt = f"""Tu es tuteur TCF Canada. Génère exactement 5 NOUVEAUX exercices en français.

Sujet : {topic}
Niveau : {level}
Résumé : {summary}

Retourne un JSON : tableau de 5 exercices au format :
{_LEARN_EXERCISES_TEMPLATE.format(about=f"sur {topic}")}

{_LEARN_RULES.format(letter=random.choice("ABCD"))}
- Adapter la difficulté au niveau {level}.
{_exclusion_block(exclude_questions)}"""
    exercises = _order_learn_exercises(_extract_exercise_list(_generate_json(prompt, temperature=0.8)))
    return _drop_repeated(exercises, exclude_questions)


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

