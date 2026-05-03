"use client";

import { forwardRef, useCallback, useImperativeHandle, useRef, useState } from "react";
import { Button } from "@/components/ui/button";

export interface SpeakingRecorderHandle {
  start: () => void;
  stop: () => void;    // emit buffered transcript
  cancel: () => void;  // discard buffer, stop silently
}

interface SpeakingRecorderProps {
  language?: string;
  isDisabled?: boolean;
  /**
   * Ms of silence after last final result before auto-submitting.
   * 0 = never auto-submit (manual mode — call stop() to emit).
   */
  silenceTimeoutMs?: number;
  /**
   * When true, buffer all final results and only call onTranscript
   * when stop() is explicitly called. Overrides silenceTimeoutMs.
   */
  manualSubmit?: boolean;
  /** When true, the recorder renders no buttons — parent provides controls. */
  hideButton?: boolean;
  onTranscript: (transcript: string) => void;
  onError?: (message: string) => void;
  onNoSpeech?: () => void;
  onListeningChange?: (listening: boolean) => void;
}

interface SpeechRecognitionResultItem {
  transcript: string;
  isFinal: boolean;
}

interface SpeechRecognitionResult {
  [index: number]: SpeechRecognitionResultItem;
  isFinal: boolean;
}

interface SpeechRecognitionEventLike {
  results: SpeechRecognitionResult[];
  resultIndex: number;
}

interface SpeechRecognitionErrorEventLike {
  error?: string;
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

const SpeakingRecorder = forwardRef<SpeakingRecorderHandle, SpeakingRecorderProps>(
  function SpeakingRecorder(
    {
      language = "fr-FR",
      isDisabled = false,
      silenceTimeoutMs = 3500,
      manualSubmit = false,
      hideButton = false,
      onTranscript,
      onError,
      onNoSpeech,
      onListeningChange,
    },
    ref
  ) {
    const [isListening, setIsListening] = useState(false);
    const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
    const bufferRef = useRef<string[]>([]);
    const interimRef = useRef<string>("");
    const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const stopTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const pendingEmitRef = useRef(false);
    const manualSubmitRef = useRef(manualSubmit);
    const silenceTimeoutMsRef = useRef(silenceTimeoutMs);
    manualSubmitRef.current = manualSubmit;
    silenceTimeoutMsRef.current = silenceTimeoutMs;

    const clearSilenceTimer = useCallback(() => {
      if (silenceTimerRef.current !== null) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
    }, []);

    const clearStopTimeout = useCallback(() => {
      if (stopTimeoutRef.current !== null) {
        clearTimeout(stopTimeoutRef.current);
        stopTimeoutRef.current = null;
      }
    }, []);

    const finalizeStop = useCallback(
      (emit: boolean) => {
        clearSilenceTimer();
        clearStopTimeout();
        setIsListening(false);
        onListeningChange?.(false);
        const combined = [...bufferRef.current, interimRef.current]
          .map((item) => item.trim())
          .filter(Boolean)
          .join(" ")
          .trim();
        bufferRef.current = [];
        interimRef.current = "";
        pendingEmitRef.current = false;
        if (emit && combined) {
          onTranscript(combined);
        }
      },
      [clearSilenceTimer, clearStopTimeout, onListeningChange, onTranscript]
    );

    // Emit buffer and stop recognition
    const doStop = useCallback(
      (emit: boolean) => {
        clearSilenceTimer();
        pendingEmitRef.current = emit;
        const rec = recognitionRef.current;
        recognitionRef.current = null; // prevent onend restart
        if (rec) {
          try { rec.stop(); } catch { try { rec.abort(); } catch { /* ignore */ } }
          clearStopTimeout();
          stopTimeoutRef.current = setTimeout(() => finalizeStop(pendingEmitRef.current), 500);
          return;
        }
        finalizeStop(emit);
      },
      [clearSilenceTimer, clearStopTimeout, finalizeStop]
    );

    const resetSilenceTimer = useCallback(() => {
      if (manualSubmitRef.current) return; // manual mode: no auto-submit
      clearSilenceTimer();
      const ms = silenceTimeoutMsRef.current;
      if (ms <= 0) return;
      silenceTimerRef.current = setTimeout(() => {
        doStop(true);
      }, ms);
    }, [clearSilenceTimer, doStop]);

    const startRecognition = useCallback(() => {
      if (isDisabled) return;

      const speechApi = window as unknown as {
        SpeechRecognition?: SpeechRecognitionConstructor;
        webkitSpeechRecognition?: SpeechRecognitionConstructor;
      };
      const SpeechRecognitionImpl =
        speechApi.SpeechRecognition ?? speechApi.webkitSpeechRecognition;

      if (!SpeechRecognitionImpl) {
        onError?.("Speech recognition is not supported in this browser.");
        return;
      }

      bufferRef.current = [];
      const recognition = new SpeechRecognitionImpl();
      recognition.lang = language;
      recognition.continuous = true;
      recognition.interimResults = true;

      recognition.onresult = (event: SpeechRecognitionEventLike) => {
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i];
          if (result.isFinal) {
            const text = result[0].transcript.trim();
            if (text) {
              bufferRef.current.push(text);
              interimRef.current = "";
              resetSilenceTimer(); // restart silence countdown on each final result
            }
          } else {
            interimRef.current = result[0].transcript.trim();
          }
        }
      };

      recognition.onerror = (event: SpeechRecognitionErrorEventLike) => {
        const code = event.error ?? "";
        if (code === "no-speech" || code === "audio-capture") {
          onNoSpeech?.();
          return;
        }
        if (code === "aborted") return; // intentional abort
        const messages: Record<string, string> = {
          "not-allowed": "Microphone access denied. Please allow microphone access.",
          network: "Network error during speech recognition.",
        };
        const msg = messages[code] ?? `Speech recognition error: ${code}`;
        if (msg) onError?.(msg);
      };

      recognition.onend = () => {
        // Auto-restart if we're still supposed to be listening (browser cuts on silence)
        if (recognitionRef.current === recognition) {
          try { recognition.start(); } catch { /* ignore if already started */ }
        } else {
          finalizeStop(pendingEmitRef.current);
        }
      };

      recognitionRef.current = recognition;
      setIsListening(true);
      onListeningChange?.(true);
      recognition.start();
    }, [isDisabled, language, onError, onListeningChange, onNoSpeech, resetSilenceTimer, finalizeStop]);

    useImperativeHandle(
      ref,
      () => ({
        start: startRecognition,
        stop: () => doStop(true),
        cancel: () => doStop(false),
      }),
      [startRecognition, doStop]
    );

    if (hideButton) return null;

    return (
      <div className="flex flex-wrap items-center gap-3">
        <Button
          onClick={isListening ? () => doStop(true) : startRecognition}
          disabled={isDisabled}
        >
          {isListening ? "Stop Recording" : "Start Recording"}
        </Button>
        <p className="text-sm text-slate-500">
          {isListening ? "Listening… speak now." : "Tap to answer in French."}
        </p>
      </div>
    );
  }
);

export default SpeakingRecorder;
