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
