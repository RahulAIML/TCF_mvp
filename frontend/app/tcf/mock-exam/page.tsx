"use client";

import { useEffect, useRef, useState } from "react";
import TcfAppShell from "@/components/TcfAppShell";
import ExamContainer from "@/components/ExamContainer";
import TcfExamResults from "@/components/TcfExamResults";
import QuestionNavigator from "@/components/QuestionNavigator";
import TextHelperTool from "@/components/TextHelperTool";
import TextExplanationCard from "@/components/TextExplanationCard";
import TimerClock from "@/components/TimerClock";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { explainText, generateTcfQuestion, submitTcfExam, translatePassage } from "@/services/api";
import type { AnswerOption } from "@/types/exam";
import {
  READING_LEVELS,
  READING_LEVEL_RANGES,
  readingLevelForQuestion,
  type TcfExamQuestion,
  type TcfSubmitExamResponse
} from "@/types/tcf-exam";
import type { ExplainTextResponse } from "@/types/text-helper";
import ExamResumeDialog from "@/components/ExamResumeDialog";
import {
  saveExamProgress,
  loadExamProgress,
  clearExamProgress,
  hasRecentProgress,
  type ReadingProgressState,
} from "@/lib/exam-progress";

const EXAM_DURATION_SECONDS = 60 * 60;
const PREFETCH_AHEAD = 4;

type DifficultyGroup = "all" | "A1" | "A2" | "B1" | "B2" | "C1" | "C2";
const DIFFICULTY_RANGES: Record<DifficultyGroup, { start: number; end: number; label: string }> = {
  all: { start: 1, end: 39, label: "All Levels" },
  ...(Object.fromEntries(
    READING_LEVELS.map((level) => [level, { ...READING_LEVEL_RANGES[level], label: level }])
  ) as Record<Exclude<DifficultyGroup, "all">, { start: number; end: number; label: string }>),
};

const isDifficultyGroup = (value: unknown): value is DifficultyGroup =>
  typeof value === "string" && value in DIFFICULTY_RANGES;

const levelLabel = (questionNumber: number) => `Q${questionNumber} · Level ${readingLevelForQuestion(questionNumber)}`;

