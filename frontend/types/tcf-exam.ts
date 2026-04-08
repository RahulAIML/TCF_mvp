import type { AnswerOption } from "@/types/exam";

export type TcfExamQuestionType =
  | "part1_a1a2"
  | "part2_a2b1"
  | "part3_b1b2"
  | "part4_b2c2";

export interface TcfGenerateQuestionRequest {
  question_number: number;
  session_id?: string;
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
  accuracy: number;
  completion_time: number;
  results: TcfExamResultItem[];
}
