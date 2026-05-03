from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal

from pydantic import BaseModel, Field, field_validator

AnswerOption = Literal["A", "B", "C", "D"]
ExamQuestionType = Literal[
  "everyday_life",
  "gap_fill",
  "rapid_reading",
  "administrative",
  "press"
]

TcfExamQuestionType = Literal[
  "part1_c2",
  "part2_b2c1",
  "part3_b1b2",
  "part4_a2"
]


class GenerateQuestionRequest(BaseModel):
  question_number: int = Field(ge=1, le=40)
  session_id: str | None = None


class ExamQuestion(BaseModel):
  text: str
  question: str
  options: List[str] = Field(default_factory=list)
  correct_answer: AnswerOption
  explanation: str
  question_type: ExamQuestionType

  @field_validator("options")
  @classmethod
  def validate_options(cls, options: List[str]) -> List[str]:
    if len(options) != 4:
      raise ValueError("Each question must contain exactly 4 options.")
    return options


class GenerateQuestionResponse(ExamQuestion):
  question_number: int


class SubmitExamQuestion(BaseModel):
  question_number: int = Field(ge=1, le=40)
  correct_answer: AnswerOption
  question_type: ExamQuestionType
  explanation: str


class SubmitExamRequest(BaseModel):
  started_at: datetime
  completed_at: datetime
  answers: Dict[int, str]
  questions: List[SubmitExamQuestion]

  @field_validator("answers")
  @classmethod
  def normalize_answers(cls, answers: Dict[int, str]) -> Dict[int, str]:
    normalized: Dict[int, str] = {}
    for key, value in answers.items():
      clean = (value or "").strip().upper()
      if clean and clean not in {"A", "B", "C", "D"}:
        raise ValueError("Answers must be one of A, B, C, D, or empty string.")
      normalized[int(key)] = clean
    return normalized


class ExamResultItem(BaseModel):
  question_number: int
  correct_answer: AnswerOption
  user_answer: str
  is_correct: bool
  explanation: str
  question_type: ExamQuestionType


class SubmitExamResponse(BaseModel):
  score: int
  total: int
  accuracy: float
  completion_time: int
  results: List[ExamResultItem]


class TcfGenerateQuestionRequest(BaseModel):
  question_number: int = Field(ge=1, le=39)
  session_id: str | None = None


class TcfExamQuestion(BaseModel):
  text: str
  question: str
  options: List[str] = Field(default_factory=list)
  correct_answer: AnswerOption
  explanation: str
  question_type: TcfExamQuestionType

  @field_validator("options")
  @classmethod
  def validate_options(cls, options: List[str]) -> List[str]:
    if len(options) != 4:
      raise ValueError("Each question must contain exactly 4 options.")
    return options


class TcfGenerateQuestionResponse(TcfExamQuestion):
  question_number: int


class TcfSubmitExamQuestion(BaseModel):
  question_number: int = Field(ge=1, le=39)
  correct_answer: AnswerOption
  question_type: TcfExamQuestionType
  explanation: str


class TcfSubmitExamRequest(BaseModel):
  started_at: datetime
  completed_at: datetime
  answers: Dict[int, str]
  questions: List[TcfSubmitExamQuestion]

  @field_validator("answers")
  @classmethod
  def normalize_answers(cls, answers: Dict[int, str]) -> Dict[int, str]:
    normalized: Dict[int, str] = {}
    for key, value in answers.items():
      clean = (value or "").strip().upper()
      if clean and clean not in {"A", "B", "C", "D"}:
        raise ValueError("Answers must be one of A, B, C, D, or empty string.")
      normalized[int(key)] = clean
    return normalized


class TcfExamResultItem(BaseModel):
  question_number: int
  correct_answer: AnswerOption
  user_answer: str
  is_correct: bool
  explanation: str
  question_type: TcfExamQuestionType


class TcfSubmitExamResponse(BaseModel):
  score: int
  total: int
  attempted: int = 0
  accuracy: float
  completion_time: int
  results: List[TcfExamResultItem]


class PassageResponse(BaseModel):
  title: str
  passage: str


