"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { TcfWritingEvaluationResponse } from "@/types/tcf-writing";
import type { PartialWritingEvaluation, ScoreKey } from "@/lib/writing-eval";

interface WritingEvaluationCardProps {
  title: string;
  evaluation: TcfWritingEvaluationResponse | PartialWritingEvaluation;
  /** True while the evaluation is still streaming in. */
  streaming?: boolean;
}

const SCORE_FIELDS: { key: ScoreKey; label: string }[] = [
  { key: "structure", label: "Structure" },
  { key: "grammar", label: "Grammar" },
  { key: "coherence", label: "Coherence" },
  { key: "vocab", label: "Vocabulary" },
];

export default function WritingEvaluationCard({ title, evaluation, streaming = false }: WritingEvaluationCardProps) {
  const scores = evaluation.scores as Record<ScoreKey, number | null>;
  return (
    <Card className="rounded-2xl border-slate-200 shadow-sm" aria-live="polite" aria-busy={streaming}>
      <CardHeader>
        <CardTitle className="text-slate-900 flex items-center gap-2">
          {title}
          {streaming && <span className="h-2 w-2 rounded-full bg-indigo-400 animate-ping" aria-hidden />}
        </CardTitle>
        <p className="text-sm text-slate-500">
          Level: {evaluation.level ?? <span className="inline-block h-3 w-8 rounded bg-slate-200 animate-pulse align-middle" />}
        </p>
      </CardHeader>
      <CardContent className="space-y-4 text-sm text-slate-700">
        <div className="grid gap-3 sm:grid-cols-2">
          {SCORE_FIELDS.map(({ key, label }) => (
            <div key={key} className="rounded-xl bg-slate-50 p-3">
              <p className="text-xs uppercase text-slate-400">{label}</p>
              {scores[key] === null || scores[key] === undefined ? (
                <div className="mt-1 h-6 w-12 rounded bg-slate-200 animate-pulse" />
              ) : (
                <p className="text-lg font-semibold text-slate-900">{scores[key]}/10</p>
              )}
            </div>
          ))}
        </div>

        {(evaluation.feedback.length > 0 || streaming) && (
          <div>
            <p className="font-semibold text-slate-900">Feedback</p>
            {evaluation.feedback.length > 0 ? (
              <ul className="mt-2 list-disc space-y-1 pl-4">
                {evaluation.feedback.map((item, index) => (
                  <li key={`${title}-fb-${index}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <div className="mt-2 space-y-2">
                <div className="h-3 w-full rounded bg-slate-100 animate-pulse" />
                <div className="h-3 w-4/5 rounded bg-slate-100 animate-pulse" />
              </div>
            )}
          </div>
        )}

        {evaluation.improved_version && (
          <div className="rounded-xl bg-slate-50 p-4">
            <p className="text-xs uppercase text-slate-400">Improved version</p>
            <p className="mt-2 whitespace-pre-line text-slate-700">{evaluation.improved_version}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
