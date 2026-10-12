import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user, get_optional_user
from database import get_db
from models import TtsAudioHistory, User
from schemas import TtsGenerateRequest, TtsGenerateResponse, TtsHistoryItem, TtsVoice
from tts_service import generate_tts_audio, list_active_voices, get_voice

logger = logging.getLogger("tts_routes")
router = APIRouter(prefix="/api/tts", tags=["tts"])


@router.get("/voices", response_model=list[TtsVoice])
async def get_voices(_user: User = Depends(get_optional_user)) -> list[TtsVoice]:
    return list_active_voices()


@router.post("/generate", response_model=TtsGenerateResponse)
async def post_generate_tts(
    payload: TtsGenerateRequest,
    user: User = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> TtsGenerateResponse:
    try:
        audio_url = generate_tts_audio(payload.text, payload.voice_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected TTS generation failure: %s", exc)
        raise HTTPException(status_code=502, detail=f"TTS generation error: {exc}") from exc

    voice = get_voice(payload.voice_id)
    preview = payload.text.strip()[:200]

    if user:
        try:
            db.add(TtsAudioHistory(
                user_id=user.id,
                audio_url=audio_url,
                voice_id=payload.voice_id,
                voice_label=voice["label"],
                text_preview=preview,
            ))
            db.commit()
        except Exception as db_err:
            db.rollback()
            logger.error("Failed to persist TTS audio history to DB: %s", db_err)

    return TtsGenerateResponse(
        audio_url=audio_url,
        voice_id=payload.voice_id,
        character_count=len(payload.text.strip()),
    )


@router.get("/history", response_model=list[TtsHistoryItem])
async def get_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TtsHistoryItem]:
    try:
        rows = (
            db.query(TtsAudioHistory)
            .filter(TtsAudioHistory.user_id == user.id)
            .order_by(TtsAudioHistory.created_at.desc())
            .limit(50)
            .all()
        )
        return [
            TtsHistoryItem(
                id=r.id,
                audio_url=r.audio_url,
                voice_id=r.voice_id,
                voice_label=r.voice_label,
                text_preview=r.text_preview,
                created_at=r.created_at.isoformat(),
            )
            for r in rows
        ]
    except Exception as db_err:
        logger.error("Failed to query TTS audio history: %s", db_err)
        return []


@router.delete("/history/{item_id}", status_code=204)
async def delete_history_item(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        row = db.query(TtsAudioHistory).filter(
            TtsAudioHistory.id == item_id,
            TtsAudioHistory.user_id == user.id,
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        db.delete(row)
        db.commit()
    except HTTPException:
        raise
    except Exception as db_err:
        db.rollback()
        logger.error("Failed to delete TTS history item %s: %s", item_id, db_err)
        raise HTTPException(status_code=500, detail="Failed to delete history item") from db_err