class PassageQuizQuestion(BaseModel):
  question: str
  options: List[str] = Field(default_factory=list)
  correct_answer: AnswerOption
  explanation: str

  @field_validator("options")
  @classmethod
  def validate_options(cls, options: List[str]) -> List[str]:
    if len(options) != 4:
      raise ValueError("Each question must contain exactly 4 options.")
    return options


class PassageQuizResponse(BaseModel):
  title: str
  passage: str
  questions: List[PassageQuizQuestion]

  @field_validator("questions")
  @classmethod
  def validate_question_count(cls, questions: List[PassageQuizQuestion]) -> List[PassageQuizQuestion]:
    if len(questions) != 10:
      raise ValueError("Passage quiz must contain exactly 10 questions.")
    return questions


class WordMeaningRequest(BaseModel):
  word: str = Field(min_length=1, max_length=120)


class WordMeaningResponse(BaseModel):
  word: str
  part_of_speech: str
  definition_simple: str
  french_explanation: str
  english_translation: str
  example_sentence: str
  synonyms: List[str]


class GenerateListeningQuestionRequest(BaseModel):
  question_number: int = Field(ge=1, le=40)
  session_id: str | None = None
  defer_audio: bool = False


class TcfGenerateListeningQuestionRequest(BaseModel):
  question_number: int = Field(ge=1, le=39)
  session_id: str | None = None
  defer_audio: bool = False


class ListeningQuestionResponse(BaseModel):
  script: str
  audio_url: str | None = None
  question: str
  options: List[str] = Field(default_factory=list)
  correct_answer: AnswerOption
  explanation: str

  @field_validator("options")
  @classmethod
  def validate_options(cls, options: List[str]) -> List[str]:
    if len(options) != 4:
      raise ValueError("Each question must contain exactly 4 options.")
    return options


class GenerateListeningAudioRequest(BaseModel):
  script: str = Field(min_length=1)
  question_number: int = Field(ge=1, le=40)
  session_id: str | None = None


class TcfGenerateListeningAudioRequest(BaseModel):
  script: str = Field(min_length=1)
  question_number: int = Field(ge=1, le=39)
  session_id: str | None = None


class GenerateListeningAudioResponse(BaseModel):
  audio_url: str | None = None


class SubmitListeningExamRequest(BaseModel):
  started_at: datetime
  completed_at: datetime
  score: int = Field(ge=0)
  total: int = Field(ge=0)
  accuracy: float = Field(ge=0, le=100)


class SubmitListeningExamResponse(BaseModel):
  score: int
  total: int
  accuracy: float
  completion_time: int


class ExplainTextRequest(BaseModel):
  text: str = Field(min_length=1)


class ExplainTextResponse(BaseModel):
  meaning: str
  explanation: str
  translation: str
  example: str


class SignupRequest(BaseModel):
  email: str = Field(min_length=5, max_length=255)
  password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
  email: str = Field(min_length=5, max_length=255)
  password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
  id: int
  email: str
  created_at: datetime


class AuthResponse(BaseModel):
  access_token: str
  token_type: str = "bearer"
  user: UserResponse


class RecentExam(BaseModel):
  id: int
  score: int
  accuracy: float
  created_at: datetime


class ModuleExamSummary(BaseModel):
  average_accuracy: float
  recent_exams: List[RecentExam]
  weakest_question_type: str | None = None


class WritingSubmissionSummary(BaseModel):
  id: int
  average_score: float
  created_at: datetime


class WritingSummary(BaseModel):
  average_score: float
  recent_submissions: List[WritingSubmissionSummary]


class LearnSessionSummary(BaseModel):
  id: int
  topic: str | None = None
  level: str | None = None
  score: float | None = None
  exercises_completed: int
  exercises_total: int
  created_at: datetime


class LearnSummary(BaseModel):
  average_score: float
  recent_sessions: List[LearnSessionSummary]


class DashboardSummaryResponse(BaseModel):
  reading: ModuleExamSummary
  listening: ModuleExamSummary
  writing: WritingSummary
  learning: LearnSummary


WritingTaskType = Literal["task1", "task2"]
WritingMode = Literal["practice", "exam"]


