"use client";

import { useRef, useState } from "react";
import TcfAppShell from "@/components/TcfAppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { generateTcfQuestion, translatePassage } from "@/services/api";
import type { AnswerOption } from "@/types/exam";
import {
  READING_LEVELS,
  READING_LEVEL_RANGES,
  type ReadingLevel,
  type TcfExamQuestion
} from "@/types/tcf-exam";

const SET_SIZE = 10;
const QUEUE_AHEAD = 4;

const LEVEL_LABELS: Record<ReadingLevel, string> = {
  A1: "A1 — Signs, short notes, simple ads",
  A2: "A2 — Menus, timetables, simple messages",
  B1: "B1 — Personal letters, practical notices",
  B2: "B2 — Opinion articles and reports",
  C1: "C1 — Long articles, editorials, essays",
  C2: "C2 — Literary and essay extracts",
};

const LEVEL_COLORS: Record<ReadingLevel, string> = {
  A1: "bg-slate-500",
  A2: "bg-indigo-600",
  B1: "bg-emerald-600",
  B2: "bg-amber-500",
  C1: "bg-orange-500",
  C2: "bg-rose-600",
};

interface AnsweredItem {
  question: TcfExamQuestion;
  answer: AnswerOption;
  correct: boolean;
}

type LevelScore = { correct: number; attempted: number };

