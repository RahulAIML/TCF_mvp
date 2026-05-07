"use client";

import { RotateCcw, PlayCircle, X } from "lucide-react";
import { formatSavedTime } from "@/lib/exam-progress";

interface ExamResumeDialogProps {
  moduleName: string;
  savedAt: number;
  onResume: () => void;
  onStartNew: () => void;
  onDismiss?: () => void;
}

export default function ExamResumeDialog({
  moduleName,
  savedAt,
  onResume,
  onStartNew,
  onDismiss,
}: ExamResumeDialogProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="resume-title"
    >
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-sm p-6 relative">
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="absolute top-4 right-4 p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
        )}

        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 text-amber-600">
            <RotateCcw className="h-5 w-5" />
          </div>
          <div>
            <h2 id="resume-title" className="font-semibold text-slate-900">Resume {moduleName}?</h2>
            <p className="text-xs text-slate-500 mt-0.5">Saved {formatSavedTime(savedAt)}</p>
          </div>
        </div>

        <p className="text-sm text-slate-600 mb-6 leading-relaxed">
          You have an unfinished <strong>{moduleName}</strong> session. Resume where you left off, or start a new session.
        </p>

        <div className="flex flex-col gap-3">
          <button
            onClick={onResume}
            className="flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-700 transition"
          >
            <PlayCircle className="h-4 w-4" />
            Resume where I left off
          </button>
          <button
            onClick={onStartNew}
            className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 hover:bg-slate-100 transition"
          >
            <RotateCcw className="h-4 w-4" />
            Start a new session
          </button>
        </div>
      </div>
    </div>
  );
}
