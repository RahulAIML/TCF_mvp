"use client";

import { useState } from "react";
import type { ExplainTextResponse } from "@/types/text-helper";
import { Card, CardContent } from "@/components/ui/card";

interface TextExplanationCardProps {
  entry: ExplainTextResponse;
}

export default function TextExplanationCard({ entry }: TextExplanationCardProps) {
  const [showTranslation, setShowTranslation] = useState(false);

  return (
    <Card className="border-slate-200 shadow-sm rounded-2xl overflow-hidden">
      <div className="border-b border-slate-100 bg-slate-50 px-4 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Phrase Explanation</p>
      </div>
      <CardContent className="p-4 space-y-3 text-sm">
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Meaning</p>
          <p className="text-slate-800">{entry.meaning}</p>
        </div>

        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Explanation</p>
          <p className="text-slate-700 leading-relaxed">{entry.explanation}</p>
        </div>

        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Translation</p>
            <button
              onClick={() => setShowTranslation((p) => !p)}
              className="text-[11px] font-medium text-indigo-500 hover:text-indigo-700 transition"
            >
              {showTranslation ? "Hide" : "Show"}
            </button>
          </div>
          {showTranslation && (
            <p className="text-slate-700 rounded-lg bg-indigo-50 px-3 py-2">{entry.translation}</p>
          )}
        </div>

        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Example</p>
          <p className="text-slate-600 italic border-l-2 border-slate-200 pl-3">{entry.example}</p>
        </div>
      </CardContent>
    </Card>
  );
}
