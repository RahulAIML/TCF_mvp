"use client";

import { useEffect, useRef, useState } from "react";
import TcfAppShell from "@/components/TcfAppShell";
import ExamContainer from "@/components/ExamContainer";
import TcfExamResults from "@/components/TcfExamResults";
import TcfQuestionCard from "@/components/TcfQuestionCard";
import QuestionNavigator from "@/components/QuestionNavigator";
import TextHelperTool from "@/components/TextHelperTool";
import TextExplanationCard from "@/components/TextExplanationCard";
import TimerClock from "@/components/TimerClock";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { explainText, generateTcfQuestion, submitTcfExam, translatePassage } from "@/services/api";
import type { AnswerOption } from "@/types/exam";
import type { TcfExamQuestion, TcfSubmitExamResponse } from "@/types/tcf-exam";
import type { ExplainTextResponse } from "@/types/text-helper";

const EXAM_DURATION_SECONDS = 60 * 60;
const PREFETCH_AHEAD = 5;

type DifficultyGroup = "all" | "c1_c2" | "b1_b2" | "a1_a2";
const DIFFICULTY_RANGES: Record<DifficultyGroup, { start: number; end: number; label: string }> = {
  all:    { start: 1,  end: 39, label: "All Levels (C2 → A2)" },
  c1_c2:  { start: 1,  end: 20, label: "C1–C2 (Questions 1–20)" },
  b1_b2:  { start: 21, end: 30, label: "B1–B2 (Questions 21–30)" },
  a1_a2:  { start: 31, end: 39, label: "A1–A2 (Questions 31–39)" },
};

