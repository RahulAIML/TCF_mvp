"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { SLOW_MESSAGE, useSlow } from "@/lib/slow-load";
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
  API_BASE_URL,
  friendlyNetworkError,
  generateTcfListeningQuestion,
  generateTcfListeningAudio,
  submitTcfListeningExam,
  explainText,
  translatePassage
} from "@/services/api";
import type { AnswerOption } from "@/types/exam";
import type { ExplainTextResponse } from "@/types/text-helper";
import type { ListeningQuestion, ListeningSubmitResult } from "@/types/listening";

const FULL_EXAM_QUESTIONS = 39;
const FULL_EXAM_SECONDS = 35 * 60;
const EXAM_PREFETCH_AHEAD = 4;
const PRACTICE_QUEUE_SIZE = 4;
const MAX_PLAYS = 1;

const LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"] as const;
type Level = (typeof LEVELS)[number];

// Official TCF Canada order: easiest first. Question number -> CEFR band.
const LEVEL_RANGES: Record<Level, [number, number]> = {
  A1: [1, 4],
  A2: [5, 10],
  B1: [11, 19],
  B2: [20, 29],
  C1: [30, 35],
  C2: [36, 39],
};

const levelForQuestion = (questionNumber: number): Level =>
  LEVELS.find((lvl) => questionNumber >= LEVEL_RANGES[lvl][0] && questionNumber <= LEVEL_RANGES[lvl][1]) ?? "C2";

type ExamFocus = "all" | Level;

const examRange = (focus: ExamFocus): [number, number] => (focus === "all" ? [1, FULL_EXAM_QUESTIONS] : LEVEL_RANGES[focus]);

// A focused exam keeps the real exam's pace: about 54 s per item, never under 5 minutes.
const examDurationSeconds = (focus: ExamFocus) => {
  if (focus === "all") return FULL_EXAM_SECONDS;
  const [start, end] = examRange(focus);
  return Math.max(5 * 60, Math.round((FULL_EXAM_SECONDS * (end - start + 1)) / FULL_EXAM_QUESTIONS / 60) * 60);
};

const newSessionId = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const resolveAudioUrl = (url: string) => (url.startsWith("http") ? url : `${API_BASE_URL}${url}`);

const questionKey = (q: ListeningQuestion) => q.question_id || q.script;

const errorMessage = (err: unknown, fallback: string) => {
  const e = friendlyNetworkError(err);
  return e.message || fallback;
};

interface QueuedQuestion {
  level: Level;
  promise: Promise<ListeningQuestion>;
  settled: boolean;
  value?: ListeningQuestion;
  failed: boolean;
}