class GenerateWritingTasksRequest(BaseModel):
  session_id: str | None = None


class GenerateWritingTasksResponse(BaseModel):
  task1_prompt: str
  task2_prompt: str


class WritingEvaluationRequest(BaseModel):
  task_type: WritingTaskType
  prompt: str
  response_text: str


class WritingEvaluationResponse(BaseModel):
  level: str
  scores: Dict[str, int]
  feedback: List[str]
  improved_version: str


class WritingStepFeedbackRequest(BaseModel):
  task_type: WritingTaskType
  step: str
  prompt: str
  text: str


class WritingStepFeedbackResponse(BaseModel):
  feedback: List[str]
  improved_version: str


class WritingProgressRequest(BaseModel):
  session_id: str
  mode: WritingMode
  task_type: WritingTaskType
  steps: Dict[str, str]
  task_prompt: str | None = None


class WritingSubmitRequest(BaseModel):
  session_id: str
  mode: WritingMode
  task1_prompt: str
  task2_prompt: str
  task1_text: str
  task2_text: str
  task1_steps: Dict[str, str] | None = None
  task2_steps: Dict[str, str] | None = None


class WritingSubmitResponse(BaseModel):
  task1: WritingEvaluationResponse
  task2: WritingEvaluationResponse


class WritingProgressResponse(BaseModel):
  status: str


TcfWritingTaskType = Literal["task1", "task2", "task3"]
TcfWritingMode = Literal["practice", "exam"]


class TcfGenerateWritingTasksRequest(BaseModel):
  session_id: str | None = None


class TcfGenerateWritingTasksResponse(BaseModel):
  task1_prompt: str
  task2_prompt: str
  task3_prompt: str


class TcfWritingEvaluationRequest(BaseModel):
  task_type: TcfWritingTaskType
  prompt: str
  response_text: str


class TcfWritingEvaluationResponse(BaseModel):
  level: str
  scores: Dict[str, int]
  feedback: List[str]
  improved_version: str


class TcfWritingStepFeedbackRequest(BaseModel):
  task_type: TcfWritingTaskType
  step: str
  prompt: str
  text: str


class TcfWritingStepFeedbackResponse(BaseModel):
  feedback: List[str]
  improved_version: str


class TcfWritingProgressRequest(BaseModel):
  session_id: str
  mode: TcfWritingMode
  task_type: TcfWritingTaskType
  steps: Dict[str, str]
  task_prompt: str | None = None


class TcfWritingSubmitRequest(BaseModel):
  session_id: str
  mode: TcfWritingMode
  task1_prompt: str
  task2_prompt: str
  task3_prompt: str
  task1_text: str
  task2_text: str
  task3_text: str
  task1_steps: Dict[str, str] | None = None
  task2_steps: Dict[str, str] | None = None
  task3_steps: Dict[str, str] | None = None


class TcfWritingSubmitResponse(BaseModel):
  task1: TcfWritingEvaluationResponse
  task2: TcfWritingEvaluationResponse
  task3: TcfWritingEvaluationResponse


TcfWritingAssistantAction = Literal["translate", "grammar", "suggestions", "example"]
TcfWritingTranslationDirection = Literal["fr-en", "en-fr"]


class TcfWritingAssistantRequest(BaseModel):
  message: str = Field(min_length=1)
  action: TcfWritingAssistantAction
  direction: TcfWritingTranslationDirection | None = None
  context: str | None = None


class TcfWritingAssistantResponse(BaseModel):
  reply: str



SpeakingTaskType = Literal["role_play", "opinion"]
SpeakingMode = Literal["practice", "exam"]


class ConversationMessage(BaseModel):
  role: Literal["user", "assistant"]
  content: str


class ConversationRequest(BaseModel):
  message: str
  history: List[ConversationMessage] = Field(default_factory=list)
  task_type: SpeakingTaskType
  mode: SpeakingMode | None = None
  hints: bool = False
  session_id: str | None = None


class ConversationResponse(BaseModel):
  reply: str
  audio_url: str | None = None


class SpeakingEvaluationRequest(BaseModel):
  history: List[ConversationMessage] = Field(default_factory=list)
  task_type: SpeakingTaskType
  mode: SpeakingMode | None = None


