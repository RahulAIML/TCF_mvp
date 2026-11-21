/**
 * Deadline-based countdown. Time left is always `deadline − now`, so it never drifts when the tab is
 * backgrounded (browsers throttle intervals there) or when re-renders restart intervals.
 */
export interface Countdown {
  /** Wall-clock end time while running; null while paused. */
  deadlineMs: number | null;
  /** Time left at the moment it was paused (or the full duration before starting). */
  pausedRemainingMs: number;
  expired: boolean;
}

export function createCountdown(durationSeconds: number): Countdown {
  return { deadlineMs: null, pausedRemainingMs: Math.max(0, durationSeconds) * 1000, expired: false };
}

/** Start or pause. Pausing stores the exact time left; resuming sets a fresh deadline from it. */
export function setRunning(state: Countdown, running: boolean, nowMs: number): Countdown {
  if (running && state.deadlineMs === null) {
    return { ...state, deadlineMs: nowMs + state.pausedRemainingMs };
  }
  if (!running && state.deadlineMs !== null) {
    return { ...state, deadlineMs: null, pausedRemainingMs: Math.max(0, state.deadlineMs - nowMs) };
  }
  return state;
}

export function remainingMs(state: Countdown, nowMs: number): number {
  return state.deadlineMs === null ? state.pausedRemainingMs : Math.max(0, state.deadlineMs - nowMs);
}

/** Whole seconds shown to the user (rounded up, so 0 appears only when time is really over). */
export function remainingSeconds(state: Countdown, nowMs: number): number {
  return Math.ceil(remainingMs(state, nowMs) / 1000);
}

/** True exactly once: the first check at or after the deadline while running. */
export function takeExpiry(state: Countdown, nowMs: number): { state: Countdown; fire: boolean } {
  if (state.expired || state.deadlineMs === null || remainingMs(state, nowMs) > 0) return { state, fire: false };
  return { state: { ...state, expired: true }, fire: true };
}
