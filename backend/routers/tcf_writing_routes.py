import json
import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from auth import get_optional_user
from database import SessionLocal, get_db
from models import TcfWritingSession, User
from schemas import (
  TcfGenerateWritingTasksRequest,
  TcfGenerateWritingTasksResponse,
  TcfWritingEvaluationRequest,
  TcfWritingEvaluationResponse,
  TcfWritingProgressRequest,
  WritingProgressResponse,
  TcfWritingStepFeedbackRequest,
  TcfWritingStepFeedbackResponse,
  TcfWritingSubmitRequest,
  TcfWritingSubmitResponse,
  TcfWritingAssistantRequest,
  TcfWritingAssistantResponse
)
from tcf_ai_service import (
  assist_tcf_writing,
  evaluate_tcf_writing_step,
  evaluate_tcf_writing_task,
  finalize_writing_evaluation,
  generate_tcf_writing_tasks,
  parse_writing_step_feedback,
  stream_assist_tcf_writing,
  stream_writing_evaluation_tokens,
  stream_writing_step_feedback,
)

logger = logging.getLogger("tcf.writing")
router = APIRouter(prefix="/tcf", tags=["tcf", "writing"])

_UNAVAILABLE = "Le service d'évaluation est momentanément indisponible. Réessayez dans un instant."
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse(payload: dict) -> str:
  return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_done() -> str:
  return "data: [DONE]\n\n"


@router.post("/generate-writing-tasks", response_model=TcfGenerateWritingTasksResponse)
def post_generate_writing_tasks(
  payload: TcfGenerateWritingTasksRequest,
  _user: User = Depends(get_optional_user)
) -> TcfGenerateWritingTasksResponse:
  try:
    prompts = generate_tcf_writing_tasks(payload.session_id)
  except RuntimeError as error:
    logger.error("writing task generation failed: %s", error)
    raise HTTPException(status_code=503, detail="Impossible de générer les consignes pour le moment. Réessayez.") from error
  return TcfGenerateWritingTasksResponse(**prompts)


@router.post("/evaluate-writing", response_model=TcfWritingEvaluationResponse)
def post_evaluate_writing(
  payload: TcfWritingEvaluationRequest,
  _user: User = Depends(get_optional_user)
) -> TcfWritingEvaluationResponse:
  try:
    evaluation = evaluate_tcf_writing_task(payload.task_type, payload.prompt, payload.response_text)
  except RuntimeError as error:
    logger.error("writing evaluation failed: %s", error)
    raise HTTPException(status_code=503, detail=_UNAVAILABLE) from error
  return TcfWritingEvaluationResponse(**evaluation)


