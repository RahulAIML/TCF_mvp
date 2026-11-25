export interface TtsVoice {
  id: string;
  label: string;
  language: string;
  gender: string;
}

export interface TtsGenerateRequest {
  text: string;
  voice_id: string;
}

export interface TtsGenerateResponse {
  audio_url: string;
  voice_id: string;
  character_count: number;
}

export interface TtsHistoryItem {
  id: number;
  audio_url: string;
  voice_id: string;
  voice_label: string;
  text_preview: string;
  created_at: string;
}

export interface TtsJobResponse {
  status: "pending" | "done" | "error";
  audio_url: string | null;
  error: string | null;
  total_parts?: number;
  done_parts?: number;
}

export interface TtsJobStart {
  job_id: string;
  status: string;
  total_parts?: number;
}

export interface TtsLanguage {
  code: "fr" | "en" | "es" | "pt";
  locale: string;
  name: string;
  voices: number;
}
