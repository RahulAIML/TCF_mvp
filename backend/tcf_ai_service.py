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
import io
import logging
import os
import random
import re
import uuid
import wave
from collections import deque
from typing import Any, Dict, Tuple

import google.generativeai as genai
import requests
from dotenv import load_dotenv
from google import genai as genai_client
from google.genai import types

from schemas import TcfExamQuestion, ListeningQuestionResponse

load_dotenv()

logger = logging.getLogger("tcf.tts")
_ELEVENLABS_SESSION = requests.Session()

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
ELEVENLABS_OUTPUT_FORMAT = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_22050_32")
ELEVENLABS_OPTIMIZE_LATENCY = int(os.getenv("ELEVENLABS_OPTIMIZE_LATENCY", "4"))
AUDIO_STORAGE_PATH = os.getenv(
    "AUDIO_STORAGE_PATH",
    os.path.join(os.path.dirname(__file__), "data", "audio")
)

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

# ── TCF Reading question profiles (CEFR-levelled parts) ─────────────────────
# (start, end, key, cefr_label, description)
TCF_QUESTION_PROFILES = [
    (1, 10, "part1_a1a2", "A1-A2", "Documents simples de la vie quotidienne"),
    (11, 20, "part2_a2b1", "A2-B1", "Textes courants et fonctionnels"),
    (21, 30, "part3_b1b2", "B1-B2", "Documents informatifs ou argumentatifs"),
    (31, 39, "part4_b2c2", "B2-C2", "Articles de presse et textes complexes"),
]

TCF_PART_GUIDANCE = {
    "part1_a1a2": (
        "Niveau A1-A2. Utilisez un document simple de la vie quotidienne : "
        "affiche, SMS, panneau, menu, horaire, petite annonce, courte instruction. "
        "Vocabulaire tres simple, phrases courtes."
    ),
    "part2_a2b1": (
        "Niveau A2-B1. Utilisez un texte courant : email informel, notice, article "
        "court de magazine, brochure, lettre simple. Vocabulaire accessible."
    ),
    "part3_b1b2": (
        "Niveau B1-B2. Utilisez un document informatif ou argumentatif : "
        "article de blog, rapport resume, lettre officielle, description de projet. "
        "Nuances et connecteurs logiques attendus."
    ),
    "part4_b2c2": (
        "Niveau B2-C2. Utilisez un article de presse, extrait litteraire, editorial "
        "ou rapport analytique. Vocabulaire soutenu, structure argumentative complexe."
    ),
}

TCF_READING_EXAMPLES = {
    "part1_a1a2": """Question 1
Texte :
Interdit de stationner.

Question :
Que signifie ce message ?

A) On peut stationner
B) Il est interdit de stationner
C) Il faut payer
D) Le parking est ferme

Bonne reponse : B""",
    "part2_a2b1": """Question 12
Texte :
Bonjour Lea, la reunion du club est deplacee a jeudi a 18 h. Peux-tu apporter les documents e Merci.

Question :
Que doit faire Lea ?

A) Annuler la reunion
B) Apporter des documents
C) Appeler le club
D) Arriver a 20 h

Bonne reponse : B""",
    "part3_b1b2": """Question 24
Texte :
La ville lance un nouveau projet de velos partages pour reduire la circulation. Les usagers pourront emprunter un velo pour 30 minutes gratuitement, puis payer un tarif reduit.

Question :
Quel est l'objectif principal du projet ?

A) Augmenter le prix des transports
B) Reduire la circulation
C) Fermer les routes du centre
D) Creer un nouveau parking

Bonne reponse : B""",
    "part4_b2c2": """Question 35
Texte :
Dans son editorial, l'auteur souligne que la transition energetique ne peut reussir sans une coordination entre Etat, entreprises et citoyens. Il insiste sur la necessite d'investissements durables et d'une fiscalite plus lisible.

Question :
Que demande l'auteur pour reussir la transition energetique ?

A) Une baisse des investissements
B) Une coordination entre acteurs
C) La suppression des taxes
D) L'arret des energies renouvelables

Bonne reponse : B""",
}

