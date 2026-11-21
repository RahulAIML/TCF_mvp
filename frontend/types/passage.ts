export type PassageLevel = "A2" | "B1" | "B2" | "C1" | "C2";

export const PASSAGE_LEVELS: PassageLevel[] = ["A2", "B1", "B2", "C1", "C2"];

export interface PassageResponse {
  title: string;
  passage: string;
}

export interface PassageQuizQuestion {
  question: string;
  options: string[];
  correct_answer: "A" | "B" | "C" | "D";
  explanation: string;
}

export interface PassageQuizResponse {
  title: string;
  passage: string;
  questions: PassageQuizQuestion[];
}
