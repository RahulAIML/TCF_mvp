/** Practice-only reading of a finished comprehension exam. Not an official TCF score. */

export const LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"] as const;
export type CefrLevel = (typeof LEVELS)[number];

const RANGES: Record<CefrLevel, [number, number]> = {
  A1: [1, 4],
  A2: [5, 10],
  B1: [11, 19],
  B2: [20, 29],
  C1: [30, 35],
  C2: [36, 39],
};

export function levelForQuestion(questionNumber: number): CefrLevel {
  return LEVELS.find((level) => questionNumber >= RANGES[level][0] && questionNumber <= RANGES[level][1]) ?? "C2";
}

/**
 * Highest band where at least half of the answered items in that band were correct,
 * provided every lower answered band also cleared that bar. Unanswered bands are skipped.
 */
export function estimateCefr(items: { question_number: number; is_correct: boolean; user_answer?: string }[]): string {
  const answered = items.filter((item) => item.user_answer);
  if (answered.length === 0) return "Not enough answers";
  let reached = "A1 not reached";
  for (const level of LEVELS) {
    const band = answered.filter((item) => levelForQuestion(item.question_number) === level);
    if (band.length === 0) continue;
    const correct = band.filter((item) => item.is_correct).length;
    if (correct / band.length >= 0.5) reached = level;
    else break;
  }
  return reached;
}

export const OFFICIAL_SCORE_NOTE =
  "The official TCF comprehension score runs from 100 to 699. IRCC converts that score to NCLC " +
  "(listening and reading use different cut scores). A count of correct practice answers is not that score, so no NCLC is assigned.";