@router.post("/evaluate-writing/stream")
def post_evaluate_writing_stream(
  payload: TcfWritingEvaluationRequest,
  _user: User = Depends(get_optional_user)
) -> StreamingResponse:
  """Streams the evaluation text ({"token"}), then the normalized result ({"evaluation"})."""

  def _generate():
    buffer: list[str] = []
    try:
      for token in stream_writing_evaluation_tokens(payload.task_type, payload.prompt, payload.response_text):
        buffer.append(token)
        yield _sse({"token": token})
      evaluation = finalize_writing_evaluation("".join(buffer), payload.task_type, payload.prompt, payload.response_text)
      yield _sse({"evaluation": evaluation})
    except Exception as exc:
      logger.error("writing evaluation stream failed: %s", exc)
      yield _sse({"error": _UNAVAILABLE})
    yield _sse_done()

  return StreamingResponse(_generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/evaluate-writing-step", response_model=TcfWritingStepFeedbackResponse)
def post_evaluate_writing_step(
  payload: TcfWritingStepFeedbackRequest,
  _user: User = Depends(get_optional_user)
) -> TcfWritingStepFeedbackResponse:
  try:
    evaluation = evaluate_tcf_writing_step(payload.task_type, payload.step, payload.prompt, payload.text)
  except RuntimeError as error:
    logger.error("writing step feedback failed: %s", error)
    raise HTTPException(status_code=503, detail=_UNAVAILABLE) from error
  return TcfWritingStepFeedbackResponse(**evaluation)


@router.post("/evaluate-writing-step/stream")
def post_evaluate_writing_step_stream(
  payload: TcfWritingStepFeedbackRequest,
  _user: User = Depends(get_optional_user)
) -> StreamingResponse:
  """Streams step feedback ({"token"}), then the parsed result ({"feedback": {...}})."""

  def _generate():
    buffer: list[str] = []
    try:
      for token in stream_writing_step_feedback(payload.task_type, payload.step, payload.prompt, payload.text):
        buffer.append(token)
        yield _sse({"token": token})
      yield _sse({"feedback": parse_writing_step_feedback("".join(buffer))})
    except Exception as exc:
      logger.error("writing step stream failed: %s", exc)
      yield _sse({"error": _UNAVAILABLE})
    yield _sse_done()

  return StreamingResponse(_generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/writing/assistant", response_model=TcfWritingAssistantResponse)
def post_writing_assistant(
  payload: TcfWritingAssistantRequest,
  _user: User = Depends(get_optional_user)
) -> TcfWritingAssistantResponse:
  try:
    reply = assist_tcf_writing(
      action=payload.action,
      message=payload.message,
      direction=payload.direction,
      context=payload.context
    )
  except RuntimeError as error:
    logger.error("writing assistant failed: %s", error)
    raise HTTPException(status_code=503, detail=_UNAVAILABLE) from error

  return TcfWritingAssistantResponse(reply=reply)


@router.post("/writing/assistant/stream")
def post_writing_assistant_stream(
  payload: TcfWritingAssistantRequest,
  _user: User = Depends(get_optional_user)
) -> StreamingResponse:
  def _generate():
    try:
      for token in stream_assist_tcf_writing(
        action=payload.action,
        message=payload.message,
        direction=payload.direction,
        context=payload.context,
      ):
        yield _sse({"token": token})
    except Exception as exc:
      logger.error("writing assistant stream failed: %s", exc)
      yield _sse({"error": _UNAVAILABLE})
    yield _sse_done()

  return StreamingResponse(_generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/writing/save-progress", response_model=WritingProgressResponse)
def post_save_writing_progress(
  payload: TcfWritingProgressRequest,
  db: Session = Depends(get_db),
  user: User = Depends(get_optional_user)
) -> WritingProgressResponse:
  session = (
    db.query(TcfWritingSession)
    .filter(TcfWritingSession.session_id == payload.session_id, TcfWritingSession.user_id == user.id)
    .first()
  )

  if session is None:
    session = TcfWritingSession(
      user_id=user.id,
      session_id=payload.session_id,
      mode=payload.mode
    )
    db.add(session)

  steps_json = json.dumps(payload.steps, ensure_ascii=False)
  if payload.task_type == "task1":
    session.task1_steps = steps_json
    if payload.task_prompt:
      session.task1_prompt = payload.task_prompt
  elif payload.task_type == "task2":
    session.task2_steps = steps_json
    if payload.task_prompt:
      session.task2_prompt = payload.task_prompt
  else:
    session.task3_steps = steps_json
    if payload.task_prompt:
      session.task3_prompt = payload.task_prompt

  session.updated_at = datetime.utcnow()
  db.commit()

  return WritingProgressResponse(status="saved")


def _task_inputs(payload: TcfWritingSubmitRequest) -> list[tuple[str, str, str]]:
  return [
    ("task1", payload.task1_prompt, payload.task1_text),
    ("task2", payload.task2_prompt, payload.task2_text),
    ("task3", payload.task3_prompt, payload.task3_text),
  ]


def _save_submission(db: Session, user_id: int, payload: TcfWritingSubmitRequest, evaluations: dict) -> None:
  session = (
    db.query(TcfWritingSession)
    .filter(TcfWritingSession.session_id == payload.session_id, TcfWritingSession.user_id == user_id)
    .first()
  )
  if session is None:
    session = TcfWritingSession(user_id=user_id, session_id=payload.session_id, mode=payload.mode)
    db.add(session)

  session.task1_prompt = payload.task1_prompt
  session.task2_prompt = payload.task2_prompt
  session.task3_prompt = payload.task3_prompt
  session.task1_text = payload.task1_text
  session.task2_text = payload.task2_text
  session.task3_text = payload.task3_text
  session.task1_steps = json.dumps(payload.task1_steps or {}, ensure_ascii=False)
  session.task2_steps = json.dumps(payload.task2_steps or {}, ensure_ascii=False)
  session.task3_steps = json.dumps(payload.task3_steps or {}, ensure_ascii=False)
  session.task1_evaluation = json.dumps(evaluations["task1"], ensure_ascii=False)
  session.task2_evaluation = json.dumps(evaluations["task2"], ensure_ascii=False)
  session.task3_evaluation = json.dumps(evaluations["task3"], ensure_ascii=False)
  session.is_submitted = True
  session.updated_at = datetime.utcnow()
  db.commit()


@router.post("/writing/submit", response_model=TcfWritingSubmitResponse)
def post_submit_writing(
  payload: TcfWritingSubmitRequest,
  db: Session = Depends(get_db),
  user: User = Depends(get_optional_user)
) -> TcfWritingSubmitResponse:
  inputs = _task_inputs(payload)
  try:
    with ThreadPoolExecutor(max_workers=3) as pool:
      results = list(pool.map(lambda args: evaluate_tcf_writing_task(*args), inputs))
  except RuntimeError as error:
    logger.error("writing submit failed: %s", error)
    raise HTTPException(status_code=503, detail=_UNAVAILABLE) from error

  evaluations = {task: result for (task, _, _), result in zip(inputs, results)}
  _save_submission(db, user.id, payload, evaluations)

  return TcfWritingSubmitResponse(
    task1=TcfWritingEvaluationResponse(**evaluations["task1"]),
    task2=TcfWritingEvaluationResponse(**evaluations["task2"]),
    task3=TcfWritingEvaluationResponse(**evaluations["task3"])
  )


@router.post("/writing/submit/stream")
def post_submit_writing_stream(
  payload: TcfWritingSubmitRequest,
  user: User = Depends(get_optional_user)
) -> StreamingResponse:
  """
  Evaluates the three tasks in parallel and streams them multiplexed:
  {"task", "token"} while writing, {"task", "evaluation"} when a task is done, {"task", "error"} on failure,
  {"saved": bool} once all three are stored, then [DONE].
  """
  user_id = user.id
  inputs = _task_inputs(payload)
  events: "queue.Queue[tuple[str, str, object]]" = queue.Queue()

  def _worker(task: str, prompt: str, text: str) -> None:
    buffer: list[str] = []
    try:
      for token in stream_writing_evaluation_tokens(task, prompt, text):
        buffer.append(token)
        events.put(("token", task, token))
      events.put(("evaluation", task, finalize_writing_evaluation("".join(buffer), task, prompt, text)))
    except Exception as exc:
      logger.error("writing submit stream failed for %s: %s", task, exc)
      events.put(("error", task, _UNAVAILABLE))

  def _generate():
    for args in inputs:
      threading.Thread(target=_worker, args=args, daemon=True).start()
    evaluations: dict[str, object] = {}
    finished = 0
    while finished < len(inputs):
      kind, task, data = events.get()
      if kind == "token":
        yield _sse({"task": task, "token": data})
        continue
      finished += 1
      if kind == "evaluation":
        evaluations[task] = data
        yield _sse({"task": task, "evaluation": data})
      else:
        yield _sse({"task": task, "error": data})

    saved = False
    if len(evaluations) == len(inputs):
      db = SessionLocal()
      try:
        _save_submission(db, user_id, payload, evaluations)
        saved = True
      except Exception as exc:
        db.rollback()
        logger.error("writing submission save failed: %s", exc)
      finally:
        db.close()
    yield _sse({"saved": saved})
    yield _sse_done()

  return StreamingResponse(_generate(), media_type="text/event-stream", headers=_SSE_HEADERS)
