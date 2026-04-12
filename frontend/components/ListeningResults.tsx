import { useMemo, useRef, useState } from "react";
import type { ListeningResultItem } from "@/types/listening";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface ListeningResultsProps {
  score: number;
  total: number;
  attempted: number;
  accuracy: number;
  results: ListeningResultItem[];
}

function ListeningResultCard({ item }: { item: ListeningResultItem }) {
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const [showTranscript, setShowTranscript] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioSrc = useMemo(() => {
    if (!item.audio_url) return "";
    return item.audio_url.startsWith("http") ? item.audio_url : `${apiBase}${item.audio_url}`;
  }, [item.audio_url, apiBase]);
  const transcriptText = item.transcript ?? "";

  const handlePlay = async () => {
    if (!audioRef.current || !audioSrc) return;
    try {
      await audioRef.current.play();
    } catch {
      // no-op
    }
  };

  const handlePause = () => {
    if (!audioRef.current) return;
    audioRef.current.pause();
  };

  return (
    <Card className="border-slate-200">
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className="text-sm font-semibold text-slate-900">Question {item.question_number}</p>
          {transcriptText && (
            <Button variant="outline" size="sm" onClick={() => setShowTranscript((prev) => !prev)}>
              {showTranscript ? "Hide Transcript" : "Show Transcript"}
            </Button>
          )}
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-3">
          <p className="text-xs font-semibold uppercase text-slate-500">Audio</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={handlePlay} disabled={!audioSrc}>
              Play
            </Button>
            <Button size="sm" variant="secondary" onClick={handlePause} disabled={!audioSrc}>
              Pause
            </Button>
            {!audioSrc && (
              <span className="text-xs text-slate-400">Audio unavailable</span>
            )}
          </div>
          <audio ref={audioRef} src={audioSrc || undefined} preload="auto" />
        </div>

        {showTranscript && transcriptText && (
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 whitespace-pre-wrap">
            {transcriptText}
          </div>
        )}

        <p className="text-sm text-slate-800">{item.question}</p>

        <div className="space-y-2">
          {item.options.map((option, index) => {
            const label = (["A", "B", "C", "D"][index] ?? "A");
            const isUser = item.user_answer === label;
            const isCorrect = item.correct_answer === label;
            const classes = isCorrect
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : isUser
                ? "border-rose-200 bg-rose-50 text-rose-700"
                : "border-slate-200 bg-white text-slate-700";
            return (
              <div key={`option-${item.question_number}-${label}`} className={`rounded-xl border px-3 py-2 text-xs ${classes}`}>
                <span className="font-semibold">{label}.</span> {option.replace(/^[A-D][).:\-\s]+/i, "").trim()}
              </div>
            );
          })}
        </div>

        <div className="text-xs text-slate-600">
          <p>Your answer: <span className="font-semibold">{item.user_answer || "(blank)"}</span></p>
          <p className="text-emerald-700">Correct answer: <span className="font-semibold">{item.correct_answer}</span></p>
        </div>
        <p className="text-xs text-slate-600">{item.explanation}</p>
      </CardContent>
    </Card>
  );
}

export default function ListeningResults({ score, total, attempted, accuracy, results }: ListeningResultsProps) {
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 flex flex-wrap gap-4">
        <span>Generated: <strong>{total}</strong></span>
        <span>Attempted: <strong>{attempted}</strong></span>
        <span>Correct: <strong>{score}</strong></span>
        <span>Accuracy: <strong>{accuracy.toFixed(1)}%</strong></span>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {results.map((item) => (
          <ListeningResultCard key={`listening-result-${item.question_number}`} item={item} />
        ))}
        {results.length === 0 && (
          <p className="text-sm text-slate-600">No attempted questions to review.</p>
        )}
      </div>
    </div>
  );
}
