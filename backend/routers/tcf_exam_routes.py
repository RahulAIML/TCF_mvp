import json
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_optional_user
from database import get_db
from models import ExamAttempt, User
from schemas import (
  TcfGenerateQuestionRequest,
  TcfGenerateQuestionResponse,
  TcfSubmitExamRequest,
  TcfSubmitExamResponse,
  TcfExamResultItem
)
from tcf_ai_service import generate_tcf_exam_question

router = APIRouter(prefix="/tcf", tags=["tcf", "exam"])


@router.post("/generate-question", response_model=TcfGenerateQuestionResponse)
async def post_generate_question(
  payload: TcfGenerateQuestionRequest,
  _user: User = Depends(get_optional_user)
) -> TcfGenerateQuestionResponse:
  try:
    question = generate_tcf_exam_question(payload.question_number, payload.session_id)
  except RuntimeError as error:
    raise HTTPException(status_code=500, detail=str(error)) from error

  return TcfGenerateQuestionResponse(
    question_number=payload.question_number,
    **question.model_dump()
  )


@router.post("/submit-exam", response_model=TcfSubmitExamResponse)
async def post_submit_exam(
  payload: TcfSubmitExamRequest,
  db: Session = Depends(get_db),
  user: User = Depends(get_optional_user)
) -> TcfSubmitExamResponse:
  if payload.completed_at < payload.started_at:
    raise HTTPException(status_code=400, detail="completed_at must be after started_at.")

  questions_by_number = {q.question_number: q for q in payload.questions}
  total = len(questions_by_number)
  if total == 0:
    raise HTTPException(status_code=400, detail="No questions submitted.")

  score = 0
  results = []
  error_types: Dict[str, int] = {}

  for number in sorted(questions_by_number.keys()):
    question = questions_by_number[number]
    user_answer = payload.answers.get(number, "")
    is_correct = user_answer == question.correct_answer
    if is_correct:
      score += 1
    else:
      error_types[question.question_type] = error_types.get(question.question_type, 0) + 1

    results.append(
      TcfExamResultItem(
        question_number=number,
        correct_answer=question.correct_answer,
        user_answer=user_answer,
        is_correct=is_correct,
        explanation=question.explanation,
        question_type=question.question_type
      )
    )

  completion_time = max(int((payload.completed_at - payload.started_at).total_seconds()), 0)
  attempted = sum(1 for n in questions_by_number if payload.answers.get(n, "").strip())
  accuracy = round(score / attempted * 100, 2) if attempted else 0.0

  attempt = ExamAttempt(
    user_id=user.id,
    score=score,
    accuracy=accuracy,
    completion_time=completion_time,
    error_types=json.dumps(error_types)
  )
  db.add(attempt)
  db.commit()
  db.refresh(attempt)

  return TcfSubmitExamResponse(
    score=score,
    total=total,
    attempted=attempted,
    accuracy=accuracy,
    completion_time=completion_time,
    results=results
  )
