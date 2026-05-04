"""
Pronunciation Training Routes
Routes for pronunciation evaluation using Gemini and ElevenLabs TTS.
"""

import io
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from database import get_db
from elevenlabs_service import elevenlabs_service
from gemini_service import gemini_service
from models import PronunciationEvaluation, User, VocabularyWord
from schemas import (
    PronunciationEvaluationRequest,
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


def get_current_user(db: Session = Depends(get_db)) -> User:
    """Get current user from token (simplified)."""
    # In production, validate JWT token here
    # For now, assume user_id=1
    user = db.query(User).filter(User.id == 1).first()
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.post("/evaluate")
async def evaluate_pronunciation(
    target_text: str = Form(...),
    audio_file: UploadFile = File(...),
    language: str = Form("fr"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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

        # Save uploaded audio
        audio_filename = f"{user.id}_{datetime.utcnow().timestamp()}.mp3"
        audio_path = os.path.join(AUDIO_STORAGE_PATH, audio_filename)

        audio_content = await audio_file.read()
        with open(audio_path, "wb") as f:
            f.write(audio_content)

        # Evaluate pronunciation using Gemini
        evaluation = gemini_service.evaluate_pronunciation(
            expected_text=target_text,
            audio_path=audio_path,
            language=language
        )

        # Store evaluation in database
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
async def get_pronunciation_guide(
    word: str,
    language: str = "fr"
) -> dict:
    """
    Get native pronunciation audio for a word.

    Args:
        word: Word to pronounce
        language: Language (fr, en)

    Returns:
        {"audio_url": str, "word": str}
    """
    try:
        # Generate audio using ElevenLabs
        audio_bytes = elevenlabs_service.generate_pronunciation_guide(
            word=word,
            language=language
        )

        if not audio_bytes:
            raise HTTPException(status_code=500, detail="Audio generation failed")

        # Save audio to storage
        os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)
        audio_filename = f"guide_{word.replace(' ', '_')}_{datetime.utcnow().timestamp()}.mp3"
        audio_path = os.path.join(AUDIO_STORAGE_PATH, audio_filename)

        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        return {
            "word": word,
            "audio_url": f"/audio/{audio_filename}",
            "language": language
        }
    except Exception as e:
        logger.error(f"Pronunciation guide generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Guide generation failed")


# ── VOCABULARY ROUTES ────────────────────────────────────────────────────────

@router.post("/vocabulary/generate")
async def generate_vocabulary(
    request: VocabularyWordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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

        # Generate audio for each word using ElevenLabs
        vocab_items = []
        for word_data in words:
            word = word_data.get("word", "")

            # Generate pronunciation audio
            audio_bytes = elevenlabs_service.generate_pronunciation_guide(
                word=word,
                language=request.language
            )

            audio_url = None
            if audio_bytes:
                os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)
                audio_filename = (
                    f"vocab_{request.language}_{word.replace(' ', '_')}_"
                    f"{datetime.utcnow().timestamp()}.mp3"
                )
                audio_path = os.path.join(AUDIO_STORAGE_PATH, audio_filename)

                with open(audio_path, "wb") as f:
                    f.write(audio_bytes)

                audio_url = f"/audio/{audio_filename}"

            # Store in database
            vocab_record = VocabularyWord(
                user_id=user.id,
                word=word,
                language=request.language,
                level=request.level,
                meaning=word_data.get("meaning", ""),
                example=word_data.get("example", ""),
                example_translation=word_data.get("example_translation"),
                phonetic=word_data.get("phonetic"),
                audio_url=audio_url,
                source="generated"
            )
            db.add(vocab_record)

            vocab_items.append(VocabularyWordItem(
                word=word,
                meaning=word_data.get("meaning", ""),
                example=word_data.get("example", ""),
                example_translation=word_data.get("example_translation"),
                phonetic=word_data.get("phonetic"),
                audio_url=audio_url
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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
