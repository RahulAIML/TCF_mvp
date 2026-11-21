import json

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import ExamAttempt, LearnSession, ListeningAttempt, TcfWritingSession, User
from schemas import (
  DashboardSummaryResponse,
  LearnSessionSummary,
  LearnSummary,
  ModuleExamSummary,
  RecentExam,
  WritingSubmissionSummary,
  WritingSummary
)

router = APIRouter(tags=["performance"])

QUESTION_TYPE_LABELS = {
  "part1_a1a2": "Part 1 (A1-A2)",
  "part2_a2b1": "Part 2 (A2-B1)",
  "part3_b1b2": "Part 3 (B1-B2)",
  "part4_b2c2": "Part 4 (B2-C2)",
  "reading_a1": "Reading A1",
  "reading_a2": "Reading A2",
  "reading_b1": "Reading B1",
  "reading_b2": "Reading B2",
  "reading_c1": "Reading C1",
  "reading_c2": "Reading C2",
}


def _build_recent_exams(attempts: list[ExamAttempt | ListeningAttempt]) -> list[RecentExam]:
  return [
    RecentExam(
      id=attempt.id,
      score=attempt.score,
      accuracy=float(attempt.accuracy),
      created_at=attempt.created_at
    )
    for attempt in attempts
  ]


def _parse_eval_score(payload: str | None) -> float | None:
  if not payload:
    return None
  try:
    data = json.loads(payload)
  except json.JSONDecodeError:
    return None
  scores = data.get("scores") if isinstance(data, dict) else None
  if not isinstance(scores, dict):
    return None
  values = []
  for key in ("structure", "grammar", "coherence", "vocab"):
    value = scores.get(key)
    try:
      values.append(float(value))
    except (TypeError, ValueError):
      continue
  if not values:
    return None
  return sum(values) / len(values)


def summarize_writing_sessions(
  sessions: list[TcfWritingSession],
) -> tuple[float, list[WritingSubmissionSummary]]:
  """Average of the per-task evaluation scores across submitted sessions (most recent first)."""
  summaries: list[WritingSubmissionSummary] = []
  session_scores: list[float] = []
  for session in sessions:
    task_scores = [
      score
      for score in (
        _parse_eval_score(session.task1_evaluation),
        _parse_eval_score(session.task2_evaluation),
        _parse_eval_score(session.task3_evaluation),
      )
      if score is not None
    ]
    if not task_scores:
      continue
    average_score = sum(task_scores) / len(task_scores)
    session_scores.append(average_score)
    if len(summaries) < 3:
      summaries.append(
        WritingSubmissionSummary(id=session.id, average_score=round(average_score, 2), created_at=session.updated_at)
      )
  overall = round(sum(session_scores) / len(session_scores), 2) if session_scores else 0.0
  return overall, summaries


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
  db: Session = Depends(get_db),
  user: User = Depends(get_current_user)
) -> DashboardSummaryResponse:
  reading_avg = db.query(func.coalesce(func.avg(ExamAttempt.accuracy), 0)).filter(
    ExamAttempt.user_id == user.id
  ).scalar()

  reading_attempts = (
    db.query(ExamAttempt)
    .filter(ExamAttempt.user_id == user.id)
    .order_by(ExamAttempt.created_at.desc())
    .limit(3)
    .all()
  )

  error_counts: dict[str, int] = {}
  for attempt in db.query(ExamAttempt.error_types).filter(ExamAttempt.user_id == user.id):
    try:
      payload = json.loads(attempt.error_types or "{}")
    except json.JSONDecodeError:
      payload = {}
    for key, value in payload.items():
      error_counts[key] = error_counts.get(key, 0) + int(value)

  weakest_key = ""
  if error_counts:
    weakest_key = max(error_counts, key=error_counts.get)

  weakest_label = QUESTION_TYPE_LABELS.get(weakest_key, "Not enough data")

  reading_summary = ModuleExamSummary(
    average_accuracy=round(float(reading_avg or 0), 2),
    recent_exams=_build_recent_exams(reading_attempts),
    weakest_question_type=weakest_label
  )

  listening_avg = db.query(func.coalesce(func.avg(ListeningAttempt.accuracy), 0)).filter(
    ListeningAttempt.user_id == user.id
  ).scalar()
  listening_attempts = (
    db.query(ListeningAttempt)
    .filter(ListeningAttempt.user_id == user.id)
    .order_by(ListeningAttempt.created_at.desc())
    .limit(3)
    .all()
  )

  listening_summary = ModuleExamSummary(
    average_accuracy=round(float(listening_avg or 0), 2),
    recent_exams=_build_recent_exams(listening_attempts),
    weakest_question_type="Not tracked"
  )

  writing_sessions = (
    db.query(TcfWritingSession)
    .filter(TcfWritingSession.user_id == user.id, TcfWritingSession.is_submitted.is_(True))
    .order_by(TcfWritingSession.updated_at.desc())
    .all()
  )
  writing_average, submission_summaries = summarize_writing_sessions(writing_sessions)
  writing_summary = WritingSummary(
    average_score=writing_average,
    recent_submissions=submission_summaries
  )

  learn_sessions = (
    db.query(LearnSession)
    .filter(LearnSession.user_id == user.id)
    .order_by(LearnSession.created_at.desc())
    .all()
  )
  learn_scores = [s.score for s in learn_sessions if s.score is not None]
  learn_average = round(sum(learn_scores) / len(learn_scores), 2) if learn_scores else 0.0
  learn_summaries: list[LearnSessionSummary] = [
    LearnSessionSummary(
      id=s.id,
      topic=s.topic,
      level=s.level,
      score=s.score,
      exercises_completed=s.exercises_completed,
      exercises_total=s.exercises_total,
      created_at=s.created_at
    )
    for s in learn_sessions[:3]
  ]
  learning_summary = LearnSummary(average_score=learn_average, recent_sessions=learn_summaries)

  return DashboardSummaryResponse(
    reading=reading_summary,
    listening=listening_summary,
    writing=writing_summary,
    learning=learning_summary
  )

