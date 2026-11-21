import type { WordMeaningRequest, WordMeaningResponse } from "@/types/dictionary";
import type {
  TcfExamQuestion,
  TcfGenerateQuestionRequest,
  TcfSubmitExamRequest,
  TcfSubmitExamResponse
} from "@/types/tcf-exam";
import type { DashboardSummaryResponse } from "@/types/dashboard";
import type { PassageLevel, PassageQuizResponse, PassageResponse } from "@/types/passage";
import type {
  GenerateListeningQuestionRequest,
  ListeningQuestion,
  GenerateListeningAudioRequest,
  GenerateListeningAudioResponse,
  SubmitListeningExamRequest,
  SubmitListeningExamResponse
} from "@/types/listening";
import type { ExplainTextRequest, ExplainTextResponse } from "@/types/text-helper";
import type {
  TcfConversationRequest,
  TcfConversationResponse,
  TcfSpeakingEvaluationRequest,
  TcfSpeakingEvaluationResponse
} from "@/types/tcf-speaking";
import type {
  LearnAnalyzeRequest,
  LearnContentResponse,
  LearnEvaluateRequest,
  LearnEvaluationResponse,
  LearnExercise,
  LearnMoreExercisesRequest,
  LearnSaveSessionRequest,
  LearnSessionSummary
} from "@/types/learn";
import type {
  TcfGenerateWritingTasksRequest,
  TcfGenerateWritingTasksResponse,
  TcfWritingAssistantRequest,
  TcfWritingAssistantResponse,
  TcfWritingEvaluationRequest,
  TcfWritingEvaluationResponse,
  TcfWritingStepFeedbackRequest,
  TcfWritingStepFeedbackResponse,
  TcfWritingProgressRequest,
  TcfWritingProgressResponse,
  TcfWritingSubmitRequest,
  TcfWritingSubmitResponse
} from "@/types/tcf-writing";
import type { AuthResponse, LoginRequest, SignupRequest } from "@/types/user";
import type { TtsGenerateRequest, TtsJobResponse, TtsHistoryItem, TtsLanguage, TtsVoice } from "@/types/tts";
import type { McpCreatedToken, McpInfo, McpTokenRecord } from "@/types/mcp";
import { getAuthToken } from "@/lib/auth";
import { emitAuthFailure } from "@/lib/auth-events";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Turn any failed response into a short message that is safe to show to a student. */
export async function friendlyErrorMessage(res: Response): Promise<string> {
  let detail = "";
  try {
    const body = await res.clone().json();
    const raw = body?.detail ?? body?.message ?? body?.error;
    if (typeof raw === "string") detail = raw;
    else if (Array.isArray(raw) && typeof raw[0]?.msg === "string") detail = raw[0].msg;
  } catch {
    // Non-JSON body (HTML error page, proxy text): never show it.
  }
  const technical = /gemini|generate_content|traceback|exception|elevenlabs|sqlalchemy|failed after retries|http \d{3}/i;
  if (detail && detail.length <= 160 && !technical.test(detail)) return detail;
  if (res.status === 404) return "This item is no longer available. Please try again.";
  if (res.status === 413) return "The file is too large.";
  if (res.status === 422 || res.status === 400) return "Some information is missing or invalid. Please check and try again.";
  if (res.status === 429) return "Too many requests right now. Please wait a moment and try again.";
  return "The service is temporarily unavailable. Please try again in a moment.";
}

export async function parseResponse<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    emitAuthFailure();
    throw new Error("Session expired. Please sign in again.");
  }
  if (!res.ok) {
    throw new Error(await friendlyErrorMessage(res));
  }
  return res.json() as Promise<T>;
}

/** Network failures (offline, CORS, dropped connection) surface as TypeError: give them a readable message. */
export function friendlyNetworkError(err: unknown): Error {
  if (err instanceof TypeError) return new Error("Connection problem. Check your internet connection and try again.");
  return err instanceof Error ? err : new Error("Something went wrong. Please try again.");
}

export function authHeaders(): HeadersInit {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function signupUser(payload: SignupRequest): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<AuthResponse>(res);
}

export async function loginUser(payload: LoginRequest): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<AuthResponse>(res);
}

