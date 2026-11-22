"""
Pronunciation training and vocabulary routes (Gemini evaluation, ElevenLabs/Gemini pronunciation audio).
"""
import json
import logging
import os
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Iterator, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from audio_mime import base_mime, extension_for
from auth import get_optional_user
from database import SessionLocal, get_db
from elevenlabs_service import elevenlabs_service
from gemini_service import GeminiService, gemini_service, no_speech_pronunciation_result
from guest import is_guest
from models import PronunciationEvaluation, User, VocabularyWord
from schemas import (
    PronunciationEvaluationResponse,
    VocabularyProgressRequest,
    VocabularyProgressResponse,
    VocabularyWordRequest,
    VocabularyGenerationResponse,
    VocabularyWordItem,
)
from pronunciation_prompts import remember_prompt, take_prompts
from speaking_pregen import take_vocabulary
from pydantic import BaseModel, Field

logger = logging.getLogger("pronunciation_routes")

router = APIRouter(prefix="/api/pronunciation", tags=["pronunciation"])

AUDIO_STORAGE_PATH = os.getenv(
    "AUDIO_STORAGE_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "user_audio")
)
MAX_AUDIO_BYTES = 15 * 1024 * 1024
MAX_GUIDE_CHARS = 200
_UNAVAILABLE = "Le service d'évaluation est momentanément indisponible. Réessayez dans un instant."
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse(payload: object) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _read_upload(audio_file: UploadFile) -> Tuple[bytes, str]:
    data = await audio_file.read()
    if not data:
        raise HTTPException(status_code=400, detail="L'enregistrement est vide. Réessayez.")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="L'enregistrement est trop long.")
    return data, base_mime(audio_file.content_type, audio_file.filename)


def _store_evaluation(user_id: int, target_text: str, language: str, evaluation: dict, audio: bytes, mime: str) -> None:
    """Keep the attempt for signed-in users only (guests share one demo account)."""
    db = SessionLocal()
    try:
        os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)
        audio_filename = f"{user_id}_{uuid.uuid4().hex}{extension_for(mime)}"
        with open(os.path.join(AUDIO_STORAGE_PATH, audio_filename), "wb") as f:
            f.write(audio)
        db.add(PronunciationEvaluation(
            user_id=user_id,
            target_text=target_text,
            user_text=evaluation.get("user_text", ""),
            accuracy=evaluation.get("accuracy", 0),
            clarity=evaluation.get("clarity", 0),
            mistakes=str(evaluation.get("mistakes", [])),
            feedback=evaluation.get("feedback", ""),
            improved_version=evaluation.get("improved_version", ""),
            audio_url=f"/audio/{audio_filename}",
            language=language,
        ))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Could not store pronunciation evaluation: %s", exc)
    finally:
        db.close()


def _evaluate_bytes(target_text: str, audio: bytes, mime: str, language: str) -> dict:
    user_text = GeminiService.transcribe_bytes(audio, language, mime)
    if not user_text:
        return no_speech_pronunciation_result(target_text)
    return GeminiService.pronunciation_scores(target_text, user_text, language, with_feedback=True)


@router.post("/evaluate", response_model=PronunciationEvaluationResponse)
async def evaluate_pronunciation(
    target_text: str = Form(..., max_length=2000),
    audio_file: UploadFile = File(...),
    language: str = Form("fr"),
    user: User = Depends(get_optional_user),
) -> PronunciationEvaluationResponse:
    audio, mime = await _read_upload(audio_file)
    try:
        evaluation = await run_in_threadpool(_evaluate_bytes, target_text, audio, mime, language)
    except Exception as e:
        logger.error("Pronunciation evaluation failed: %s", e)
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from e
    if not is_guest(user) and not evaluation.get("no_speech"):
        await run_in_threadpool(_store_evaluation, user.id, target_text, language, evaluation, audio, mime)
    return PronunciationEvaluationResponse(**evaluation)


