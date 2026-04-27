"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import TcfAppShell from "@/components/TcfAppShell";
import ExamContainer from "@/components/ExamContainer";
import ListeningQuestionCard from "@/components/ListeningQuestionCard";
import ListeningResults from "@/components/ListeningResults";
import QuestionNavigator from "@/components/QuestionNavigator";
import TextHelperTool from "@/components/TextHelperTool";
import TextExplanationCard from "@/components/TextExplanationCard";
import TimerClock from "@/components/TimerClock";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  generateTcfListeningQuestion,
  submitTcfListeningExam,
  explainText,
  translatePassage
} from "@/services/api";
import type { AnswerOption } from "@/types/exam";
import type { ExplainTextResponse } from "@/types/text-helper";
import type { ListeningQuestion, ListeningSubmitResult } from "@/types/listening";

const TOTAL_QUESTIONS = 39;
const EXAM_DURATION_SECONDS = 35 * 60;
const PREFETCH_AHEAD = 1;
const MAX_PLAYS = 1;

type ListeningDifficultyGroup = "all" | "c2" | "c1" | "b2" | "b1" | "a2" | "a1";
const LISTENING_DIFFICULTY_RANGES: Record<ListeningDifficultyGroup, { start: number; end: number; label: string }> = {
  all: { start: 1,  end: 39, label: "All Levels" },
  c2:  { start: 1,  end: 10, label: "C2" },
  c1:  { start: 11, end: 20, label: "C1" },
  b2:  { start: 11, end: 20, label: "B2" },
  b1:  { start: 21, end: 30, label: "B1" },
  a2:  { start: 31, end: 39, label: "A2" },
  a1:  { start: 31, end: 39, label: "A1" },
};

type PracticeLevel = "C2" | "C1" | "B2" | "B1" | "A2" | "A1";
const PRACTICE_LEVEL_RANGES: Record<PracticeLevel, [number, number]> = {
  "C2": [1,  10],
  "C1": [11, 20],
  "B2": [11, 20],
  "B1": [21, 30],
  "A2": [31, 39],
  "A1": [31, 39],
};

const levelLabel = (questionNumber: number) => {
  if (questionNumber <= 10) return "C2";
  if (questionNumber <= 20) return "B2-C1";
  if (questionNumber <= 30) return "B1-B2";
  return "A2-B1";
};

