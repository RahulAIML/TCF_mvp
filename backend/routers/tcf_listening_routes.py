from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from tcf_ai_service import generate_tcf_listening_audio
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
from tcf_ai_service import generate_tcf_listening_question

router = APIRouter(prefix="/tcf", tags=["tcf", "listening"])


@router.post("/generate-listening-question", response_model=ListeningQuestionResponse)
async def post_generate_listening_question(
  payload: TcfGenerateListeningQuestionRequest,
  _user: User = Depends(get_optional_user)
) -> ListeningQuestionResponse:
  return generate_tcf_listening_question(payload.question_number, payload.session_id, payload.defer_audio)


@router.post("/generate-listening-audio", response_model=GenerateListeningAudioResponse)
async def post_generate_listening_audio(
  payload: TcfGenerateListeningAudioRequest,
  _user: User = Depends(get_optional_user)
) -> GenerateListeningAudioResponse:
  audio_url = generate_tcf_listening_audio(payload.script, payload.question_number, payload.session_id)
  return GenerateListeningAudioResponse(audio_url=audio_url)


@router.post("/submit-listening-exam", response_model=SubmitListeningExamResponse)
async def post_submit_listening_exam(
  payload: SubmitListeningExamRequest,
  db: Session = Depends(get_db),
  user: User = Depends(get_optional_user)
) -> SubmitListeningExamResponse:
  total = max(payload.total, 0)
  score = max(payload.score, 0)
  accuracy = (score / total) * 100 if total else 0
  completion_time = int((payload.completed_at - payload.started_at).total_seconds())

  attempt = ListeningAttempt(
    user_id=user.id,
    score=score,
    total=total,
    accuracy=accuracy,
    completion_time=max(completion_time, 0)
  )
  db.add(attempt)
  db.commit()

  return SubmitListeningExamResponse(
    score=score,
    total=total,
    accuracy=round(accuracy, 2),
    completion_time=max(completion_time, 0)
  )
