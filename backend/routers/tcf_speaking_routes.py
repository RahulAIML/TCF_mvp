import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Iterator

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from audio_mime import NO_SPEECH_MESSAGE, base_mime
from auth import get_optional_user
from gemini_service import GeminiService
from models import User
from schemas import (
  TcfConversationRequest,
  TcfConversationResponse,
  TcfSpeakingEvaluationRequest,
  TcfSpeakingEvaluationResponse,
  TcfSpeakingOpeningRequest,
)
from speaking_pregen import take_opening
from tcf_ai_service import (
  evaluate_tcf_speaking_conversation,
  generate_tcf_speaking_reply,
  speaking_low_response_evaluation,
  speaking_reply_audio,
  speaking_scores_without_model_answer,
  stream_speaking_model_answer,
  stream_tcf_speaking_reply,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tcf", tags=["tcf", "speaking"])

MAX_AUDIO_BYTES = 15 * 1024 * 1024
_UNAVAILABLE = "Le service vocal est momentanément indisponible. Réessayez dans un instant."
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse(payload: object) -> str:
  return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _is_opening(payload: TcfConversationRequest) -> bool:
  return payload.message == "__START__" and not payload.history and not payload.session_topic


@router.post("/speaking/opening", response_model=TcfConversationResponse)
def post_speaking_opening(
  payload: TcfSpeakingOpeningRequest,
  _user: User = Depends(get_optional_user)
) -> TcfConversationResponse:
  """A ready-made session start (new topic + examiner's first line + audio), served once."""
  try:
    opening = take_opening(payload.task_type, payload.mode or "practice", payload.hints, payload.session_id)
  except Exception as error:
    logger.error("Speaking opening failed: %s", error)
    raise HTTPException(status_code=503, detail=_UNAVAILABLE) from error
  return TcfConversationResponse(**opening)


@router.post("/conversation", response_model=TcfConversationResponse)
def post_conversation(
  payload: TcfConversationRequest,
  _user: User = Depends(get_optional_user)
) -> TcfConversationResponse:
  try:
    if _is_opening(payload):
      response = take_opening(payload.task_type, payload.mode or "practice", payload.hints, payload.session_id)
    else:
      response = generate_tcf_speaking_reply(
        message=payload.message,
        history=[item.model_dump() for item in payload.history],
        task_type=payload.task_type,
        mode=payload.mode or "practice",
        hints=payload.hints,
        session_id=payload.session_id,
        session_topic=payload.session_topic,
        examiner_name=payload.examiner_name,
      )
  except Exception as error:
    logger.error("Speaking reply failed: %s", error)
    raise HTTPException(status_code=503, detail=_UNAVAILABLE) from error

  return TcfConversationResponse(**response)


@router.post("/conversation/stream")
def post_conversation_stream(
  payload: TcfConversationRequest,
  _user: User = Depends(get_optional_user)
) -> StreamingResponse:
  """
  SSE: {"type":"meta"} → {"type":"token"}* → {"type":"reply"} → {"type":"audio"} → [DONE].
  The examiner's text appears as it is written; the audio follows once the text is complete.
  """
  def _events() -> Iterator[str]:
    try:
      if _is_opening(payload):
        opening = take_opening(payload.task_type, payload.mode or "practice", payload.hints, payload.session_id)
        yield _sse({"type": "meta", "session_topic": opening.get("session_topic"), "examiner_name": opening.get("examiner_name")})
        yield _sse({"type": "token", "token": opening["reply"]})
        yield _sse({"type": "reply", "reply": opening["reply"]})
        yield _sse({"type": "audio", "audio_url": opening.get("audio_url")})
      else:
        reply_text = ""
        for kind, value in stream_tcf_speaking_reply(
          message=payload.message,
          history=[item.model_dump() for item in payload.history],
          task_type=payload.task_type,
          mode=payload.mode or "practice",
          hints=payload.hints,
          session_id=payload.session_id,
          session_topic=payload.session_topic,
          examiner_name=payload.examiner_name,
        ):
          if kind == "meta":
            yield _sse({"type": "meta", **value})
          elif kind == "token":
            yield _sse({"type": "token", "token": value})
          else:
            reply_text = value
        if not reply_text:
          raise RuntimeError("Empty examiner reply.")
        yield _sse({"type": "reply", "reply": reply_text})
        yield _sse({"type": "audio", "audio_url": speaking_reply_audio(reply_text, payload.session_id)})
    except Exception as error:
      logger.error("Speaking stream failed: %s", error)
      yield _sse({"type": "error", "message": _UNAVAILABLE})
    yield "data: [DONE]\n\n"

  return StreamingResponse(_events(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/evaluate", response_model=TcfSpeakingEvaluationResponse)
def post_speaking_evaluation(
  payload: TcfSpeakingEvaluationRequest,
  _user: User = Depends(get_optional_user)
) -> TcfSpeakingEvaluationResponse:
  try:
    evaluation = evaluate_tcf_speaking_conversation(
      history=[item.model_dump() for item in payload.history],
      task_type=payload.task_type
    )
  except Exception as error:
    logger.error("Speaking evaluation failed: %s", error)
    raise HTTPException(status_code=503, detail=_UNAVAILABLE) from error

  return TcfSpeakingEvaluationResponse(**evaluation)


@router.post("/evaluate/stream")
def post_speaking_evaluation_stream(
  payload: TcfSpeakingEvaluationRequest,
  _user: User = Depends(get_optional_user)
) -> StreamingResponse:
  """
  SSE: {"type":"scores", ...} as soon as the scores are ready, while the model answer streams as
  {"type":"token"} chunks; then {"type":"done"} and [DONE].
  """
  history = [item.model_dump() for item in payload.history]

  def _events() -> Iterator[str]:
    low = speaking_low_response_evaluation(history)
    if low is not None:
      yield _sse({"type": "scores", **low})
      yield _sse({"type": "done"})
      yield "data: [DONE]\n\n"
      return

    executor = ThreadPoolExecutor(max_workers=1)
    scores_future = executor.submit(speaking_scores_without_model_answer, history, payload.task_type)
    scores_sent = False

    def _scores_event() -> str:
      scores = scores_future.result()
      scores.pop("improved_response", None)
      return _sse({"type": "scores", **scores})

    try:
      try:
        for token in stream_speaking_model_answer(history, payload.task_type):
          if not scores_sent and scores_future.done():
            yield _scores_event()
            scores_sent = True
          yield _sse({"type": "token", "token": token})
      except Exception as error:
        logger.warning("Model answer stream failed: %s", error)
      if not scores_sent:
        yield _scores_event()
      yield _sse({"type": "done"})
    except Exception as error:
      logger.error("Speaking evaluation stream failed: %s", error)
      yield _sse({"type": "error", "message": _UNAVAILABLE})
    finally:
      executor.shutdown(wait=False)
    yield "data: [DONE]\n\n"

  return StreamingResponse(_events(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/transcribe-audio")
async def transcribe_audio(
  audio: UploadFile = File(...),
  language: str = Form(default="fr"),
  _user: User = Depends(get_optional_user)
) -> dict:
  """
  Transcribe uploaded audio (webm, ogg, mp4/m4a, wav, mp3 — whatever MediaRecorder produces).
  Returns {"transcript": str, "no_speech": bool}; silence gives an empty transcript, never invented text.
  """
  mime = base_mime(audio.content_type, audio.filename)
  audio_data = await audio.read()
  if not audio_data:
    raise HTTPException(status_code=400, detail="L'enregistrement est vide. Réessayez.")
  if len(audio_data) > MAX_AUDIO_BYTES:
    raise HTTPException(status_code=413, detail="L'enregistrement est trop long.")

  try:
    transcript = await run_in_threadpool(
      GeminiService.transcribe_bytes, audio_data, language.split("-")[0], mime
    )
  except Exception as exc:
    logger.error("Transcription failed: %s", exc)
    raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc

  if not transcript:
    return {"transcript": "", "no_speech": True, "message": NO_SPEECH_MESSAGE}
  return {"transcript": transcript, "no_speech": False}
