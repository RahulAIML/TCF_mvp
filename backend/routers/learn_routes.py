from __future__ import annotations
from starlette.concurrency import run_in_threadpool

import hashlib
import json
import logging
import threading
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Iterator

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import content_bank
import content_dedupe as dedupe
from learner import active_learner
from tcf_ai_service import (
  evaluate_learn_answer,
  extract_text_from_image_bytes,
  generate_learn_exercises,
  generate_learn_overview,
  generate_more_exercises,
  learn_question_fingerprint,
)
from auth import get_optional_user, is_guest_user
from database import get_db
from models import LearnSession, User
from schemas import (
  LearnAnalyzeRequest,
  LearnContentResponse,
  LearnEvaluateBatchRequest,
  LearnEvaluateRequest,
  LearnEvaluationResponse,
  LearnExercise,
  LearnMoreExercisesRequest,
  LearnSaveSessionRequest,
  LearnSessionSummary
)

logger = logging.getLogger("tcf.learn")
router = APIRouter(prefix="/learn", tags=["learn"])

_EXECUTOR = ThreadPoolExecutor(max_workers=6, thread_name_prefix="learn")
_OBJECTIVE_TYPES = {"mcq", "fill_blank", "sentence_correction"}
_FRIENDLY_ERROR = "L'analyse a échoué. Veuillez réessayer."
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def content_id_for(topic: str, level: str, summary: str) -> str:
  raw = f"{topic.strip().lower()}|{level.strip().upper()}|{summary.strip()}"
  return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _valid_exercises(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
  valid: list[dict[str, Any]] = []
  for item in raw:
    try:
      valid.append(LearnExercise(**item).model_dump(exclude_none=True))
    except Exception:
      continue
  return valid


class ExerciseBatchCache:
  """
  Per-content pre-generated "More exercises" batch. A batch is handed out once (popped),
  and every question served for a content id is remembered so later batches never repeat it.
  """

  def __init__(self, producer, max_contents: int = 300) -> None:
    self._producer = producer
    self._max = max_contents
    self._lock = threading.Lock()
    self._futures: "OrderedDict[str, Future]" = OrderedDict()
    self._contexts: "OrderedDict[str, tuple[str, str, str]]" = OrderedDict()
    self._seen: "OrderedDict[str, list[str]]" = OrderedDict()

  def _touch(self, mapping: OrderedDict, key: str) -> None:
    mapping.move_to_end(key)
    while len(mapping) > self._max:
      mapping.popitem(last=False)

  def remember(self, content_id: str, questions: list[str]) -> None:
    with self._lock:
      seen = self._seen.setdefault(content_id, [])
      known = {learn_question_fingerprint(q) for q in seen}
      for q in questions:
        if q and learn_question_fingerprint(q) not in known:
          seen.append(q)
          known.add(learn_question_fingerprint(q))
      self._touch(self._seen, content_id)

  def seen(self, content_id: str) -> list[str]:
    with self._lock:
      return list(self._seen.get(content_id, []))

  def schedule(self, content_id: str, topic: str, level: str, summary: str) -> None:
    with self._lock:
      self._contexts[content_id] = (topic, level, summary)
      self._touch(self._contexts, content_id)
      if content_id in self._futures:
        return
      self._futures[content_id] = _EXECUTOR.submit(self._produce, content_id)
      self._touch(self._futures, content_id)

  def _produce(self, content_id: str) -> list[dict[str, Any]]:
    with self._lock:
      topic, level, summary = self._contexts[content_id]
    return _valid_exercises(self._producer(topic, level, summary, self.seen(content_id)))

  def take(self, content_id: str, timeout: float = 90.0) -> list[dict[str, Any]] | None:
    """Pop the pre-generated batch (waiting for it if still running); None if none was scheduled."""
    with self._lock:
      future = self._futures.pop(content_id, None)
    if future is None:
      return None
    try:
      batch = future.result(timeout=timeout)
    except Exception as err:
      logger.warning("Prefetched exercise batch failed: %s", err)
      return None
    # Drop anything already served (another tab may have consumed questions meanwhile).
    seen = {learn_question_fingerprint(q) for q in self.seen(content_id)}
    return [ex for ex in batch if learn_question_fingerprint(ex.get("question", "")) not in seen]


_batches = ExerciseBatchCache(generate_more_exercises)


def _sse(event: dict[str, Any]) -> str:
  return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _start_analysis(text: str) -> tuple[Future, Future]:
  return _EXECUTOR.submit(generate_learn_overview, text), _EXECUTOR.submit(generate_learn_exercises, text)


def _unseen_exercises(exercises: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Drop exercises this learner has already been served, and remember the ones we keep."""
  learner = active_learner()
  kept: list[dict[str, Any]] = []
  for exercise in exercises:
    question = str(exercise.get("question", ""))
    fp = dedupe.fingerprint(question)
    sim = dedupe.simhash_of(question)
    if not question or content_bank.is_seen(learner, "learn", fp, sim):
      continue
    content_bank.remember(learner, "learn", fp, sim, label=question[:240])
    kept.append(exercise)
  return kept


def _finish_analysis(overview: dict[str, Any], exercises: list[dict[str, Any]]) -> str:
  content_id = content_id_for(overview["topic"], overview["level"], overview["summary"])
  _batches.remember(content_id, [ex.get("question", "") for ex in exercises])
  _batches.schedule(content_id, overview["topic"], overview["level"], overview["summary"])
  return content_id


@router.post("/analyze", response_model=LearnContentResponse)
def analyze_content(
  payload: LearnAnalyzeRequest,
  _user: User = Depends(get_optional_user)
) -> LearnContentResponse:
  overview_f, exercises_f = _start_analysis(payload.text)
  try:
    overview = overview_f.result()
    exercises = _valid_exercises(exercises_f.result())
  except Exception as err:
    logger.error("learn analysis failed: %s", err)
    raise HTTPException(status_code=503, detail=_FRIENDLY_ERROR)
  exercises = _unseen_exercises(exercises)
  if not exercises:
    raise HTTPException(status_code=503, detail=_FRIENDLY_ERROR)
  content_id = _finish_analysis(overview, exercises)
  return LearnContentResponse(**overview, exercises=exercises, content_id=content_id)


@router.post("/analyze/stream")
def analyze_content_stream(
  payload: LearnAnalyzeRequest,
  _user: User = Depends(get_optional_user)
) -> StreamingResponse:
  """SSE: an `overview` event and an `exercises` event (whichever is ready first), then `done`."""
  text = payload.text

  def _generate() -> Iterator[str]:
    overview_f, exercises_f = _start_analysis(text)
    labels = {overview_f: "overview", exercises_f: "exercises"}
    overview: dict[str, Any] | None = None
    exercises: list[dict[str, Any]] = []
    try:
      for future in as_completed(labels):
        if labels[future] == "overview":
          overview = future.result()
          yield _sse({"type": "overview", **overview})
        else:
          exercises = _unseen_exercises(_valid_exercises(future.result()))
          if not exercises:
            raise RuntimeError("no valid exercises")
          yield _sse({"type": "exercises", "exercises": exercises})
      assert overview is not None
      yield _sse({"type": "done", "content_id": _finish_analysis(overview, exercises)})
    except Exception as err:
      logger.error("learn analysis stream failed: %s", err)
      yield _sse({"type": "error", "message": _FRIENDLY_ERROR})

  return StreamingResponse(_generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/upload")
async def upload_content(
  file: UploadFile = File(...),
  _user: User = Depends(get_optional_user)
) -> dict:
  """Accept PDF or image upload; extract text and return it for the frontend to send to /learn/analyze."""
  content_type = (file.content_type or "").lower()
  raw = await file.read()

  if content_type == "application/pdf" or (file.filename or "").endswith(".pdf"):
    text = await run_in_threadpool(_extract_pdf_text, raw)
    source_type = "pdf"
  elif content_type.startswith("image/"):
    text = await run_in_threadpool(extract_text_from_image_bytes, raw, content_type)
    source_type = "image"
  else:
    raise HTTPException(status_code=415, detail="Only PDF and image files are supported.")

  if not text.strip():
    raise HTTPException(status_code=422, detail="No readable text found in the file.")

  return {"text": text, "source_type": source_type}


def _evaluate(item: LearnEvaluateRequest) -> dict[str, Any]:
  return evaluate_learn_answer(
    exercise_type=item.exercise_type,
    question=item.question,
    correct_answer=item.correct_answer,
    user_answer=item.user_answer,
    context=item.context,
    explanation=item.explanation,
  )


@router.post("/evaluate", response_model=LearnEvaluationResponse)
def evaluate_answer(
  payload: LearnEvaluateRequest,
  _user: User = Depends(get_optional_user)
) -> LearnEvaluationResponse:
  try:
    result = _evaluate(payload)
  except Exception as err:
    logger.error("evaluate_learn_answer failed: %s", err)
    raise HTTPException(status_code=503, detail="L'évaluation a échoué. Veuillez réessayer.")
  return LearnEvaluationResponse(**result)


@router.post("/evaluate-batch/stream")
def evaluate_batch_stream(
  payload: LearnEvaluateBatchRequest,
  _user: User = Depends(get_optional_user)
) -> StreamingResponse:
  """SSE: one `result` event per item as soon as it is evaluated (objective items instantly), then `done`."""
  items = payload.items

  def _generate() -> Iterator[str]:
    pending: dict[Future, int] = {}
    for item in items:
      if item.exercise_type in _OBJECTIVE_TYPES or not item.user_answer.strip():
        yield _sse({"type": "result", "index": item.index, "evaluation": LearnEvaluationResponse(**_evaluate(item)).model_dump()})
      else:
        pending[_EXECUTOR.submit(_evaluate, item)] = item.index
    for future in as_completed(pending):
      index = pending[future]
      try:
        evaluation = LearnEvaluationResponse(**future.result()).model_dump()
        yield _sse({"type": "result", "index": index, "evaluation": evaluation})
      except Exception as err:
        logger.error("batch evaluation failed for item %s: %s", index, err)
        yield _sse({"type": "result", "index": index, "error": "L'évaluation a échoué. Réessayez."})
    yield _sse({"type": "done"})

  return StreamingResponse(_generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/more-exercises", response_model=list[LearnExercise])
def more_exercises(
  payload: LearnMoreExercisesRequest,
  _user: User = Depends(get_optional_user)
) -> list[LearnExercise]:
  content_id = payload.content_id or content_id_for(payload.topic, payload.level, payload.summary)
  if payload.exclude_questions:
    _batches.remember(content_id, payload.exclude_questions)

  exercises = _batches.take(content_id)
  if not exercises:
    try:
      exercises = _valid_exercises(
        generate_more_exercises(payload.topic, payload.level, payload.summary, _batches.seen(content_id))
      )
    except Exception as err:
      logger.error("generate_more_exercises failed: %s", err)
      raise HTTPException(status_code=503, detail="La génération des exercices a échoué. Veuillez réessayer.")
  exercises = _unseen_exercises(exercises or [])
  if not exercises:
    raise HTTPException(status_code=503, detail="La génération des exercices a échoué. Veuillez réessayer.")

  _batches.remember(content_id, [ex.get("question", "") for ex in exercises])
  # Keep the next batch one step ahead.
  _batches.schedule(content_id, payload.topic, payload.level, payload.summary)
  return [LearnExercise(**ex) for ex in exercises]


@router.post("/session/save", response_model=LearnSessionSummary)
def save_session(
  payload: LearnSaveSessionRequest,
  db: Session = Depends(get_db),
  user: User = Depends(get_optional_user)
) -> LearnSessionSummary:
  if is_guest_user(user):
    # Guests share one account: nothing is stored, so nobody's results leak to other guests.
    return LearnSessionSummary(
      id=0,
      topic=payload.topic,
      level=payload.level,
      score=payload.score,
      exercises_completed=payload.exercises_completed,
      exercises_total=payload.exercises_total,
      created_at=datetime.utcnow(),
    )
  session = LearnSession(
    user_id=user.id,
    source_type=payload.source_type,
    topic=payload.topic,
    level=payload.level,
    score=payload.score,
    grammar=payload.grammar,
    vocabulary=payload.vocabulary,
    structure=payload.structure,
    exercises_total=payload.exercises_total,
    exercises_completed=payload.exercises_completed
  )
  db.add(session)
  db.commit()
  db.refresh(session)
  return LearnSessionSummary(
    id=session.id,
    topic=session.topic,
    level=session.level,
    score=session.score,
    exercises_completed=session.exercises_completed,
    exercises_total=session.exercises_total,
    created_at=session.created_at
  )


def _extract_pdf_text(raw: bytes) -> str:
  try:
    import pypdf
    import io
    reader = pypdf.PdfReader(io.BytesIO(raw))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()
  except ImportError:
    logger.warning("pypdf not installed; falling back to empty PDF text")
    return ""
  except Exception as err:
    logger.error("PDF extraction error: %s", err)
    return ""
