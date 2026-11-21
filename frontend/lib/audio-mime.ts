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
