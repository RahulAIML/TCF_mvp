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