TCF_READING_PROMPT_TEMPLATES = {
    "part1_a1a2": """Tu es un concepteur d'epreuves TCF Canada. Genere UNE question de comprehension ecrite.

Numero de question : {question_number} sur 39
Partie : {cefr_label} - {part_desc}
Consigne de difficulte : {guidance}
Lieu de mise en scene : {place}
Contexte narratif : {context}
Jeton de fraicheur : {freshness_token} (ne pas inclure dans la sortie)

---
EXEMPLE DE FORMAT ATTENDU (ne pas reproduire cet exemple) :

{example}
---

Regles :
- Langue : francais uniquement.
- Le texte doit etre unique, ancre dans {place} / {context}.
- Longueur du texte : 40 a 80 mots.
- Complexite linguistique adaptee au niveau {cefr_label}.
- La bonne reponse doit etre l'une des lettres A, B, C ou D.
- Sortie : JSON valide uniquement (pas de Markdown, pas de commentaire).
- Forme exacte du JSON :
{{
  "text": "...",
  "question": "...",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "correct_answer": "A",
  "explanation": "...",
  "question_type": "{question_type}"
}}
""",
    "part2_a2b1": """Tu es un concepteur d'epreuves TCF Canada. Genere UNE question de comprehension ecrite.

Numero de question : {question_number} sur 39
Partie : {cefr_label} - {part_desc}
Consigne de difficulte : {guidance}
Lieu de mise en scene : {place}
Contexte narratif : {context}
Jeton de fraicheur : {freshness_token} (ne pas inclure dans la sortie)

---
EXEMPLE DE FORMAT ATTENDU (ne pas reproduire cet exemple) :

{example}
---

Regles :
- Langue : francais uniquement.
- Le texte doit etre unique, ancre dans {place} / {context}.
- Longueur du texte : 60 a 100 mots.
- Complexite linguistique adaptee au niveau {cefr_label}.
- La bonne reponse doit etre l'une des lettres A, B, C ou D.
- Sortie : JSON valide uniquement (pas de Markdown, pas de commentaire).
- Forme exacte du JSON :
{{
  "text": "...",
  "question": "...",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "correct_answer": "A",
  "explanation": "...",
  "question_type": "{question_type}"
}}
""",
    "part3_b1b2": """Tu es un concepteur d'epreuves TCF Canada. Genere UNE question de comprehension ecrite.

Numero de question : {question_number} sur 39
Partie : {cefr_label} - {part_desc}
Consigne de difficulte : {guidance}
Lieu de mise en scene : {place}
Contexte narratif : {context}
Jeton de fraicheur : {freshness_token} (ne pas inclure dans la sortie)

---
EXEMPLE DE FORMAT ATTENDU (ne pas reproduire cet exemple) :

{example}
---

Regles :
- Langue : francais uniquement.
- Le texte doit etre unique, ancre dans {place} / {context}.
- Longueur du texte : 80 a 140 mots.
- Complexite linguistique adaptee au niveau {cefr_label}.
- La bonne reponse doit etre l'une des lettres A, B, C ou D.
- Sortie : JSON valide uniquement (pas de Markdown, pas de commentaire).
- Forme exacte du JSON :
{{
  "text": "...",
  "question": "...",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "correct_answer": "A",
  "explanation": "...",
  "question_type": "{question_type}"
}}
""",
    "part4_b2c2": """Tu es un concepteur d'epreuves TCF Canada. Genere UNE question de comprehension ecrite.

Numero de question : {question_number} sur 39
Partie : {cefr_label} - {part_desc}
Consigne de difficulte : {guidance}
Lieu de mise en scene : {place}
Contexte narratif : {context}
Jeton de fraicheur : {freshness_token} (ne pas inclure dans la sortie)

---
EXEMPLE DE FORMAT ATTENDU (ne pas reproduire cet exemple) :

{example}
---

Regles :
- Langue : francais uniquement.
- Le texte doit etre unique, ancre dans {place} / {context}.
- Longueur du texte : 120 a 200 mots.
- Complexite linguistique adaptee au niveau {cefr_label}.
- La bonne reponse doit etre l'une des lettres A, B, C ou D.
- Sortie : JSON valide uniquement (pas de Markdown, pas de commentaire).
- Forme exacte du JSON :
{{
  "text": "...",
  "question": "...",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "correct_answer": "A",
  "explanation": "...",
  "question_type": "{question_type}"
}}
""",
}

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


# ── Deduplication caches (separate from other services) ─────────────────────

_TCF_EXAM_HASHES_PER_SESSION = 50
_TCF_EXAM_HASHES_PER_SESSION_ALL = 250
_MAX_SESSIONS = 200

_tcf_exam_hashes_by_session: dict[str, dict[str, deque[str]]] = {}
_tcf_exam_hashes_all_by_session: dict[str, deque[str]] = {}
_tcf_exam_text_hashes_all_by_session: dict[str, deque[str]] = {}
_tcf_exam_sessions: deque[str] = deque()
_tcf_exam_hashes_global: dict[str, deque[str]] = {}
_tcf_exam_hashes_all_global: deque[str] = deque(maxlen=_TCF_EXAM_HASHES_PER_SESSION_ALL)
_tcf_exam_text_hashes_all_global: deque[str] = deque(maxlen=_TCF_EXAM_HASHES_PER_SESSION_ALL)

_tcf_listening_hashes_by_session: dict[str, deque[str]] = {}
_tcf_listening_hashes_all_by_session: dict[str, deque[str]] = {}
_tcf_listening_script_hashes_by_session: dict[str, deque[str]] = {}
_tcf_listening_sessions: deque[str] = deque()
_tcf_listening_hashes_global: deque[str] = deque(maxlen=200)
_tcf_listening_hashes_all_global: deque[str] = deque(maxlen=200)
_tcf_listening_script_hashes_global: deque[str] = deque(maxlen=200)

_TCF_PASSAGE_HASHES: deque[str] = deque(maxlen=25)

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


