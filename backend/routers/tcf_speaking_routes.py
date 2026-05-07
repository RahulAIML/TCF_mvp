import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from auth import get_optional_user
from gemini_service import GeminiService
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
      session_id=payload.session_id,
      session_topic=payload.session_topic
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


@router.post("/transcribe-audio")
async def transcribe_audio(
  audio: UploadFile = File(...),
  language: str = Form(default="fr"),
  _user: User = Depends(get_optional_user)
) -> dict:
  """
  Transcribe uploaded audio using Gemini.
  Accepts webm, mp4, wav, ogg, mp3 — whatever MediaRecorder produces.
  Returns: { "transcript": str }
  """
  # Determine extension from content type
  content_type = audio.content_type or "audio/webm"
  ext_map = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".mp4",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
  }
  ext = ext_map.get(content_type, ".webm")

  audio_data = await audio.read()
  if not audio_data:
    raise HTTPException(status_code=400, detail="Empty audio file")

  tmp_path: str | None = None
  try:
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
      tmp.write(audio_data)
      tmp_path = tmp.name

    transcript = GeminiService.transcribe_speech(tmp_path, language, mime_type=content_type)
    return {"transcript": transcript.strip()}
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}") from exc
  finally:
    if tmp_path:
      try:
        os.unlink(tmp_path)
      except Exception:
        pass
