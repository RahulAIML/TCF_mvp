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
    PronunciationEvaluation, VocabularyWord, TtsAudioHistory
  )

  Base.metadata.create_all(bind=engine)

  # Add columns and tables that were introduced after the initial database creation.
  migrations = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(100)",
    """
    CREATE TABLE IF NOT EXISTS tts_audio_history (
      id SERIAL PRIMARY KEY,
      user_id INTEGER REFERENCES users(id),
      audio_url VARCHAR(500) NOT NULL,
      voice_id VARCHAR(50) NOT NULL,
      voice_label VARCHAR(100) NOT NULL,
      text_preview VARCHAR(200) NOT NULL,
      created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
    )
    """,
  ]
  with engine.begin() as conn:
    for sql in migrations:
      try:
        conn.execute(text(sql))
      except Exception:
        pass  # SQLite / syntax difference — skip gracefully