def _generate_gemini_tts_audio(script: str, question_number: int, session_id: str | None) -> str:
    _ensure_api_key()
    os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)
    client = genai_client.Client(api_key=API_KEY)
    try:
        response = client.models.generate_content(
            model=GEMINI_TTS_MODEL,
            contents=script,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Kore"
                        )
                    )
                )
            )
        )
    except Exception as error:
        logger.error("Gemini TTS request failed: %s", error)
        raise RuntimeError(f"Gemini TTS failed with model '{GEMINI_TTS_MODEL}': {error}") from error

    try:
        inline_data = response.candidates[0].content.parts[0].inline_data
        audio_bytes = inline_data.data
    except Exception as error:
        logger.error("Gemini TTS returned no audio data: %s", error)
        raise RuntimeError("Gemini TTS returned no audio data.") from error

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(audio_bytes)
    wav_bytes = buffer.getvalue()

    file_name = f"tcf_audio_{question_number}_{session_id or 'global'}_{uuid.uuid4().hex[:8]}.wav"
    file_path = os.path.join(AUDIO_STORAGE_PATH, file_name)
    with open(file_path, "wb") as audio_file:
        audio_file.write(wav_bytes)

    logger.info("Gemini TTS success: bytes=%s file=%s", len(wav_bytes), file_name)
    return f"/audio/{file_name}"


def _generate_tts_audio(script: str, question_number: int, session_id: str | None) -> str:
    """Generate TTS audio. Tries ElevenLabs first, falls back to Gemini TTS."""
    if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
        return _generate_gemini_tts_audio(script, question_number, session_id)

    os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    payload = {
        "text": script,
        "model_id": "eleven_multilingual_v2",
        "optimize_streaming_latency": ELEVENLABS_OPTIMIZE_LATENCY,
        "output_format": ELEVENLABS_OUTPUT_FORMAT
    }
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}

    logger.info(
        "ElevenLabs TTS request: question=%s session=%s chars=%s",
        question_number, session_id or "global", len(script)
    )

    try:
        response = _ELEVENLABS_SESSION.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
    except requests.RequestException as error:
        logger.warning("ElevenLabs TTS failed: %s. Falling back to Gemini TTS.", error)
        return _generate_gemini_tts_audio(script, question_number, session_id)

    file_name = f"tcf_audio_{question_number}_{session_id or 'global'}_{uuid.uuid4().hex[:8]}.mp3"
    file_path = os.path.join(AUDIO_STORAGE_PATH, file_name)
    with open(file_path, "wb") as audio_file:
        audio_file.write(response.content)

    logger.info(
        "ElevenLabs TTS success: status=%s bytes=%s file=%s",
        response.status_code, len(response.content), file_name
    )
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
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                response_mime_type="application/json"
            )
        )
    except Exception as error:
        raise RuntimeError(f"Gemini generate_content failed: {error}") from error
    if not getattr(response, "text", None):
        raise RuntimeError("Gemini returned an empty response.")
    return _extract_json(response.text)


def _generate_text(prompt: str, temperature: float = 0.4) -> str:
    _ensure_api_key()
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                response_mime_type="text/plain"
            )
        )
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


def _normalize_exam_question(payload: Dict[str, Any], question_type: str) -> Dict[str, Any]:
    options_raw = payload.get("options", [])
    options = [str(item) for item in options_raw][:4]
    while len(options) < 4:
        options.append("Option manquante")
    options = [_normalize_option(opt, i) for i, opt in enumerate(options)]
    raw_answer = str(payload.get("correct_answer", "")).strip().upper()
    match = re.match(r"([A-D])", raw_answer)
    normalized_answer = match.group(1) if match else "A"
    return {
        "text": str(payload.get("text", "")).strip(),
        "question": str(payload.get("question", "")).strip(),
        "options": options,
        "correct_answer": normalized_answer,
        "explanation": str(payload.get("explanation", "")).strip(),
        "question_type": question_type
    }


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


def _normalize_passage_question(payload: Dict[str, Any]) -> Dict[str, Any]:
    options_raw = payload.get("options", [])
    options = [str(item) for item in options_raw][:4]
    while len(options) < 4:
        options.append("Option manquante")
    options = [_normalize_option(opt, i) for i, opt in enumerate(options)]
    raw_answer = str(payload.get("correct_answer", "")).strip().upper()
    match = re.match(r"([A-D])", raw_answer)
    normalized_answer = match.group(1) if match else "A"
    return {
        "question": str(payload.get("question", "")).strip(),
        "options": options,
        "correct_answer": normalized_answer,
        "explanation": str(payload.get("explanation", "")).strip(),
    }