@router.post("/evaluate/stream")
async def evaluate_pronunciation_stream(
    target_text: str = Form(..., max_length=2000),
    audio_file: UploadFile = File(...),
    language: str = Form("fr"),
    user: User = Depends(get_optional_user),
) -> StreamingResponse:
    """
    SSE: {"type":"transcript"} (what the learner said) → {"type":"token"}* (coach feedback as it is written)
    and {"type":"scores"} as soon as they are ready → {"type":"done"}; or {"type":"no_speech"}.
    """
    audio, mime = await _read_upload(audio_file)
    user_id = None if is_guest(user) else user.id

    def _events() -> Iterator[str]:
        executor: Optional[ThreadPoolExecutor] = None
        try:
            user_text = GeminiService.transcribe_bytes(audio, language, mime)
            if not user_text:
                yield _sse({"type": "no_speech", **no_speech_pronunciation_result(target_text)})
                yield "data: [DONE]\n\n"
                return
            yield _sse({"type": "transcript", "user_text": user_text})

            executor = ThreadPoolExecutor(max_workers=1)
            scores_future = executor.submit(
                GeminiService.pronunciation_scores, target_text, user_text, language, False
            )
            scores_sent = False
            feedback_parts: list[str] = []
            try:
                for token in GeminiService.stream_pronunciation_feedback(target_text, user_text, language):
                    if not scores_sent and scores_future.done():
                        yield _sse({"type": "scores", **scores_future.result()})
                        scores_sent = True
                    feedback_parts.append(token)
                    yield _sse({"type": "token", "token": token})
            except Exception as error:
                logger.warning("Pronunciation feedback stream failed: %s", error)
            scores = scores_future.result()
            if not scores_sent:
                yield _sse({"type": "scores", **scores})
            scores["feedback"] = "".join(feedback_parts).strip()
            if user_id is not None:
                _store_evaluation(user_id, target_text, language, scores, audio, mime)
            yield _sse({"type": "done"})
        except Exception as error:
            logger.error("Pronunciation stream failed: %s", error)
            yield _sse({"type": "error", "message": _UNAVAILABLE})
        finally:
            if executor is not None:
                executor.shutdown(wait=False)
        yield "data: [DONE]\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream", headers=_SSE_HEADERS)


# ── Pronunciation guide audio (cached, pre-warmed for served vocabulary) ───────

_GUIDE_CACHE_MAX = 400
_guide_cache: "OrderedDict[Tuple[str, str], Tuple[bytes, str]]" = OrderedDict()
_guide_lock = threading.Lock()
_guide_warmer = ThreadPoolExecutor(max_workers=2, thread_name_prefix="guide-warm")


def _guide_audio(word: str, language: str) -> Optional[Tuple[bytes, str]]:
    key = (word.strip().lower(), language)
    with _guide_lock:
        cached = _guide_cache.get(key)
        if cached is not None:
            _guide_cache.move_to_end(key)
            return cached
    result: Optional[Tuple[bytes, str]] = None
    try:
        audio_bytes = elevenlabs_service.generate_pronunciation_guide(word=word, language=language)
        if audio_bytes:
            result = (audio_bytes, "audio/mpeg")
    except Exception as exc:
        logger.warning("ElevenLabs failed for %r: %s", word, exc)
    if result is None:
        wav_bytes = GeminiService.generate_tts(text=word, language=language)
        if wav_bytes:
            result = (wav_bytes, "audio/wav")
    if result is not None:
        with _guide_lock:
            _guide_cache[key] = result
            while len(_guide_cache) > _GUIDE_CACHE_MAX:
                _guide_cache.popitem(last=False)
    return result


def _warm_guides(words: list[str], language: str) -> None:
    for word in words:
        try:
            _guide_warmer.submit(_guide_audio, word, language)
        except RuntimeError:
            return


@router.get("/guide/{word}")
def get_pronunciation_guide(word: str, language: str = "fr") -> Response:
    """Native pronunciation audio. ElevenLabs (MP3), then Gemini TTS (WAV); 503 only if both fail."""
    word = word.strip()
    if not word or len(word) > MAX_GUIDE_CHARS:
        raise HTTPException(status_code=400, detail="Texte invalide pour la prononciation.")
    result = _guide_audio(word, language)
    if result is None:
        logger.error("All TTS sources failed for %r", word)
        raise HTTPException(status_code=503, detail="L'audio de prononciation est momentanément indisponible.")
    audio_bytes, media_type = result
    return Response(content=audio_bytes, media_type=media_type, headers={"Cache-Control": "public, max-age=3600"})


class PronunciationPromptRequest(BaseModel):
    level: str = "A2"
    language: str = "fr"
    count: int = 8


class PronunciationSeenRequest(BaseModel):
    text: str = Field(min_length=1, max_length=240)
    language: str = "fr"


