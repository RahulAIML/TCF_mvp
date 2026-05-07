"use client";

/**
 * AudioSpeakingRecorder
 * Records audio via MediaRecorder, uploads to /tcf/transcribe-audio, returns transcript.
 * Works on Chrome, Edge, Firefox, Safari (iOS 14.5+).
 * Does NOT depend on browser speech recognition APIs.
 */

import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { Mic, MicOff, Loader } from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AudioSpeakingRecorderHandle {
  start: () => void;
  stop: () => void;
  cancel: () => void;
}

interface AudioSpeakingRecorderProps {
  language?: string;
  isDisabled?: boolean;
  hideButton?: boolean;
  onTranscript: (transcript: string) => void;
  onError?: (message: string) => void;
  onListeningChange?: (listening: boolean) => void;
}

/** Preferred MIME types ordered by browser support. */
function getSupportedMimeType(): string {
  const types = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
    "audio/mp4",
  ];
  for (const type of types) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(type)) {
      return type;
    }
  }
  return "";
}

const AudioSpeakingRecorder = forwardRef<
  AudioSpeakingRecorderHandle,
  AudioSpeakingRecorderProps
>(function AudioSpeakingRecorder(
  {
    language = "fr",
    isDisabled = false,
    hideButton = false,
    onTranscript,
    onError,
    onListeningChange,
  },
  ref
) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const cancelledRef = useRef(false);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const transcribeAudio = useCallback(
    async (blob: Blob, mimeType: string) => {
      if (cancelledRef.current) return;
      setIsTranscribing(true);
      try {
        const form = new FormData();
        const ext = mimeType.startsWith("audio/ogg")
          ? "ogg"
          : mimeType.startsWith("audio/mp4")
          ? "mp4"
          : "webm";
        form.append("audio", blob, `recording.${ext}`);
        form.append("language", language.split("-")[0]); // fr-FR -> fr

        const res = await fetch(`${API_BASE_URL}/tcf/transcribe-audio`, {
          method: "POST",
          body: form,
        });

        if (!res.ok) {
          const err = await res.text();
          throw new Error(err || "Transcription failed");
        }

        const data = (await res.json()) as { transcript: string };
        const text = data.transcript.trim();
        if (text) {
          onTranscript(text);
        } else {
          onError?.("No speech detected. Please try again.");
        }
      } catch (err) {
        onError?.(err instanceof Error ? err.message : "Transcription error");
      } finally {
        setIsTranscribing(false);
      }
    },
    [language, onTranscript, onError]
  );

  const startRecording = useCallback(async () => {
    if (isDisabled || isRecording) return;

    if (!navigator.mediaDevices?.getUserMedia) {
      onError?.("Microphone access is not supported in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      cancelledRef.current = false;
      chunksRef.current = [];

      const mimeType = getSupportedMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        stopStream();
        setIsRecording(false);
        onListeningChange?.(false);
        if (!cancelledRef.current && chunksRef.current.length > 0) {
          const blob = new Blob(chunksRef.current, { type: mimeType || "audio/webm" });
          void transcribeAudio(blob, mimeType || "audio/webm");
        }
        chunksRef.current = [];
      };

      mediaRecorderRef.current = recorder;
      recorder.start(250); // collect chunks every 250ms
      setIsRecording(true);
      onListeningChange?.(true);
    } catch (err) {
      stopStream();
      const msg =
        err instanceof Error && err.name === "NotAllowedError"
          ? "Microphone access denied. Please allow microphone access in your browser."
          : "Failed to access microphone.";
      onError?.(msg);
    }
  }, [isDisabled, isRecording, stopStream, transcribeAudio, onError, onListeningChange]);

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    } else {
      stopStream();
      setIsRecording(false);
      onListeningChange?.(false);
    }
  }, [stopStream, onListeningChange]);

  const cancelRecording = useCallback(() => {
    cancelledRef.current = true;
    chunksRef.current = [];
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    } else {
      stopStream();
      setIsRecording(false);
      onListeningChange?.(false);
    }
  }, [stopStream, onListeningChange]);

  useImperativeHandle(
    ref,
    () => ({
      start: startRecording,
      stop: stopRecording,
      cancel: cancelRecording,
    }),
    [startRecording, stopRecording, cancelRecording]
  );

  if (hideButton) return null;

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        onClick={isRecording ? stopRecording : startRecording}
        disabled={isDisabled || isTranscribing}
        className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition ${
          isRecording
            ? "bg-red-600 text-white hover:bg-red-700 animate-pulse"
            : "bg-emerald-600 text-white hover:bg-emerald-700"
        } disabled:opacity-40 disabled:cursor-not-allowed`}
        aria-label={isRecording ? "Stop recording" : "Start recording"}
      >
        {isTranscribing ? (
          <>
            <Loader className="h-4 w-4 animate-spin" />
            Transcribing…
          </>
        ) : isRecording ? (
          <>
            <MicOff className="h-4 w-4" />
            Stop Recording
          </>
        ) : (
          <>
            <Mic className="h-4 w-4" />
            Start Recording
          </>
        )}
      </button>
      <p className="text-sm text-slate-500">
        {isTranscribing
          ? "Processing your response…"
          : isRecording
          ? "Recording… speak your answer, then click Stop."
          : "Click to record your answer in French."}
      </p>
    </div>
  );
});

export default AudioSpeakingRecorder;