def _fingerprint(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _exam_fingerprint(question: TcfExamQuestion) -> str:
    combined = f"{question.text} {question.question} {' '.join(question.options)}"
    return _fingerprint(combined)


def _tcf_question_profile(question_number: int) -> Tuple[str, str, str]:
    for start, end, key, cefr, desc in TCF_QUESTION_PROFILES:
        if start <= question_number <= end:
            return key, cefr, desc
    return "part1_a1a2", "A1–A2", "Documents simples de la vie quotidienne"


# ── Cache helpers ────────────────────────────────────────────────────────────

def _ensure_tcf_exam_session(session_id: str) -> None:
    if session_id in _tcf_exam_hashes_by_session:
        _tcf_exam_hashes_all_by_session.setdefault(
            session_id, deque(maxlen=_TCF_EXAM_HASHES_PER_SESSION_ALL)
        )
        _tcf_exam_text_hashes_all_by_session.setdefault(
            session_id, deque(maxlen=_TCF_EXAM_HASHES_PER_SESSION_ALL)
        )
        return
    _tcf_exam_hashes_by_session[session_id] = {}
    _tcf_exam_hashes_all_by_session[session_id] = deque(maxlen=_TCF_EXAM_HASHES_PER_SESSION_ALL)
    _tcf_exam_text_hashes_all_by_session[session_id] = deque(maxlen=_TCF_EXAM_HASHES_PER_SESSION_ALL)
    _tcf_exam_sessions.append(session_id)
    if len(_tcf_exam_sessions) > _MAX_SESSIONS:
        oldest = _tcf_exam_sessions.popleft()
        _tcf_exam_hashes_by_session.pop(oldest, None)
        _tcf_exam_hashes_all_by_session.pop(oldest, None)
        _tcf_exam_text_hashes_all_by_session.pop(oldest, None)


def _get_tcf_exam_cache(session_id: str | None, qtype: str) -> deque[str]:
    if not session_id:
        return _tcf_exam_hashes_global.setdefault(
            qtype, deque(maxlen=_TCF_EXAM_HASHES_PER_SESSION)
        )
    _ensure_tcf_exam_session(session_id)
    return _tcf_exam_hashes_by_session[session_id].setdefault(
        qtype, deque(maxlen=_TCF_EXAM_HASHES_PER_SESSION)
    )


def _get_tcf_exam_cache_all(session_id: str | None) -> deque[str]:
    if not session_id:
        return _tcf_exam_hashes_all_global
    _ensure_tcf_exam_session(session_id)
    return _tcf_exam_hashes_all_by_session[session_id]


def _get_tcf_exam_text_cache_all(session_id: str | None) -> deque[str]:
    if not session_id:
        return _tcf_exam_text_hashes_all_global
    _ensure_tcf_exam_session(session_id)
    return _tcf_exam_text_hashes_all_by_session[session_id]


# ── Public API ───────────────────────────────────────────────────────────────

def generate_tcf_exam_question(
    question_number: int,
    session_id: str | None = None
) -> TcfExamQuestion:
    """
    Generate one TCF Canada reading question.

    Structure (39 questions total):
      Part 1  Q1–10   A1–A2   Documents simples
      Part 2  Q11–20  A2–B1   Textes courants
      Part 3  Q21–30  B1–B2   Documents informatifs
      Part 4  Q31–39  B2–C2   Articles de presse / textes complexes

    Uses structured example-based prompting as required.
    """
    question_type, cefr_label, part_desc = _tcf_question_profile(question_number)
    guidance = TCF_PART_GUIDANCE[question_type]
    freshness_token = _freshness_token()
    place, context = _scenario_from_seed(freshness_token)

    example = TCF_READING_EXAMPLES[question_type]
    template = TCF_READING_PROMPT_TEMPLATES[question_type]
    prompt = template.format(
        question_number=question_number,
        cefr_label=cefr_label,
        part_desc=part_desc,
        guidance=guidance,
        place=place,
        context=context,
        freshness_token=freshness_token,
        question_type=question_type,
        example=example
    )

    last_error: Exception | None = None
    for _ in range(8):
        try:
            payload = _generate_json(prompt, temperature=1.0)
            normalized = _normalize_exam_question(payload, question_type)
            question = TcfExamQuestion.model_validate(normalized)

            fp = _exam_fingerprint(question)
            text_fp = _fingerprint(question.text)
            cache = _get_tcf_exam_cache(session_id, question_type)
            cache_all = _get_tcf_exam_cache_all(session_id)
            text_cache_all = _get_tcf_exam_text_cache_all(session_id)
            global_cache = _get_tcf_exam_cache(None, question_type)
            global_cache_all = _get_tcf_exam_cache_all(None)
            global_text_cache_all = _get_tcf_exam_text_cache_all(None)

            if (
                fp in cache or fp in cache_all or text_fp in text_cache_all
                or fp in global_cache or fp in global_cache_all
                or text_fp in global_text_cache_all
            ):
                last_error = RuntimeError("Duplicate TCF question; retrying.")
                continue

            cache.append(fp)
            cache_all.append(fp)
            text_cache_all.append(text_fp)
            global_cache.append(fp)
            global_cache_all.append(fp)
            global_text_cache_all.append(text_fp)
            return question

        except Exception as error:
            last_error = error
            continue

    raise RuntimeError(
        f"TCF exam question generation failed after retries: {last_error}"
    ) from last_error


def generate_tcf_listening_question(
    question_number: int,
    session_id: str | None = None,
    defer_audio: bool = False
) -> ListeningQuestionResponse:
    """
    Generate one TCF Canada listening question.
    39 questions, 35 minutes, progressive difficulty A1→C2.
    Audio generation is delegated to the shared TTS helpers in ai_service.py.
    """
    # Determine CEFR band from question number
    if question_number <= 10:
        cefr = "A1–A2"
        style = "annonce simple, dialogue quotidien ou message court"
        complexity = "vocabulaire de base, phrases courtes"
    elif question_number <= 20:
        cefr = "A2–B1"
        style = "conversation informelle, interview courte ou annonce publique"
        complexity = "vocabulaire courant, quelques expressions idiomatiques"
    elif question_number <= 30:
        cefr = "B1–B2"
        style = "reportage radio, entretien professionnel ou émission culturelle"
        complexity = "vocabulaire varié, registres formel et informel"
    else:
        cefr = "B2–C2"
        style = "débat, conférence courte ou extrait de documentaire"
        complexity = "vocabulaire soutenu, argumentation complexe"

    domain = _pick_domain()
    freshness_token = _freshness_token()
    place, context = _scenario_from_seed(freshness_token)

    prompt = f"""Tu es un concepteur d'epreuves TCF Canada. Genere UNE question de comprehension orale en francais.

Numero : {question_number} sur 39
Niveau : {cefr}
Style du document audio : {style}
Complexite lexicale : {complexity}
Domaine thematique : {domain}
Lieu : {place}, contexte : {context}
Jeton de fraicheur : {freshness_token} (ne pas inclure dans la sortie)

---
EXEMPLE DE FORMAT ATTENDU (ne pas reproduire cet exemple) :

Script :
Bonsoir a tous, le musee sera ferme lundi pour des travaux.

Question :
Pourquoi le musee sera-t-il ferme ?

A) Pour une greve
B) Pour des travaux
C) Pour une exposition
D) Pour un demenagement

Bonne reponse : B
---

Regles :
- Script : 35 a 80 mots selon le niveau {cefr} (parle naturellement, 8-20 secondes).
- Une seule question a choix multiples portant sur le contenu du script.
- 4 options, une seule bonne reponse (A, B, C ou D).
- Sortie : JSON valide uniquement.
{{
  "script": "...",
  "question": "...",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "correct_answer": "A",
  "explanation": "..."
}}
"""

    last_error: Exception | None = None
    for _ in range(3):
        try:
            payload = _generate_json(prompt, temperature=0.8)
            normalized = _normalize_listening_question(payload)

            fp = _fingerprint(
                normalized["script"] + normalized["question"] + "".join(normalized["options"])
            )
            script_fp = _fingerprint(normalized["script"])

            session_cache = _tcf_listening_hashes_by_session.setdefault(
                session_id or "__global__", deque(maxlen=80)
            )
            if fp in session_cache or fp in _tcf_listening_hashes_global:
                last_error = RuntimeError("Duplicate TCF listening question; retrying.")
                continue

            audio_url = None
            if not defer_audio:
                audio_url = _generate_tts_audio(
                    normalized["script"], question_number, session_id
                )

            session_cache.append(fp)
            _tcf_listening_hashes_global.append(fp)
            normalized["audio_url"] = audio_url
            return ListeningQuestionResponse.model_validate(normalized)

        except Exception as error:
            last_error = error
            continue

    raise RuntimeError(
        f"TCF listening question generation failed after retries: {last_error}"
    ) from last_error


def generate_tcf_writing_tasks() -> dict[str, str]:
    """
    Generate 3 TCF Canada writing task prompts.
      Task 1: Short message (A1–A2), 60–100 words
      Task 2: Description (A2–B1), 100–150 words
      Task 3: Opinion + justification (B1–C1), 150–250 words
    """
    prompt = """Tu es un concepteur d'epreuves TCF Canada. Genere trois consignes d'expression ecrite en francais.

---
EXEMPLE DE FORMAT ATTENDU (ne pas reproduire cet exemple) :

Tache 1 : Vous laissez un message court a votre voisin pour lui demander de recuperer un colis.
Tache 2 : Decrivez un lieu que vous aimez visiter et expliquez pourquoi.
Tache 3 : Donnez votre opinion sur le teletravail et justifiez votre point de vue.
---

Contraintes :
- Tache 1 (A1-A2) : Message court (60-100 mots).
- Tache 2 (A2-B1) : Description (100-150 mots).
- Tache 3 (B1-C1) : Opinion et justification (150-250 mots).

Regles :
- Consignes concises, realistes, de style examen.
- Sortie : JSON valide uniquement.
{
  "task1_prompt": "...",
  "task2_prompt": "...",
  "task3_prompt": "..."
}
"""
    payload = _generate_json(prompt, temperature=0.7)
    return {
        "task1_prompt": str(payload.get("task1_prompt", "")).strip(),
        "task2_prompt": str(payload.get("task2_prompt", "")).strip(),
        "task3_prompt": str(payload.get("task3_prompt", "")).strip(),
    }


def evaluate_tcf_writing_task(
    task_type: str,
    prompt_text: str,
    response_text: str
) -> dict[str, object]:
    """
    Evaluate a TCF Canada writing submission.
    task_type: 'task1' | 'task2' | 'task3'
    """
    config = {
        "task1": {
            "label": "Message court (A1–A2)",
            "word_range": "60–100 mots",
            "criteria": "Accomplissement de la tâche, clarté, orthographe de base, registre approprié.",
        },
        "task2": {
            "label": "Description (A2–B1)",
            "word_range": "100–150 mots",
            "criteria": "Organisation, cohérence, vocabulaire descriptif, correction grammaticale.",
        },
        "task3": {
            "label": "Opinion et justification (B1–C1)",
            "word_range": "150–250 mots",
            "criteria": "Qualité de l'argumentation, connecteurs logiques, richesse lexicale, grammaire.",
        },
    }.get(task_type, {
        "label": "Tâche d'expression écrite",
        "word_range": "60–250 mots",
        "criteria": "Accomplissement de la tâche, grammaire, cohérence, vocabulaire.",
    })

    prompt = f"""Tu es evaluateur TCF Canada pour l'expression ecrite.

Type de tache : {config['label']}
Nombre de mots attendu : {config['word_range']}
Criteres d'evaluation : {config['criteria']}

Consigne :
{prompt_text}

Production du candidat :
{response_text}

Retourne un JSON avec :
{{
  "level": "A2/B1",
  "scores": {{
    "structure": 0-10,
    "grammar": 0-10,
    "coherence": 0-10,
    "vocab": 0-10
  }},
  "feedback": ["..."],
  "improved_version": "..."
}}

EXEMPLE DE SORTIE (ne pas reproduire cet exemple) :
{{
  "level": "B1",
  "scores": {{
    "structure": 6,
    "grammar": 7,
    "coherence": 6,
    "vocab": 6
  }},
  "feedback": ["Clarifier la demande", "Ajouter un connecteur logique"],
  "improved_version": "..."
}}

Regles :
- Scores entiers entre 0 et 10.
- 3 a 6 points de feedback concrets et actionnables.
- improved_version : version amelioree respectant la plage de mots.
- Sortie : JSON valide uniquement.
"""

    payload = _generate_json(prompt, temperature=0.3)
    scores = payload.get("scores", {}) if isinstance(payload.get("scores", {}), dict) else {}

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
        "level": str(payload.get("level", "A2/B1")).strip(),
        "scores": {
            "structure": _clamp(scores.get("structure")),
            "grammar": _clamp(scores.get("grammar")),
            "coherence": _clamp(scores.get("coherence")),
            "vocab": _clamp(scores.get("vocab")),
        },
        "feedback": feedback,
        "improved_version": str(payload.get("improved_version", "")).strip(),
    }