const partLabel = (questionNumber: number) => {
  if (questionNumber <= 10) return "Part 1 - C2";
  if (questionNumber <= 20) return "Part 2 - B2-C1";
  if (questionNumber <= 30) return "Part 3 - B1-B2";
  return "Part 4 - A2";
};

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

  const questionsRef = useRef<Record<number, TcfExamQuestion>>({});
  const inFlightRef = useRef<Partial<Record<number, Promise<TcfExamQuestion>>>>({});
  const examSessionIdRef = useRef<string | null>(null);

  useEffect(() => {
    questionsRef.current = questions;
  }, [questions]);

  const ensureQuestion = async (questionNumber: number, showLoader = true) => {
    const existing = questionsRef.current[questionNumber];
    if (existing) {
      return existing;
    }
    const inFlight = inFlightRef.current[questionNumber];
    if (inFlight) {
      if (showLoader) {
        setLoadingQuestion(true);
      }
      const shouldResumeTimer = showLoader && timerActive;
      if (shouldResumeTimer) {
        setTimerActive(false);
      }
      try {
        return await inFlight;
      } finally {
        if (showLoader) {
          setLoadingQuestion(false);
        }
        if (shouldResumeTimer && !timeUp && !results) {
          setTimerActive(true);
        }
      }
    }

    if (showLoader) {
      setLoadingQuestion(true);
    }
    const shouldResumeTimer = showLoader && timerActive;
    if (shouldResumeTimer) {
      setTimerActive(false);
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
      }
      if (shouldResumeTimer && !timeUp && !results) {
        setTimerActive(true);
      }
    }
  };

  const prefetchQuestions = (fromQuestion: number) => {
    if (!isExamStarted || timeUp || results) {
      return;
    }
    for (let offset = 1; offset <= PREFETCH_AHEAD; offset += 1) {
      const questionNumber = fromQuestion + offset;
      if (questionNumber > TOTAL_QUESTIONS) {
        break;
      }
      if (questionsRef.current[questionNumber]) {
        continue;
      }
      if (inFlightRef.current[questionNumber]) {
        continue;
      }
      void ensureQuestion(questionNumber, false).catch(() => undefined);
    }
  };

  const handleStartExam = async () => {
    if (isExamStarted) return;
    setIsExamStarted(true);
    const startQ = DIFFICULTY_RANGES[difficultyGroup].start;
    setCurrentQuestion(startQ);
    const sessionId = typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    examSessionIdRef.current = sessionId;
    setTimeUp(false);
    setError("");
    setSubmitNote("");
    try {
      await ensureQuestion(startQ);
      prefetchQuestions(startQ);
      setStartedAt(new Date().toISOString());
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
    setCurrentQuestion(questionNumber);
    if (!questionsRef.current[questionNumber]) {
      try {
        await ensureQuestion(questionNumber);
        prefetchQuestions(questionNumber);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load question.");
      }
      return;
    }
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
    void handleSubmitExam();
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
      const questionList = Object.values(questionsRef.current)
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

    const questionList = Object.values(questionsRef.current)
      .sort((a, b) => a.question_number - b.question_number)
      .map((question) => ({
        question_number: question.question_number,
        correct_answer: question.correct_answer,
        question_type: question.question_type,
        explanation: question.explanation
      }));

    if (questionList.length < TOTAL_QUESTIONS) {
      const note =
        `Partial submission: ${questionList.length} of ${TOTAL_QUESTIONS} questions generated. ` +
        "Score is based only on generated questions.";
      setSubmitNote(note);
      setConfirmPartial(true);
      return;
    }

    await submitExamNow();
  };

  const currentQuestionData = questions[currentQuestion];
  const currentAnswer = answers[currentQuestion] ?? "";

  const diffRange = DIFFICULTY_RANGES[difficultyGroup];
  const TOTAL_QUESTIONS = diffRange.end - diffRange.start + 1;

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
      // silent
    } finally {
      setIsTranslating(false);
    }
  };

  return (
    <TcfAppShell title="Reading Mock Exam" subtitle="Complete the full reading mock exam">
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
                  {DIFFICULTY_RANGES[difficultyGroup].end - DIFFICULTY_RANGES[difficultyGroup].start + 1} questions · 60 minutes
                </p>
              </div>
              <Button onClick={handleStartExam}>Start Exam</Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <ExamContainer
              currentQuestion={currentQuestion}
              totalQuestions={TOTAL_QUESTIONS}
              title="TCF Reading Mock Exam"
              timer={
                <TimerClock
                  durationSeconds={EXAM_DURATION_SECONDS}
                  isActive={timerActive}
                  resetKey={timerKey}
                  onExpire={handleTimerExpire}
                />
              }
            >
              <div className="flex items-center gap-2 text-xs font-medium text-emerald-700">
                <span className="rounded-full bg-emerald-50 px-2.5 py-1">{partLabel(currentQuestion)}</span>
              </div>
              {timeUp && (
                <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  Time is up. Your exam has been submitted.
                </div>
              )}
              {submitNote && (
                <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                  {submitNote}
                </div>
              )}
              {error && (
                <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {error}
                </div>
              )}
              {loadingQuestion && (
                <p className="text-sm text-slate-500">Generating question...</p>
              )}
              {currentQuestionData && (
                <div onMouseUp={handleTextSelection} className="mx-auto w-full max-w-3xl space-y-3">
                  {/* Passage with translation toggle */}
                  <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-5">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-semibold uppercase text-slate-400">Passage</span>
                      <button
                        onClick={() => void handleTranslatePassage()}
                        disabled={isTranslating}
                        className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-indigo-600 hover:bg-indigo-50 transition disabled:opacity-50"
                      >
                        {isTranslating ? "Translating..." : showTranslation && translations[currentQuestion] ? "Hide Translation" : "Show Translation"}
                      </button>
                    </div>
                    <div className={showTranslation && translations[currentQuestion] ? "grid grid-cols-2 gap-4" : ""}>
                      <p className="text-[1.02rem] leading-7 text-slate-800">{currentQuestionData.text}</p>
                      {showTranslation && translations[currentQuestion] && (
                        <div className="border-l border-indigo-100 pl-4">
                          <p className="text-[10px] font-semibold uppercase text-indigo-400 mb-1">English Translation</p>
                          <p className="text-sm leading-7 text-slate-600">{translations[currentQuestion]}</p>
                        </div>
                      )}
                    </div>
                  </div>
                  {/* Question & options (without passage — passed separately) */}
                  <div>
                    <h3 className="text-base font-semibold text-slate-900 mb-3">{currentQuestionData.question}</h3>
                    <div className="space-y-2">
                      {currentQuestionData.options.map((option, index) => {
                        const value = (["A", "B", "C", "D"][index] as AnswerOption) ?? "A";
                        const isSelected = currentAnswer === value;
                        return (
                          <label
                            key={`${currentQuestion}-opt-${index}`}
                            className={`flex cursor-pointer items-start gap-3 rounded-xl border px-4 py-3 text-sm transition ${
                              isSelected
                                ? "border-emerald-600 bg-emerald-600 text-white"
                                : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"
                            } ${(Boolean(results) || timeUp) ? "cursor-not-allowed opacity-70" : ""}`}
                          >
                            <input
                              type="radio"
                              name={`question-${currentQuestion}`}
                              value={value}
                              checked={isSelected}
                              disabled={Boolean(results) || timeUp}
                              onChange={() => handleAnswerSelect(value)}
                              className="mt-1"
                            />
                            <span>{option}</span>
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
                  disabled={currentQuestion === diffRange.start}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => handleSelectQuestion(Math.min(diffRange.end, currentQuestion + 1))}
                  disabled={currentQuestion === diffRange.end}
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
                currentQuestion={currentQuestion}
                answers={answers}
                onSelect={handleSelectQuestion}
              />
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

        {results && (
          <div className="space-y-4">
            <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              Exam submitted successfully.
            </div>
            <TcfExamResults results={results} questions={questions} />
          </div>
        )}
      </div>
    </TcfAppShell>
  );
}