class SpeakingEvaluationResponse(BaseModel):
  fluency: int
  grammar: int
  vocabulary: int
  interaction: int
  feedback: List[str]
  improved_response: str


TcfSpeakingTaskType = Literal["basic_interaction", "role_play", "opinion"]
TcfSpeakingMode = Literal["practice", "exam"]


class TcfConversationRequest(BaseModel):
  message: str
  history: List[ConversationMessage] = Field(default_factory=list)
  task_type: TcfSpeakingTaskType
  mode: TcfSpeakingMode | None = None
  hints: bool = False
  session_id: str | None = None
  session_topic: str | None = None


class TcfConversationResponse(BaseModel):
  reply: str
  audio_url: str | None = None
  session_topic: str | None = None


class TcfSpeakingEvaluationRequest(BaseModel):
  history: List[ConversationMessage] = Field(default_factory=list)
  task_type: TcfSpeakingTaskType
  mode: TcfSpeakingMode | None = None


class TcfSpeakingEvaluationResponse(BaseModel):
  fluency: int
  grammar: int
  vocabulary: int
  interaction: int
  feedback: List[str]
  improved_response: str


# ── Learn Module ────────────────────────────────────────────────────────────

LearnSourceType = Literal["text", "pdf", "image", "chat"]
LearnExerciseType = Literal["mcq", "fill_blank", "sentence_correction", "writing_task", "speaking_prompt"]


class LearnVocabItem(BaseModel):
  word: str
  definition: str
  example: str


class LearnExercise(BaseModel):
  type: LearnExerciseType
  question: str
  options: List[str] | None = None
  correct_answer: str | None = None
  hint: str | None = None
  explanation: str | None = None
  incorrect: str | None = None
  correct: str | None = None
  prompt: str | None = None
  hints: List[str] | None = None
  criteria: List[str] | None = None


class LearnAnalyzeRequest(BaseModel):
  text: str = Field(min_length=10)
  source_type: LearnSourceType = "text"


class LearnContentResponse(BaseModel):
  topic: str
  level: str
  summary: str
  key_points: List[str]
  vocabulary: List[LearnVocabItem]
  exercises: List[LearnExercise]


class LearnEvaluateRequest(BaseModel):
  exercise_type: LearnExerciseType
  question: str
  correct_answer: str
  user_answer: str
  context: str = ""


class LearnEvaluationResponse(BaseModel):
  score: int = Field(ge=0, le=10)
  grammar: int = Field(ge=0, le=10)
  vocabulary: int = Field(ge=0, le=10)
  structure: int = Field(ge=0, le=10)
  fluency: int = Field(ge=0, le=10)
  tone: int | None = None          # speaking only
  pronunciation: int | None = None  # speaking only
  is_correct: bool
  feedback: List[str]
  improved_answer: str
  explanation: str


class LearnMoreExercisesRequest(BaseModel):
  topic: str
  level: str
  summary: str


class LearnSaveSessionRequest(BaseModel):
  source_type: LearnSourceType
  topic: str | None = None
  level: str | None = None
  score: float | None = None
  grammar: float | None = None
  vocabulary: float | None = None
  structure: float | None = None
  exercises_total: int = 0
  exercises_completed: int = 0


# ── ENHANCED SPEAKING MODULE ────────────────────────────────────────────────

class EnhancedConversationMessage(BaseModel):
  """Extended conversation message with audio support for speaking module."""
  role: Literal["examiner", "user"]
  content: str
  audio_url: str | None = None  # URL to audio file (examiner TTS or user recording)
  timestamp: int | None = None  # Unix timestamp


class SpeakingSessionInitRequest(BaseModel):
  """Initialize a speaking session with topic and task type."""
  task_type: TcfSpeakingTaskType
  mode: TcfSpeakingMode = "practice"


class SpeakingSessionInitResponse(BaseModel):
  """Response with session initialization details."""
  session_id: str
  topic: str
  initial_question: str
  initial_audio_url: str | None = None


