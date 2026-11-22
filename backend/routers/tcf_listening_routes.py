import logging

import audio_jobs
import resilience
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import listening_service
from auth import get_optional_user
from database import get_db
from models import ListeningAttempt, User
from schemas import (
  TcfGenerateListeningAudioRequest,
  GenerateListeningAudioResponse,
  TcfGenerateListeningQuestionRequest,
  ListeningQuestionResponse,
  SubmitListeningExamRequest,
  SubmitListeningExamResponse
)

logger = logging.getLogger("tcf.listening")

router = APIRouter(prefix="/tcf", tags=["tcf", "listening"])

_UNAVAILABLE = "The listening question could not be prepared right now. Please try again."


@router.post("/generate-listening-question", response_model=ListeningQuestionResponse)
def post_generate_listening_question(
  payload: TcfGenerateListeningQuestionRequest,
  _user: User = Depends(get_optional_user)
) -> ListeningQuestionResponse:
  try:
    return listening_service.get_question(
      payload.question_number, payload.session_id, payload.defer_audio, payload.target_level
    )
  except Exception as error:
    logger.error("Listening question failed: %s", error)
    raise HTTPException(status_code=503, detail=_UNAVAILABLE) from error


def _synthesize_for_job(script: str, speakers: list[str] | None) -> dict:
  """Run synthesis, retrying transient provider failures. Returns the URL and the per-turn voices."""
  turns: list = []

  def once() -> str:
    turns.clear()
    return listening_service.synthesize_listening_audio(script, speakers, report=turns)

  url = resilience.retry(once, attempts=3, base=0.4)
  return {"audio_url": url, "voices": list(turns)}


@router.post("/generate-listening-audio", response_model=GenerateListeningAudioResponse)
def post_generate_listening_audio(
  payload: TcfGenerateListeningAudioRequest,
  _user: User = Depends(get_optional_user)
) -> GenerateListeningAudioResponse:
  """Start synthesis and return as soon as the file is ready, or a job id if it is still running.

  The host cuts HTTP requests off at about 100 seconds. A long interview stays under that limit
  because the work continues in the background and the client polls.
  """
  job_id = audio_jobs.submit(lambda: _synthesize_for_job(payload.script, payload.speakers or None))
  done = audio_jobs.wait(job_id, audio_jobs.INLINE_WAIT_SECONDS)
  if done and done.get("status") == "ready" and done.get("audio_url"):
    return GenerateListeningAudioResponse(
      audio_url=done["audio_url"], voices=done.get("voices") or [], job_id=job_id, status="ready",
    )
  if done and done.get("status") == "failed":
    logger.error("Listening audio failed: %s", done.get("error"))
    raise HTTPException(status_code=503, detail="The audio could not be generated right now. Please try again.")
  return GenerateListeningAudioResponse(job_id=job_id, status="pending")


@router.get("/listening-audio-jobs/{job_id}", response_model=GenerateListeningAudioResponse)
def get_listening_audio_job(job_id: str) -> GenerateListeningAudioResponse:
  found = audio_jobs.snapshot(job_id)
  if found is None:
    raise HTTPException(status_code=404, detail="This audio request has expired. Please start it again.")
  return GenerateListeningAudioResponse(
    audio_url=found.get("audio_url"),
    voices=found.get("voices") or [],
    job_id=job_id,
    status=found.get("status") or "pending",
  )


@router.post("/submit-listening-exam", response_model=SubmitListeningExamResponse)
def post_submit_listening_exam(
  payload: SubmitListeningExamRequest,
  db: Session = Depends(get_db),
  user: User = Depends(get_optional_user)
) -> SubmitListeningExamResponse:
  total = max(payload.total, 0)
  score = max(payload.score, 0)
  accuracy = (score / total) * 100 if total else 0
  completion_time = max(int((payload.completed_at - payload.started_at).total_seconds()), 0)

  if user is not None:
    db.add(ListeningAttempt(
      user_id=user.id,
      score=score,
      total=total,
      accuracy=accuracy,
      completion_time=completion_time
    ))
    db.commit()

  return SubmitListeningExamResponse(
    score=score,
    total=total,
    accuracy=round(accuracy, 2),
    completion_time=completion_time
  )
