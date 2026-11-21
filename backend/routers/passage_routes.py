import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from auth import get_optional_user
from models import User
from reading_service import generate_passage, get_passage_quiz
from schemas import PassageQuizRequest, PassageQuizResponse, PassageResponse

router = APIRouter(tags=["passage"])
logger = logging.getLogger(__name__)

_UNAVAILABLE = "Impossible de générer le texte pour le moment. Veuillez réessayer."


@router.post("/generate-passage", response_model=PassageResponse)
def post_generate_passage(
  payload: PassageQuizRequest | None = Body(default=None),
  _user: User = Depends(get_optional_user)
) -> PassageResponse:
  try:
    return generate_passage(payload.level if payload else None)
  except RuntimeError as error:
    logger.warning("Passage generation failed: %s", error)
    raise HTTPException(status_code=503, detail=_UNAVAILABLE) from error


@router.post("/generate-passage-quiz", response_model=PassageQuizResponse)
def post_generate_passage_quiz(
  payload: PassageQuizRequest | None = Body(default=None),
  _user: User = Depends(get_optional_user)
) -> PassageQuizResponse:
  try:
    return get_passage_quiz(payload.level if payload else None, payload.session_id if payload else None)
  except RuntimeError as error:
    logger.warning("Passage quiz generation failed: %s", error)
    raise HTTPException(status_code=503, detail=_UNAVAILABLE) from error