export async function generateTcfListeningQuestion(
  payload: GenerateListeningQuestionRequest
): Promise<ListeningQuestion> {
  const res = await fetch(`${API_BASE_URL}/tcf/generate-listening-question`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<ListeningQuestion>(res);
}

export async function generateTcfListeningAudio(
  payload: GenerateListeningAudioRequest
): Promise<GenerateListeningAudioResponse> {
  const res = await fetch(`${API_BASE_URL}/tcf/generate-listening-audio`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<GenerateListeningAudioResponse>(res);
}

export async function submitTcfListeningExam(
  payload: SubmitListeningExamRequest
): Promise<SubmitListeningExamResponse> {
  const res = await fetch(`${API_BASE_URL}/tcf/submit-listening-exam`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<SubmitListeningExamResponse>(res);
}

export async function generateTcfQuestion(
  payload: TcfGenerateQuestionRequest
): Promise<TcfExamQuestion> {
  const res = await fetch(`${API_BASE_URL}/tcf/generate-question`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<TcfExamQuestion>(res);
}

export async function submitTcfExam(payload: TcfSubmitExamRequest): Promise<TcfSubmitExamResponse> {
  const res = await fetch(`${API_BASE_URL}/tcf/submit-exam`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<TcfSubmitExamResponse>(res);
}

export async function generatePassage(): Promise<PassageResponse> {
  const res = await fetch(`${API_BASE_URL}/generate-passage`, {
    method: "POST",
    headers: { ...authHeaders() },
    cache: "no-store"
  });
  return parseResponse<PassageResponse>(res);
}

export async function generatePassageQuiz(level?: PassageLevel, sessionId?: string): Promise<PassageQuizResponse> {
  const res = await fetch(`${API_BASE_URL}/generate-passage-quiz`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ level, session_id: sessionId }),
    cache: "no-store"
  });
  return parseResponse<PassageQuizResponse>(res);
}

export async function explainText(
  payload: ExplainTextRequest
): Promise<ExplainTextResponse> {
  const res = await fetch(`${API_BASE_URL}/explain-text`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<ExplainTextResponse>(res);
}

export async function translatePassage(text: string): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/translate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ text }),
    cache: "no-store"
  });
  const data = await parseResponse<{ translation: string }>(res);
  return data.translation;
}

