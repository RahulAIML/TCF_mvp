export type TcfSpeakingTaskType = "basic_interaction" | "role_play" | "opinion";
export type TcfSpeakingMode = "practice" | "exam";

export interface TcfConversationMessage {
  role: "user" | "assistant";
  content: string;
}

export interface TcfConversationRequest {
  message: string;
  history: TcfConversationMessage[];
  task_type: TcfSpeakingTaskType;
  mode?: TcfSpeakingMode;
  hints?: boolean;
  session_id?: string;
  session_topic?: string;
  examiner_name?: string;
}

export interface TcfConversationResponse {
  reply: string;
  audio_url?: string | null;
  session_topic?: string | null;
  examiner_name?: string | null;
}

export interface TcfSpeakingOpeningRequest {
  task_type: TcfSpeakingTaskType;
  mode?: TcfSpeakingMode;
  hints?: boolean;
  session_id?: string;
}

export interface TcfSpeakingEvaluationRequest {
  history: TcfConversationMessage[];
  task_type: TcfSpeakingTaskType;
  mode?: TcfSpeakingMode;
}

export interface TcfSpeakingEvaluationResponse {
  fluency: number;
  grammar: number;
  vocabulary: number;
  interaction: number;
  feedback: string[];
  improved_response: string;
  cefr_level?: string | null;
}

export interface TranscriptionResult {
  transcript: string;
  no_speech: boolean;
  message?: string;
}

export interface PronunciationEvalResult {
  accuracy: number;
  clarity: number;
  mistakes: string[];
  feedback: string;
  improved_version: string;
  user_text: string;
  no_speech?: boolean;
}

export interface VocabularyItem {
  word: string;
  meaning: string;
  example: string;
  example_translation?: string | null;
  phonetic?: string | null;
  audio_url?: string | null;
}