@router.post("/prompts")
def post_pronunciation_prompts(body: PronunciationPromptRequest) -> dict:
    """New read-aloud phrases for this learner. The offline list is used when generation is unavailable, and it is tracked too."""
    try:
        prompts = take_prompts(body.language, body.level, body.count)
    except Exception as error:
        logger.error("Pronunciation prompts failed: %s", error)
        raise HTTPException(status_code=503, detail="No new pronunciation phrases are available right now. Please try again.") from error
    return {"prompts": prompts}


@router.post("/prompts/seen")
def post_pronunciation_prompt_seen(body: PronunciationSeenRequest) -> dict:
    """Remember a phrase the browser showed from its own fallback list."""
    remember_prompt(body.text, body.language)
    return {"status": "recorded"}


# ── VOCABULARY ROUTES ────────────────────────────────────────────────────────

@router.post("/vocabulary/generate", response_model=VocabularyGenerationResponse)
def generate_vocabulary(
    request: VocabularyWordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_optional_user),
) -> VocabularyGenerationResponse:
    """Words at the requested level, never repeated within a session (served from a pre-generated pool)."""
    try:
        words = take_vocabulary(
            level=request.level,
            count=request.count,
            topic=request.topic,
            language=request.language,
            session_id=request.session_id,
        )
    except Exception as e:
        logger.error("Vocabulary generation failed: %s", e)
        raise HTTPException(status_code=503, detail="La génération du vocabulaire est momentanément indisponible.") from e
    if not words:
        raise HTTPException(status_code=503, detail="La génération du vocabulaire est momentanément indisponible.")

    items = [
        VocabularyWordItem(
            word=w.get("word", ""),
            meaning=w.get("meaning", ""),
            example=w.get("example", ""),
            example_translation=w.get("example_translation"),
            phonetic=w.get("phonetic"),
            audio_url=None,
        )
        for w in words
    ]

    if not is_guest(user):
        try:
            for item in items:
                db.add(VocabularyWord(
                    user_id=user.id,
                    word=item.word,
                    language=request.language,
                    level=request.level,
                    meaning=item.meaning,
                    example=item.example,
                    example_translation=item.example_translation,
                    phonetic=item.phonetic,
                    audio_url=None,
                    source="generated",
                ))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Could not store vocabulary for user %s: %s", user.id, exc)

    _warm_guides([item.word for item in items], request.language)
    return VocabularyGenerationResponse(words=items, level=request.level, count=len(items))


def _progress_response(vocab: VocabularyWord) -> VocabularyProgressResponse:
    return VocabularyProgressResponse(
        word=vocab.word,
        is_learned=vocab.is_learned,
        practice_count=vocab.practice_count,
        correct_count=vocab.correct_count,
        accuracy_score=vocab.accuracy_score,
        last_practiced=vocab.last_practiced,
    )


@router.get("/vocabulary/word/{word}", response_model=VocabularyProgressResponse)
def get_vocabulary_word(
    word: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_optional_user),
) -> VocabularyProgressResponse:
    try:
        vocab = None if is_guest(user) else db.query(VocabularyWord).filter(
            VocabularyWord.user_id == user.id,
            VocabularyWord.word == word,
        ).first()
    except Exception as e:
        logger.error("Vocabulary lookup failed: %s", e)
        raise HTTPException(status_code=500, detail="Lookup failed") from e
    if not vocab:
        raise HTTPException(status_code=404, detail="Word not found")
    return _progress_response(vocab)


@router.put("/vocabulary/progress", response_model=VocabularyProgressResponse)
def update_vocabulary_progress(
    request: VocabularyProgressRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_optional_user),
) -> VocabularyProgressResponse:
    if is_guest(user):
        raise HTTPException(status_code=404, detail="Word not found")
    try:
        vocab = db.query(VocabularyWord).filter(
            VocabularyWord.user_id == user.id,
            VocabularyWord.word == request.word,
        ).first()
        if not vocab:
            raise HTTPException(status_code=404, detail="Word not found")

        vocab.practice_count += 1
        vocab.last_practiced = datetime.utcnow()
        if request.is_learned is not None:
            vocab.is_learned = request.is_learned
        if request.accuracy_score is not None:
            if vocab.accuracy_score is None:
                vocab.accuracy_score = request.accuracy_score
            else:
                vocab.accuracy_score = (
                    vocab.accuracy_score * vocab.correct_count + request.accuracy_score
                ) / (vocab.correct_count + 1)
            if request.accuracy_score >= 8:
                vocab.correct_count += 1
        db.commit()
        return _progress_response(vocab)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Progress update failed: %s", e)
        raise HTTPException(status_code=500, detail="Update failed") from e
