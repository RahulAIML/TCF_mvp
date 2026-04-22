"use client";

import type { AnswerOption } from "@/types/exam";

interface QuestionNavigatorProps {
  totalQuestions: number;
  currentQuestion: number;
  answers: Record<number, AnswerOption | "">;
  onSelect: (questionNumber: number) => void;
}

export default function QuestionNavigator({
  totalQuestions,
  currentQuestion,
  answers,
  onSelect
}: QuestionNavigatorProps) {
  const items = Array.from({ length: totalQuestions }, (_, index) => index + 1);

  const answeredCount = Object.values(answers).filter(Boolean).length;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-slate-800">Question Navigator</h4>
        <span className="text-xs text-slate-400">
          {answeredCount} / {totalQuestions} answered
        </span>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-5 gap-1.5 sm:grid-cols-8 md:grid-cols-10">
        {items.map((number) => {
          const isCurrent = number === currentQuestion;
          const answered = Boolean(answers[number]);
          return (
            <button
              type="button"
              key={`nav-${number}`}
              onClick={() => onSelect(number)}
              title={`Question ${number}${answered ? " (answered)" : ""}`}
              className={`aspect-square rounded-lg border text-xs font-medium transition-all duration-150 ${
                isCurrent
                  ? "border-indigo-600 bg-indigo-600 text-white shadow-sm ring-2 ring-indigo-200"
                  : answered
                    ? "border-emerald-400 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                    : "border-slate-200 bg-white text-slate-500 hover:border-indigo-300 hover:text-indigo-600"
              }`}
            >
              {number}
            </button>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 border-t border-slate-100 pt-2.5">
        {[
          { color: "bg-indigo-600 border-indigo-600", label: "Current" },
          { color: "bg-emerald-50 border-emerald-400", label: "Answered" },
          { color: "bg-white border-slate-200", label: "Unanswered" },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1.5">
            <span className={`h-3 w-3 rounded border ${color} flex-shrink-0`} />
            <span className="text-[11px] text-slate-500">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
