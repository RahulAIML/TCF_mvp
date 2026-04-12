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
}

export interface TcfConversationResponse {
  reply: string;
  audio_url?: string | null;
  session_topic?: string | null;
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
}
