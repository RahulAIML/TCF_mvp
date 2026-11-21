import type { AnswerOption } from "@/types/exam";

export type ReadingLevel = "A1" | "A2" | "B1" | "B2" | "C1" | "C2";

export const READING_LEVELS: ReadingLevel[] = ["A1", "A2", "B1", "B2", "C1", "C2"];

/** Official item order (easiest first): question-number range for each level. */
export const READING_LEVEL_RANGES: Record<ReadingLevel, { start: number; end: number }> = {
  A1: { start: 1, end: 4 },
  A2: { start: 5, end: 10 },
  B1: { start: 11, end: 19 },
  B2: { start: 20, end: 29 },
  C1: { start: 30, end: 35 },
  C2: { start: 36, end: 39 },
};

export function readingLevelForQuestion(questionNumber: number): ReadingLevel {
  const found = READING_LEVELS.find((level) => {
    const { start, end } = READING_LEVEL_RANGES[level];
    return questionNumber >= start && questionNumber <= end;
  });
  return found ?? (questionNumber < 1 ? "A1" : "C2");
}

export type TcfExamQuestionType =
  | "reading_a1"
  | "reading_a2"
  | "reading_b1"
  | "reading_b2"
  | "reading_c1"
  | "reading_c2"
  | "part1_c2"
  | "part2_b2c1"
  | "part3_b1b2"
  | "part4_a2";

export interface TcfGenerateQuestionRequest {
  question_number: number;
  session_id?: string;
  /** Practice: generate at exactly this level. Omit in the exam (level follows question_number). */
  target_level?: ReadingLevel;
}

export interface TcfExamQuestion {
  question_number: number;
  text: string;
  question: string;
  options: string[];
  correct_answer: AnswerOption;
  explanation: string;
  question_type: TcfExamQuestionType;
}

export interface TcfSubmitExamQuestion {
  question_number: number;
  correct_answer: AnswerOption;
  question_type: TcfExamQuestionType;
  explanation: string;
}

export interface TcfSubmitExamRequest {
  started_at: string;
  completed_at: string;
  answers: Record<number, AnswerOption | "">;
  questions: TcfSubmitExamQuestion[];
}

export interface TcfExamResultItem {
  question_number: number;
  correct_answer: AnswerOption;
  user_answer: AnswerOption | "";
  is_correct: boolean;
  explanation: string;
  question_type: TcfExamQuestionType;
}

export interface TcfSubmitExamResponse {
  score: number;
  total: number;
  attempted: number;
  accuracy: number;
  completion_time: number;
  results: TcfExamResultItem[];
}
