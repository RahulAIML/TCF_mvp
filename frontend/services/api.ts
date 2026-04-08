import type { WordMeaningRequest, WordMeaningResponse } from "@/types/dictionary";
import type {
  TcfExamQuestion,
  TcfGenerateQuestionRequest,
  TcfSubmitExamRequest,
  TcfSubmitExamResponse
} from "@/types/tcf-exam";
import type { DashboardSummaryResponse } from "@/types/dashboard";
import type { PassageQuizResponse, PassageResponse } from "@/types/passage";
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
import { getAuthToken } from "@/lib/auth";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function parseResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(errorText || `Request failed with status ${res.status}`);
  }
  return res.json() as Promise<T>;
}

function authHeaders(): HeadersInit {
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

export async function generatePassageQuiz(): Promise<PassageQuizResponse> {
  const res = await fetch(`${API_BASE_URL}/generate-passage-quiz`, {
    method: "POST",
    headers: { ...authHeaders() },
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
