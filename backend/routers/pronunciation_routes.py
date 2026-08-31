"""
Pronunciation Training Routes
Routes for pronunciation evaluation using Gemini and ElevenLabs TTS.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from auth import get_optional_user
from database import get_db
from elevenlabs_service import elevenlabs_service
from gemini_service import GeminiService, gemini_service
from models import PronunciationEvaluation, User, VocabularyWord
from schemas import (
    PronunciationEvaluationResponse,
    VocabularyProgressRequest,
    VocabularyProgressResponse,
    VocabularyWordRequest,
    VocabularyGenerationResponse,
    VocabularyWordItem,
)

logger = logging.getLogger("pronunciation_routes")

router = APIRouter(prefix="/api/pronunciation", tags=["pronunciation"])

AUDIO_STORAGE_PATH = os.getenv(
    "AUDIO_STORAGE_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "user_audio")
)


@router.post("/evaluate")
async def evaluate_pronunciation(
    target_text: str = Form(...),
    audio_file: UploadFile = File(...),
    language: str = Form("fr"),
    db: Session = Depends(get_db),
    user: User = Depends(get_optional_user),
) -> PronunciationEvaluationResponse:
    """
    Evaluate pronunciation of user's speech.

    Args:
        target_text: Expected text to pronounce
        audio_file: User's audio recording
        language: Language (fr, en)

    Returns:
        Pronunciation evaluation with accuracy, feedback, etc.
    """
    try:
        # Create audio storage directory
        os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)

        # Preserve actual extension from upload
        ct = audio_file.content_type or "audio/webm"
        ext = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".mp4",
               "audio/mpeg": ".mp3", "audio/wav": ".wav"}.get(ct, ".webm")
        user_prefix = str(user.id) if user else "anon"
        audio_filename = f"{user_prefix}_{uuid.uuid4().hex}{ext}"
        audio_path = os.path.join(AUDIO_STORAGE_PATH, audio_filename)

        audio_content = await audio_file.read()
        with open(audio_path, "wb") as f:
            f.write(audio_content)

        # Evaluate pronunciation using Gemini (pass actual mime type)
        evaluation = gemini_service.evaluate_pronunciation(
            expected_text=target_text,
            audio_path=audio_path,
            language=language,
            mime_type=ct,
        )

        # Store evaluation in database only for authenticated users
        if user:
            db_eval = PronunciationEvaluation(
                user_id=user.id,
                target_text=target_text,
                user_text=evaluation.get("user_text", ""),
                accuracy=evaluation.get("accuracy", 0),
                clarity=evaluation.get("clarity", 0),
                mistakes=str(evaluation.get("mistakes", [])),
                feedback=evaluation.get("feedback", ""),
                improved_version=evaluation.get("improved_version", ""),
                audio_url=f"/audio/{audio_filename}",
                language=language
            )
            db.add(db_eval)
            db.commit()

        return PronunciationEvaluationResponse(**evaluation)
    except Exception as e:
        logger.error(f"Pronunciation evaluation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Evaluation failed")


@router.get("/guide/{word}")
async def get_pronunciation_guide(word: str, language: str = "fr") -> Response:
    """
    Stream native pronunciation audio directly — no disk writes.
    Primary: ElevenLabs (MP3). Fallback: Gemini TTS (WAV). Returns 503 only if both fail.
    """
    # 1. Try ElevenLabs
    try:
        audio_bytes = elevenlabs_service.generate_pronunciation_guide(word=word, language=language)
        if audio_bytes:
            return Response(
                content=audio_bytes,
                media_type="audio/mpeg",
                headers={"Cache-Control": "public, max-age=3600"},
            )
    except Exception as exc:
        logger.warning(f"ElevenLabs failed for '{word}': {exc}")

    # 2. Fallback: Gemini TTS
    try:
        wav_bytes = GeminiService.generate_tts(text=word, language=language)
        if wav_bytes:
            return Response(
                content=wav_bytes,
                media_type="audio/wav",
                headers={"Cache-Control": "public, max-age=3600"},
            )
    except Exception as exc:
        logger.warning(f"Gemini TTS failed for '{word}': {exc}")

    # 3. Both failed
    logger.error(f"All TTS sources failed for '{word}'")
    raise HTTPException(status_code=503, detail="TTS unavailable")


# ── VOCABULARY ROUTES ────────────────────────────────────────────────────────

@router.post("/vocabulary/generate")
async def generate_vocabulary(
    request: VocabularyWordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_optional_user),
) -> VocabularyGenerationResponse:
    """
    Generate vocabulary words using Gemini.

    Args:
        request: Generation request with level, count, topic

    Returns:
        List of generated vocabulary words
    """
    try:
        # Generate words using Gemini
        words = gemini_service.generate_vocabulary(
            level=request.level,
            count=request.count,
            topic=request.topic,
            language=request.language
        )

        # Build vocab items — audio is fetched on-demand via /guide/{word}
        vocab_items = []
        for word_data in words:
            word = word_data.get("word", "")

            vocab_record = VocabularyWord(
                user_id=user.id,
                word=word,
                language=request.language,
                level=request.level,
                meaning=word_data.get("meaning", ""),
                example=word_data.get("example", ""),
                example_translation=word_data.get("example_translation"),
                phonetic=word_data.get("phonetic"),
                audio_url=None,
                source="generated"
            )
            db.add(vocab_record)

            vocab_items.append(VocabularyWordItem(
                word=word,
                meaning=word_data.get("meaning", ""),
                example=word_data.get("example", ""),
                example_translation=word_data.get("example_translation"),
                phonetic=word_data.get("phonetic"),
                audio_url=None,
            ))

        db.commit()

        return VocabularyGenerationResponse(
            words=vocab_items,
            level=request.level,
            count=len(vocab_items)
        )
    except Exception as e:
        logger.error(f"Vocabulary generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Generation failed")


@router.get("/vocabulary/word/{word}")
async def get_vocabulary_word(
    word: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_optional_user),
) -> Optional[VocabularyProgressResponse]:
    """
    Get vocabulary word progress.

    Args:
        word: The vocabulary word

    Returns:
        Word progress information
    """
    try:
        vocab = db.query(VocabularyWord).filter(
            VocabularyWord.user_id == user.id,
            VocabularyWord.word == word
        ).first()

        if not vocab:
            raise HTTPException(status_code=404, detail="Word not found")

        return VocabularyProgressResponse(
            word=vocab.word,
            is_learned=vocab.is_learned,
            practice_count=vocab.practice_count,
            correct_count=vocab.correct_count,
            accuracy_score=vocab.accuracy_score,
            last_practiced=vocab.last_practiced
        )
    except Exception as e:
        logger.error(f"Vocabulary lookup failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Lookup failed")


@router.put("/vocabulary/progress")
async def update_vocabulary_progress(
    request: VocabularyProgressRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_optional_user),
) -> VocabularyProgressResponse:
    """
    Update vocabulary word progress.

    Args:
        request: Progress update with accuracy, learned status, etc.

    Returns:
        Updated progress
    """
    try:
        vocab = db.query(VocabularyWord).filter(
            VocabularyWord.user_id == user.id,
            VocabularyWord.word == request.word
        ).first()

        if not vocab:
            raise HTTPException(status_code=404, detail="Word not found")

        # Update progress
        vocab.practice_count += 1
        vocab.last_practiced = datetime.utcnow()

        if request.is_learned is not None:
            vocab.is_learned = request.is_learned

        if request.accuracy_score is not None:
            # Update average accuracy
            if vocab.accuracy_score is None:
                vocab.accuracy_score = request.accuracy_score
            else:
                # Weighted average
                vocab.accuracy_score = (
                    vocab.accuracy_score * vocab.correct_count +
                    request.accuracy_score
                ) / (vocab.correct_count + 1)

            if request.accuracy_score >= 8:  # Good pronunciation
                vocab.correct_count += 1

        db.commit()

        return VocabularyProgressResponse(
            word=vocab.word,
            is_learned=vocab.is_learned,
            practice_count=vocab.practice_count,
            correct_count=vocab.correct_count,
            accuracy_score=vocab.accuracy_score,
            last_practiced=vocab.last_practiced
        )
    except Exception as e:
        logger.error(f"Progress update failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Update failed")
