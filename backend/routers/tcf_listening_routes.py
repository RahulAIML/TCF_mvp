import logging

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


@router.post("/generate-listening-audio", response_model=GenerateListeningAudioResponse)
def post_generate_listening_audio(
  payload: TcfGenerateListeningAudioRequest,
  _user: User = Depends(get_optional_user)
) -> GenerateListeningAudioResponse:
  try:
    turns: list = []
    audio_url = listening_service.synthesize_listening_audio(payload.script, payload.speakers or None, report=turns)
  except Exception as error:
    logger.error("Listening audio failed: %s", error)
    raise HTTPException(status_code=503, detail="The audio could not be generated right now. Please try again.") from error
  return GenerateListeningAudioResponse(audio_url=audio_url, voices=turns)


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
