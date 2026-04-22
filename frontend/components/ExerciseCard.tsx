"use client";

import { useCallback, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { LearnExercise, LearnEvaluationResponse } from "@/types/learn";

interface ExerciseCardProps {
  exercise: LearnExercise;
  index: number;
  answer: string;
  onAnswerChange: (answer: string) => void;
  evaluation: LearnEvaluationResponse | null;
  isEvaluating: boolean;
}

const EXERCISE_TITLES: Record<string, string> = {
  mcq: "Multiple Choice",
  fill_blank: "Fill in the Blank",
  sentence_correction: "Sentence Correction",
  writing_task: "Writing Task",
  speaking_prompt: "Speaking Exercise"
};

const EXERCISE_BADGE: Record<string, string> = {
  mcq: "bg-indigo-100 text-indigo-700",
  fill_blank: "bg-sky-100 text-sky-700",
  sentence_correction: "bg-amber-100 text-amber-700",
  writing_task: "bg-emerald-100 text-emerald-700",
  speaking_prompt: "bg-rose-100 text-rose-700",
};

const OPTION_LETTERS = ["A", "B", "C", "D"];

const SCORE_COLOR = (score: number) => {
  if (score >= 8) return "text-emerald-600";
  if (score >= 6) return "text-amber-600";
  return "text-rose-600";
};

// ── Inline mic hook ────────────────────────────────────────────────────────
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: { results: { 0: { transcript: string } }[] }) => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

function useMic(onTranscript: (t: string) => void) {
  const [isListening, setIsListening] = useState(false);
  const [micError, setMicError] = useState("");
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const lastResultIndexRef = useRef(0);

  const toggle = useCallback(() => {
    if (isListening) {
      recRef.current?.stop();
      return;
    }
    setMicError("");
    const win = window as unknown as {
      SpeechRecognition?: new () => SpeechRecognitionLike;
      webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    };
    const Ctor = win.SpeechRecognition ?? win.webkitSpeechRecognition;
    if (!Ctor) {
      setMicError("Speech recognition not supported in this browser.");
      return;
    }
    const rec = new Ctor();
    rec.lang = "fr-FR";
    rec.continuous = true;
    rec.interimResults = false;
    lastResultIndexRef.current = 0;
    rec.onresult = (e) => {
      // Only process new results since last callback
      const texts: string[] = [];
      for (let i = lastResultIndexRef.current; i < e.results.length; i++) {
        const t = e.results[i][0].transcript.trim();
        if (t) texts.push(t);
      }
      lastResultIndexRef.current = e.results.length;
      const combined = texts.join(" ").trim();
      if (combined) onTranscript(combined);
    };
    rec.onerror = (e) => {
      const code = e.error ?? "";
      if (code !== "no-speech" && code !== "aborted") {
        setMicError(code === "not-allowed" ? "Microphone access denied." : `Error: ${code}`);
      }
    };
    rec.onend = () => {
      setIsListening(false);
      recRef.current = null;
    };
    recRef.current = rec;
    setIsListening(true);
    rec.start();
  }, [isListening, onTranscript]);

  return { isListening, micError, toggle };
}