class EnhancedTcfConversationRequest(BaseModel):
  """Enhanced conversation request with conversation context tracking."""
  session_id: str
  message: str  # User's spoken response (transcribed)
  user_audio_url: str | None = None  # URL to user's recorded audio blob
  history: List[EnhancedConversationMessage] = Field(default_factory=list)
  task_type: TcfSpeakingTaskType
  mode: TcfSpeakingMode = "practice"
  exchange_count: int = 0  # Track number of exchanges (max 5)


class EnhancedTcfConversationResponse(BaseModel):
  """Enhanced response with follow-up questions and context awareness."""
  session_id: str
  reply: str  # Examiner's next question/statement
  audio_url: str | None = None  # TTS-generated audio
  topic: str  # Persistent topic for session
  exchange_count: int  # Incremented exchange counter
  is_complete: bool = False  # True if 5 exchanges reached
  follow_up_category: str | None = None  # "follow_up", "clarification", "deepening"


class UserAudioBlobRequest(BaseModel):
  """Store user's audio blob during speaking test."""
  session_id: str
  exchange_number: int
  audio_data: str  # Base64-encoded audio blob
  transcript: str | None = None  # User's transcribed response


class UserAudioBlobResponse(BaseModel):
  """Response with stored audio URL."""
  audio_url: str
  stored_successfully: bool


class EnhancedSpeakingEvaluationResponse(BaseModel):
  """Realistic evaluation with multiple scoring criteria."""
  transcription_accuracy: float  # 0-10: How accurately was speech recognized
  grammar_score: float  # 0-10: Grammar correctness
  relevance_score: float  # 0-10: Answer relevance to question
  length_score: float  # 0-10: Response length/completeness
  overall_score: float  # Weighted average
  feedback: List[str]
  recommendations: List[str]
  should_improve: bool  # True if score < 6


# ── ENHANCED WRITING MODULE ────────────────────────────────────────────────

class WritingStepFeedbackRequest(BaseModel):
  """Request step-by-step feedback on writing (not full evaluation yet)."""
  task_type: TcfWritingTaskType
  prompt: str
  user_answer: str


class WritingStepFeedbackResponse(BaseModel):
  """Step feedback focusing on issues to fix."""
  task_type: TcfWritingTaskType
  grammar_issues: List[str]  # Specific grammar problems
  missing_points: List[str]  # Required points not covered
  suggestions: List[str]  # Actionable improvements
  estimated_current_score: float  # Current score estimate (0-10)


class WritingFinalEvaluationRequest(BaseModel):
  """Request final comprehensive evaluation."""
  task_type: TcfWritingTaskType
  prompt: str
  user_answer: str  # Final improved answer


class WritingFinalEvaluationResponse(BaseModel):
  """Final evaluation with score and detailed feedback."""
  task_type: TcfWritingTaskType
  overall_score: float  # 0-10
  grammar_score: float  # 0-10
  vocabulary_score: float  # 0-10
  structure_score: float  # 0-10
  relevance_score: float  # 0-10
  feedback: List[str]
  improved_version: str  # AI-improved version for reference
  final_suggestions: List[str]


# ── QUESTION VALIDATION ────────────────────────────────────────────────────

class QuestionValidationRequest(BaseModel):
  """Request to validate if question answer is grounded in source text/audio."""
  question_id: str
  module: Literal["reading", "listening"]
  source_text: str  # The passage or transcript
  question: str
  correct_answer: str
  correct_answer_letter: AnswerOption


class QuestionValidationResponse(BaseModel):
  """Response indicating if question is valid (answer grounded in source)."""
  is_valid: bool
  validation_score: float  # 0-1 confidence
  source_text_span: str  # The specific part supporting the question
  correct_answer_span: str  # The specific part proving the answer
  feedback: str  # Explanation of why valid/invalid


# ── LISTENING DIFFICULTY DISPLAY ────────────────────────────────────────────

class ListeningQuestionWithDifficultyResponse(ListeningQuestionResponse):
  """Extends listening question with actual difficulty level."""
  difficulty_level: str  # A1, A2, B1, B2, C1, C2
  difficulty_range: str  # "A1-A2", "B1-B2", "C1-C2"