export default function ListeningExamPage() {
  const [mode, setMode] = useState<"practice" | "exam">("practice");
  const [showTranscript, setShowTranscript] = useState(false);

  // Exam state is indexed by position in the exam (1..examSize); positions map to real TCF question numbers.
  const [isExamStarted, setIsExamStarted] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState(1);
  const [questions, setQuestions] = useState<Record<number, ListeningQuestion>>({});
  const [answers, setAnswers] = useState<Record<number, AnswerOption | "">>({});
  const [playCounts, setPlayCounts] = useState<Record<number, number>>({});
  const [loadingQuestion, setLoadingQuestion] = useState(false);
  const questionSlow = useSlow(loadingQuestion);
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
  const [practiceScore, setPracticeScore] = useState({ correct: 0, total: 0 });

  const [helperText, setHelperText] = useState("");
  const [helperResult, setHelperResult] = useState<ExplainTextResponse | null>(null);
  const [helperLoading, setHelperLoading] = useState(false);

  const [examFocus, setExamFocus] = useState<ExamFocus>("all");
  const [practiceLevel, setPracticeLevel] = useState<Level>("A1");
  const [transcriptTranslations, setTranscriptTranslations] = useState<Record<string, string>>({});
  const [showTranslation, setShowTranslation] = useState(false);
  const [isTranslating, setIsTranslating] = useState(false);
  const [translationError, setTranslationError] = useState("");

  const [pendingPracticeLevel, setPendingPracticeLevel] = useState<Level | null>(null);
  const [audioUrls, setAudioUrls] = useState<Record<string, string>>({});
  const [audioBusy, setAudioBusy] = useState(false);

  const questionsRef = useRef<Record<number, ListeningQuestion>>({});
  const inFlightRef = useRef<Partial<Record<number, Promise<ListeningQuestion>>>>({});
  const examSessionIdRef = useRef<string | null>(null);
  const practiceSessionIdRef = useRef<string | null>(null);
  const practiceQueueRef = useRef<QueuedQuestion[]>([]);
  const practiceSeenRef = useRef<Set<string>>(new Set());
  const practiceLevelRef = useRef<Level>(practiceLevel);
  const audioCacheRef = useRef<Record<string, Promise<string | undefined>>>({});
  const warmAudioRef = useRef<Map<string, HTMLAudioElement>>(new Map());
  const visitedRef = useRef<Set<number>>(new Set());

  const [examStart, examEnd] = examRange(examFocus);
  const examSize = examEnd - examStart + 1;
  const realNumber = (position: number) => examStart + position - 1;

  useEffect(() => {
    questionsRef.current = questions;
  }, [questions]);

  useEffect(() => {
    practiceLevelRef.current = practiceLevel;
  }, [practiceLevel]);

  useEffect(() => {
    setShowTranscript(false);
  }, [mode]);

  // The first render is always Practice so the server and the browser match.
  // Reading ?mode= happens after that, and the URL must not be rewritten to Practice
  // before that read has been applied.
  const skipModeWrite = useRef(true);
  useEffect(() => {
    const urlMode = new URLSearchParams(window.location.search).get("mode");
    if (urlMode === "practice" || urlMode === "exam") setMode(urlMode);
  }, []);

  useEffect(() => {
    if (skipModeWrite.current) {
      skipModeWrite.current = false;
      return;
    }
    const params = new URLSearchParams(window.location.search);
    params.set("mode", mode);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, [mode]);

  useEffect(() => {
    setError("");
    if (mode === "practice") {
      setIsExamStarted(false);
      setResults(null);
      setTimeUp(false);
      setTimerActive(false);
      setSubmitNote("");
    } else {
      setPracticeQuestion(null);
      setPracticeAnswer("");
    }
  }, [mode]);

  // Exam integrity: the transcript stays closed when moving between exam questions.
  useEffect(() => {
    if (mode === "exam") setShowTranscript(false);
  }, [currentQuestion, mode]);

  useEffect(() => {
    if (mode === "exam" && isExamStarted) visitedRef.current.add(currentQuestion);
  }, [mode, isExamStarted, currentQuestion]);

  // ── Audio: requested as soon as a question exists, then pre-buffered by the browser ──────────────

  const warmAudio = (url: string) => {
    const resolved = resolveAudioUrl(url);
    const cache = warmAudioRef.current;
    if (cache.has(resolved) || typeof Audio === "undefined") return;
    const el = new Audio();
    el.preload = "auto";
    el.src = resolved;
    el.load();
    cache.set(resolved, el);
    if (cache.size > 12) {
      const oldest = cache.keys().next().value;
      if (oldest) cache.delete(oldest);
    }
  };

  const fetchAudio = (question: ListeningQuestion): Promise<string | undefined> => {
    if (question.audio_url) {
      warmAudio(question.audio_url);
      return Promise.resolve(question.audio_url);
    }
    const cache = audioCacheRef.current;
    const key = question.script;
    if (!cache[key]) {
      cache[key] = generateTcfListeningAudio({ script: question.script, speakers: question.speakers ?? [] })
        .then((res) => {
          const url = res.audio_url || undefined;
          if (url) {
            setAudioUrls((prev) => ({ ...prev, [key]: url }));
            warmAudio(url);
          }
          return url;
        })
        .catch(() => {
          delete cache[key];
          return undefined;
        });
    }
    return cache[key];
  };

  const handleRequestAudio = (question: ListeningQuestion): Promise<string | undefined> =>
    question.script ? fetchAudio(question) : Promise.resolve(undefined);

  const withAudio = (q: ListeningQuestion | null | undefined): ListeningQuestion | null =>
    q ? (q.audio_url || !audioUrls[q.script] ? q : { ...q, audio_url: audioUrls[q.script] }) : null;

  // ── Exam ─────────────────────────────────────────────────────────────────────────────────────────

  const ensureQuestion = async (position: number, showLoader = true, withAudio = true) => {
    const existing = questionsRef.current[position];
    if (existing) return existing;

    const resumeTimer = showLoader && timerActive;
    if (showLoader) setLoadingQuestion(true);
    if (resumeTimer) setTimerActive(false);
    try {
      let request = inFlightRef.current[position];
      if (!request) {
        const number = realNumber(position);
        request = generateTcfListeningQuestion({
          question_number: number,
          session_id: examSessionIdRef.current ?? undefined,
          defer_audio: true,
          target_level: examFocus === "all" ? levelForQuestion(number) : examFocus,
        }).then((question) => {
          const normalized: ListeningQuestion = {
            ...question,
            transcript: question.transcript ?? question.script,
            user_answer: question.user_answer ?? ""
          };
          const updated = { ...questionsRef.current, [position]: normalized };
          questionsRef.current = updated;
          setQuestions(updated);
          if (withAudio) void fetchAudio(normalized);
          return normalized;
        });
        inFlightRef.current[position] = request;
        request.finally(() => {
          delete inFlightRef.current[position];
        }).catch(() => undefined);
      }
      return await request;
    } finally {
      if (showLoader) setLoadingQuestion(false);
      if (resumeTimer && !timeUp && !results) setTimerActive(true);
    }
  };

  const prefetchQuestions = (fromPosition: number) => {
    if (timeUp || results) return;
    for (let offset = 1; offset <= EXAM_PREFETCH_AHEAD; offset += 1) {
      const position = fromPosition + offset;
      if (position > examSize) break;
      if (questionsRef.current[position] || inFlightRef.current[position]) continue;
      // Only the next item fetches audio. The rest wait, so five clips are not synthesized at once.
      void ensureQuestion(position, false, offset === 1).catch(() => undefined);
    }
  };

  const handleStartExam = async () => {
    if (isExamStarted) return;
    examSessionIdRef.current = newSessionId();
    questionsRef.current = {};
    inFlightRef.current = {};
    setQuestions({});
    setAnswers({});
    setPlayCounts({});
    visitedRef.current = new Set([1]);
    setResults(null);
    setIsExamStarted(true);
    setCurrentQuestion(1);
    setTimeUp(false);
    setError("");
    setSubmitNote("");
    // Load the first questions in parallel; the timer starts once the first one is on screen.
    prefetchQuestions(1);
    try {
      await ensureQuestion(1);
      setStartedAt(new Date().toISOString());
      setTimerKey((prev) => prev + 1);
      setTimerActive(true);
    } catch (err) {
      setError(errorMessage(err, "Failed to generate question."));
      setIsExamStarted(false);
    }
  };

  const handleSelectQuestion = async (position: number) => {
    if (results || timeUp) return;
    if (position < 1 || position > examSize) return;
    setCurrentQuestion(position);
    setShowTranslation(false);
    setError("");
    prefetchQuestions(position);
    if (!questionsRef.current[position]) {
      try {
        await ensureQuestion(position);
      } catch (err) {
        setError(errorMessage(err, "Failed to load question."));
      }
    }
  };

  const handleAnswerSelect = (value: AnswerOption) => {
    if (results || timeUp) return;
    setAnswers((prev) => ({ ...prev, [currentQuestion]: value }));
    setQuestions((prev) => {
      const existing = prev[currentQuestion];
      if (!existing) return prev;
      const updated = { ...prev, [currentQuestion]: { ...existing, user_answer: value } };
      questionsRef.current = updated;
      return updated;
    });
  };

  const submitExamNow = async () => {
    if (isSubmitting || results) return;
    if (!startedAt) {
      setError("Exam has not started.");
      return;
    }
    setIsSubmitting(true);
    setError("");
    setTimerActive(false);

    try {
      const questionList = [...visitedRef.current]
        .filter((position) => questionsRef.current[position])
        .sort((a, b) => a - b)
        .map((position) => ({ position, question: questionsRef.current[position] }));

      let correct = 0;
      const detailed = questionList.map(({ position, question }) => {
        const userAnswer = question.user_answer ?? answers[position] ?? "";
        const isCorrect = userAnswer === question.correct_answer;
        if (isCorrect) correct += 1;
        return {
          question_number: realNumber(position),
          question: question.question,
          options: question.options,
          correct_answer: question.correct_answer,
          user_answer: userAnswer,
          is_correct: isCorrect,
          explanation: question.explanation,
          audio_url: question.audio_url ?? audioUrls[question.script] ?? null,
          transcript: question.transcript ?? question.script
        };
      });

      const total = questionList.length;
      const attempted = questionList.filter(({ position, question }) =>
        (question.user_answer ?? answers[position] ?? "") !== ""
      ).length;
      const accuracy = attempted ? (correct / attempted) * 100 : 0;

      setResults({ score: correct, total, attempted, accuracy, results: detailed });
      void submitTcfListeningExam({
        started_at: startedAt,
        completed_at: new Date().toISOString(),
        score: correct,
        total,
        accuracy
      }).catch(() => undefined);
    } catch (err) {
      setError(errorMessage(err, "Failed to submit exam."));
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
    const opened = visitedRef.current.size;
    if (opened < examSize) {
      setSubmitNote(
        `You opened ${opened} of ${examSize} questions. Your score uses only those questions.`
      );
      setConfirmPartial(true);
      return;
    }
    await submitExamNow();
  };

  // When time runs out the exam is submitted as it stands: no confirmation dialog.
  const handleTimerExpire = () => {
    if (timeUp || results) return;
    setTimeUp(true);
    setConfirmPartial(false);
    void submitExamNow();
  };

  const handlePlay = (position: number) => {
    setPlayCounts((prev) => {
      const current = prev[position] ?? 0;
      if (current >= MAX_PLAYS) return prev;
      return { ...prev, [position]: current + 1 };
    });
  };

  // ── Practice: a queue of ready questions for the current level ──────────────────────────────────

  const practiceSession = () => {
    if (!practiceSessionIdRef.current) practiceSessionIdRef.current = newSessionId();
    return practiceSessionIdRef.current;
  };

  const fetchPracticeQuestion = (level: Level): Promise<ListeningQuestion> => {
    const [minQ, maxQ] = LEVEL_RANGES[level];
    const qNum = Math.floor(Math.random() * (maxQ - minQ + 1)) + minQ;
    return generateTcfListeningQuestion({
      question_number: qNum,
      session_id: practiceSession(),
      defer_audio: true,
      target_level: level,
    }).then((question) => ({
      ...question,
      transcript: question.transcript ?? question.script,
      user_answer: ""
    }));
  };

  const enqueuePractice = (level: Level) => {
    const entry: QueuedQuestion = { level, settled: false, failed: false, promise: Promise.resolve(null as never) };
    entry.promise = fetchPracticeQuestion(level).then(
      (q) => {
        entry.settled = true;
        entry.value = q;
        void fetchAudio(q);
        return q;
      },
      (err) => {
        entry.settled = true;
        entry.failed = true;
        throw err;
      }
    );
    entry.promise.catch(() => undefined);
    practiceQueueRef.current.push(entry);
  };

  const prunePracticeQueue = (level: Level) => {
    practiceQueueRef.current = practiceQueueRef.current.filter(
      (e) => e.level === level && !e.failed && !(e.value && practiceSeenRef.current.has(questionKey(e.value)))
    );
  };

  const topUpPracticeQueue = (level: Level) => {
    prunePracticeQueue(level);
    while (practiceQueueRef.current.length < PRACTICE_QUEUE_SIZE) enqueuePractice(level);
  };

  const takePracticeQuestion = async (level: Level): Promise<ListeningQuestion> => {
    if (!practiceQueueRef.current.some((e) => e.level === level)) topUpPracticeQueue(level);
    for (;;) {
      prunePracticeQueue(level);
      const ready = practiceQueueRef.current.find((e) => e.value);
      if (ready?.value) {
        practiceQueueRef.current = practiceQueueRef.current.filter((e) => e !== ready);
        return ready.value;
      }
      const pending = practiceQueueRef.current.filter((e) => !e.settled);
      if (!pending.length) break;
      await Promise.race(pending.map((e) => e.promise.then(() => undefined, () => undefined)));
    }
    // Every queued request failed: one direct attempt, whose error is shown with a Retry button.
    return fetchPracticeQuestion(level);
  };

  // Keep questions ready for the selected level as soon as practice is open.
  // The first render is practice even when the URL says exam, so read the URL before starting audio.
  useEffect(() => {
    const urlMode = new URLSearchParams(window.location.search).get("mode");
    if (urlMode === "exam" || mode !== "practice") return;
    topUpPracticeQueue(practiceLevel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, practiceLevel]);

  const practiceLoadLock = useRef(false);
  const loadPracticeQuestion = async () => {
    if (practiceLoadLock.current) return;
    practiceLoadLock.current = true;
    const level = practiceLevel;
    setError("");
    setLoadingQuestion(true);
    setShowTranslation(false);
    setTranslationError("");
    setShowTranscript(false);
    try {
      const question = await takePracticeQuestion(level);
      if (practiceLevelRef.current !== level) return;
      practiceSeenRef.current.add(questionKey(question));
      setPracticeQuestion(question);
      setPracticeAnswer("");
      setPracticeCount((prev) => prev + 1);
      topUpPracticeQueue(level);
    } catch (err) {
      setError(errorMessage(err, "Failed to load practice question."));
    } finally {
      practiceLoadLock.current = false;
      setLoadingQuestion(false);
    }
  };

  const applyPracticeLevel = (lvl: Level) => {
    practiceQueueRef.current = [];
    setPracticeLevel(lvl);
    setPracticeQuestion(null);
    setPracticeAnswer("");
    setPracticeCount(1);
    setPracticeScore({ correct: 0, total: 0 });
    setError("");
  };

  const handlePracticeAnswer = (value: AnswerOption) => {
    if (practiceAnswer) return;
    setPracticeAnswer(value);
    if (practiceQuestion) {
      setPracticeScore((prev) => ({
        correct: prev.correct + (value === practiceQuestion.correct_answer ? 1 : 0),
        total: prev.total + 1,
      }));
    }
  };

  // ── Helpers ──────────────────────────────────────────────────────────────────────────────────────

  const handleExplainText = async () => {
    if (!helperText.trim()) return;
    setHelperLoading(true);
    setError("");
    try {
      const result = await explainText({ text: helperText.trim() });
      setHelperResult(result);
    } catch (err) {
      setError(errorMessage(err, "Failed to explain text."));
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
    setTranslationError("");
    try {
      const result = await translatePassage(script);
      setTranscriptTranslations((prev) => ({ ...prev, [key]: result }));
      setShowTranslation(true);
    } catch {
      setTranslationError("The translation is not available right now. Please try again.");
    } finally {
      setIsTranslating(false);
    }
  };

  const currentQuestionData = withAudio(questions[currentQuestion]);
  const displayedPracticeQuestion = withAudio(practiceQuestion);
  const currentAnswer = answers[currentQuestion] ?? "";
  const currentPlays = playCounts[currentQuestion] ?? 0;
  const practiceHasProgress = Boolean(practiceQuestion) || loadingQuestion || practiceScore.total > 0;

  const questionNavigatorAnswers = useMemo(() => answers, [answers]);

  return (
    <TcfAppShell title="Listening Module" subtitle="Practice or take a full TCF listening mock exam">
      <div className="space-y-6">
        {/* Mode toggle */}
        <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 gap-0.5 w-fit">
          {(["practice", "exam"] as const).map((m) => (
            // Real links: a click before hydration still lands on the right mode (no lost first click).
            <a
              key={m}
              href={`?mode=${m}`}
              role="tab"
              aria-selected={mode === m}
              onClick={(e) => {
                e.preventDefault();
                setMode(m);
              }}
              className={`rounded-md px-4 py-1.5 text-sm font-medium capitalize transition-all duration-150 ${
                mode === m
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {m === "practice" ? "Practice" : "Mock Exam"}
            </a>
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
                    {LEVELS.map((lvl) => (
                      <button
                        key={lvl}
                        onClick={() => {
                          if (lvl === practiceLevel) return;
                          if (practiceHasProgress) {
                            setPendingPracticeLevel(lvl);
                          } else {
                            applyPracticeLevel(lvl);
                          }
                        }}
                        className={`rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
                          practiceLevel === lvl
                            ? "bg-indigo-600 text-white"
                            : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                        }`}
                      >
                        {lvl}
                      </button>
                    ))}
                    {pendingPracticeLevel && (
                      <div className="w-full mt-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 flex flex-wrap items-center gap-3">
                        <span>
                          Switch to <strong>{pendingPracticeLevel}</strong>? The current question and your score
                          ({practiceScore.correct}/{practiceScore.total}) will be reset.
                        </span>
                        <button
                          className="font-semibold text-amber-900 underline"
                          onClick={() => {
                            const lvl = pendingPracticeLevel;
                            setPendingPracticeLevel(null);
                            applyPracticeLevel(lvl);
                          }}
                        >Confirm</button>
                        <button
                          className="font-semibold text-amber-700 underline"
                          onClick={() => setPendingPracticeLevel(null)}
                        >Cancel</button>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>

              {error && (
                <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  <span>{error}</span>
                  <Button size="sm" variant="outline" onClick={() => void loadPracticeQuestion()} disabled={loadingQuestion}>
                    Retry
                  </Button>
                </div>
              )}

              {!displayedPracticeQuestion ? (
                <Card className="border-slate-200 shadow-sm rounded-2xl">
                  <CardContent className="p-6">
                    <h2 className="text-xl font-semibold text-slate-900">Listening Practice</h2>
                    <p className="mt-2 text-sm text-slate-600">
                      Practice one question at a time. Level: <strong>{practiceLevel}</strong>. The transcript is
                      hidden until you choose to show it.
                    </p>
                    <Button className="mt-4" onClick={() => { practiceLoadLock.current = false; setLoadingQuestion(false); void loadPracticeQuestion(); }} disabled={loadingQuestion && !questionSlow}>
                      {loadingQuestion && !questionSlow ? "Loading question…" : questionSlow ? "Retry" : "Start Practice"}
                    </Button>
                    {questionSlow && (
                      <p className="mt-3 text-sm text-slate-600" role="alert">{SLOW_MESSAGE}</p>
                    )}
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <span className="rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-700">
                      {practiceLevel}
                    </span>
                    <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
                      Score: {practiceScore.correct}/{practiceScore.total}
                    </span>
                  </div>
                  <ListeningQuestionCard
                    key={questionKey(displayedPracticeQuestion)}
                    question={displayedPracticeQuestion}
                    questionNumber={practiceCount - 1}
                    selectedAnswer={practiceAnswer}
                    onSelect={handlePracticeAnswer}
                    onRequestAudio={handleRequestAudio}
                    showTranscript={showTranscript}
                    onToggleTranscript={() => setShowTranscript((prev) => !prev)}
                    onTranscriptSelect={handleTranscriptSelection}
                    translationText={transcriptTranslations[`practice-${practiceCount}`]}
                    onTranslate={() => void handleTranslateTranscript(displayedPracticeQuestion.script, `practice-${practiceCount}`)}
                    isTranslating={isTranslating}
                    showTranslation={showTranslation}
                    replayPlays={true}
                  />
                  {translationError && <p className="text-xs text-rose-600">{translationError}</p>}
                  {practiceAnswer && (
                    <Card className={`rounded-2xl shadow-sm ${practiceAnswer === displayedPracticeQuestion.correct_answer ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50"}`}>
                      <CardContent className="p-5 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className={`text-sm font-bold ${practiceAnswer === displayedPracticeQuestion.correct_answer ? "text-emerald-700" : "text-rose-700"}`}>
                            {practiceAnswer === displayedPracticeQuestion.correct_answer ? "✓ Correct!" : "✗ Incorrect"}
                          </span>
                          <span className="text-sm text-slate-600">
                            Answer: <span className="font-semibold text-slate-900">{displayedPracticeQuestion.correct_answer}</span>
                          </span>
                        </div>
                        {displayedPracticeQuestion.explanation && (
                          <div className="rounded-xl bg-white/70 px-4 py-3">
                            <p className="text-xs font-semibold uppercase text-slate-400 mb-1">Explanation</p>
                            <p className="text-sm text-slate-700">{displayedPracticeQuestion.explanation}</p>
                          </div>
                        )}
                        <Button onClick={() => void loadPracticeQuestion()} disabled={loadingQuestion}>
                          {loadingQuestion ? "Loading…" : "Next Question"}
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
                    <li className="flex gap-2"><span className="text-slate-300">•</span>Listen as many times as you need</li>
                    <li className="flex gap-2"><span className="text-slate-300">•</span>Try to answer before opening the transcript</li>
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

        {mode === "exam" && results && (
          <ListeningResults
            score={results.score}
            total={results.total}
            attempted={results.attempted}
            accuracy={results.accuracy}
            results={results.results}
          />
        )}

        {mode === "exam" && !results && (
          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <ExamContainer
              currentQuestion={currentQuestion}
              totalQuestions={examSize}
              title={examFocus === "all" ? "TCF Listening Mock Exam" : `TCF Listening Mock Exam · ${examFocus} focus`}
              timer={
                <TimerClock
                  durationSeconds={examDurationSeconds(examFocus)}
                  isActive={timerActive && !loadingQuestion && !audioBusy}
                  resetKey={timerKey}
                  onExpire={handleTimerExpire}
                  holdLabel={
                    !isExamStarted
                      ? undefined
                      : !timerActive
                        ? "Starts when the first question is ready"
                        : loadingQuestion || audioBusy
                          ? "Paused while loading"
                          : undefined
                  }
                />
              }
            >
              <div className="flex items-center gap-2 text-xs font-medium text-emerald-700">
                <span className="rounded-full bg-emerald-50 px-2.5 py-1">
                  {levelForQuestion(realNumber(currentQuestion))}
                </span>
                <span className="text-slate-500">Each recording plays only once.</span>
              </div>
              {!isExamStarted ? (
                <Card className="border-slate-200 shadow-sm rounded-2xl">
                  <CardContent className="p-6 space-y-4">
                    <div>
                      <h2 className="text-xl font-semibold text-slate-900">Listening Mock Exam</h2>
                      <p className="mt-1 text-sm text-slate-600">
                        {examSize} questions · {Math.round(examDurationSeconds(examFocus) / 60)} minutes · each
                        recording plays once · transcripts are shown with your results
                      </p>
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-700 mb-2">Difficulty Focus</p>
                      <div className="flex flex-wrap gap-2">
                        {(["all", ...LEVELS] as ExamFocus[]).map((key) => (
                          <button
                            key={key}
                            onClick={() => setExamFocus(key)}
                            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                              examFocus === key
                                ? "bg-slate-800 text-white"
                                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                            }`}
                          >
                            {key === "all" ? "All Levels" : key}
                          </button>
                        ))}
                      </div>
                    </div>
                    {error && (
                      <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                        {error}
                      </div>
                    )}
                    <Button onClick={() => void handleStartExam()}>Start Exam</Button>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  {timeUp && (
                    <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                      Time is up. Your exam has been submitted.
                    </div>
                  )}
                  {error && (
                    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                      <span>{error}</span>
                      {!questions[currentQuestion] && (
                        <Button size="sm" variant="outline" onClick={() => void handleSelectQuestion(currentQuestion)}>
                          Retry
                        </Button>
                      )}
                    </div>
                  )}
                  {loadingQuestion && !currentQuestionData && (
                    <Card className="border-slate-200 shadow-sm rounded-2xl animate-pulse">
                      <CardContent className="p-6 space-y-4">
                        <div className="h-4 w-2/3 rounded bg-slate-200" />
                        <div className="h-16 w-full rounded-xl bg-slate-100" />
                        <div className="grid grid-cols-2 gap-3 pt-1">
                          {[1, 2, 3, 4].map((i) => (
                            <div key={i} className="h-10 rounded-xl bg-slate-100" />
                          ))}
                        </div>
                        {questionSlow ? (
                          <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600" role="alert">
                            <span>{SLOW_MESSAGE}</span>
                            <Button size="sm" variant="outline" onClick={() => void handleSelectQuestion(currentQuestion)}>Retry</Button>
                          </div>
                        ) : (
                          <p className="text-xs text-slate-400 flex items-center gap-1.5">
                            <span className="h-2 w-2 rounded-full bg-indigo-400 animate-ping inline-block" />
                            Loading question…
                          </p>
                        )}
                      </CardContent>
                    </Card>
                  )}
                  {currentQuestionData && (
                    <ListeningQuestionCard
                      key={`exam-${currentQuestion}-${questionKey(currentQuestionData)}`}
                      question={currentQuestionData}
                      questionNumber={currentQuestion}
                      selectedAnswer={currentAnswer}
                      onSelect={handleAnswerSelect}
                      disabled={Boolean(results) || timeUp}
                      maxPlays={MAX_PLAYS}
                      playCount={currentPlays}
                      onPlay={() => handlePlay(currentQuestion)}
                      onRequestAudio={handleRequestAudio}
                      onBufferingChange={setAudioBusy}
                      showTranscript={Boolean(results) && showTranscript}
                      onToggleTranscript={results ? () => setShowTranscript((prev) => !prev) : undefined}
                      onTranscriptSelect={handleTranscriptSelection}
                      translationText={transcriptTranslations[`exam-${currentQuestion}`]}
                      onTranslate={results ? () => void handleTranslateTranscript(currentQuestionData.script, `exam-${currentQuestion}`) : undefined}
                      isTranslating={isTranslating}
                      showTranslation={showTranslation}
                      hideReplay={true}
                      hideSpeedControls={true}
                    />
                  )}
                  <div className="flex flex-wrap items-center gap-3">
                    <Button
                      variant="secondary"
                      onClick={() => void handleSelectQuestion(currentQuestion - 1)}
                      disabled={currentQuestion <= 1}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => void handleSelectQuestion(currentQuestion + 1)}
                      disabled={currentQuestion >= examSize}
                    >
                      Next
                    </Button>
                    <Button onClick={() => void handleSubmitExam()} disabled={isSubmitting || Boolean(results)}>
                      {isSubmitting ? "Submitting..." : "Submit Exam"}
                    </Button>
                  </div>
                </div>
              )}
            </ExamContainer>

            <div className="space-y-4">
              <QuestionNavigator
                totalQuestions={examSize}
                currentQuestion={currentQuestion}
                answers={questionNavigatorAnswers}
                onSelect={(position) => void handleSelectQuestion(position)}
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

      </div>
    </TcfAppShell>
  );
}
