import logging
import threading
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user, get_optional_user
from database import SessionLocal, get_db
from models import TtsAudioHistory, User
from schemas import TtsGenerateRequest, TtsHistoryItem, TtsVoice
from tts_service import generate_tts_audio, get_voice, list_active_voices

logger = logging.getLogger("tts_routes")
router = APIRouter(prefix="/api/tts", tags=["tts"])

# ---------------------------------------------------------------------------
# In-process job cache (single Render dyno → works fine)
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_jobs: dict[str, dict] = {}  # job_id → {status, audio_url, error}
_MAX_JOBS = 500


def _evict() -> None:
    if len(_jobs) > _MAX_JOBS:
        for k in list(_jobs.keys())[: _MAX_JOBS // 2]:
            _jobs.pop(k, None)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/voices", response_model=list[TtsVoice])
async def get_voices(_user: User = Depends(get_optional_user)) -> list[TtsVoice]:
    return list_active_voices()


@router.post("/generate")
async def post_generate_tts(
    payload: TtsGenerateRequest,
    user: User = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> dict:
    """Start generation in a background thread; return job_id immediately."""
    job_id = str(uuid4())
    with _lock:
        _evict()
        _jobs[job_id] = {"status": "pending", "audio_url": None, "error": None}

    user_id = user.id if user else None

    def _run() -> None:
        try:
            audio_url = generate_tts_audio(payload.text, payload.voice_id)
            with _lock:
                _jobs[job_id]["audio_url"] = audio_url
                _jobs[job_id]["status"] = "done"

            if user_id is not None:
                session = SessionLocal()
                try:
                    voice = get_voice(payload.voice_id)
                    session.add(TtsAudioHistory(
                        user_id=user_id,
                        audio_url=audio_url,
                        voice_id=payload.voice_id,
                        voice_label=voice["label"],
                        text_preview=payload.text.strip()[:200],
                    ))
                    session.commit()
                except Exception as exc:
                    logger.warning("DB write failed for job %s: %s", job_id, exc)
                    session.rollback()
                finally:
                    session.close()

        except Exception as exc:
            logger.error("TTS job %s failed: %s", job_id, exc)
            with _lock:
                _jobs[job_id]["status"] = "error"
                _jobs[job_id]["error"] = str(exc)

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id, "status": "pending"}


@router.get("/job/{job_id}")
async def get_tts_job(job_id: str) -> dict:
    """Poll job status. Returns {status, audio_url, error}."""
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    return job


@router.get("/history", response_model=list[TtsHistoryItem])
async def get_history(
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
async def delete_history_item(
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