def evaluate_tcf_writing_step(
    task_type: str,
    step: str,
    prompt_text: str,
    text: str
) -> dict[str, object]:
    prompt = f"""Tu es un coach TCF Canada en expression ecrite. Donne un retour sur une etape de redaction.

Type de tache : {task_type}
Etape : {step}
Consigne :
{prompt_text}

Brouillon du candidat pour cette etape :
{text}

Retourne un JSON avec :
{{
  "feedback": ["..."],
  "improved_version": "..."
}}

EXEMPLE DE SORTIE (ne pas reproduire cet exemple) :
{{
  "feedback": ["Ajouter une formule de politesse", "Preciser la demande"],
  "improved_version": "..."
}}

Regles :
- 2 a 4 points de retour concis et actionnables.
- improved_version : version legerement amelioree de l'etape.
- Sortie : JSON valide uniquement.
"""
    payload = _generate_json(prompt, temperature=0.4)
    feedback = payload.get("feedback", [])
    if isinstance(feedback, str):
        feedback = [item.strip() for item in feedback.split("-") if item.strip()]
    feedback = [str(item).strip() for item in feedback if str(item).strip()]
    return {
        "feedback": feedback,
        "improved_version": str(payload.get("improved_version", "")).strip(),
    }


def generate_tcf_speaking_reply(
    message: str,
    history: list[dict[str, str]],
    task_type: str,
    mode: str = "practice",
    hints: bool = False,
    session_id: str | None = None
) -> dict[str, object]:
    """
    Generate an AI examiner reply for TCF Canada speaking.
    task_type: 'basic_interaction' | 'role_play' | 'opinion'
    """
    if task_type == "basic_interaction":
        scenario = random.choice(TCF_BASIC_INTERACTIONS)
        system_context = (
            f"Tu es examinateur TCF Canada. Scénario : {scenario} "
            "Engage une interaction basique et naturelle, réponses courtes."
        )
    elif task_type == "role_play":
        scenario = random.choice(TCF_ROLE_PLAYS)
        system_context = (
            f"Tu es examinateur TCF Canada. Jeu de rôle : {scenario} "
            "Joue le rôle indiqué, pose des questions pertinentes."
        )
    else:  # opinion
        topic = random.choice(TCF_OPINION_TOPICS)
        system_context = (
            f"Tu es examinateur TCF Canada. Sujet d'opinion : {topic} "
            "Stimule la discussion, demande des justifications."
        )

    history_text = "\n".join(
        f"{'Candidat' if m['role'] == 'user' else 'Examinateur'}: {m['content']}"
        for m in history
    )
    hint_instruction = (
        "\nDonne un indice court entre [crochets] si le candidat semble bloqué."
        if hints else ""
    )
    exam_instruction = (
        "\nMode examen : reste neutre, n'aide pas, évalue implicitement."
        if mode == "exam" else ""
    )

    prompt = f"""{system_context}
{exam_instruction}
{hint_instruction}

EXEMPLE DE REPONSE (ne pas reproduire cet exemple) :
Examinateur : Merci. Pouvez-vous donner un autre detail ?

Historique de la conversation :
{history_text}

Candidat : {message}

Réponds en tant qu'examinateur en français (2 à 4 phrases maximum). Sortie : texte brut uniquement.
"""

    reply_text = _generate_text(prompt, temperature=0.7)

    # Trim to safe length
    max_chars = int(os.getenv("SPEAKING_MAX_CHARS", "600"))
    if len(reply_text) > max_chars:
        reply_text = reply_text[:max_chars].rsplit(".", 1)[0] + "."

    audio_url = None
    try:
        audio_url = _generate_tts_audio(reply_text, 0, session_id)
    except Exception:
        pass

    return {"reply": reply_text, "audio_url": audio_url}


