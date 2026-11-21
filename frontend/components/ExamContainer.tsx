"use client";

import type { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";

interface ExamContainerProps {
  currentQuestion: number;
  totalQuestions: number;
  /** First question number of the exam range (default 1); header and progress count within the range. */
  startQuestion?: number;
  timer: ReactNode;
  children: ReactNode;
  title?: string;
}

export default function ExamContainer({
  currentQuestion,
  totalQuestions,
  startQuestion = 1,
  timer,
  children,
  title
}: ExamContainerProps) {
  const position = Math.min(Math.max(currentQuestion - startQuestion + 1, 1), totalQuestions);
  const progress = Math.round((position / totalQuestions) * 100);

  return (
    <Card className="border-slate-200 shadow-sm rounded-2xl overflow-hidden">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 px-6 py-4">
        <div>
          <p className="text-xs font-medium text-slate-400">{title ?? "TCF Mock Exam"}</p>
          <h2 className="text-lg font-semibold text-slate-900">
            Question <span className="text-indigo-600">{position}</span>
            <span className="text-slate-400 font-normal"> / {totalQuestions}</span>
          </h2>
        </div>
        {timer}
      </div>

      {/* Progress bar */}
      <div className="h-1 w-full bg-slate-100">
        <div
          className="h-1 bg-indigo-500 transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>

      <CardContent className="space-y-5 p-6">{children}</CardContent>
    </Card>
  );
}