export async function explainWord(
  payload: WordMeaningRequest
): Promise<WordMeaningResponse> {
  const res = await fetch(`${API_BASE_URL}/word-meaning`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<WordMeaningResponse>(res);
}

export async function getDashboardSummary(): Promise<DashboardSummaryResponse> {
  const res = await fetch(`${API_BASE_URL}/dashboard/summary`, {
    method: "GET",
    headers: { ...authHeaders() },
    cache: "no-store"
  });
  return parseResponse<DashboardSummaryResponse>(res);
}

export async function generateTcfWritingTasks(
  payload: TcfGenerateWritingTasksRequest
): Promise<TcfGenerateWritingTasksResponse> {
  const res = await fetch(`${API_BASE_URL}/tcf/generate-writing-tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<TcfGenerateWritingTasksResponse>(res);
}

export async function evaluateTcfWritingTask(
  payload: TcfWritingEvaluationRequest
): Promise<TcfWritingEvaluationResponse> {
  const res = await fetch(`${API_BASE_URL}/tcf/evaluate-writing`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<TcfWritingEvaluationResponse>(res);
}

export async function evaluateTcfWritingStep(
  payload: TcfWritingStepFeedbackRequest
): Promise<TcfWritingStepFeedbackResponse> {
  const res = await fetch(`${API_BASE_URL}/tcf/evaluate-writing-step`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<TcfWritingStepFeedbackResponse>(res);
}

export async function saveTcfWritingProgress(
  payload: TcfWritingProgressRequest
): Promise<TcfWritingProgressResponse> {
  const res = await fetch(`${API_BASE_URL}/tcf/writing/save-progress`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<TcfWritingProgressResponse>(res);
}

export async function submitTcfWriting(
  payload: TcfWritingSubmitRequest
): Promise<TcfWritingSubmitResponse> {
  const res = await fetch(`${API_BASE_URL}/tcf/writing/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<TcfWritingSubmitResponse>(res);
}

export async function sendTcfWritingAssistant(
  payload: TcfWritingAssistantRequest
): Promise<TcfWritingAssistantResponse> {
  const res = await fetch(`${API_BASE_URL}/tcf/writing/assistant`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<TcfWritingAssistantResponse>(res);
}

export async function sendTcfConversation(
  payload: TcfConversationRequest
): Promise<TcfConversationResponse> {
  const res = await fetch(`${API_BASE_URL}/tcf/conversation`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<TcfConversationResponse>(res);
}

export async function evaluateTcfSpeaking(
  payload: TcfSpeakingEvaluationRequest
): Promise<TcfSpeakingEvaluationResponse> {
  const res = await fetch(`${API_BASE_URL}/tcf/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<TcfSpeakingEvaluationResponse>(res);
}

export async function analyzeLearnContent(
  payload: LearnAnalyzeRequest
): Promise<LearnContentResponse> {
  const res = await fetch(`${API_BASE_URL}/learn/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<LearnContentResponse>(res);
}

export async function uploadLearnFile(file: File): Promise<{ text: string; source_type: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE_URL}/learn/upload`, {
    method: "POST",
    headers: { ...authHeaders() },
    body: form,
    cache: "no-store"
  });
  return parseResponse<{ text: string; source_type: string }>(res);
}

export async function evaluateLearnAnswer(
  payload: LearnEvaluateRequest
): Promise<LearnEvaluationResponse> {
  const res = await fetch(`${API_BASE_URL}/learn/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<LearnEvaluationResponse>(res);
}

export async function generateMoreExercises(
  payload: LearnMoreExercisesRequest
): Promise<LearnExercise[]> {
  const res = await fetch(`${API_BASE_URL}/learn/more-exercises`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<LearnExercise[]>(res);
}

export async function saveLearnSession(
  payload: LearnSaveSessionRequest
): Promise<LearnSessionSummary> {
  const res = await fetch(`${API_BASE_URL}/learn/session/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<LearnSessionSummary>(res);
}

export async function transcribeAudio(blob: Blob): Promise<{ transcript: string }> {
  const form = new FormData();
  form.append("audio", blob, "recording.webm");
  form.append("language", "fr");
  const res = await fetch(`${API_BASE_URL}/tcf/transcribe-audio`, {
    method: "POST",
    headers: { ...authHeaders() },
    body: form,
    cache: "no-store"
  });
  return parseResponse<{ transcript: string }>(res);
}

export interface PronunciationEvalResult {
  accuracy: number;
  clarity: number;
  mistakes: string[];
  feedback: string;
  improved_version: string;
  user_text: string;
}

export async function evaluatePronunciationAudio(
  targetText: string,
  blob: Blob
): Promise<PronunciationEvalResult> {
  const form = new FormData();
  form.append("target_text", targetText);
  form.append("audio_file", blob, "recording.webm");
  form.append("language", "fr");
  const res = await fetch(`${API_BASE_URL}/api/pronunciation/evaluate`, {
    method: "POST",
    headers: { ...authHeaders() },
    body: form,
    cache: "no-store"
  });
  return parseResponse<PronunciationEvalResult>(res);
}

export async function getTtsLanguages(): Promise<TtsLanguage[]> {
  const res = await fetch(`${API_BASE_URL}/api/tts/languages`, {
    method: "GET",
    headers: { ...authHeaders() },
    cache: "no-store"
  });
  return parseResponse<TtsLanguage[]>(res);
}

export async function getTtsVoices(language?: string): Promise<TtsVoice[]> {
  const query = language ? `?language=${encodeURIComponent(language)}` : "";
  const res = await fetch(`${API_BASE_URL}/api/tts/voices${query}`, {
    method: "GET",
    headers: { ...authHeaders() },
    cache: "no-store"
  });
  return parseResponse<TtsVoice[]>(res);
}

export async function getTtsHistory(): Promise<TtsHistoryItem[]> {
  const res = await fetch(`${API_BASE_URL}/api/tts/history`, {
    method: "GET",
    headers: { ...authHeaders() },
    cache: "no-store",
  });
  return parseResponse<TtsHistoryItem[]>(res);
}

export async function deleteTtsHistoryItem(id: number): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/tts/history/${id}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
    cache: "no-store",
  });
  if (!res.ok && res.status !== 204) {
    throw new Error(`Delete failed: ${res.status}`);
  }
}

export async function startTtsJob(
  payload: TtsGenerateRequest
): Promise<{ job_id: string; status: string }> {
  const res = await fetch(`${API_BASE_URL}/api/tts/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return parseResponse<{ job_id: string; status: string }>(res);
}

export async function pollTtsJob(jobId: string): Promise<TtsJobResponse> {
  const res = await fetch(`${API_BASE_URL}/api/tts/job/${jobId}`, {
    headers: { ...authHeaders() },
    cache: "no-store"
  });
  return parseResponse<TtsJobResponse>(res);
}

// ── MCP (Connect Grok) ──────────────────────────────────────────────────────

async function mcpError(res: Response, fallback: string): Promise<never> {
  let message = fallback;
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") message = body.detail;
  } catch {}
  throw new Error(message);
}

export async function getMcpInfo(): Promise<McpInfo> {
  const res = await fetch(`${API_BASE_URL}/api/mcp/info`, { headers: { ...authHeaders() }, cache: "no-store" });
  return parseResponse<McpInfo>(res);
}

export async function listMcpTokens(): Promise<McpTokenRecord[]> {
  const res = await fetch(`${API_BASE_URL}/api/mcp/tokens`, { headers: { ...authHeaders() }, cache: "no-store" });
  const body = await parseResponse<{ tokens: McpTokenRecord[] }>(res);
  return body.tokens;
}

export async function createMcpToken(name: string): Promise<McpCreatedToken> {
  const res = await fetch(`${API_BASE_URL}/api/mcp/tokens`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name }),
    cache: "no-store"
  });
  if (res.status === 409) return mcpError(res, "You have too many active tokens. Revoke one first.");
  return parseResponse<McpCreatedToken>(res);
}

export async function revokeMcpToken(id: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/mcp/tokens/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
    cache: "no-store"
  });
  if (!res.ok && res.status !== 204) return mcpError(res, `Revoke failed: ${res.status}`);
}
