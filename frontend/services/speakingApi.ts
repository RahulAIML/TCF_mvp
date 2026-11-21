import { API_BASE_URL, authHeaders, friendlyErrorMessage, friendlyNetworkError, parseResponse } from "@/services/api";
import { extensionForMime } from "@/lib/audio-mime";
import type {
  PronunciationEvalResult,
  TcfConversationRequest,
  TcfConversationResponse,
  TcfSpeakingEvaluationRequest,
  TcfSpeakingEvaluationResponse,
  TcfSpeakingOpeningRequest,
  TranscriptionResult,
  VocabularyItem,
} from "@/types/tcf-speaking";

type SseEvent = { type: string; [key: string]: unknown };

/** POST and read a Server-Sent Events stream, calling onEvent for each JSON event until [DONE]. */
async function streamEvents(
  path: string,
  init: { body: BodyInit; json?: boolean },
  onEvent: (event: SseEvent) => void,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { ...(init.json ? { "Content-Type": "application/json" } : {}), ...authHeaders() },
      body: init.body,
      cache: "no-store",
    });
  } catch (err) {
    throw friendlyNetworkError(err);
  }
  if (!res.ok) throw new Error(await friendlyErrorMessage(res));
  if (!res.body) throw new Error("The service is temporarily unavailable. Please try again in a moment.");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") return;
        let event: SseEvent;
        try {
          event = JSON.parse(raw) as SseEvent;
        } catch {
          continue;
        }
        if (event.type === "error") {
          throw new Error(typeof event.message === "string" ? event.message : "Something went wrong. Please try again.");
        }
        onEvent(event);
      }
    }
  } catch (err) {
    throw friendlyNetworkError(err);
  }
}

/** A stable anonymous id for this browser, so practice content is never repeated for the same learner. */
export function getLearnerId(): string {
  const key = "tcf_learner_id";
  try {
    const existing = window.localStorage.getItem(key);
    if (existing) return existing;
    const created = typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    window.localStorage.setItem(key, created);
    return created;
  } catch {
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
}

function recordingFile(blob: Blob): { blob: Blob; name: string } {
  return { blob, name: `recording.${extensionForMime(blob.type)}` };
}

export async function transcribeRecording(blob: Blob, language = "fr"): Promise<TranscriptionResult> {
  const form = new FormData();
  const file = recordingFile(blob);
  form.append("audio", file.blob, file.name);
  form.append("language", language.split("-")[0]);
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/tcf/transcribe-audio`, {
      method: "POST",
      headers: { ...authHeaders() },
      body: form,
      cache: "no-store",
    });
  } catch (err) {
    throw friendlyNetworkError(err);
  }
  return parseResponse<TranscriptionResult>(res);
}

export interface PronunciationStreamHandlers {
  onTranscript?: (userText: string) => void;
  onFeedbackToken?: (token: string) => void;
  onScores?: (scores: PronunciationEvalResult) => void;
  onNoSpeech?: (result: PronunciationEvalResult) => void;
}

/** Streams: transcript first, then coach feedback word by word, scores as soon as they are ready. */
export async function streamPronunciationEvaluation(
  targetText: string,
  blob: Blob,
  language: string,
  handlers: PronunciationStreamHandlers,
): Promise<void> {
  const form = new FormData();
  const file = recordingFile(blob);
  form.append("target_text", targetText);
  form.append("audio_file", file.blob, file.name);
  form.append("language", language);
  await streamEvents("/api/pronunciation/evaluate/stream", { body: form }, (event) => {
    if (event.type === "transcript") handlers.onTranscript?.(String(event.user_text ?? ""));
    else if (event.type === "token") handlers.onFeedbackToken?.(String(event.token ?? ""));
    else if (event.type === "scores") handlers.onScores?.(event as unknown as PronunciationEvalResult);
    else if (event.type === "no_speech") handlers.onNoSpeech?.(event as unknown as PronunciationEvalResult);
  });
}

export async function fetchSpeakingOpening(payload: TcfSpeakingOpeningRequest): Promise<TcfConversationResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/tcf/speaking/opening`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
  } catch (err) {
    throw friendlyNetworkError(err);
  }
  return parseResponse<TcfConversationResponse>(res);
}

export interface ConversationStreamHandlers {
  onMeta?: (meta: { session_topic?: string | null; examiner_name?: string | null }) => void;
  onToken?: (token: string) => void;
  onReply?: (reply: string) => void;
  onAudio?: (audioUrl: string | null) => void;
}

/** Examiner reply: text streams first, then the audio URL once the text is complete. */
export async function streamConversation(
  payload: TcfConversationRequest,
  handlers: ConversationStreamHandlers,
): Promise<void> {
  await streamEvents("/tcf/conversation/stream", { body: JSON.stringify(payload), json: true }, (event) => {
    if (event.type === "meta") handlers.onMeta?.(event as { session_topic?: string; examiner_name?: string });
    else if (event.type === "token") handlers.onToken?.(String(event.token ?? ""));
    else if (event.type === "reply") handlers.onReply?.(String(event.reply ?? ""));
    else if (event.type === "audio") handlers.onAudio?.((event.audio_url as string | null) ?? null);
  });
}

export interface EvaluationStreamHandlers {
  onScores?: (scores: Omit<TcfSpeakingEvaluationResponse, "improved_response"> & { improved_response?: string }) => void;
  onModelAnswerToken?: (token: string) => void;
}

/** Scores arrive as soon as they are ready; the model answer streams word by word. */
export async function streamSpeakingEvaluation(
  payload: TcfSpeakingEvaluationRequest,
  handlers: EvaluationStreamHandlers,
): Promise<void> {
  await streamEvents("/tcf/evaluate/stream", { body: JSON.stringify(payload), json: true }, (event) => {
    if (event.type === "scores") {
      handlers.onScores?.(event as unknown as TcfSpeakingEvaluationResponse);
    } else if (event.type === "token") {
      handlers.onModelAnswerToken?.(String(event.token ?? ""));
    }
  });
}

export async function generateVocabularySet(params: {
  level: string;
  count: number;
  topic?: string;
  language: string;
  sessionId: string;
}): Promise<VocabularyItem[]> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/pronunciation/vocabulary/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        level: params.level,
        count: params.count,
        topic: params.topic,
        language: params.language,
        session_id: params.sessionId,
      }),
      cache: "no-store",
    });
  } catch (err) {
    throw friendlyNetworkError(err);
  }
  const data = await parseResponse<{ words: VocabularyItem[] }>(res);
  if (!data.words?.length) throw new Error("No vocabulary could be generated. Please try again.");
  return data.words;
}