function randomInRange(min: number, max: number) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function newSessionId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function ReadingPracticePage() {
  const [level, setLevel] = useState<ReadingLevel | null>(null);
  const [pendingLevel, setPendingLevel] = useState<ReadingLevel | null>(null);
  const [question, setQuestion] = useState<TcfExamQuestion | null>(null);
  const [position, setPosition] = useState(0);
  const [answered, setAnswered] = useState<AnsweredItem[]>([]);
  const [setComplete, setSetComplete] = useState(false);
  const [selectedAnswer, setSelectedAnswer] = useState<AnswerOption | "">("");
  const [revealed, setRevealed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [scores, setScores] = useState<Partial<Record<ReadingLevel, LevelScore>>>({});

  const [translation, setTranslation] = useState("");
  const [showTranslation, setShowTranslation] = useState(false);
  const [isTranslating, setIsTranslating] = useState(false);
  const [translateError, setTranslateError] = useState("");

  // One id for the whole visit: the backend never serves the same item twice to this session.
  const sessionIdRef = useRef<string>(newSessionId());
  const queueRef = useRef<Promise<TcfExamQuestion>[]>([]);
  const requestedRef = useRef(0);
  const generationRef = useRef(0);

  const fetchOne = (lvl: ReadingLevel): Promise<TcfExamQuestion> => {
    const { start, end } = READING_LEVEL_RANGES[lvl];
    return generateTcfQuestion({
      question_number: randomInRange(start, end),
      session_id: sessionIdRef.current,
      target_level: lvl,
    });
  };

  const fillQueue = (lvl: ReadingLevel) => {
    while (queueRef.current.length < QUEUE_AHEAD && requestedRef.current < SET_SIZE) {
      const request = fetchOne(lvl);
      request.catch(() => undefined); // handled when consumed; avoids unhandled-rejection noise
      queueRef.current.push(request);
      requestedRef.current += 1;
    }
  };

  const showNextQuestion = async (lvl: ReadingLevel) => {
    const generation = generationRef.current;
    setLoading(true);
    setError("");
    let next: TcfExamQuestion | null = null;
    const queued = queueRef.current.shift();
    if (!queued) requestedRef.current += 1;
    try {
      next = await (queued ?? fetchOne(lvl));
    } catch {
      try {
        next = await fetchOne(lvl);
      } catch (err) {
        if (generation === generationRef.current) {
          setError(err instanceof Error ? err.message : "Could not load the next question.");
          setLoading(false);
        }
        return;
      }
    }
    if (generation !== generationRef.current) return;
    setQuestion(next);
    setPosition((p) => p + 1);
    setSelectedAnswer("");
    setRevealed(false);
    setTranslation("");
    setShowTranslation(false);
    setTranslateError("");
    setLoading(false);
    fillQueue(lvl);
  };

  const startSet = (lvl: ReadingLevel) => {
    generationRef.current += 1;
    queueRef.current = [];
    requestedRef.current = 0;
    setLevel(lvl);
    setPendingLevel(null);
    setQuestion(null);
    setPosition(0);
    setAnswered([]);
    setSetComplete(false);
    fillQueue(lvl);
    void showNextQuestion(lvl);
  };

  const setInProgress = !setComplete && (answered.length > 0 || question !== null || loading);

  const handleLevelSelect = (lvl: ReadingLevel) => {
    if (lvl === level && !setComplete) return;
    if (setInProgress && lvl !== level) {
      setPendingLevel(lvl);
      return;
    }
    startSet(lvl);
  };

  const handleAnswer = (value: AnswerOption) => {
    if (revealed) return;
    setSelectedAnswer(value);
  };

  const handleReveal = () => {
    if (!selectedAnswer || !question || !level) return;
    const correct = selectedAnswer === question.correct_answer;
    setRevealed(true);
    setAnswered((prev) => [...prev, { question, answer: selectedAnswer, correct }]);
    setScores((prev) => {
      const current = prev[level] ?? { correct: 0, attempted: 0 };
      return { ...prev, [level]: { correct: current.correct + (correct ? 1 : 0), attempted: current.attempted + 1 } };
    });
  };

  const handleNext = () => {
    if (!level || loading) return;
    if (answered.length >= SET_SIZE) {
      setSetComplete(true);
      setQuestion(null);
      return;
    }
    void showNextQuestion(level);
  };

  const handleTranslate = async () => {
    if (!question) return;
    if (translation) {
      setShowTranslation((p) => !p);
      return;
    }
    setIsTranslating(true);
    setTranslateError("");
    try {
      const result = await translatePassage(question.text);
      setTranslation(result);
      setShowTranslation(true);
    } catch {
      setTranslateError("Translation failed. Please try again.");
    } finally {
      setIsTranslating(false);
    }
  };

  const setScore = answered.filter((a) => a.correct).length;
  const scoredLevels = READING_LEVELS.filter((l) => (scores[l]?.attempted ?? 0) > 0);

  return (
    <TcfAppShell
      title="Reading Practice"
      subtitle={`Choose a level and practise sets of ${SET_SIZE} questions`}
      backHref="/tcf/reading"
    >
      <div className="max-w-5xl space-y-6">
        <Card className="border-slate-200 shadow-sm">
          <CardContent className="p-6">
            <p className="mb-3 text-sm font-semibold text-slate-700">Select CEFR Level</p>
            <div className="flex flex-wrap gap-2">
              {READING_LEVELS.map((lvl) => (
                <button
                  key={lvl}
                  onClick={() => handleLevelSelect(lvl)}
                  className={`rounded-full px-4 py-1.5 text-sm font-semibold text-white transition-opacity ${LEVEL_COLORS[lvl]} ${
                    level === lvl ? "ring-2 ring-offset-2 ring-slate-800" : "opacity-80 hover:opacity-100"
                  }`}
                >
                  {lvl}
                </button>
              ))}
            </div>
            {level && <p className="mt-2 text-xs text-slate-500">{LEVEL_LABELS[level]}</p>}

            {pendingLevel && (
              <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                <p className="font-medium">Switch to {pendingLevel}?</p>
                <p className="mt-1 text-xs text-amber-800">
                  Your current {level} set ({answered.length} of {SET_SIZE} answered) will end. Your per-level score is kept.
                </p>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" onClick={() => startSet(pendingLevel)}>Switch level</Button>
                  <Button size="sm" variant="secondary" onClick={() => setPendingLevel(null)}>Keep practising {level}</Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {scoredLevels.length > 0 && (
          <div className="flex flex-wrap gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-5 py-3">
            {scoredLevels.map((lvl) => {
              const s = scores[lvl]!;
              return (
                <div key={lvl} className="flex items-center gap-2 text-sm">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-bold text-white ${LEVEL_COLORS[lvl]}`}>{lvl}</span>
                  <span className="font-semibold text-slate-900">{s.correct}/{s.attempted}</span>
                  <span className="text-xs text-slate-500">{Math.round((s.correct / s.attempted) * 100)}%</span>
                </div>
              );
            })}
          </div>
        )}

        {level && !setComplete && position > 0 && (
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs text-slate-500">
              <span>Question {Math.min(position, SET_SIZE)} of {SET_SIZE}</span>
              <span>{setScore} correct so far</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-1.5 rounded-full bg-indigo-500 transition-all duration-300"
                style={{ width: `${(answered.length / SET_SIZE) * 100}%` }}
              />
            </div>
          </div>
        )}

        {error && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            <span>{error}</span>
            {level && (
              <Button size="sm" variant="secondary" onClick={() => void showNextQuestion(level)} disabled={loading}>
                Retry
              </Button>
            )}
          </div>
        )}

        {loading && (
          <Card className="border-slate-200 shadow-sm rounded-2xl animate-pulse">
            <CardContent className="p-6 space-y-4">
              <div className="h-3 w-full rounded bg-slate-100" />
              <div className="h-3 w-5/6 rounded bg-slate-100" />
              <div className="h-3 w-4/6 rounded bg-slate-100" />
              <div className="h-4 w-3/4 rounded bg-slate-200" />
              <div className="grid gap-2 pt-1">
                {[1, 2, 3, 4].map((i) => <div key={i} className="h-10 rounded-xl bg-slate-100" />)}
              </div>
              <p className="flex items-center gap-1.5 pt-1 text-xs text-slate-400">
                <span className="inline-block h-2 w-2 animate-ping rounded-full bg-indigo-400" />
                Loading question…
              </p>
            </CardContent>
          </Card>
        )}

        {setComplete && level && (
          <Card className="border-slate-200 shadow-sm rounded-2xl overflow-hidden">
            <div className="border-b border-slate-100 bg-emerald-50 px-6 py-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Set complete · Level {level}</p>
              <p className="mt-1 text-2xl font-bold text-slate-900">
                {setScore} / {SET_SIZE}
                <span className="ml-2 text-base font-medium text-slate-500">{Math.round((setScore / SET_SIZE) * 100)}%</span>
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button onClick={() => startSet(level)}>New {level} set</Button>
                <Button
                  variant="secondary"
                  onClick={() => { setSetComplete(false); setLevel(null); setPosition(0); setAnswered([]); }}
                >
                  Choose another level
                </Button>
              </div>
            </div>
            <div className="divide-y divide-slate-100 px-6 py-2">
              {answered.map((item, index) => (
                <div key={`review-${index}`} className="space-y-1.5 py-4">
                  <div className="flex items-start gap-3">
                    <span className={`mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                      item.correct ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-600"
                    }`}>
                      {item.correct ? "✓" : "✗"}
                    </span>
                    <p className="text-sm font-medium text-slate-800">{index + 1}. {item.question.question}</p>
                  </div>
                  <p className="ml-9 text-xs text-slate-500">
                    Your answer: <span className={`font-semibold ${item.correct ? "text-emerald-700" : "text-rose-600"}`}>{item.answer}</span>
                    {!item.correct && (
                      <> · Correct: <span className="font-semibold text-emerald-700">{item.question.correct_answer}</span></>
                    )}
                  </p>
                  {item.question.explanation && (
                    <p className="ml-9 text-xs leading-relaxed text-slate-500">{item.question.explanation}</p>
                  )}
                </div>
              ))}
            </div>
          </Card>
        )}

        {question && !loading && !setComplete && level && (
          <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
            <div className="space-y-4">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <div className="mb-3 flex items-center justify-between">
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold text-white ${LEVEL_COLORS[level]}`}>
                    {level}
                  </span>
                  <button
                    onClick={() => void handleTranslate()}
                    disabled={isTranslating}
                    className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-indigo-600 transition-all duration-150 hover:bg-indigo-50 disabled:opacity-50"
                  >
                    {isTranslating ? (
                      <><span className="h-3 w-3 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />Translating…</>
                    ) : showTranslation && translation ? "Hide Translation →" : "Show Translation →"}
                  </button>
                </div>
                <p className="mb-2 text-[10px] font-semibold uppercase text-slate-400">Passage (French)</p>
                <p className="whitespace-pre-line text-sm leading-7 text-slate-800">{question.text}</p>
                {translateError && <p className="mt-2 text-xs text-rose-600">{translateError}</p>}
              </div>

              <div className="space-y-3">
                <h3 className="text-base font-semibold text-slate-900">{question.question}</h3>
                <div className="space-y-2">
                  {question.options.map((option, index) => {
                    const value = (["A", "B", "C", "D"][index] as AnswerOption);
                    const isSelected = selectedAnswer === value;
                    const isCorrect = revealed && value === question.correct_answer;
                    const isWrong = revealed && isSelected && value !== question.correct_answer;
                    return (
                      <label
                        key={value}
                        className={`group flex items-start gap-3 rounded-xl border px-3 py-3 text-sm transition-all duration-150 ${
                          isCorrect
                            ? "border-emerald-500 bg-emerald-50 text-emerald-800"
                            : isWrong
                              ? "border-rose-400 bg-rose-50 text-rose-800"
                              : isSelected
                                ? "border-indigo-600 bg-indigo-600 text-white"
                                : "border-slate-200 bg-white text-slate-700 hover:border-indigo-200 hover:bg-indigo-50"
                        } ${revealed ? "cursor-default" : "cursor-pointer"}`}
                      >
                        <input
                          type="radio"
                          name="practice-answer"
                          value={value}
                          checked={isSelected}
                          onChange={() => handleAnswer(value)}
                          disabled={revealed}
                          className="sr-only"
                        />
                        <span className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md text-xs font-bold transition-colors ${
                          isCorrect ? "bg-emerald-100 text-emerald-700"
                            : isWrong ? "bg-rose-100 text-rose-700"
                              : isSelected ? "bg-white/20 text-white"
                                : "bg-slate-100 text-slate-600 group-hover:bg-indigo-100 group-hover:text-indigo-700"
                        }`}>
                          {value}
                        </span>
                        <span className="mt-0.5 flex-1">{option.replace(/^[A-D]\.\s*/, "")}</span>
                        {isCorrect && <span className="ml-auto font-bold text-emerald-600">✓</span>}
                        {isWrong && <span className="ml-auto font-bold text-rose-500">✗</span>}
                      </label>
                    );
                  })}
                </div>

                <div className="flex gap-3 pt-2">
                  {!revealed && (
                    <Button onClick={handleReveal} disabled={!selectedAnswer}>Check Answer</Button>
                  )}
                  {revealed && (
                    <Button onClick={handleNext} disabled={loading}>
                      {answered.length >= SET_SIZE ? "See set results" : "Next Question"}
                    </Button>
                  )}
                </div>
              </div>
            </div>

            <div className="space-y-4">
              {showTranslation && translation && (
                <Card className="border-indigo-200 bg-indigo-50 shadow-sm">
                  <CardContent className="space-y-2 p-4">
                    <div className="flex items-center justify-between">
                      <p className="text-[10px] font-semibold uppercase tracking-wide text-indigo-500">English Translation</p>
                      <button onClick={() => setShowTranslation(false)} className="text-xs text-indigo-400 transition hover:text-indigo-600">
                        ✕ Hide
                      </button>
                    </div>
                    <p className="text-sm leading-6 text-slate-700">{translation}</p>
                  </CardContent>
                </Card>
              )}

              {revealed && (
                <Card className={`border shadow-sm ${selectedAnswer === question.correct_answer ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50"}`}>
                  <CardContent className="space-y-3 p-5">
                    <p className={`text-sm font-bold ${selectedAnswer === question.correct_answer ? "text-emerald-700" : "text-rose-700"}`}>
                      {selectedAnswer === question.correct_answer ? "✓ Correct!" : "✗ Incorrect"}
                    </p>
                    <p className="text-sm text-slate-700">
                      <span className="font-semibold">Correct answer: </span>
                      {question.correct_answer}
                    </p>
                    {question.explanation && (
                      <div className="rounded-xl bg-white/70 px-4 py-3">
                        <p className="mb-1 text-xs font-semibold uppercase text-slate-400">Explanation</p>
                        <p className="text-sm text-slate-700">{question.explanation}</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}

        {!level && !setComplete && (
          <Card className="border-slate-200 shadow-sm">
            <CardContent className="p-5">
              <p className="mb-3 text-sm font-semibold text-slate-700">How it works</p>
              <ul className="space-y-2 text-sm text-slate-500">
                <li className="flex gap-2"><span className="text-slate-300">1.</span>Select a CEFR level above (A1 to C2)</li>
                <li className="flex gap-2"><span className="text-slate-300">2.</span>Answer a set of {SET_SIZE} questions written for that exact level</li>
                <li className="flex gap-2"><span className="text-slate-300">3.</span>Use &quot;Show Translation →&quot; if you need help with the passage</li>
                <li className="flex gap-2"><span className="text-slate-300">4.</span>Review every answer in the end-of-set summary</li>
              </ul>
            </CardContent>
          </Card>
        )}
      </div>
    </TcfAppShell>
  );
}
