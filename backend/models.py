from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from database import Base


class User(Base):
  __tablename__ = "users"

  id = Column(Integer, primary_key=True, index=True)
  email = Column(String(255), unique=True, index=True, nullable=False)
  password_hash = Column(String(255), nullable=False)
  created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ExamAttempt(Base):
  __tablename__ = "exam_attempts"

  id = Column(Integer, primary_key=True, index=True)
  user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
  score = Column(Integer, nullable=False)
  accuracy = Column(Float, nullable=False)
  completion_time = Column(Integer, nullable=False)
  error_types = Column(Text, nullable=False)
  created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ListeningAttempt(Base):
  __tablename__ = "listening_attempts"

  id = Column(Integer, primary_key=True, index=True)
  user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
  score = Column(Integer, nullable=False)
  total = Column(Integer, nullable=False)
  accuracy = Column(Float, nullable=False)
  completion_time = Column(Integer, nullable=False)
  created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WritingSession(Base):
  __tablename__ = "writing_sessions"

  id = Column(Integer, primary_key=True, index=True)
  user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
  session_id = Column(String(64), unique=True, index=True, nullable=False)
  mode = Column(String(20), nullable=False)
  task1_prompt = Column(Text, nullable=True)
  task2_prompt = Column(Text, nullable=True)
  task1_steps = Column(Text, nullable=True)
  task2_steps = Column(Text, nullable=True)
  task1_text = Column(Text, nullable=True)
  task2_text = Column(Text, nullable=True)
  task1_evaluation = Column(Text, nullable=True)
  task2_evaluation = Column(Text, nullable=True)
  is_submitted = Column(Boolean, default=False, nullable=False)
  created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
  updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TcfWritingSession(Base):
  __tablename__ = "tcf_writing_sessions"

  id = Column(Integer, primary_key=True, index=True)
  user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
  session_id = Column(String(64), unique=True, index=True, nullable=False)
  mode = Column(String(20), nullable=False)
  task1_prompt = Column(Text, nullable=True)
  task2_prompt = Column(Text, nullable=True)
  task3_prompt = Column(Text, nullable=True)
  task1_steps = Column(Text, nullable=True)
  task2_steps = Column(Text, nullable=True)
  task3_steps = Column(Text, nullable=True)
  task1_text = Column(Text, nullable=True)
  task2_text = Column(Text, nullable=True)
  task3_text = Column(Text, nullable=True)
  task1_evaluation = Column(Text, nullable=True)
  task2_evaluation = Column(Text, nullable=True)
  task3_evaluation = Column(Text, nullable=True)
  is_submitted = Column(Boolean, default=False, nullable=False)
  created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
  updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class LearnSession(Base):
  __tablename__ = "learn_sessions"

  id = Column(Integer, primary_key=True, index=True)
  user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
  source_type = Column(String(20), nullable=False)  # text, pdf, image, chat
  topic = Column(String(200), nullable=True)
  level = Column(String(10), nullable=True)
  score = Column(Float, nullable=True)
  grammar = Column(Float, nullable=True)
  vocabulary = Column(Float, nullable=True)
  structure = Column(Float, nullable=True)
  exercises_total = Column(Integer, default=0, nullable=False)
  exercises_completed = Column(Integer, default=0, nullable=False)
  created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SpeakingSession(Base):
  """Stores speaking test session with conversation context and audio responses."""
  __tablename__ = "speaking_sessions"

  id = Column(Integer, primary_key=True, index=True)
  user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
  session_id = Column(String(64), unique=True, index=True, nullable=False)
  task_type = Column(String(20), nullable=False)  # basic_interaction, role_play, opinion
  topic = Column(String(255), nullable=True)
  conversation_context = Column(Text, nullable=True)  # JSON: [{role, text, audio_url?, timestamp}...]
  exchange_count = Column(Integer, default=0, nullable=False)  # Track max 5 exchanges
  overall_score = Column(Float, nullable=True)
  transcription_accuracy = Column(Float, nullable=True)
  grammar_score = Column(Float, nullable=True)
  relevance_score = Column(Float, nullable=True)
  length_score = Column(Float, nullable=True)
  is_completed = Column(Boolean, default=False, nullable=False)
  created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
  updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserAudioResponse(Base):
  """Stores individual user audio responses during speaking tests."""
  __tablename__ = "user_audio_responses"

  id = Column(Integer, primary_key=True, index=True)
  user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
  speaking_session_id = Column(Integer, ForeignKey("speaking_sessions.id"), index=True, nullable=False)
  exchange_number = Column(Integer, nullable=False)  # 1st, 2nd, 3rd response, etc.
  audio_url = Column(String(500), nullable=True)  # Path to stored audio blob
  transcript = Column(Text, nullable=True)  # User's transcribed response
  response_score = Column(Float, nullable=True)  # Score for this specific response
  created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class QuestionValidation(Base):
  """Tracks question generation validation (ensures answer grounded in text/audio)."""
  __tablename__ = "question_validations"

  id = Column(Integer, primary_key=True, index=True)
  question_id = Column(String(100), nullable=False, index=True)  # question_number-session_id
  module = Column(String(20), nullable=False)  # reading, listening
  source_text_span = Column(Text, nullable=True)  # The actual text supporting the question
  correct_answer_span = Column(Text, nullable=True)  # The specific text proving the answer
  is_valid = Column(Boolean, default=True, nullable=False)
  validation_score = Column(Float, nullable=True)  # Confidence 0-1
  created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

