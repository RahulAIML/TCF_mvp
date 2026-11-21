/**
 * MediaRecorder format helpers. Chrome/Firefox record WebM/Opus, Safari records MP4/AAC:
 * always pick a supported type, and label uploads with what the recorder actually produced.
 */

const PREFERRED_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4;codecs=mp4a.40.2",
  "audio/mp4",
  "audio/ogg;codecs=opus",
  "audio/ogg",
];

/** Best recording type this browser supports, or "" to let the browser choose. */
export function getSupportedMimeType(): string {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return "";
  return PREFERRED_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

/** "audio/mp4;codecs=mp4a.40.2" -> "audio/mp4". */
export function baseMime(mime: string | undefined | null): string {
  const base = (mime ?? "").split(";")[0].trim().toLowerCase();
  if (base === "video/mp4" || base === "audio/x-m4a") return "audio/mp4";
  if (base === "video/webm") return "audio/webm";
  return base || "audio/webm";
}

export function extensionForMime(mime: string | undefined | null): string {
  switch (baseMime(mime)) {
    case "audio/mp4":
      return "m4a";
    case "audio/ogg":
      return "ogg";
    case "audio/wav":
      return "wav";
    case "audio/mpeg":
      return "mp3";
    default:
      return "webm";
  }
}

/** Create a recorder with the best supported type; falls back to the browser default. */
export function createRecorder(stream: MediaStream): MediaRecorder {
  const mimeType = getSupportedMimeType();
  try {
    return new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  } catch {
    return new MediaRecorder(stream);
  }
}

/** The type the recorder really produced (recorder.mimeType is empty in some browsers until start). */
export function recordedMime(recorder: MediaRecorder | null, chunks: Blob[]): string {
  return recorder?.mimeType || chunks.find((c) => c.type)?.type || "audio/webm";
}

export function microphoneErrorMessage(err: unknown): string {
  const name = err instanceof DOMException || err instanceof Error ? err.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Microphone access was denied. Allow the microphone in your browser settings and try again.";
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return "No microphone was found. Connect a microphone and try again.";
  }
  if (name === "NotReadableError") {
    return "The microphone is being used by another application. Close it and try again.";
  }
  if (typeof MediaRecorder === "undefined") {
    return "Audio recording is not supported in this browser. Try the latest Chrome, Edge, Firefox or Safari.";
  }
  return "Could not start the microphone. Please try again.";
}

const FRAME_SECONDS = 0.03;
const VOICE_FRAME_RMS = 0.02;
const MIN_VOICE_SECONDS = 0.3;

/**
 * True when the recording decodes and holds under 0.3 s of voice-level audio. Speech models invent words from
 * silence, so silent recordings must never be uploaded. Decode failures return false (unknown → let it through).
 */
export async function isSilentRecording(blob: Blob): Promise<boolean> {
  if (typeof window === "undefined" || blob.size === 0) return blob.size === 0;
  const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctx) return false;
  const ctx = new Ctx();
  try {
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    const data = decoded.getChannelData(0);
    const frame = Math.max(1, Math.floor(decoded.sampleRate * FRAME_SECONDS));
    let voiced = 0;
    for (let start = 0; start + frame <= data.length; start += frame) {
      let sum = 0;
      for (let i = start; i < start + frame; i += 1) sum += data[i] * data[i];
      if (Math.sqrt(sum / frame) >= VOICE_FRAME_RMS) voiced += 1;
    }
    return voiced * FRAME_SECONDS < MIN_VOICE_SECONDS;
  } catch {
    return false;
  } finally {
    void ctx.close().catch(() => undefined);
  }
}

export const NO_SPEECH_MESSAGE = "Aucune parole détectée. Parlez plus près du micro et réessayez.";
