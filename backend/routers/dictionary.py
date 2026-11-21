import json
import logging
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from tcf_ai_service import explain_word, explain_text, translate_passage, stream_explain_text, stream_translate
from auth import get_optional_user
from models import User
from schemas import WordMeaningRequest, WordMeaningResponse, ExplainTextRequest, ExplainTextResponse

logger = logging.getLogger("dictionary")
router = APIRouter(tags=["dictionary"])

_UNAVAILABLE = "Le service est momentanément indisponible. Réessayez dans un instant."


class TranslateStreamRequest(BaseModel):
  text: str = Field(min_length=1, max_length=8000)
  direction: Literal["fr-en", "en-fr"] = "fr-en"


def _sse_stream(tokens) -> StreamingResponse:
  def _generate():
    try:
      for token in tokens:
        yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
    except Exception as exc:
      logger.error("Dictionary stream error: %s", exc)
      yield f"data: {json.dumps({'error': _UNAVAILABLE}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"

  return StreamingResponse(
    _generate(),
    media_type="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
  )


@router.post("/word-meaning", response_model=WordMeaningResponse)
def post_word_meaning(
  payload: WordMeaningRequest,
  _user: User = Depends(get_optional_user)
) -> WordMeaningResponse:
  try:
    return explain_word(payload.word)
  except RuntimeError as error:
    logger.error("word-meaning failed: %s", error)
    raise HTTPException(status_code=503, detail=_UNAVAILABLE) from error


@router.post("/explain-text", response_model=ExplainTextResponse)
def post_explain_text(
  payload: ExplainTextRequest,
  _user: User = Depends(get_optional_user)
) -> ExplainTextResponse:
  try:
    return ExplainTextResponse(**explain_text(payload.text))
  except RuntimeError as error:
    logger.error("explain-text failed: %s", error)
    raise HTTPException(status_code=503, detail=_UNAVAILABLE) from error


@router.post("/explain-text/stream")
def post_explain_text_stream(
  payload: ExplainTextRequest,
  _user: User = Depends(get_optional_user)
) -> StreamingResponse:
  return _sse_stream(stream_explain_text(payload.text))


@router.post("/translate")
def post_translate(
  text: str = Body(..., embed=True),
  _user: User = Depends(get_optional_user)
) -> dict:
  try:
    translation = translate_passage(text)
    return {"translation": translation}
  except RuntimeError as error:
    logger.error("translate failed: %s", error)
    raise HTTPException(status_code=503, detail=_UNAVAILABLE) from error


@router.post("/translate/stream")
def post_translate_stream(
  payload: TranslateStreamRequest,
  _user: User = Depends(get_optional_user)
) -> StreamingResponse:
  return _sse_stream(stream_translate(payload.text, payload.direction))
