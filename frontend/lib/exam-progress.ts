/**
 * Exam Progress Recovery System
 * Saves and restores exam state using localStorage.
 * Supports Reading, Listening, Writing, and Speaking modules.
 */

const PREFIX = "tcf_progress_";

export type ExamModule = "reading" | "listening" | "writing" | "speaking";

/** Generic progress record stored for any module */
export interface ExamProgressRecord<T = unknown> {
  module: ExamModule;
  savedAt: number;   // Unix ms timestamp
  state: T;
}

/** Reading exam saved state */
export interface ReadingProgressState {
  currentQuestion: number;
  answers: Record<number, string>;  // questionIndex -> answer letter
  sessionId: string | null;
  timeRemaining: number | null;
}

/** Listening exam saved state */
export interface ListeningProgressState {
  currentQuestion: number;
  answers: Record<number, string>;
  sessionId: string | null;
  timeRemaining: number | null;
}

/** Writing exam saved state */
export interface WritingProgressState {
  task1Text: string;
  task2Text: string;
  task3Text: string;
  currentTask: number;
  sessionId: string | null;
  prompts: string[];
}

/** Speaking exam saved state */
export interface SpeakingProgressState {
  history: Array<{ role: string; content: string; audio_url?: string }>;
  taskType: string | null;
  sessionId: string | null;
  userTurnCount: number;
}

function key(module: ExamModule): string {
  return `${PREFIX}${module}`;
}

export function saveExamProgress<T>(module: ExamModule, state: T): void {
  try {
    const record: ExamProgressRecord<T> = {
      module,
      savedAt: Date.now(),
      state,
    };
    localStorage.setItem(key(module), JSON.stringify(record));
  } catch {
    // Storage quota exceeded or private browsing — silently ignore
  }
}

export function loadExamProgress<T>(module: ExamModule): ExamProgressRecord<T> | null {
  try {
    const raw = localStorage.getItem(key(module));
    if (!raw) return null;
    return JSON.parse(raw) as ExamProgressRecord<T>;
  } catch {
    return null;
  }
}

export function clearExamProgress(module: ExamModule): void {
  try {
    localStorage.removeItem(key(module));
  } catch {
    // ignore
  }
}

/** Returns true if saved progress is recent (within maxAgeMs, default 24 hours) */
export function hasRecentProgress(module: ExamModule, maxAgeMs = 24 * 60 * 60 * 1000): boolean {
  const record = loadExamProgress(module);
  if (!record) return false;
  return Date.now() - record.savedAt < maxAgeMs;
}

/** Format relative time for the resume dialog */
export function formatSavedTime(savedAt: number): string {
  const diffMs = Date.now() - savedAt;
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin} minute${diffMin === 1 ? "" : "s"} ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} hour${diffHr === 1 ? "" : "s"} ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay} day${diffDay === 1 ? "" : "s"} ago`;
}