def evaluate_tcf_speaking_conversation(
    history: list[dict[str, str]],
    task_type: str
) -> dict[str, object]:
    """
    Evaluate a complete TCF Canada speaking session.
    """
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

evalue UNIQUEMENT les repliques du candidat. Retourne un JSON avec :
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


def translate_passage(text: str) -> str:
    clean = text.strip()
    prompt = (
        "Translate the following French text to English. "
        "Output only the English translation — no explanations, no labels.\n\n"
        f"French text:\n{clean}"
    )
    return _generate_text(prompt, temperature=0.2).strip()


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


def generate_passage() -> Any:
    from schemas import PassageResponse
    last_error: Exception | None = None
    for _ in range(3):
        domain = _pick_domain()
        token = _freshness_token()
        place, context = _scenario_from_seed(token)
        prompt = f"""Genere un passage de lecture TCF Canada en francais.

Retourne un JSON avec :
title
passage

Regles :
- Longueur : 100 a 150 mots.
- Domaine : {domain}. Lieu : {place}. Contexte : {context}.
- Le passage doit commencer par une phrase complete (pas un titre comme "Avis").
- Jeton de fraicheur : {token} (ne pas inclure dans la sortie).
- Sortie : JSON valide uniquement.
{{
  "title": "...",
  "passage": "..."
}}
"""
        try:
            payload = _generate_json(prompt, temperature=0.85)
            passage = PassageResponse.model_validate(payload)
            fp = _fingerprint(passage.title + passage.passage)
            if fp in _TCF_PASSAGE_HASHES:
                last_error = RuntimeError("Duplicate passage; retrying.")
                continue
            _TCF_PASSAGE_HASHES.append(fp)
            return passage
        except Exception as error:
            last_error = error
    raise RuntimeError(f"Passage generation failed: {last_error}") from last_error


