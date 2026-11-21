"use client";

import { useMemo, useRef, useState } from "react";
import TcfAppShell from "@/components/TcfAppShell";
import TextExplanationCard from "@/components/TextExplanationCard";
import ReadingPanel from "@/components/ReadingPanel";
import TextHelperTool from "@/components/TextHelperTool";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { explainText, generatePassageQuiz } from "@/services/api";
import type { ExplainTextResponse } from "@/types/text-helper";
import { PASSAGE_LEVELS, type PassageLevel, type PassageQuizQuestion, type PassageQuizResponse } from "@/types/passage";
import type { AnswerOption } from "@/types/exam";

function newSessionId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function PassageAnalyzerPage() {
  const [quiz, setQuiz] = useState<PassageQuizResponse | null>(null);
  const [level, setLevel] = useState<PassageLevel>("B1");
  const sessionIdRef = useRef<string>(newSessionId());
  // The next quiz for the chosen level is generated in the background while the student reads.
  const nextQuizRef = useRef<{ level: PassageLevel; request: Promise<PassageQuizResponse> } | null>(null);
  const [lookupText, setLookupText] = useState("");
  const [explanationDetails, setExplanationDetails] = useState<ExplainTextResponse | null>(null);
  const [loadingPassage, setLoadingPassage] = useState(false);
  const [loadingHelper, setLoadingHelper] = useState(false);
  const [error, setError] = useState("");
  const [quizAnswers, setQuizAnswers] = useState<Record<number, AnswerOption | "">>({});
  const [quizSubmitted, setQuizSubmitted] = useState(false);
  const [quizScore, setQuizScore] = useState(0);
  const [quizResults, setQuizResults] = useState<
    Array<PassageQuizQuestion & { question_number: number; user_answer: AnswerOption | "" }>
  >([]);

  const unansweredCount = useMemo(() => {
    if (!quiz) {
      return 0;
    }
    return quiz.questions.filter((_, index) => !quizAnswers[index + 1]).length;
  }, [quiz, quizAnswers]);

  const requestQuiz = (lvl: PassageLevel) => {
    const request = generatePassageQuiz(lvl, sessionIdRef.current);
    request.catch(() => undefined);
    return request;
  };

  const handleGeneratePassage = async () => {
    setLoadingPassage(true);
    setError("");
    try {
      const queued = nextQuizRef.current?.level === level ? nextQuizRef.current.request : null;
      nextQuizRef.current = null;
      let result: PassageQuizResponse;
      try {
        result = await (queued ?? requestQuiz(level));
      } catch (err) {
        if (!queued) throw err;
        result = await requestQuiz(level);
      }
      nextQuizRef.current = { level, request: requestQuiz(level) };
      setQuiz(result);
      setLookupText("");
      setExplanationDetails(null);
      setQuizAnswers({});
      setQuizSubmitted(false);
      setQuizScore(0);
      setQuizResults([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate passage.");
    } finally {
      setLoadingPassage(false);
    }
  };

  const handleExplainText = async () => {
    if (!lookupText.trim()) {
      return;
    }
    setLoadingHelper(true);
    setError("");
    try {
      const result = await explainText({ text: lookupText.trim() });
      setExplanationDetails(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to explain text.");
    } finally {
      setLoadingHelper(false);
    }
  };

  const handleAnswerSelect = (questionNumber: number, value: AnswerOption) => {
    if (quizSubmitted) {
      return;
    }
    setQuizAnswers((prev) => ({ ...prev, [questionNumber]: value }));
  };

  const handleSubmitQuiz = () => {
    if (!quiz) {
      return;
    }
    const results = quiz.questions.map((question, index) => ({
      ...question,
      question_number: index + 1,
      user_answer: quizAnswers[index + 1] ?? ""
    }));

    const score = results.reduce(
      (total, item) => total + (item.user_answer === item.correct_answer ? 1 : 0),
      0
    );

    setQuizSubmitted(true);
    setQuizScore(score);
    setQuizResults(results);
  };

  const answeredCount = Object.values(quizAnswers).filter(Boolean).length;

  return (
    <TcfAppShell title="Passage Analyzer" subtitle="Read, select text for explanations, then take the quiz" backHref="/tcf/reading">
      <div className="space-y-6">
        {/* Top bar */}
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
          <div>
            <p className="text-sm font-semibold text-slate-900">Passage Analyzer</p>
            <p className="text-xs text-slate-400 mt-0.5">Generate a French passage · select text for instant explanations · take the comprehension quiz</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-0.5" role="group" aria-label="CEFR level">
              {PASSAGE_LEVELS.map((lvl) => (
                <button
                  key={lvl}
                  type="button"
                  onClick={() => setLevel(lvl)}
                  disabled={loadingPassage}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                    level === lvl ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
                  }`}
                >
                  {lvl}
                </button>
              ))}
            </div>
            <Button onClick={handleGeneratePassage} disabled={loadingPassage}>
              {loadingPassage ? (
                <span className="flex items-center gap-2">
                  <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  Generating…
                </span>
              ) : quiz ? `New ${level} Passage` : `Generate ${level} Passage`}
            </Button>
          </div>
        </div>

        {error && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            <span>{error}</span>
            <Button size="sm" variant="secondary" onClick={() => void handleGeneratePassage()} disabled={loadingPassage}>
              Retry
            </Button>
          </div>
        )}

        {loadingPassage && !quiz && (
          <Card className="border-slate-200 shadow-sm rounded-2xl animate-pulse">
            <CardContent className="p-6 space-y-3">
              {[1, 2, 3, 4, 5].map((i) => <div key={i} className="h-3 w-full rounded bg-slate-100" />)}
              <p className="text-xs text-slate-400">Preparing a {level} passage and its 10 questions…</p>
            </CardContent>
          </Card>
        )}

        {quiz && (
          <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
            <ReadingPanel
              title={quiz.title}
              passage={quiz.passage}
              onTextHighlight={(text) => setLookupText(text)}
            />
            <aside className="space-y-4">
              <Card className="border-slate-200 shadow-sm">
                <CardContent className="p-5">
                  <TextHelperTool
                    text={lookupText}
                    onTextChange={setLookupText}
                    onExplain={handleExplainText}
                    isLoading={loadingHelper}
                  />
                </CardContent>
              </Card>
              {explanationDetails && <TextExplanationCard entry={explanationDetails} />}
            </aside>
          </div>
        )}

        {quiz && (
          <Card className="border-slate-200 shadow-sm rounded-2xl overflow-hidden">
            <div className="border-b border-slate-100 bg-slate-50 px-6 py-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-slate-900">Comprehension Quiz</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  {answeredCount} of {quiz.questions.length} answered
                  {unansweredCount > 0 && !quizSubmitted && ` · ${unansweredCount} remaining`}
                </p>
              </div>
              <div className="flex flex-col items-end gap-1">
                <Button onClick={handleSubmitQuiz} disabled={quizSubmitted || answeredCount === 0}>
                  {quizSubmitted ? "✓ Submitted" : "Submit Answers"}
                </Button>
                {!quizSubmitted && unansweredCount > 0 && answeredCount > 0 && (
                  <span className="text-[11px] text-slate-400">Unanswered questions count as incorrect.</span>
                )}
              </div>
            </div>

            <div className="divide-y divide-slate-50 px-6 py-2">
              {quiz.questions.map((question, index) => {
                const questionNumber = index + 1;
                const selected = quizAnswers[questionNumber] ?? "";
                return (
                  <div key={`passage-question-${questionNumber}`} className="py-5">
                    <div className="flex items-start gap-3 mb-3">
                      <span className="flex-shrink-0 h-6 w-6 rounded-full bg-slate-100 text-xs font-bold text-slate-500 flex items-center justify-center mt-0.5">{questionNumber}</span>
                      <p className="text-sm font-medium text-slate-800">{question.question}</p>
                    </div>
                    <div className="ml-9 space-y-2">
                      {question.options.map((option, optionIndex) => {
                        const value = (["A", "B", "C", "D"][optionIndex] as AnswerOption) ?? "A";
                        const isSelected = selected === value;
                        return (
                          <label
                            key={`passage-option-${questionNumber}-${optionIndex}`}
                            className={`group flex items-start gap-3 rounded-xl border px-3 py-2.5 text-sm transition-all duration-150 ${
                              isSelected
                                ? "border-indigo-600 bg-indigo-600 text-white cursor-default"
                                : "border-slate-200 bg-white text-slate-700 hover:border-indigo-200 hover:bg-indigo-50"
                            } ${quizSubmitted ? "cursor-default" : "cursor-pointer"}`}
                          >
                            <input
                              type="radio"
                              name={`passage-question-${questionNumber}`}
                              className="sr-only"
                              value={value}
                              checked={isSelected}
                              disabled={quizSubmitted}
                              onChange={() => handleAnswerSelect(questionNumber, value)}
                            />
                            <span className={`flex-shrink-0 h-5 w-5 rounded-md text-[10px] font-bold flex items-center justify-center ${
                              isSelected ? "bg-white/20 text-white" : "bg-slate-100 text-slate-500 group-hover:bg-indigo-100 group-hover:text-indigo-700"
                            }`}>
                              {value}
                            </span>
                            <span>{option.replace(/^[A-D]\.\s*/, "")}</span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        )}

        {quizSubmitted && (
          <Card className="border-slate-200 shadow-sm rounded-2xl overflow-hidden">
            <div className="border-b border-slate-100 bg-emerald-50 px-6 py-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-emerald-800">Quiz Results</p>
                <p className="text-xs text-emerald-600 mt-0.5">
                  Score: <span className="font-bold">{quizScore}</span> / {quizResults.length}
                  {" — "}
                  {quizResults.length > 0 ? Math.round((quizScore / quizResults.length) * 100) : 0}%
                  {" · "}
                  {quizResults.filter((r) => !r.user_answer).length} unanswered
                </p>
              </div>
            </div>
            <div className="divide-y divide-slate-50 px-6 py-2">
              {quizResults.map((result) => {
                const isCorrect = result.user_answer === result.correct_answer;
                const unanswered = !result.user_answer;
                return (
                  <div key={`quiz-result-${result.question_number}`} className="py-5 space-y-2">
                    <div className="flex items-start gap-3">
                      <span className={`flex-shrink-0 h-6 w-6 rounded-full text-xs font-bold flex items-center justify-center mt-0.5 ${
                        isCorrect ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-600"
                      }`}>
                        {isCorrect ? "✓" : "✗"}
                      </span>
                      <p className="text-sm font-medium text-slate-800">{result.question}</p>
                    </div>
                    <div className="ml-9 flex flex-wrap gap-4 text-xs">
                      <span className="text-slate-500">
                        Your answer:{" "}
                        <span className={`font-semibold ${isCorrect ? "text-emerald-700" : "text-rose-600"}`}>
                          {unanswered ? "Not answered" : result.user_answer}
                        </span>
                      </span>
                      {!isCorrect && (
                        <span className="text-slate-500">
                          Correct: <span className="font-semibold text-emerald-700">{result.correct_answer}</span>
                        </span>
                      )}
                    </div>
                    {result.explanation && (
                      <p className="ml-9 text-xs text-slate-500 leading-relaxed">{result.explanation}</p>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>
        )}
      </div>
    </TcfAppShell>
  );
}
