export type LearnSourceType = "text" | "pdf" | "image" | "chat";
export type LearnExerciseType =
  | "mcq"
  | "fill_blank"
  | "sentence_correction"
  | "writing_task"
  | "speaking_prompt";

export interface LearnVocabItem {
  word: string;
  definition: string;
  example: string;
}

export interface LearnExercise {
  type: LearnExerciseType;
  question: string;
  // MCQ
  options?: string[];
  correct_answer?: string;
  explanation?: string;
  // fill_blank
  hint?: string;
  // sentence_correction
  incorrect?: string;
  correct?: string;
  // writing_task / speaking_prompt
  prompt?: string;
  hints?: string[];
  criteria?: string[];
}

export interface LearnContentResponse {
  topic: string;
  level: string;
  summary: string;
  key_points: string[];
  vocabulary: LearnVocabItem[];
  exercises: LearnExercise[];
  content_id?: string | null;
}

export type LearnOverview = Omit<LearnContentResponse, "exercises" | "content_id">;

export interface LearnAnalyzeStreamHandlers {
  onOverview: (overview: LearnOverview) => void;
  onExercises: (exercises: LearnExercise[]) => void;
  onDone: (contentId: string) => void;
}

export interface LearnEvaluateBatchItem extends LearnEvaluateRequest {
  index: number;
}

export type LearnBatchResult =
  | { index: number; evaluation: LearnEvaluationResponse; error?: undefined }
  | { index: number; error: string; evaluation?: undefined };

export interface LearnAnalyzeRequest {
  text: string;
  source_type?: LearnSourceType;
}

export interface LearnEvaluateRequest {
  exercise_type: LearnExerciseType;
  question: string;
  correct_answer: string;
  user_answer: string;
  context?: string;
  explanation?: string;
}

export interface LearnEvaluationResponse {
  score: number;
  grammar: number;
  vocabulary: number;
  structure: number;
  fluency: number;
  tone?: number | null;           // speaking only
  pronunciation?: number | null;  // speaking only
  is_correct: boolean;
  feedback: string[];
  improved_answer: string;
  explanation: string;
}

export interface LearnMoreExercisesRequest {
  topic: string;
  level: string;
  summary: string;
  content_id?: string;
  exclude_questions?: string[];
}

export interface LearnSaveSessionRequest {
  source_type: LearnSourceType;
  topic?: string;
  level?: string;
  score?: number;
  grammar?: number;
  vocabulary?: number;
  structure?: number;
  exercises_total?: number;
  exercises_completed?: number;
}

export interface LearnSessionSummary {
  id: number;
  topic?: string | null;
  level?: string | null;
  score?: number | null;
  exercises_completed: number;
  exercises_total: number;
  created_at: string;
}