// ── MicButton ──────────────────────────────────────────────────────────────
function MicButton({ disabled, onTranscript, onAppend }: {
  disabled: boolean;
  onTranscript: (t: string) => void;
  onAppend: (t: string) => void;
}) {
  const { isListening, micError, toggle } = useMic((text) => {
    onTranscript(text);
    onAppend(text);
  });

  return (
    <div className="space-y-1">
      <button
        type="button"
        disabled={disabled}
        onClick={toggle}
        title={isListening ? "Stop recording" : "Speak your answer"}
        className={`flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium transition-all
          ${isListening
            ? "border-rose-400 bg-rose-500 text-white shadow-md"
            : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
          }
          ${disabled ? "cursor-default opacity-50" : "cursor-pointer"}`}
      >
        {isListening ? (
          <>
            <span className="relative flex h-3 w-3">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75" />
              <span className="relative inline-flex h-3 w-3 rounded-full bg-white" />
            </span>
            Stop Recording
          </>
        ) : (
          <>
            <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 1a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V5a4 4 0 0 1 4-4zm0 2a2 2 0 0 0-2 2v6a2 2 0 0 0 4 0V5a2 2 0 0 0-2-2zm7 8a1 1 0 0 1 1 1 8 8 0 0 1-7 7.938V21h2a1 1 0 0 1 0 2H9a1 1 0 0 1 0-2h2v-1.062A8 8 0 0 1 4 12a1 1 0 1 1 2 0 6 6 0 0 0 12 0 1 1 0 0 1 1-1z" />
            </svg>
            Speak Answer
          </>
        )}
      </button>
      {isListening && (
        <p className="text-xs text-slate-500 animate-pulse">Listening in French... speak now</p>
      )}
      {micError && <p className="text-xs text-rose-500">{micError}</p>}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────
export default function ExerciseCard({
  exercise,
  index,
  answer,
  onAnswerChange,
  evaluation,
  isEvaluating
}: ExerciseCardProps) {
  const isLocked = isEvaluating || evaluation !== null;

  // Append spoken text to existing textarea content
  const handleSpokenAppend = useCallback((text: string) => {
    onAnswerChange(answer ? `${answer} ${text}` : text);
  }, [answer, onAnswerChange]);

  return (
    <Card className="border-slate-200 shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-bold text-slate-400">#{index + 1}</span>
            <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${EXERCISE_BADGE[exercise.type] ?? "bg-slate-100 text-slate-600"}`}>
              {EXERCISE_TITLES[exercise.type] ?? exercise.type}
            </span>
          </div>
          {isEvaluating && (
            <span className="flex items-center gap-1.5 text-xs text-slate-400 animate-pulse">
              <span className="h-1.5 w-1.5 rounded-full bg-slate-300 animate-pulse" />
              Evaluating…
            </span>
          )}
          {evaluation && (
            <span className={`text-xl font-bold tabular-nums ${SCORE_COLOR(evaluation.score)}`}>
              {evaluation.score}<span className="text-sm font-normal text-slate-300">/10</span>
            </span>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Question / Prompt */}
        <div>
          {exercise.type === "sentence_correction" ? (
            <div className="space-y-1">
              <p className="text-sm font-medium text-slate-700">Correct this sentence:</p>
              <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-800">
                {exercise.incorrect}
              </p>
            </div>
          ) : (
            <p className="text-sm font-medium text-slate-800">
              {exercise.prompt ?? exercise.question}
            </p>
          )}
          {exercise.hint && !isLocked && (
            <p className="mt-1 text-xs text-slate-500">Hint: {exercise.hint}</p>
          )}
          {exercise.hints && exercise.hints.length > 0 && !isLocked && (
            <ul className="mt-2 space-y-1">
              {exercise.hints.map((h, i) => (
                <li key={i} className="text-xs text-slate-500">• {h}</li>
              ))}
            </ul>
          )}
        </div>

        {/* Answer Input */}
        {exercise.type === "mcq" && exercise.options && (
          <div className="space-y-2">
            {exercise.options.map((opt, i) => {
              const letter = OPTION_LETTERS[i] ?? opt.charAt(0);
              const isSelected = answer === letter;
              return (
                <button
                  key={opt}
                  disabled={isLocked}
                  onClick={() => onAnswerChange(letter)}
                  className={`group flex w-full items-start gap-3 rounded-xl border px-3 py-2.5 text-left text-sm transition-all duration-150
                    ${isSelected
                      ? "border-indigo-600 bg-indigo-600 text-white shadow-sm"
                      : "border-slate-200 bg-white text-slate-700 hover:border-indigo-200 hover:bg-indigo-50"
                    }
                    ${isLocked ? "cursor-default" : "cursor-pointer"}`}
                >
                  <span className={`flex-shrink-0 h-6 w-6 rounded-md text-xs font-bold flex items-center justify-center transition-colors ${
                    isSelected ? "bg-white/20 text-white" : "bg-slate-100 text-slate-600 group-hover:bg-indigo-100 group-hover:text-indigo-700"
                  }`}>
                    {letter}
                  </span>
                  <span className="mt-0.5">{opt.replace(/^[A-D]\.\s*/, "")}</span>
                </button>
              );
            })}
          </div>
        )}

        {(exercise.type === "fill_blank" || exercise.type === "sentence_correction") && (
          <input
            type="text"
            disabled={isLocked}
            value={answer}
            onChange={(e) => onAnswerChange(e.target.value)}
            placeholder={
              exercise.type === "fill_blank"
                ? "Type your answer..."
                : "Type the corrected sentence..."
            }
            className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300 disabled:opacity-60"
          />
        )}

        {exercise.type === "writing_task" && (
          <textarea
            disabled={isLocked}
            value={answer}
            onChange={(e) => onAnswerChange(e.target.value)}
            rows={4}
            placeholder="Write your response in French..."
            className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300 disabled:opacity-60 resize-none"
          />
        )}

        {/* Speaking exercise: textarea + mic button */}
        {exercise.type === "speaking_prompt" && (
          <div className="space-y-3">
            <textarea
              disabled={isLocked}
              value={answer}
              onChange={(e) => onAnswerChange(e.target.value)}
              rows={4}
              placeholder="Speak using the mic below, or type what you would say in French..."
              className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300 disabled:opacity-60 resize-none"
            />
            {!isLocked && (
              <MicButton
                disabled={isLocked}
                onTranscript={() => undefined}
                onAppend={handleSpokenAppend}
              />
            )}
            {answer && !isLocked && (
              <button
                onClick={() => onAnswerChange("")}
                className="text-xs text-slate-400 underline hover:text-slate-600"
              >
                Clear
              </button>
            )}
          </div>
        )}

        {/* Evaluation Result */}
        {evaluation && (
          <div className="space-y-3 border-t border-slate-100 pt-4">
            {/* Correct / Wrong banner */}
            <div className={`flex items-center gap-2 rounded-xl px-4 py-2.5 ${
              evaluation.is_correct
                ? "bg-emerald-50 border border-emerald-200"
                : "bg-rose-50 border border-rose-200"
            }`}>
              <span className={`text-base font-bold ${evaluation.is_correct ? "text-emerald-600" : "text-rose-600"}`}>
                {evaluation.is_correct ? "✓" : "✗"}
              </span>
              <span className={`text-sm font-semibold ${evaluation.is_correct ? "text-emerald-700" : "text-rose-700"}`}>
                {evaluation.is_correct ? "Correct" : "Incorrect"}
              </span>
              <span className={`ml-auto text-xs font-medium ${evaluation.is_correct ? "text-emerald-500" : "text-rose-500"}`}>
                Score: {evaluation.score}/10
              </span>
            </div>

            {/* Sub-scores */}
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
              {[
                { label: "Grammar", val: evaluation.grammar },
                { label: "Vocabulary", val: evaluation.vocabulary },
                { label: "Structure", val: evaluation.structure },
                { label: "Fluency", val: evaluation.fluency },
                ...(evaluation.tone != null ? [{ label: "Tone", val: evaluation.tone }] : []),
                ...(evaluation.pronunciation != null ? [{ label: "Pronunciation", val: evaluation.pronunciation }] : [])
              ].filter(({ val }) => val != null).map(({ label, val }) => (
                <div key={label} className="rounded-xl bg-slate-50 px-2 py-2 text-center">
                  <p className="text-[10px] uppercase tracking-wide text-slate-400">{label}</p>
                  <p className={`text-base font-bold tabular-nums ${SCORE_COLOR(val ?? 0)}`}>{val}</p>
                </div>
              ))}
            </div>

            {evaluation.feedback.length > 0 && (
              <div className="rounded-xl bg-slate-50 px-4 py-3 space-y-1">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Feedback</p>
                <ul className="space-y-1">
                  {evaluation.feedback.map((f, i) => (
                    <li key={i} className="flex gap-1.5 text-sm text-slate-700">
                      <span className="text-slate-400 flex-shrink-0">•</span>
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {evaluation.improved_answer && (
              <div className="rounded-xl bg-emerald-50 border border-emerald-100 px-4 py-3 space-y-1">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-emerald-500">Model Answer</p>
                <p className="text-sm text-emerald-900">{evaluation.improved_answer}</p>
              </div>
            )}

            {evaluation.explanation && (
              <div className="rounded-xl bg-slate-50 px-4 py-3 space-y-1">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Explanation</p>
                <p className="text-sm text-slate-700">{evaluation.explanation}</p>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
