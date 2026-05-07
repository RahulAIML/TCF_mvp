import os
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tcf.db")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
  connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator:
  db = SessionLocal()
  try:
    yield db
  finally:
    db.close()


def init_db() -> None:
  from models import (
    ExamAttempt, ListeningAttempt, User, WritingSession, TcfWritingSession,
    SpeakingSession, UserAudioResponse, QuestionValidation, LearnSession,
    PronunciationEvaluation, VocabularyWord
  )

  Base.metadata.create_all(bind=engine)

  # Add columns that were introduced after the initial table creation.
  # ALTER TABLE ... ADD COLUMN IF NOT EXISTS is idempotent — safe to run every startup.
  migrations = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(100)",
  ]
  with engine.begin() as conn:
    for sql in migrations:
      try:
        conn.execute(text(sql))
      except Exception:
        pass  # SQLite doesn't support IF NOT EXISTS — skip gracefully