export default function MockExamPage() {
  const [isExamStarted, setIsExamStarted] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState(1);
  const [questions, setQuestions] = useState<Record<number, TcfExamQuestion>>({});
  const [answers, setAnswers] = useState<Record<number, AnswerOption | "">>({});
  const [loadingQuestion, setLoadingQuestion] = useState(false);
  const [error, setError] = useState("");
  const [submitNote, setSubmitNote] = useState("");
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const [timerKey, setTimerKey] = useState(0);
  const [timerActive, setTimerActive] = useState(false);
  // Questions currently loading with a visible loader: the clock pauses only while this is > 0.
  const [loadingPauses, setLoadingPauses] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [results, setResults] = useState<TcfSubmitExamResponse | null>(null);
  const [timeUp, setTimeUp] = useState(false);
  const [helperText, setHelperText] = useState("");
  const [helperResult, setHelperResult] = useState<ExplainTextResponse | null>(null);
  const [helperLoading, setHelperLoading] = useState(false);
  const [confirmPartial, setConfirmPartial] = useState(false);
  const [difficultyGroup, setDifficultyGroup] = useState<DifficultyGroup>("all");
  const [translations, setTranslations] = useState<Record<number, string>>({});
  const [showTranslation, setShowTranslation] = useState(false);
  const [isTranslating, setIsTranslating] = useState(false);

  const [showResumeDialog, setShowResumeDialog] = useState(false);
  const [resumeSavedAt, setResumeSavedAt] = useState(0);
  const [timerDuration, setTimerDuration] = useState(EXAM_DURATION_SECONDS);

  const questionsRef = useRef<Record<number, TcfExamQuestion>>({});
  const visitedRef = useRef<Set<number>>(new Set());
  const remainingRef = useRef(EXAM_DURATION_SECONDS);

  const diffRange = DIFFICULTY_RANGES[difficultyGroup];
  const TOTAL_QUESTIONS = diffRange.end - diffRange.start + 1;

  const inFlightRef = useRef<Partial<Record<number, Promise<TcfExamQuestion>>>>({});
  const examSessionIdRef = useRef<string | null>(null);

  useEffect(() => {
    questionsRef.current = questions;
  }, [questions]);

  useEffect(() => {
    if (isExamStarted) visitedRef.current.add(currentQuestion);
  }, [isExamStarted, currentQuestion]);

  // Check for saved progress on mount
  useEffect(() => {
    if (hasRecentProgress("reading")) {
      const record = loadExamProgress<ReadingProgressState>("reading");
      if (record) {
        setResumeSavedAt(record.savedAt);
        setShowResumeDialog(true);
      }
    }
  }, []);

  // Auto-save progress every 10 seconds during exam
  useEffect(() => {
    if (!isExamStarted || results || timeUp) return;
    const interval = setInterval(() => {
      saveExamProgress<ReadingProgressState>("reading", {
        currentQuestion,
        answers: answers as Record<number, string>,
        sessionId: examSessionIdRef.current,
        timeRemaining: remainingRef.current,
        difficultyGroup,
        startedAt,
      });
    }, 10_000);
    return () => clearInterval(interval);
  }, [isExamStarted, results, timeUp, currentQuestion, answers, difficultyGroup, startedAt]);

  const ensureQuestion = async (questionNumber: number, showLoader = true) => {
    const existing = questionsRef.current[questionNumber];
    if (existing) {
      return existing;
    }
    const inFlight = inFlightRef.current[questionNumber];
    if (inFlight) {
      if (showLoader) {
        setLoadingQuestion(true);
        setLoadingPauses((count) => count + 1);
      }
      try {
        return await inFlight;
      } finally {
        if (showLoader) {
          setLoadingQuestion(false);
          setLoadingPauses((count) => Math.max(0, count - 1));
        }
      }
    }

    if (showLoader) {
      setLoadingQuestion(true);
      setLoadingPauses((count) => count + 1);
    }
    try {
      const request = generateTcfQuestion({
        question_number: questionNumber,
        session_id: examSessionIdRef.current ?? undefined
      }).then((question) => {
        const updated = { ...questionsRef.current, [questionNumber]: question };
        questionsRef.current = updated;
        setQuestions(updated);
        return question;
      });
      inFlightRef.current[questionNumber] = request;
      return await request;
    } finally {
      delete inFlightRef.current[questionNumber];
      if (showLoader) {
        setLoadingQuestion(false);
        setLoadingPauses((count) => Math.max(0, count - 1));
      }
    }
  };

  const prefetchQuestions = (fromQuestion: number, endQuestion?: number) => {
    // Use ref instead of state so this works inside async closures
    if (!examSessionIdRef.current || timeUp || results) {
      return;
    }
    const cap = endQuestion ?? diffRange.end;
    for (let offset = 1; offset <= PREFETCH_AHEAD; offset += 1) {
      const questionNumber = fromQuestion + offset;
      if (questionNumber > cap) break;
      if (questionsRef.current[questionNumber]) continue;
      if (inFlightRef.current[questionNumber]) continue;
      void ensureQuestion(questionNumber, false).catch(() => undefined);
    }
  };

  const handleResumeExam = () => {
    const record = loadExamProgress<ReadingProgressState>("reading");
    if (!record) { setShowResumeDialog(false); return; }
    const { state } = record;
    const group = isDifficultyGroup(state.difficultyGroup) ? state.difficultyGroup : "all";
    const range = DIFFICULTY_RANGES[group];
    const remaining = typeof state.timeRemaining === "number" && state.timeRemaining > 0
      ? state.timeRemaining
      : EXAM_DURATION_SECONDS;
    setDifficultyGroup(group);
    setCurrentQuestion(state.currentQuestion);
    setAnswers(state.answers as Record<number, AnswerOption | "">);
    examSessionIdRef.current = state.sessionId;
    setIsExamStarted(true);
    setStartedAt(state.startedAt ?? new Date().toISOString());
    remainingRef.current = remaining;
    setTimerDuration(remaining);
    setTimerKey((p) => p + 1);
    setTimerActive(true);
    setShowResumeDialog(false);
    setError("");
    void ensureQuestion(state.currentQuestion)
      .then(() => prefetchQuestions(state.currentQuestion, range.end))
      .catch(() => setError("Could not load this question. Please try again."));
  };

  const handleStartNew = () => {
    clearExamProgress("reading");
    setShowResumeDialog(false);
  };

  const handleStartExam = async () => {
    if (isExamStarted) return;
    clearExamProgress("reading");
    setIsExamStarted(true);
    const startQ = DIFFICULTY_RANGES[difficultyGroup].start;
    setCurrentQuestion(startQ);
    visitedRef.current = new Set([startQ]);
    const sessionId = typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    examSessionIdRef.current = sessionId;
    setTimeUp(false);
    setError("");
    setSubmitNote("");
    try {
      // Kick off the next questions immediately — in parallel with the first one
      prefetchQuestions(startQ, DIFFICULTY_RANGES[difficultyGroup].end);
      await ensureQuestion(startQ);
      setStartedAt(new Date().toISOString());
      remainingRef.current = EXAM_DURATION_SECONDS;
      setTimerDuration(EXAM_DURATION_SECONDS);
      setTimerKey((prev) => prev + 1);
      setTimerActive(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate question.");
      setIsExamStarted(false);
    }
  };

  const handleSelectQuestion = async (questionNumber: number) => {
    if (results || timeUp) {
      return;
    }
    if (questionNumber < diffRange.start || questionNumber > diffRange.end) {
      return;
    }
    setCurrentQuestion(questionNumber);
    setShowTranslation(false);
    if (!questionsRef.current[questionNumber]) {
      try {
        await ensureQuestion(questionNumber);
        setError("");
        prefetchQuestions(questionNumber);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load question.");
      }
      return;
    }
    setError("");
    prefetchQuestions(questionNumber);
  };

  const handleAnswerSelect = (value: AnswerOption) => {
    if (results || timeUp) {
      return;
    }
    setAnswers((prev) => ({ ...prev, [currentQuestion]: value }));
  };

  const normalizeSelection = (rawSelection: string) => rawSelection.replace(/\s+/g, " ").trim();

  const handleExplainText = async () => {
    if (!helperText.trim()) {
      return;
    }
    setHelperLoading(true);
    setError("");
    try {
      const result = await explainText({ text: helperText.trim() });
      setHelperResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to explain text.");
    } finally {
      setHelperLoading(false);
    }
  };

  const handleTextSelection = () => {
    const selection = window.getSelection()?.toString() ?? "";
    const chosenText = normalizeSelection(selection);
    if (chosenText) {
      setHelperText(chosenText);
    }
  };

  const handleTimerExpire = () => {
    if (timeUp || results) {
      return;
    }
    setTimeUp(true);
    // Time is over: submit what exists right away (no partial-submission dialog).
    void submitExamNow();
  };

  const submitExamNow = async () => {
    if (isSubmitting || results) {
      return;
    }
    if (!startedAt) {
      setError("Exam has not started.");
      return;
    }
    setIsSubmitting(true);
    setError("");
    setSubmitNote("");
    setTimerActive(false);
    try {
      const completedAt = new Date().toISOString();
      const questionList = [...visitedRef.current]
        .map((number) => questionsRef.current[number])
        .filter((question): question is TcfExamQuestion => Boolean(question))
        .sort((a, b) => a.question_number - b.question_number)
        .map((question) => ({
          question_number: question.question_number,
          correct_answer: question.correct_answer,
          question_type: question.question_type,
          explanation: question.explanation
        }));

      const response = await submitTcfExam({
        started_at: startedAt,
        completed_at: completedAt,
        answers,
        questions: questionList
      });
      setResults(response);
      clearExamProgress("reading");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit exam.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmitExam = async () => {
    if (isSubmitting || results) {
      return;
    }
    if (!startedAt) {
      setError("Exam has not started.");
      return;
    }

    const opened = visitedRef.current.size;
    const inExam = diffRange.end - diffRange.start + 1;
    if (opened < inExam) {
      const note =
        `You opened ${opened} of ${inExam} questions. Your score uses only those questions.`;
      setSubmitNote(note);
      setConfirmPartial(true);
      return;
    }

    await submitExamNow();
  };

  const currentQuestionData = questions[currentQuestion];
  const currentAnswer = answers[currentQuestion] ?? "";

  const handleTranslatePassage = async () => {
    if (!currentQuestionData) return;
    const qn = currentQuestion;
    if (translations[qn]) {
      setShowTranslation((p) => !p);
      return;
    }
    setIsTranslating(true);
    try {
      const result = await translatePassage(currentQuestionData.text);
      setTranslations((prev) => ({ ...prev, [qn]: result }));
      setShowTranslation(true);
    } catch {
      setError("Translation failed. Please try again.");
    } finally {
      setIsTranslating(false);
    }
  };

  return (
    <TcfAppShell title="Reading Mock Exam" subtitle="Complete the full reading mock exam">
      {showResumeDialog && (
        <ExamResumeDialog
          moduleName="Reading Exam"
          savedAt={resumeSavedAt}
          onResume={handleResumeExam}
          onStartNew={handleStartNew}
        />
      )}
      <div className="space-y-6">
        {!isExamStarted ? (
          <Card className="border-slate-200 shadow-sm">
            <CardContent className="p-6 space-y-5">
              <div>
                <h2 className="text-2xl font-semibold text-slate-900">Reading Mock Exam</h2>
                <p className="mt-2 text-sm text-slate-600">
                  Questions are generated dynamically. A translation toggle is available during the exam.
                </p>
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-700 mb-2">Difficulty Focus</p>
                <div className="flex flex-wrap gap-2">
                  {(Object.entries(DIFFICULTY_RANGES) as [DifficultyGroup, typeof DIFFICULTY_RANGES[DifficultyGroup]][]).map(([key, val]) => (
                    <button
                      key={key}
                      onClick={() => setDifficultyGroup(key)}
                      className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                        difficultyGroup === key
                          ? "bg-slate-800 text-white"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      {val.label}
                    </button>
                  ))}
                </div>
                <p className="mt-2 text-xs text-slate-500">
                  {TOTAL_QUESTIONS} questions (Q{diffRange.start}–Q{diffRange.end}) · 60 minutes
                </p>
              </div>
              {error && (
                <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {error}
                </div>
              )}
              <Button onClick={handleStartExam} disabled={isExamStarted}>
                {isExamStarted ? "Preparing exam…" : "Start Exam"}
              </Button>
            </CardContent>
          </Card>
        ) : results ? (
          <TcfExamResults results={results} questions={questions} />
        ) : (
          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <ExamContainer
              currentQuestion={currentQuestion}
              totalQuestions={TOTAL_QUESTIONS}
              startQuestion={diffRange.start}
              title="TCF Reading Mock Exam"
              timer={
                <TimerClock
                  durationSeconds={timerDuration}
                  isActive={timerActive && !loadingQuestion}
                  holdLabel={
                    !timerActive
                      ? "Starts when the first question is ready"
                      : loadingQuestion
                        ? "Paused while loading"
                        : undefined
                  }
                  resetKey={timerKey}
                  onExpire={handleTimerExpire}
                  onTick={(seconds) => {
                    remainingRef.current = seconds;
                  }}
                />
              }
            >
              <div className="flex items-center gap-2 text-xs font-medium text-emerald-700">
                <span className="rounded-full bg-emerald-50 px-2.5 py-1">{levelLabel(currentQuestion)}</span>
              </div>
              {timeUp && (
                <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {results
                    ? "Time is up. Your exam has been submitted."
                    : isSubmitting
                      ? "Time is up. Submitting your exam…"
                      : "Time is up. Your exam could not be submitted yet."}
                </div>
              )}
              {error && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  <span>{error}</span>
                  {timeUp && !results ? (
                    <Button size="sm" variant="secondary" onClick={() => void submitExamNow()} disabled={isSubmitting}>
                      Retry submission
                    </Button>
                  ) : !currentQuestionData && !loadingQuestion ? (
                    <Button size="sm" variant="secondary" onClick={() => void handleSelectQuestion(currentQuestion)}>
                      Retry
                    </Button>
                  ) : null}
                </div>
              )}
              {loadingQuestion && (
                <Card className="border-slate-200 shadow-sm rounded-2xl animate-pulse">
                  <CardContent className="p-6 space-y-4">
                    <div className="h-4 w-3/4 rounded bg-slate-200" />
                    <div className="h-3 w-full rounded bg-slate-100" />
                    <div className="h-3 w-5/6 rounded bg-slate-100" />
                    <div className="grid grid-cols-2 gap-3 pt-2">
                      {[1, 2, 3, 4].map((i) => (
                        <div key={i} className="h-10 rounded-xl bg-slate-100" />
                      ))}
                    </div>
                    <p className="text-xs text-slate-400 pt-1 flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-indigo-400 animate-ping inline-block" />
                      Generating question…
                    </p>
                  </CardContent>
                </Card>
              )}
              {currentQuestionData && (
                <div onMouseUp={handleTextSelection} className="mx-auto w-full max-w-3xl space-y-3">
                  {/* Passage — French text only; translation appears in the right panel */}
                  <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-5">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-semibold uppercase text-slate-400">Passage (French)</span>
                      <button
                        onClick={() => void handleTranslatePassage()}
                        disabled={isTranslating}
                        className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-indigo-600 hover:bg-indigo-50 transition-all duration-150 disabled:opacity-50"
                      >
                        {isTranslating ? (
                          <><span className="h-3 w-3 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin" />Translating…</>
                        ) : showTranslation && translations[currentQuestion] ? "Hide Translation →" : "Show Translation →"}
                      </button>
                    </div>
                    <p className="text-[1.02rem] leading-7 text-slate-800">{currentQuestionData.text}</p>
                  </div>
                  {/* Question & options (without passage — passed separately) */}
                  <div>
                    <h3 className="text-base font-semibold text-slate-900 mb-3">{currentQuestionData.question}</h3>
                    <div className="space-y-2">
                      {currentQuestionData.options.map((option, index) => {
                        const value = (["A", "B", "C", "D"][index] as AnswerOption) ?? "A";
                        const isSelected = currentAnswer === value;
                        const isDisabled = Boolean(results) || timeUp;
                        return (
                          <label
                            key={`${currentQuestion}-opt-${index}`}
                            className={`group flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-3 text-sm transition-all duration-150 ${
                              isSelected
                                ? "border-indigo-600 bg-indigo-600 text-white shadow-sm"
                                : "border-slate-200 bg-white text-slate-700 hover:border-indigo-200 hover:bg-indigo-50"
                            } ${isDisabled ? "cursor-not-allowed opacity-70" : ""}`}
                          >
                            <input
                              type="radio"
                              name={`question-${currentQuestion}`}
                              value={value}
                              checked={isSelected}
                              disabled={isDisabled}
                              onChange={() => handleAnswerSelect(value)}
                              className="sr-only"
                            />
                            <span className={`flex-shrink-0 h-6 w-6 rounded-md text-xs font-bold flex items-center justify-center transition-colors ${
                              isSelected ? "bg-white/20 text-white" : "bg-slate-100 text-slate-600 group-hover:bg-indigo-100 group-hover:text-indigo-700"
                            }`}>
                              {value}
                            </span>
                            <span className="mt-0.5">{option.replace(/^[A-D]\.\s*/, "")}</span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  variant="secondary"
                  onClick={() => handleSelectQuestion(Math.max(diffRange.start, currentQuestion - 1))}
                  disabled={currentQuestion === diffRange.start || loadingQuestion}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => handleSelectQuestion(Math.min(diffRange.end, currentQuestion + 1))}
                  disabled={currentQuestion === diffRange.end || loadingQuestion}
                >
                  Next
                </Button>
                <Button onClick={handleSubmitExam} disabled={isSubmitting || Boolean(results)}>
                  {isSubmitting ? "Submitting..." : "Submit Exam"}
                </Button>
              </div>
            </ExamContainer>

            <div className="space-y-4">
              <QuestionNavigator
                totalQuestions={TOTAL_QUESTIONS}
                startQuestion={diffRange.start}
                currentQuestion={currentQuestion}
                answers={answers}
                onSelect={handleSelectQuestion}
              />

              {/* Translation panel — right side only */}
              {showTranslation && translations[currentQuestion] && (
                <Card className="border-indigo-200 bg-indigo-50 shadow-sm">
                  <CardContent className="p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="text-[10px] font-semibold uppercase tracking-wide text-indigo-500">English Translation</p>
                      <button
                        onClick={() => setShowTranslation(false)}
                        className="text-xs text-indigo-400 hover:text-indigo-600"
                      >
                        ✕ Hide
                      </button>
                    </div>
                    <p className="text-sm leading-6 text-slate-700">{translations[currentQuestion]}</p>
                  </CardContent>
                </Card>
              )}

              <Card className="border-slate-200 shadow-sm">
                <CardContent className="p-5">
                  <TextHelperTool
                    text={helperText}
                    onTextChange={setHelperText}
                    onExplain={handleExplainText}
                    isLoading={helperLoading}
                  />
                </CardContent>
              </Card>
              {helperResult && <TextExplanationCard entry={helperResult} />}
            </div>
          </div>
        )}

        {confirmPartial && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
            <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-slate-900">Partial submission confirmation</h3>
              <p className="mt-2 text-sm text-slate-600">{submitNote}</p>
              <div className="mt-4 flex justify-end gap-3">
                <Button variant="secondary" onClick={() => setConfirmPartial(false)}>Cancel</Button>
                <Button onClick={() => { setConfirmPartial(false); void submitExamNow(); }}>Submit anyway</Button>
              </div>
            </div>
          </div>
        )}

      </div>
    </TcfAppShell>
  );
}
