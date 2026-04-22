"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import TcfAppShell from "@/components/TcfAppShell";
import SpeakingChat from "@/components/SpeakingChat";
import SpeakingRecorder, { SpeakingRecorderHandle } from "@/components/SpeakingRecorder";
import TimerClock from "@/components/TimerClock";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { sendTcfConversation, evaluateTcfSpeaking } from "@/services/api";
import type {
  TcfConversationMessage,
  TcfSpeakingEvaluationResponse,
  TcfSpeakingMode,
  TcfSpeakingTaskType
} from "@/types/tcf-speaking";

const EXAM_DURATION_SECONDS = 12 * 60;
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MAX_EXCHANGES = 5;

type ConvState = "idle" | "listening" | "processing" | "speaking";

const initialHints = [
  "Answer in 1-2 sentences.",
  "Use simple connectors (par exemple: d'abord, ensuite).",
  "Stay polite and natural.",
  "Ask a short follow-up question back."
];

export default function SpeakingPage() {
  const [mode, setMode] = useState<TcfSpeakingMode>("practice");
  const [taskType, setTaskType] = useState<TcfSpeakingTaskType | null>(null);
  const [history, setHistory] = useState<TcfConversationMessage[]>([]);
  const [transcript, setTranscript] = useState("");
  const [convState, setConvState] = useState<ConvState>("idle");
  const [error, setError] = useState("");
  const [evaluation, setEvaluation] = useState<TcfSpeakingEvaluationResponse | null>(null);
  const [timerKey, setTimerKey] = useState(0);
  const [timerActive, setTimerActive] = useState(false);
  const [isExamStarted, setIsExamStarted] = useState(false);
  const [hintsEnabled, setHintsEnabled] = useState(true);
  const [handsFreeEnabled, setHandsFreeEnabled] = useState(false);
  const [userTurnCount, setUserTurnCount] = useState(0);

  const historyRef = useRef<TcfConversationMessage[]>([]);
  const sessionIdRef = useRef<string | null>(null);
  const sessionTopicRef = useRef<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recorderRef = useRef<SpeakingRecorderHandle | null>(null);
  const pendingEvaluateRef = useRef(false);
  const convStateRef = useRef<ConvState>("idle");
  // Always points to the latest handleEvaluate — safe to call from async audio callbacks.
  const handleEvaluateRef = useRef<() => Promise<void>>(async () => {});

  useEffect(() => { historyRef.current = history; }, [history]);
  useEffect(() => { convStateRef.current = convState; }, [convState]);

  const isSessionActive = history.length > 0 || convState !== "idle";

  const stopAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current.src = "";
    }
    if (convStateRef.current === "speaking") setConvState("idle");
    // If the user manually stops audio on the last exchange, the onended event
    // won't fire — trigger the pending evaluation directly from here.
    if (pendingEvaluateRef.current) {
      pendingEvaluateRef.current = false;
      window.setTimeout(() => void handleEvaluateRef.current(), 400);
    }
  }, []);

  const startListening = useCallback(() => {
    if (convStateRef.current === "processing") return;
    if (convStateRef.current === "speaking") return;
    if (mode === "exam" && !isExamStarted) return;
    if (convStateRef.current === "listening") return;
    setConvState("listening");
    recorderRef.current?.start();
  }, [mode, isExamStarted]);

  const stopListening = useCallback(() => {
    recorderRef.current?.stop();
  }, []);

  const buildSessionId = () =>
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

  const resetSession = useCallback(() => {
    recorderRef.current?.cancel();
    stopAudio();
    pendingEvaluateRef.current = false;
    setHistory([]);
    setTranscript("");
    setEvaluation(null);
    setError("");
    setConvState("idle");
    setTimerActive(false);
    setIsExamStarted(false);
    setUserTurnCount(0);
    sessionIdRef.current = null;
    sessionTopicRef.current = null;
  }, [stopAudio]);

  const resetAfterEvaluation = useCallback(() => {
    recorderRef.current?.cancel();
    stopAudio();
    pendingEvaluateRef.current = false;
    setHistory([]);
    setTranscript("");
    setError("");
    setConvState("idle");
    setTimerActive(false);
    setIsExamStarted(false);
    setUserTurnCount(0);
    sessionIdRef.current = null;
    sessionTopicRef.current = null;
    setTaskType(null);
  }, [stopAudio]);

  const buildAudioUrl = (audioUrl?: string | null) => {
    if (!audioUrl) return null;
    if (audioUrl.startsWith("http")) return audioUrl;
    return `${API_BASE_URL}${audioUrl}`;
  };

  const handleEvaluate = useCallback(async () => {
    if (historyRef.current.length === 0) {
      setError("No conversation to evaluate yet.");
      return;
    }
    if (!taskType) {
      setError("Please select a task before evaluating.");
      return;
    }
    // Stop any ongoing recording without emitting a partial transcript.
    recorderRef.current?.cancel();
    // Stop audio immediately — this also clears pendingEvaluateRef so we
    // don't accidentally schedule a second evaluation.
    pendingEvaluateRef.current = false;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setError("");
    setConvState("processing");
    // Snapshot history now before resetAfterEvaluation wipes it.
    const historySnapshot = [...historyRef.current];
    try {
      const result = await evaluateTcfSpeaking({
        history: historySnapshot,
        task_type: taskType,
        mode
      });
      setEvaluation(result);
      setTimerActive(false);
      resetAfterEvaluation();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to evaluate speaking.");
    } finally {
      setConvState("idle");
    }
  }, [taskType, mode, resetAfterEvaluation]);

  // Keep the ref up-to-date so audio callbacks always call the latest version.
  handleEvaluateRef.current = handleEvaluate;

  const playAudio = useCallback((audioUrl: string, onEnded?: () => void) => {
    if (!audioRef.current) return;
    setConvState("speaking");
    audioRef.current.src = audioUrl;
    audioRef.current.onended = () => {
      setConvState("idle");
      onEnded?.();
    };
    audioRef.current.onerror = () => {
      setConvState("idle");
      onEnded?.();
    };
    audioRef.current.play().catch(() => {
      setConvState("idle");
      onEnded?.();
    });
  }, []);

  const startExaminer = useCallback(async () => {
    if (!taskType) {
      setError("Please select a task to begin.");
      setConvState("idle");
      return;
    }
    setError("");
    setEvaluation(null);
    setTranscript("");
    setConvState("processing");
    try {
      const response = await sendTcfConversation({
        message: "__START__",
        history: [],
        task_type: taskType,
        mode,
        hints: mode === "practice" && hintsEnabled,
        session_id: sessionIdRef.current ?? undefined
      });
      if (response.session_topic) {
        sessionTopicRef.current = response.session_topic;
      }
      const assistantMessage: TcfConversationMessage = { role: "assistant", content: response.reply };
      setHistory([assistantMessage]);

      const audioUrl = buildAudioUrl(response.audio_url);
      if (audioUrl) {
        playAudio(audioUrl, () => {
          if (handsFreeEnabled) {
            window.setTimeout(() => startListening(), 800);
          }
        });
      } else {
        setConvState("idle");
        if (handsFreeEnabled) {
          window.setTimeout(() => startListening(), 800);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start conversation.");
      setConvState("idle");
    }
  }, [taskType, mode, hintsEnabled, handsFreeEnabled, playAudio, startListening]);

  const startSession = () => {
    if (!taskType) {
      setError("Please select a task to begin.");
      return;
    }
    resetSession();
    sessionIdRef.current = buildSessionId();
    if (mode === "exam") {
      setTimerKey((prev) => prev + 1);
      setTimerActive(true);
      setIsExamStarted(true);
    }
    window.setTimeout(() => void startExaminer(), 400);
  };

  const handleTranscript = useCallback(async (text: string) => {
    if (!text) {
      if (convStateRef.current === "listening") setConvState("idle");
      return;
    }
    if (userTurnCount >= MAX_EXCHANGES) return;
    if (mode === "exam" && !isExamStarted) {
      setError("Please start the exam first.");
      return;
    }
    if (!taskType) {
      setError("Please select a task to continue.");
      return;
    }

    setError("");
    setTranscript(text);
    setEvaluation(null);
    stopAudio();

    const nextTurnCount = userTurnCount + 1;
    setUserTurnCount(nextTurnCount);
    const isLastTurn = nextTurnCount >= MAX_EXCHANGES;

    const previousHistory = historyRef.current;
    const nextHistory: TcfConversationMessage[] = [...previousHistory, { role: "user", content: text }];
    setHistory(nextHistory);
    setConvState("processing");

    // Brief pause so the UI updates to "Examiner is thinking…" before the
    // request fires. The API call itself provides most of the natural delay.
    await new Promise((resolve) => window.setTimeout(resolve, 500));

    try {
      const response = await sendTcfConversation({
        message: text,
        history: previousHistory,
        task_type: taskType,
        mode,
        hints: mode === "practice" && hintsEnabled,
        session_id: sessionIdRef.current ?? undefined,
        session_topic: sessionTopicRef.current ?? undefined
      });

      const assistantMessage: TcfConversationMessage = { role: "assistant", content: response.reply };
      setHistory((prev) => [...prev, assistantMessage]);

      const audioUrl = buildAudioUrl(response.audio_url);
      if (audioUrl) {
        // Mark last-turn BEFORE playing so stopAudio() can pick it up if needed.
        if (isLastTurn) pendingEvaluateRef.current = true;
        playAudio(audioUrl, () => {
          if (pendingEvaluateRef.current) {
            pendingEvaluateRef.current = false;
            // Use ref so we always call the latest handleEvaluate even if deps changed.
            window.setTimeout(() => void handleEvaluateRef.current(), 400);
          } else if (handsFreeEnabled) {
            window.setTimeout(() => startListening(), 800);
          }
        });
      } else if (isLastTurn) {
        setConvState("idle");
        window.setTimeout(() => void handleEvaluateRef.current(), 400);
      } else {
        setConvState("idle");
        if (handsFreeEnabled) {
          window.setTimeout(() => startListening(), 800);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to get examiner response.");
      setConvState("idle");
    }
  }, [mode, isExamStarted, userTurnCount, taskType, hintsEnabled, handsFreeEnabled,
      stopAudio, startListening, playAudio]);

  const handleTimerExpire = () => {
    if (!isExamStarted) return;
    void handleEvaluate();
  };

  const statusLabel = useMemo(() => {
    if (mode === "exam" && !isExamStarted) return "Start the exam to begin.";
    switch (convState) {
      case "processing": return "Examiner is thinking...";
      case "speaking": return "Examiner is speaking...";
      case "listening": return "Listening... speak now.";
      default:
        if (handsFreeEnabled) return "Hands-free active - ready.";
        return isSessionActive ? "Click Start Recording to respond." : "Ready.";
    }
  }, [convState, handsFreeEnabled, mode, isExamStarted, isSessionActive]);

  const taskLabel = useMemo(() => {
    if (!taskType) return "Select a task";
    if (taskType === "basic_interaction") return "Task 1: Basic interaction";
    if (taskType === "role_play") return "Task 2: Role-play";
    return "Task 3: Opinion";
  }, [taskType]);

  const stateIndicatorColor: Record<ConvState, string> = {
    idle: "bg-slate-300",
    listening: "bg-emerald-500 animate-pulse",
    processing: "bg-amber-400 animate-pulse",
    speaking: "bg-indigo-500 animate-pulse"
  };

  const isRecorderDisabled =
    convState === "processing" ||
    convState === "speaking" ||
    (mode === "exam" && !isExamStarted) ||
    !!evaluation;

  return (
    <TcfAppShell title="Speaking Module" subtitle="Live speaking practice for TCF Canada">
      <div className="space-y-5">

        {/* ── Top control bar ── */}
        <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
          {/* Mode toggle */}
          <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 gap-0.5">
            {(["practice", "exam"] as const).map((m) => (
              <button
                key={m}
                disabled={isSessionActive}
                onClick={() => { setMode(m); resetSession(); }}
                className={`rounded-md px-3 py-1.5 text-sm font-medium capitalize transition-all duration-150 ${
                  mode === m
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-500 hover:text-slate-700 disabled:opacity-50"
                }`}
              >
                {m === "practice" ? "Practice" : "Exam"}
              </button>
            ))}
          </div>

          <div className="h-5 w-px bg-slate-200 mx-1" />

          {/* Task selector */}
          {(
            [
              { key: "basic_interaction", label: "Task 1 — Basic" },
              { key: "role_play",         label: "Task 2 — Role-play" },
              { key: "opinion",           label: "Task 3 — Opinion" },
            ] as { key: TcfSpeakingTaskType; label: string }[]
          ).map(({ key, label }) => (
            <button
              key={key}
              disabled={isSessionActive}
              onClick={() => setTaskType(key)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-all duration-150 ${
                taskType === key
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "border border-slate-200 bg-white text-slate-600 hover:border-slate-300 disabled:opacity-50"
              }`}
            >
              {label}
            </button>
          ))}

          <div className="ml-auto flex items-center gap-2">
            {/* Hands-free toggle */}
            <button
              title="Hands-free: mic auto-starts after examiner finishes."
              onClick={() => setHandsFreeEnabled((prev) => !prev)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium border transition-all duration-150 ${
                handsFreeEnabled
                  ? "border-emerald-400 bg-emerald-50 text-emerald-700"
                  : "border-slate-200 bg-white text-slate-500 hover:border-slate-300"
              }`}
            >
              {handsFreeEnabled ? "🎙 Hands-free On" : "🎙 Hands-free Off"}
            </button>

            {/* Reset */}
            <button
              onClick={resetSession}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-500 hover:border-slate-300 transition"
            >
              Reset
            </button>

            {mode === "exam" && (
              <TimerClock durationSeconds={EXAM_DURATION_SECONDS} isActive={timerActive}
                resetKey={timerKey} onExpire={handleTimerExpire} />
            )}
          </div>
        </div>

        {/* ── Start prompt cards ── */}
        {mode === "exam" && !isExamStarted && (
          <Card className="border-slate-200 shadow-sm">
            <CardContent className="flex items-center justify-between gap-4 p-5">
              <div>
                <p className="font-semibold text-slate-900">Ready to start the exam?</p>
                <p className="mt-0.5 text-sm text-slate-500">
                  You have 12 minutes. Select a task above, then start — the examiner speaks first.
                </p>
              </div>
              <Button onClick={startSession} disabled={!taskType}>Start Exam</Button>
            </CardContent>
          </Card>
        )}

        {mode === "practice" && !isSessionActive && (
          <Card className="border-slate-200 shadow-sm">
            <CardContent className="flex items-center justify-between gap-4 p-5">
              <div>
                <p className="font-semibold text-slate-900">Ready to practise?</p>
                <p className="mt-0.5 text-sm text-slate-500">
                  Select a task above. The examiner will speak first — respond naturally.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setHintsEnabled((prev) => !prev)}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                    hintsEnabled
                      ? "border-amber-300 bg-amber-50 text-amber-700"
                      : "border-slate-200 bg-white text-slate-500"
                  }`}
                >
                  Hints {hintsEnabled ? "On" : "Off"}
                </button>
                <Button onClick={startSession} disabled={!taskType}>Start Practice</Button>
              </div>
            </CardContent>
          </Card>
        )}

        {error && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        {/* ── Main grid ── */}
        <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">

          {/* Left — recorder + chat */}
          <div className="space-y-4">

            {/* Recorder status card */}
            <Card className="border-slate-200 shadow-sm">
              <CardContent className="p-5 space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Active Task</p>
                    <h2 className="mt-0.5 text-base font-semibold text-slate-900">{taskLabel}</h2>
                  </div>
                  {/* State pill */}
                  <span
                    className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
                      convState === "listening"
                        ? "bg-emerald-50 text-emerald-700"
                        : convState === "processing"
                          ? "bg-amber-50 text-amber-700"
                          : convState === "speaking"
                            ? "bg-indigo-50 text-indigo-700"
                            : "bg-slate-100 text-slate-500"
                    }`}
                  >
                    <span className={`h-2 w-2 rounded-full ${stateIndicatorColor[convState]}`} />
                    {convState === "listening" ? "Listening…" :
                     convState === "processing" ? "Thinking…" :
                     convState === "speaking" ? "Examiner speaking…" : "Ready"}
                  </span>
                </div>

                <audio ref={audioRef} className="hidden" />

                <div className="flex flex-wrap items-center gap-2">
                  {convState === "speaking" && (
                    <Button variant="secondary" size="sm" onClick={stopAudio}>
                      ⏹ Stop Audio
                    </Button>
                  )}
                  {!handsFreeEnabled && isSessionActive && !evaluation && convState !== "speaking" && (
                    convState === "listening" ? (
                      <Button variant="secondary" size="sm" onClick={stopListening}>
                        ⏹ Stop Recording
                      </Button>
                    ) : (
                      <Button size="sm" disabled={isRecorderDisabled} onClick={startListening}>
                        🎙 Start Recording
                      </Button>
                    )
                  )}
                </div>

                <SpeakingRecorder
                  ref={recorderRef}
                  hideButton={true}
                  silenceTimeoutMs={handsFreeEnabled ? 3500 : 0}
                  manualSubmit={!handsFreeEnabled}
                  onTranscript={handleTranscript}
                  onError={(message) => setError(message)}
                  onNoSpeech={() => {
                    if (convStateRef.current === "listening") setConvState("idle");
                  }}
                  onListeningChange={(listening) => {
                    if (!listening && convStateRef.current === "listening") setConvState("idle");
                  }}
                  isDisabled={isRecorderDisabled}
                />

                {isSessionActive && (
                  <p className="text-xs text-slate-400">{statusLabel}</p>
                )}
              </CardContent>
            </Card>

            <SpeakingChat
              history={history}
              isThinking={convState === "processing"}
              currentTranscript={transcript}
              exchangeCount={userTurnCount}
              maxExchanges={MAX_EXCHANGES}
            />
          </div>

          {/* Right — hints + evaluate + results */}
          <div className="space-y-4">

            {/* Hints */}
            {mode === "practice" && hintsEnabled && (
              <Card className="border-amber-200 bg-amber-50 shadow-sm">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-amber-800">💡 Speaking Tips</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1.5 text-sm text-amber-700 pb-4">
                  {initialHints.map((hint) => (
                    <p key={hint} className="flex items-start gap-1.5">
                      <span className="mt-0.5 text-amber-400">•</span>
                      {hint}
                    </p>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* End & Evaluate */}
            <Card className="border-slate-200 shadow-sm">
              <CardContent className="p-5 space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Finish</p>
                <Button
                  className="w-full"
                  onClick={() => void handleEvaluate()}
                  disabled={convState === "processing" || history.length === 0}
                >
                  {convState === "processing" ? "Evaluating…" : "End & Get Feedback"}
                </Button>
                <p className="text-xs text-slate-400">
                  Ends the conversation and scores fluency, grammar, and interaction.
                </p>
              </CardContent>
            </Card>

            {/* Evaluation result */}
            {evaluation && (
              <Card className="border-emerald-200 bg-emerald-50 shadow-sm">
                <CardContent className="p-5 space-y-4 text-sm">
                  <p className="font-semibold text-emerald-800">✓ Evaluation Complete</p>

                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { label: "Fluency",       val: evaluation.fluency },
                      { label: "Grammar",       val: evaluation.grammar },
                      { label: "Vocabulary",    val: evaluation.vocabulary },
                      { label: "Interaction",   val: evaluation.interaction }
                    ].map(({ label, val }) => (
                      <div key={label} className="rounded-xl bg-white/70 p-3 text-center">
                        <p className="text-[10px] font-semibold uppercase text-slate-400">{label}</p>
                        <p className="mt-0.5 text-2xl font-bold text-slate-900">{val}</p>
                        <p className="text-[10px] text-slate-400">/ 10</p>
                      </div>
                    ))}
                  </div>

                  <div className="rounded-xl bg-white/70 p-3 space-y-1.5">
                    <p className="text-xs font-semibold uppercase text-slate-400">Feedback</p>
                    <ul className="space-y-1">
                      {evaluation.feedback.map((item, index) => (
                        <li key={`fb-${index}`} className="flex gap-1.5 text-slate-700">
                          <span className="text-emerald-500 mt-0.5 flex-shrink-0">•</span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>

                  {evaluation.improved_response && (
                    <div className="rounded-xl bg-white/70 p-3 space-y-1">
                      <p className="text-xs font-semibold uppercase text-slate-400">Model Response</p>
                      <p className="whitespace-pre-line text-slate-700">{evaluation.improved_response}</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </TcfAppShell>
  );
}
