"use client";

import type { TcfExamQuestion, TcfSubmitExamResponse } from "@/types/tcf-exam";

interface TcfExamResultsProps {
  results: TcfSubmitExamResponse;
  questions: Record<number, TcfExamQuestion>;
}

const LETTER_TO_INDEX: Record<string, number> = { A: 0, B: 1, C: 2, D: 3 };

export default function TcfExamResults({ results, questions }: TcfExamResultsProps) {
  const attemptedResults = results.results.filter((item) => item.user_answer);
  const attempted = results.attempted ?? attemptedResults.length;

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-900">Exam Results</h3>
        <div className="mt-3 flex flex-wrap gap-6 text-sm text-slate-600">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Generated</p>
            <p className="mt-0.5 text-2xl font-bold text-slate-900">{results.total}</p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Attempted</p>
            <p className="mt-0.5 text-2xl font-bold text-slate-900">{attempted}</p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Correct</p>
            <p className="mt-0.5 text-2xl font-bold text-emerald-600">{results.score}</p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Accuracy</p>
            <p className="mt-0.5 text-2xl font-bold text-blue-600">{results.accuracy}%</p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Time</p>
            <p className="mt-0.5 text-2xl font-bold text-slate-900">
              {Math.floor(results.completion_time / 60)}m {results.completion_time % 60}s
            </p>
          </div>
        </div>
      </div>

      {/* Per-question review */}
      <div className="space-y-5">
        {attemptedResults.length === 0 && (
          <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
            No attempted questions to review yet.
          </div>
        )}
        {attemptedResults.map((item) => {
          const question = questions[item.question_number];
          const correctIdx = LETTER_TO_INDEX[item.correct_answer] ?? -1;
          const userIdx = item.user_answer ? (LETTER_TO_INDEX[item.user_answer] ?? -1) : -1;

          return (
            <div
              key={`result-${item.question_number}`}
              className={`rounded-xl border bg-white p-5 shadow-sm ${
                item.is_correct ? "border-emerald-200" : "border-rose-200"
              }`}
            >
              {/* Question header */}
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Question {item.question_number}
                </span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                    item.is_correct
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-rose-100 text-rose-700"
                  }`}
                >
                  {item.is_correct ? "Correct" : "Incorrect"}
                </span>
              </div>

              {/* Passage */}
              {question?.text && (
                <div className="mt-3 rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-700 leading-relaxed border border-slate-100">
                  {question.text}
                </div>
              )}

              {/* Question text */}
              {question?.question && (
                <p className="mt-3 text-sm font-semibold text-slate-900">{question.question}</p>
              )}

              {/* Options with color coding */}
              {question?.options && question.options.length > 0 && (
                <div className="mt-3 space-y-2">
                  {question.options.map((option, idx) => {
                    const letter = ["A", "B", "C", "D"][idx];
                    const isCorrect = idx === correctIdx;
                    const isUserWrong = idx === userIdx && !item.is_correct;

                    let classes =
                      "flex items-start gap-3 rounded-lg px-3 py-2 text-sm border transition-colors";
                    if (isCorrect) {
                      classes += " bg-emerald-50 border-emerald-300 text-emerald-800 font-medium";
                    } else if (isUserWrong) {
                      classes += " bg-rose-50 border-rose-300 text-rose-800";
                    } else {
                      classes += " bg-white border-slate-200 text-slate-600";
                    }

                    return (
                      <div key={letter} className={classes}>
                        <span className="mt-0.5 min-w-[1.25rem] font-semibold">{letter}.</span>
                        <span>{option.replace(/^[A-D]\.\s*/, "")}</span>
                        {isCorrect && (
                          <span className="ml-auto text-xs text-emerald-600 font-semibold shrink-0">
                            Correct
                          </span>
                        )}
                        {isUserWrong && (
                          <span className="ml-auto text-xs text-rose-600 font-semibold shrink-0">
                            Your answer
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Explanation */}
              {item.explanation && (
                <div className="mt-3 rounded-lg bg-blue-50 border border-blue-100 px-4 py-3 text-sm text-blue-800">
                  <span className="font-semibold">Explanation: </span>
                  {item.explanation}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
