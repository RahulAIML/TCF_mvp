export type TcfWritingTaskType = "task1" | "task2" | "task3";
export type TcfWritingMode = "practice" | "exam";

export interface TcfGenerateWritingTasksRequest {
  session_id?: string;
}

export interface TcfGenerateWritingTasksResponse {
  task1_prompt: string;
  task2_prompt: string;
  task3_prompt: string;
}

export interface TcfWritingEvaluationRequest {
  task_type: TcfWritingTaskType;
  prompt: string;
  response_text: string;
}

export interface TcfWritingEvaluationResponse {
  level: string;
  scores: {
    structure: number;
    grammar: number;
    coherence: number;
    vocab: number;
  };
  feedback: string[];
  improved_version: string;
}

export interface TcfWritingStepFeedbackRequest {
  task_type: TcfWritingTaskType;
  step: string;
  prompt: string;
  text: string;
}

export interface TcfWritingStepFeedbackResponse {
  feedback: string[];
  improved_version: string;
}

export interface TcfWritingProgressRequest {
  session_id: string;
  mode: TcfWritingMode;
  task_type: TcfWritingTaskType;
  steps: Record<string, string>;
  task_prompt?: string;
}

export interface TcfWritingProgressResponse {
  status: string;
}

export interface TcfWritingSubmitRequest {
  session_id: string;
  mode: TcfWritingMode;
  task1_prompt: string;
  task2_prompt: string;
  task3_prompt: string;
  task1_text: string;
  task2_text: string;
  task3_text: string;
  task1_steps?: Record<string, string>;
  task2_steps?: Record<string, string>;
  task3_steps?: Record<string, string>;
}

export interface TcfWritingSubmitResponse {
  task1: TcfWritingEvaluationResponse;
  task2: TcfWritingEvaluationResponse;
  task3: TcfWritingEvaluationResponse;
}

export type TcfWritingAssistantAction = "translate" | "grammar" | "suggestions" | "example";
export type TcfWritingTranslationDirection = "fr-en" | "en-fr";

export interface TcfWritingAssistantRequest {
  message: string;
  action: TcfWritingAssistantAction;
  direction?: TcfWritingTranslationDirection;
  context?: string;
}

export interface TcfWritingAssistantResponse {
  reply: string;
}
