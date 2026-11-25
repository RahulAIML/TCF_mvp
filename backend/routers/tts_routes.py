import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user, get_optional_user
from database import SessionLocal, get_db
from guest import is_guest
from models import TtsAudioHistory, User
from schemas import TtsGenerateRequest, TtsHistoryItem, TtsVoice
import tts_jobs
from tts_service import (
    MAX_LONG_TEXT_LENGTH, generate_tts_audio, get_voice, list_active_voices, list_languages,
    split_for_speech,
)

logger = logging.getLogger("tts_routes")
router = APIRouter(prefix="/api/tts", tags=["tts"])

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/voices", response_model=list[TtsVoice])
async def get_voices(language: str | None = None, _user: User = Depends(get_optional_user)) -> list[TtsVoice]:
    """Every voice, or only those of one language (fr, en, es, pt)."""
    return list_active_voices(language)


@router.get("/languages")
async def get_languages(_user: User = Depends(get_optional_user)) -> list[dict]:
    """The languages text can be spoken in, with how many voices each has."""
    return list_languages()


@router.post("/generate")
def post_generate_tts(
    payload: TtsGenerateRequest,
    user: User = Depends(get_optional_user),
) -> dict:
    """Start generation in the background and return a job_id at once; poll /job/{job_id} for progress."""
    try:
        voice = get_voice(payload.voice_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Cette voix n'est pas disponible.") from exc
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Le texte est vide.")
    if len(text) > MAX_LONG_TEXT_LENGTH:
        raise HTTPException(status_code=400, detail=f"The text is longer than {MAX_LONG_TEXT_LENGTH:,} characters.")

    job_id = str(uuid4())
    total_parts = max(1, len(split_for_speech(text)))
    tts_jobs.create(job_id, total_parts, len(text))

    # Guests share one demo account: their history lives in the browser, not the database.
    user_id = None if is_guest(user) else user.id

    def _progress(done: int, total: int) -> None:
        tts_jobs.update(job_id, done_parts=min(done, total), total_parts=total)

    def _run() -> None:
        try:
            audio_url = generate_tts_audio(text, payload.voice_id, _progress)
            tts_jobs.update(job_id, audio_url=audio_url, status="done", done_parts=total_parts)

            if user_id is not None:
                session = SessionLocal()
                try:
                    session.add(TtsAudioHistory(
                        user_id=user_id,
                        audio_url=audio_url,
                        voice_id=payload.voice_id,
                        voice_label=voice["label"],
                        text_preview=text[:200],
                    ))
                    session.commit()
                except Exception as exc:
                    logger.warning("DB write failed for job %s: %s", job_id, exc)
                    session.rollback()
                finally:
                    session.close()

        except Exception as exc:
            logger.error("TTS job %s failed: %s", job_id, exc)
            tts_jobs.update(job_id, status="error", error="The audio could not be generated. Please try again.")

    import limits
    try:
        if total_parts > 1:
            tts_jobs.submit_long(_run)
        else:
            limits.submit(_run)
    except tts_jobs.LongBusy:
        tts_jobs.update(job_id, status="error", error="Another long recording is being made. Please try again in a minute.")
    except limits.Busy:
        tts_jobs.update(job_id, status="error", error="Audio is busy right now. Please try again.")
    return {"job_id": job_id, "status": "pending", "total_parts": total_parts}


@router.get("/job/{job_id}")
def get_tts_job(job_id: str) -> dict:
    """Poll job status. Returns {status, audio_url, error, total_parts, done_parts}."""
    job = tts_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    return job


@router.get("/history", response_model=list[TtsHistoryItem])
def get_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TtsHistoryItem]:
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


@router.delete("/history/{item_id}", status_code=204)
def delete_history_item(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    row = db.query(TtsAudioHistory).filter(
        TtsAudioHistory.id == item_id,
        TtsAudioHistory.user_id == user.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
