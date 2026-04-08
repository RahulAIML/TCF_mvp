import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_optional_user
from database import get_db
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
  TcfWritingSubmitResponse
)
from tcf_ai_service import (
  evaluate_tcf_writing_step,
  evaluate_tcf_writing_task,
  generate_tcf_writing_tasks
)

router = APIRouter(prefix="/tcf", tags=["tcf", "writing"])


@router.post("/generate-writing-tasks", response_model=TcfGenerateWritingTasksResponse)
async def post_generate_writing_tasks(
  payload: TcfGenerateWritingTasksRequest,
  _user: User = Depends(get_optional_user)
) -> TcfGenerateWritingTasksResponse:
  try:
    prompts = generate_tcf_writing_tasks()
  except RuntimeError as error:
    raise HTTPException(status_code=500, detail=str(error)) from error

  return TcfGenerateWritingTasksResponse(**prompts)


@router.post("/evaluate-writing", response_model=TcfWritingEvaluationResponse)
async def post_evaluate_writing(
  payload: TcfWritingEvaluationRequest,
  _user: User = Depends(get_optional_user)
) -> TcfWritingEvaluationResponse:
  try:
    evaluation = evaluate_tcf_writing_task(payload.task_type, payload.prompt, payload.response_text)
  except RuntimeError as error:
    raise HTTPException(status_code=500, detail=str(error)) from error

  return TcfWritingEvaluationResponse(**evaluation)


@router.post("/evaluate-writing-step", response_model=TcfWritingStepFeedbackResponse)
async def post_evaluate_writing_step(
  payload: TcfWritingStepFeedbackRequest,
  _user: User = Depends(get_optional_user)
) -> TcfWritingStepFeedbackResponse:
  try:
    evaluation = evaluate_tcf_writing_step(payload.task_type, payload.step, payload.prompt, payload.text)
  except RuntimeError as error:
    raise HTTPException(status_code=500, detail=str(error)) from error

  return TcfWritingStepFeedbackResponse(**evaluation)


@router.post("/writing/save-progress", response_model=WritingProgressResponse)
async def post_save_writing_progress(
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


@router.post("/writing/submit", response_model=TcfWritingSubmitResponse)
async def post_submit_writing(
  payload: TcfWritingSubmitRequest,
  db: Session = Depends(get_db),
  user: User = Depends(get_optional_user)
) -> TcfWritingSubmitResponse:
  try:
    evaluation_task1 = evaluate_tcf_writing_task("task1", payload.task1_prompt, payload.task1_text)
    evaluation_task2 = evaluate_tcf_writing_task("task2", payload.task2_prompt, payload.task2_text)
    evaluation_task3 = evaluate_tcf_writing_task("task3", payload.task3_prompt, payload.task3_text)
  except RuntimeError as error:
    raise HTTPException(status_code=500, detail=str(error)) from error

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

  session.task1_prompt = payload.task1_prompt
  session.task2_prompt = payload.task2_prompt
  session.task3_prompt = payload.task3_prompt
  session.task1_text = payload.task1_text
  session.task2_text = payload.task2_text
  session.task3_text = payload.task3_text
  session.task1_steps = json.dumps(payload.task1_steps or {}, ensure_ascii=False)
  session.task2_steps = json.dumps(payload.task2_steps or {}, ensure_ascii=False)
  session.task3_steps = json.dumps(payload.task3_steps or {}, ensure_ascii=False)
  session.task1_evaluation = json.dumps(evaluation_task1, ensure_ascii=False)
  session.task2_evaluation = json.dumps(evaluation_task2, ensure_ascii=False)
  session.task3_evaluation = json.dumps(evaluation_task3, ensure_ascii=False)
  session.is_submitted = True
  session.updated_at = datetime.utcnow()
  db.commit()

  return TcfWritingSubmitResponse(
    task1=TcfWritingEvaluationResponse(**evaluation_task1),
    task2=TcfWritingEvaluationResponse(**evaluation_task2),
    task3=TcfWritingEvaluationResponse(**evaluation_task3)
  )
