import type {
  LearnAnalyzeRequest,
  LearnAnalyzeStreamHandlers,
  LearnBatchResult,
  LearnEvaluateBatchItem,
  LearnEvaluationResponse,
  LearnExercise,
  LearnOverview
} from "@/types/learn";
import { emitAuthFailure } from "@/lib/auth-events";
import { API_BASE_URL, authHeaders, friendlyErrorMessage, friendlyNetworkError } from "@/services/api";

type LearnSseEvent =
  | ({ type: "overview" } & LearnOverview)
  | { type: "exercises"; exercises: LearnExercise[] }
  | { type: "progress"; ready: number; total: number }
  | { type: "done"; content_id?: string }
  | { type: "error"; message: string }
  | { type: "result"; index: number; evaluation?: LearnEvaluationResponse; error?: string };

export const LEARN_ANALYSIS_INTERRUPTED = "L'analyse a été interrompue. Veuillez réessayer.";

async function postSse(path: string, body: unknown, onEvent: (event: LearnSseEvent) => void): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
      cache: "no-store"
    });
  } catch (err) {
    throw friendlyNetworkError(err);
  }
  if (!res.ok || !res.body) {
    if (res.status === 401) emitAuthFailure();
    throw new Error(await friendlyErrorMessage(res));
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const line = frame.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        let event: LearnSseEvent;
        try {
          event = JSON.parse(line.slice(6)) as LearnSseEvent;
        } catch {
          continue;
        }
        onEvent(event);
      }
    }
  } catch (err) {
    throw friendlyNetworkError(err);
  }
}

/** Streams the analysis: the overview and the exercises render as soon as each is ready. */
export async function analyzeLearnContentStream(
  payload: LearnAnalyzeRequest,
  handlers: LearnAnalyzeStreamHandlers
): Promise<void> {
  let failure: string | null = null;
  let finished = false;
  await postSse("/learn/analyze/stream", payload, (event) => {
    if (event.type === "overview") {
      const { type: _type, ...overview } = event;
      handlers.onOverview(overview);
    } else if (event.type === "progress") {
      handlers.onProgress?.(event.ready, event.total);
    } else if (event.type === "exercises") {
      handlers.onExercises(event.exercises);
    } else if (event.type === "done") {
      finished = true;
      handlers.onDone(event.content_id ?? "");
    } else if (event.type === "error") {
      failure = event.message;
    }
  });
  if (failure) throw new Error(failure);
  if (!finished) throw new Error(LEARN_ANALYSIS_INTERRUPTED);
}

/** The server evaluates every item in parallel; `onResult` fires per item as soon as it is ready. */
export async function evaluateLearnBatchStream(
  items: LearnEvaluateBatchItem[],
  onResult: (result: LearnBatchResult) => void
): Promise<void> {
  await postSse("/learn/evaluate-batch/stream", { items }, (event) => {
    if (event.type !== "result") return;
    if (event.evaluation) onResult({ index: event.index, evaluation: event.evaluation });
    else onResult({ index: event.index, error: event.error ?? "L'évaluation a échoué. Réessayez." });
  });
}
