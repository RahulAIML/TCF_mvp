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
import { createRecorder, microphoneErrorMessage, recordedMime } from "@/lib/audio-mime";
import { transcribeRecording } from "@/services/speakingApi";

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
    async (blob: Blob) => {
      if (cancelledRef.current) return;
      setIsTranscribing(true);
      try {
        const result = await transcribeRecording(blob, language);
        const text = result.transcript.trim();
        if (text) {
          onTranscript(text);
        } else {
          onError?.(result.message ?? "Aucune parole détectée. Parlez plus près du micro et réessayez.");
          onTranscript("");
        }
      } catch (err) {
        onError?.(err instanceof Error ? err.message : "Transcription failed. Please try again.");
        onTranscript("");
      } finally {
        setIsTranscribing(false);
      }
    },
    [language, onTranscript, onError]
  );

  const startRecording = useCallback(async () => {
    if (isDisabled || isRecording) return;

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      onError?.(microphoneErrorMessage(null));
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      cancelledRef.current = false;
      chunksRef.current = [];

      const recorder = createRecorder(stream);

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
          const blob = new Blob(chunksRef.current, { type: recordedMime(recorder, chunksRef.current) });
          void transcribeAudio(blob);
        }
        chunksRef.current = [];
      };

      mediaRecorderRef.current = recorder;
      recorder.start(250); // collect chunks every 250ms
      setIsRecording(true);
      onListeningChange?.(true);
    } catch (err) {
      stopStream();
      onError?.(microphoneErrorMessage(err));
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