export default function ListeningExamPage() {
  const [mode, setMode] = useState<"practice" | "exam">("exam");
  const [showTranscript, setShowTranscript] = useState(false);

  const [isExamStarted, setIsExamStarted] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState(1);
  const [questions, setQuestions] = useState<Record<number, ListeningQuestion>>({});
  const [answers, setAnswers] = useState<Record<number, AnswerOption | "">>({});
  const [playCounts, setPlayCounts] = useState<Record<number, number>>({});
  const [loadingQuestion, setLoadingQuestion] = useState(false);
  const [error, setError] = useState("");
  const [submitNote, setSubmitNote] = useState("");
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const [timerKey, setTimerKey] = useState(0);
  const [timerActive, setTimerActive] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [results, setResults] = useState<ListeningSubmitResult | null>(null);
  const [timeUp, setTimeUp] = useState(false);
  const [confirmPartial, setConfirmPartial] = useState(false);

  const [practiceQuestion, setPracticeQuestion] = useState<ListeningQuestion | null>(null);
  const [practiceAnswer, setPracticeAnswer] = useState<AnswerOption | "">("");
  const [practiceCount, setPracticeCount] = useState(1);
  const [practicePlayCount, setPracticePlayCount] = useState(0);

  const [helperText, setHelperText] = useState("");
  const [helperResult, setHelperResult] = useState<ExplainTextResponse | null>(null);
  const [helperLoading, setHelperLoading] = useState(false);

  // Difficulty + translation state
  const [examDifficulty, setExamDifficulty] = useState<ListeningDifficultyGroup>("all");
  const [practiceLevel, setPracticeLevel] = useState<PracticeLevel>("B1");
  const [transcriptTranslations, setTranscriptTranslations] = useState<Record<string, string>>({});
  const [showTranslation, setShowTranslation] = useState(false);
  const [isTranslating, setIsTranslating] = useState(false);

  const questionsRef = useRef<Record<number, ListeningQuestion>>({});
  const inFlightRef = useRef<Partial<Record<number, Promise<ListeningQuestion>>>>({});
  const examSessionIdRef = useRef<string | null>(null);
  const practiceSessionIdRef = useRef<string | null>(null);

  useEffect(() => {
    questionsRef.current = questions;
  }, [questions]);

  useEffect(() => {
    if (mode === "practice") {
      setShowTranscript(true);
    } else {
      setShowTranscript(false);
    }
  }, [mode]);

  useEffect(() => {
    if (mode === "practice") {
      setIsExamStarted(false);
      setResults(null);
      setTimeUp(false);
      setTimerActive(false);
      setSubmitNote("");
      setError("");
    } else {
      setPracticeQuestion(null);
      setPracticeAnswer("");
    }
  }, [mode]);

  const ensureQuestion = async (questionNumber: number, showLoader = true) => {
    const existing = questionsRef.current[questionNumber];
    if (existing) {
      return existing;
    }
    const inFlight = inFlightRef.current[questionNumber];
    if (inFlight) {
      if (showLoader) setLoadingQuestion(true);
      const shouldResumeTimer = showLoader && timerActive;
      if (shouldResumeTimer) setTimerActive(false);
      try {
        return await inFlight;
      } finally {
        if (showLoader) setLoadingQuestion(false);
        if (shouldResumeTimer && !timeUp && !results) setTimerActive(true);
      }
    }

    if (showLoader) setLoadingQuestion(true);
    const shouldResumeTimer = showLoader && timerActive;
    if (shouldResumeTimer) setTimerActive(false);
    try {
      const request = generateTcfListeningQuestion({
        question_number: questionNumber,
        session_id: examSessionIdRef.current ?? undefined,
        defer_audio: false
      }).then((question) => {
        const normalizedQuestion: ListeningQuestion = {
          ...question,
          transcript: question.transcript ?? question.script,
          user_answer: question.user_answer ?? ""
        };
        const updated = { ...questionsRef.current, [questionNumber]: normalizedQuestion };
        questionsRef.current = updated;
        setQuestions(updated);
        return normalizedQuestion;
      });
      inFlightRef.current[questionNumber] = request;
      return await request;
    } finally {
      delete inFlightRef.current[questionNumber];
      if (showLoader) setLoadingQuestion(false);
      if (shouldResumeTimer && !timeUp && !results) setTimerActive(true);
    }
  };

  const prefetchQuestions = (fromQuestion: number) => {
    if (!isExamStarted || timeUp || results) return;
    for (let offset = 1; offset <= PREFETCH_AHEAD; offset += 1) {
      const questionNumber = fromQuestion + offset;
      if (questionNumber > TOTAL_QUESTIONS) break;
      if (questionsRef.current[questionNumber]) continue;
      if (inFlightRef.current[questionNumber]) continue;
      void ensureQuestion(questionNumber, false).catch(() => undefined);
    }
  };

  const handleStartExam = async () => {
    if (isExamStarted) return;
    setIsExamStarted(true);
    const startQ = LISTENING_DIFFICULTY_RANGES[examDifficulty].start;
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
    setShowTranslation(false);
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
    if (results || timeUp) return;
    setAnswers((prev) => ({ ...prev, [currentQuestion]: value }));
    setQuestions((prev) => {
      const existing = prev[currentQuestion];
      if (!existing) return prev;
      const updatedQuestion: ListeningQuestion = { ...existing, user_answer: value };
      const updated = { ...prev, [currentQuestion]: updatedQuestion };
      questionsRef.current = updated;
      return updated;
    });
  };

  const handleTimerExpire = () => {
    if (timeUp || results) return;
    setTimeUp(true);
    void handleSubmitExam();
  };

  const submitExamNow = async () => {
    if (isSubmitting || results) return;
    if (!startedAt) {
      setError("Exam has not started.");
      return;
    }
    setIsSubmitting(true);
    setError("");
    setSubmitNote("");
    setTimerActive(false);

    try {
      const questionList = Object.entries(questionsRef.current)
        .map(([num, question]) => ({ number: Number(num), question }))
        .sort((a, b) => a.number - b.number);

      let correct = 0;
      const detailed = questionList.map(({ number, question }) => {
        const userAnswer = question.user_answer ?? answers[number] ?? "";
        const isCorrect = userAnswer === question.correct_answer;
        if (isCorrect) correct += 1;
        return {
          question_number: number,
          question: question.question,
          options: question.options,
          correct_answer: question.correct_answer,
          user_answer: userAnswer,
          is_correct: isCorrect,
          explanation: question.explanation,
          audio_url: question.audio_url ?? null,
          transcript: question.transcript ?? question.script
        };
      });

      const total = questionList.length;
      const attempted = questionList.filter(({ number, question }) =>
        (question.user_answer ?? answers[number] ?? "") !== ""
      ).length;
      const accuracy = attempted ? (correct / attempted) * 100 : 0;

      const payload: ListeningSubmitResult = {
        score: correct,
        total,
        attempted,
        accuracy,
        results: detailed
      };
      setResults(payload);
      const completedAt = new Date().toISOString();
      void submitTcfListeningExam({
        started_at: startedAt,
        completed_at: completedAt,
        score: correct,
        total,
        accuracy
      }).catch(() => undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit exam.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmitExam = async () => {
    if (isSubmitting || results) return;
    if (!startedAt) {
      setError("Exam has not started.");
      return;
    }

    const questionList = Object.entries(questionsRef.current)
      .map(([num, question]) => ({ number: Number(num), question }))
      .sort((a, b) => a.number - b.number);

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

  const handlePlay = (questionNumber: number) => {
    setPlayCounts((prev) => {
      const current = prev[questionNumber] ?? 0;
      if (current >= MAX_PLAYS) return prev;
      return { ...prev, [questionNumber]: current + 1 };
    });
  };

  const loadPracticeQuestion = async () => {
    const sessionId = practiceSessionIdRef.current
      ?? (typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(16).slice(2)}`);
    practiceSessionIdRef.current = sessionId;

    setError("");
    setLoadingQuestion(true);
    setShowTranslation(false);
    try {
      // Pick a random question number from the selected practice level range
      const [minQ, maxQ] = PRACTICE_LEVEL_RANGES[practiceLevel];
      const qNum = Math.floor(Math.random() * (maxQ - minQ + 1)) + minQ;
      const question = await generateTcfListeningQuestion({
        question_number: qNum,
        session_id: sessionId ?? undefined,
        defer_audio: false
      });
      const normalizedQuestion: ListeningQuestion = {
        ...question,
        transcript: question.transcript ?? question.script,
        user_answer: ""
      };
      setPracticeQuestion(normalizedQuestion);
      setPracticeAnswer("");
      setPracticePlayCount(0);
      setPracticeCount((prev) => prev + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load practice question.");
    } finally {
      setLoadingQuestion(false);
    }
  };

  const handlePracticePlay = () => {
    setPracticePlayCount((prev) => (prev >= MAX_PLAYS ? prev : prev + 1));
  };

  const handlePracticeAnswer = (value: AnswerOption) => {
    setPracticeAnswer(value);
  };

  const handleExplainText = async () => {
    if (!helperText.trim()) return;
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

  const handleTranscriptSelection = (text: string) => {
    setHelperText(text);
  };

  const handleTranslateTranscript = async (script: string, key: string) => {
    if (transcriptTranslations[key]) {
      setShowTranslation((p) => !p);
      return;
    }
    setIsTranslating(true);
    try {
      const result = await translatePassage(script);
      setTranscriptTranslations((prev) => ({ ...prev, [key]: result }));
      setShowTranslation(true);
    } catch {
      // silent
    } finally {
      setIsTranslating(false);
    }
  };

  const currentQuestionData = questions[currentQuestion];
  const currentAnswer = answers[currentQuestion] ?? "";
  const currentPlays = playCounts[currentQuestion] ?? 0;

  const questionNavigatorAnswers = useMemo(() => answers, [answers]);

  return (
    <TcfAppShell title="Listening Module" subtitle="Practice or take a full TCF listening mock exam">
      <div className="space-y-6">
        {/* Mode toggle */}
        <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 gap-0.5 w-fit">
          {(["practice", "exam"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`rounded-md px-4 py-1.5 text-sm font-medium capitalize transition-all duration-150 ${
                mode === m
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {m === "practice" ? "Practice" : "Mock Exam"}
            </button>
          ))}
        </div>

        {mode === "practice" && (
          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <div className="space-y-4">
              {/* Level selector */}
              <Card className="border-slate-200 shadow-sm rounded-2xl">
                <CardContent className="p-4">
                  <p className="text-sm font-semibold text-slate-700 mb-2">CEFR Level</p>
                  <div className="flex flex-wrap gap-2">
                    {(Object.keys(PRACTICE_LEVEL_RANGES) as PracticeLevel[]).map((lvl) => (
                      <button
                        key={lvl}
                        onClick={() => { setPracticeLevel(lvl); setPracticeQuestion(null); setPracticeCount(1); }}
                        disabled={loadingQuestion}
                        className={`rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
                          practiceLevel === lvl
                            ? "bg-indigo-600 text-white"
                            : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                        } disabled:opacity-50`}
                      >
                        {lvl}
                      </button>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {!practiceQuestion ? (
                <Card className="border-slate-200 shadow-sm rounded-2xl">
                  <CardContent className="p-6">
                    <h2 className="text-xl font-semibold text-slate-900">Listening Practice</h2>
                    <p className="mt-2 text-sm text-slate-600">
                      Practice one question at a time. Level: <strong>{practiceLevel}</strong>. Transcript is enabled by default.
                    </p>
                    <Button className="mt-4" onClick={loadPracticeQuestion} disabled={loadingQuestion}>
                      {loadingQuestion ? "Preparing audio..." : "Start Practice"}
                    </Button>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  {loadingQuestion && (
                    <p className="text-sm text-slate-500">Preparing practice audio...</p>
                  )}
                  <div className="flex items-center gap-2">
                    <span className="rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-700">
                      {practiceLevel}
                    </span>
                  </div>
                  <ListeningQuestionCard
                    question={practiceQuestion}
                    questionNumber={practiceCount - 1}
                    selectedAnswer={practiceAnswer}
                    onSelect={handlePracticeAnswer}
                    maxPlays={MAX_PLAYS}
                    playCount={practicePlayCount}
                    onPlay={handlePracticePlay}
                    showTranscript={showTranscript}
                    onToggleTranscript={() => setShowTranscript((prev) => !prev)}
                    onTranscriptSelect={handleTranscriptSelection}
                    translationText={transcriptTranslations[`practice-${practiceCount}`]}
                    onTranslate={() => void handleTranslateTranscript(practiceQuestion.script, `practice-${practiceCount}`)}
                    isTranslating={isTranslating}
                    showTranslation={showTranslation}
                    replayPlays={true}
                  />
                  {practiceAnswer && (
                    <Card className={`rounded-2xl shadow-sm ${practiceAnswer === practiceQuestion.correct_answer ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50"}`}>
                      <CardContent className="p-5 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className={`text-sm font-bold ${practiceAnswer === practiceQuestion.correct_answer ? "text-emerald-700" : "text-rose-700"}`}>
                            {practiceAnswer === practiceQuestion.correct_answer ? "✓ Correct!" : "✗ Incorrect"}
                          </span>
                          <span className="text-sm text-slate-600">
                            Answer: <span className="font-semibold text-slate-900">{practiceQuestion.correct_answer}</span>
                          </span>
                        </div>
                        {practiceQuestion.explanation && (
                          <div className="rounded-xl bg-white/70 px-4 py-3">
                            <p className="text-xs font-semibold uppercase text-slate-400 mb-1">Explanation</p>
                            <p className="text-sm text-slate-700">{practiceQuestion.explanation}</p>
                          </div>
                        )}
                        <Button onClick={loadPracticeQuestion}>
                          Next Question
                        </Button>
                      </CardContent>
                    </Card>
                  )}
                </div>
              )}
            </div>
            <div className="space-y-4">
              <Card className="border-slate-200 shadow-sm rounded-2xl">
                <CardContent className="p-4 space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Practice Tips</p>
                  <ul className="space-y-1.5 text-xs text-slate-500">
                    <li className="flex gap-2"><span className="text-slate-300">•</span>Audio plays once per question</li>
                    <li className="flex gap-2"><span className="text-slate-300">•</span>Transcript is shown below the audio controls</li>
                    <li className="flex gap-2"><span className="text-slate-300">•</span>Use the translation toggle inside the transcript</li>
                    <li className="flex gap-2"><span className="text-slate-300">•</span>Select transcript text → Phrase Helper auto-fills</li>
                  </ul>
                </CardContent>
              </Card>
              <Card className="border-slate-200 shadow-sm rounded-2xl">
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

        {mode === "exam" && (
          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <ExamContainer
              currentQuestion={currentQuestion}
              totalQuestions={TOTAL_QUESTIONS}
              title="TCF Listening Mock Exam"
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
                <span className="rounded-full bg-emerald-50 px-2.5 py-1">
                  {examDifficulty === "all" ? levelLabel(currentQuestion) : LISTENING_DIFFICULTY_RANGES[examDifficulty].label}
                </span>
                <span className="text-slate-500">Audio plays only once.</span>
              </div>
              {!isExamStarted ? (
                <Card className="border-slate-200 shadow-sm rounded-2xl">
                  <CardContent className="p-6 space-y-4">
                    <div>
                      <h2 className="text-xl font-semibold text-slate-900">Listening Mock Exam</h2>
                      <p className="mt-1 text-sm text-slate-600">
                        35 minutes · Transcript off by default · Transcript translation available
                      </p>
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-700 mb-2">Difficulty Focus</p>
                      <div className="flex flex-wrap gap-2">
                        {(Object.entries(LISTENING_DIFFICULTY_RANGES) as [ListeningDifficultyGroup, typeof LISTENING_DIFFICULTY_RANGES[ListeningDifficultyGroup]][]).map(([key, val]) => (
                          <button
                            key={key}
                            onClick={() => setExamDifficulty(key)}
                            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                              examDifficulty === key
                                ? "bg-slate-800 text-white"
                                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                            }`}
                          >
                            {val.label}
                          </button>
                        ))}
                      </div>
                    </div>
                    <Button onClick={handleStartExam}>Start Exam</Button>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  {timeUp && (
                    <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                      Time is up. Your exam has been submitted.
                    </div>
                  )}
                  {submitNote && (
                    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                      {submitNote}
                    </div>
                  )}
                  {error && (
                    <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                      {error}
                    </div>
                  )}
                  {loadingQuestion && (
                    <p className="text-sm text-slate-500">Generating question...</p>
                  )}
                  {currentQuestionData && (
                    <ListeningQuestionCard
                      question={currentQuestionData}
                      questionNumber={currentQuestion}
                      selectedAnswer={currentAnswer}
                      onSelect={handleAnswerSelect}
                      disabled={Boolean(results) || timeUp}
                      maxPlays={MAX_PLAYS}
                      playCount={currentPlays}
                      onPlay={() => handlePlay(currentQuestion)}
                      showTranscript={showTranscript}
                      onToggleTranscript={() => setShowTranscript((prev) => !prev)}
                      onTranscriptSelect={handleTranscriptSelection}
                      translationText={transcriptTranslations[`exam-${currentQuestion}`]}
                      onTranslate={() => void handleTranslateTranscript(currentQuestionData.script, `exam-${currentQuestion}`)}
                      isTranslating={isTranslating}
                      showTranslation={showTranslation}
                    />
                  )}
                  <div className="flex flex-wrap items-center gap-3">
                    <Button
                      variant="secondary"
                      onClick={() => handleSelectQuestion(Math.max(LISTENING_DIFFICULTY_RANGES[examDifficulty].start, currentQuestion - 1))}
                      disabled={currentQuestion === LISTENING_DIFFICULTY_RANGES[examDifficulty].start}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => handleSelectQuestion(Math.min(LISTENING_DIFFICULTY_RANGES[examDifficulty].end, currentQuestion + 1))}
                      disabled={currentQuestion === LISTENING_DIFFICULTY_RANGES[examDifficulty].end}
                    >
                      Next
                    </Button>
                    <Button onClick={handleSubmitExam} disabled={isSubmitting || Boolean(results)}>
                      {isSubmitting ? "Submitting..." : "Submit Exam"}
                    </Button>
                  </div>
                </div>
              )}
            </ExamContainer>

            <div className="space-y-4">
              <QuestionNavigator
                totalQuestions={TOTAL_QUESTIONS}
                currentQuestion={currentQuestion}
                answers={questionNavigatorAnswers}
                onSelect={handleSelectQuestion}
              />
              <Card className="border-slate-200 shadow-sm rounded-2xl">
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
          <ListeningResults
            score={results.score}
            total={results.total}
            attempted={results.attempted}
            accuracy={results.accuracy}
            results={results.results}
          />
        )}
      </div>
    </TcfAppShell>
  );
}