def generate_passage_quiz() -> Any:
    from schemas import PassageQuizResponse
    last_error: Exception | None = None
    for _ in range(5):
        domain = _pick_domain()
        token = _freshness_token()
        place, context = _scenario_from_seed(token)
        prompt = f"""Genere un passage de lecture TCF Canada en francais avec 10 questions de comprehension.

Retourne un JSON avec :
title
passage
questions (tableau de 10)

Chaque question doit inclure :
question
4 options
correct_answer
explanation

Regles :
- Longueur du passage : 200 a 250 mots.
- Domaine : {domain}. Lieu : {place}. Contexte : {context}.
- Jeton de fraicheur : {token} (ne pas inclure dans la sortie).
- correct_answer doit etre l'une des lettres A, B, C ou D.
- Sortie : JSON valide uniquement.
{{
  "title": "...",
  "passage": "...",
  "questions": [
    {{
      "question": "...",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "correct_answer": "A",
      "explanation": "..."
    }}
  ]
}}
"""
        try:
            payload = _generate_json(prompt, temperature=0.85)
            payload["questions"] = [
                _normalize_passage_question(q) for q in payload.get("questions", [])
            ]
            quiz = PassageQuizResponse.model_validate(payload)
            fp = _fingerprint(quiz.title + quiz.passage)
            if fp in _TCF_PASSAGE_HASHES:
                last_error = RuntimeError("Duplicate passage quiz; retrying.")
                continue
            _TCF_PASSAGE_HASHES.append(fp)
            return quiz
        except Exception as error:
            last_error = error
    raise RuntimeError(f"Passage quiz generation failed: {last_error}") from last_error


