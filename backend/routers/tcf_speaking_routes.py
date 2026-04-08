from fastapi import APIRouter, Depends, HTTPException

from auth import get_optional_user
from models import User
from schemas import (
  TcfConversationRequest,
  TcfConversationResponse,
  TcfSpeakingEvaluationRequest,
  TcfSpeakingEvaluationResponse
)
from tcf_ai_service import evaluate_tcf_speaking_conversation, generate_tcf_speaking_reply

router = APIRouter(prefix="/tcf", tags=["tcf", "speaking"])


@router.post("/conversation", response_model=TcfConversationResponse)
async def post_conversation(
  payload: TcfConversationRequest,
  _user: User = Depends(get_optional_user)
) -> TcfConversationResponse:
  try:
    response = generate_tcf_speaking_reply(
      message=payload.message,
      history=[item.model_dump() for item in payload.history],
      task_type=payload.task_type,
      mode=payload.mode or "practice",
      hints=payload.hints,
      session_id=payload.session_id
    )
  except RuntimeError as error:
    raise HTTPException(status_code=500, detail=str(error)) from error

  return TcfConversationResponse(**response)


@router.post("/evaluate", response_model=TcfSpeakingEvaluationResponse)
async def post_speaking_evaluation(
  payload: TcfSpeakingEvaluationRequest,
  _user: User = Depends(get_optional_user)
) -> TcfSpeakingEvaluationResponse:
  try:
    evaluation = evaluate_tcf_speaking_conversation(
      history=[item.model_dump() for item in payload.history],
      task_type=payload.task_type
    )
  except RuntimeError as error:
    raise HTTPException(status_code=500, detail=str(error)) from error

  return TcfSpeakingEvaluationResponse(**evaluation)