def generate_tcf_listening_audio(script: str, question_number: int, session_id: str | None = None) -> str:
    """Public wrapper for TTS — used by the listening route's audio endpoint."""
    return _generate_tts_audio(script, question_number, session_id)


def analyze_learn_content(text: str) -> Dict[str, Any]:
    clean = text.strip()
    prompt = f"""Tu es un tuteur TCF Canada. Analyse ce texte francais et genere des exercices d'apprentissage.

Texte :
{clean}

Retourne un JSON avec :
{{
  "topic": "sujet en quelques mots",
  "level": "A1/A2/B1/B2/C1",
  "summary": "resume en 2-3 phrases",
  "key_points": ["point 1", "point 2", "point 3"],
  "vocabulary": [
    {{"word": "...", "definition": "...", "example": "..."}}
  ],
  "exercises": [
    {{
      "type": "mcq",
      "question": "...",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "correct_answer": "...",
      "explanation": "..."
    }}
  ]
}}

Regles :
- 3 a 5 points cles.
- 3 a 5 mots de vocabulaire avec definition et exemple en francais.
- 3 a 5 exercices varies (mcq, fill_blank, sentence_correction, writing_task, speaking_prompt).
- Sortie : JSON valide uniquement.
"""
    payload = _generate_json(prompt, temperature=0.6)
    vocab = payload.get("vocabulary", [])
    if not isinstance(vocab, list):
        vocab = []
    exercises = payload.get("exercises", [])
    if not isinstance(exercises, list):
        exercises = []
    return {
        "topic": str(payload.get("topic", "")).strip(),
        "level": str(payload.get("level", "B1")).strip(),
        "summary": str(payload.get("summary", "")).strip(),
        "key_points": [str(p).strip() for p in payload.get("key_points", []) if str(p).strip()],
        "vocabulary": vocab,
        "exercises": exercises,
    }


def evaluate_learn_answer(
    exercise_type: str,
    question: str,
    correct_answer: str,
    user_answer: str,
    context: str = ""
) -> Dict[str, Any]:
    prompt = f"""Tu es evaluateur TCF Canada. Evalue la reponse d'un apprenant.

Type d'exercice : {exercise_type}
Question : {question}
Reponse correcte : {correct_answer}
Reponse de l'apprenant : {user_answer}
Contexte : {context}

Retourne un JSON avec :
{{
  "score": 0-10,
  "grammar": 0-10,
  "vocabulary": 0-10,
  "structure": 0-10,
  "fluency": 0-10,
  "is_correct": true/false,
  "feedback": ["..."],
  "improved_answer": "...",
  "explanation": "..."
}}

Regles :
- Scores entiers 0 a 10.
- 2 a 4 points de feedback concrets.
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
        feedback = [f.strip() for f in feedback.split("-") if f.strip()]
    feedback = [str(f).strip() for f in feedback if str(f).strip()]

    return {
        "score": _clamp(payload.get("score")),
        "grammar": _clamp(payload.get("grammar")),
        "vocabulary": _clamp(payload.get("vocabulary")),
        "structure": _clamp(payload.get("structure")),
        "fluency": _clamp(payload.get("fluency")),
        "is_correct": bool(payload.get("is_correct", False)),
        "feedback": feedback,
        "improved_answer": str(payload.get("improved_answer", "")).strip(),
        "explanation": str(payload.get("explanation", "")).strip(),
    }


def generate_more_exercises(topic: str, level: str, summary: str) -> list[Dict[str, Any]]:
    prompt = f"""Tu es tuteur TCF Canada. Genere des exercices supplementaires en francais.

Sujet : {topic}
Niveau : {level}
Resume : {summary}

Retourne un JSON : tableau de 5 exercices varies.
Chaque exercice doit avoir le format :
{{
  "type": "mcq | fill_blank | sentence_correction | writing_task | speaking_prompt",
  "question": "...",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "correct_answer": "...",
  "hint": "...",
  "explanation": "..."
}}

Regles :
- Varier les types d'exercices.
- Adapter la difficulte au niveau {level}.
- Sortie : JSON valide uniquement (tableau, pas d'objet enveloppe).
"""
    payload_raw = _generate_json(prompt, temperature=0.7)
    if isinstance(payload_raw, list):
        return payload_raw
    # Some models wrap in an object
    for key in ("exercises", "items", "data"):
        if key in payload_raw and isinstance(payload_raw[key], list):
            return payload_raw[key]
    return []


def extract_text_from_image_bytes(raw: bytes, content_type: str) -> str:
    """Extract text from an image using Gemini vision."""
    import base64
    _ensure_api_key()
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    b64 = base64.b64encode(raw).decode("utf-8")
    mime = content_type or "image/jpeg"
    try:
        response = model.generate_content(
            [
                {"mime_type": mime, "data": b64},
                "Extract all readable text from this image. Output plain text only."
            ],
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                response_mime_type="text/plain"
            )
        )
        return str(response.text).strip() if getattr(response, "text", None) else ""
    except Exception as error:
        raise RuntimeError(f"Image text extraction failed: {error}") from error
