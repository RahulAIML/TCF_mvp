"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { MarkdownText } from "@/lib/markdown";
import { streamText } from "@/lib/sse";

interface TextHelperToolProps {
  text: string;
  onTextChange: (text: string) => void;
  /** Kept for compatibility: the explanation now streams inside this component. */
  onExplain?: () => void;
  isLoading?: boolean;
}

/**
 * Phrase Helper: streams the explanation (meaning, usage, translation, example) as it is written,
 * so the first words appear in about a second.
 */
export default function TextHelperTool({ text, onTextChange }: TextHelperToolProps) {
  const [explanation, setExplanation] = useState("");
  const [explainedText, setExplainedText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const handleExplain = async () => {
    const query = text.trim();
    if (!query) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setExplanation("");
    setExplainedText(query);
    setError("");
    setIsStreaming(true);
    try {
      await streamText("/explain-text/stream", { text: query }, setExplanation, controller.signal);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : "Explanation unavailable. Please try again.");
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setIsStreaming(false);
      }
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <label className="text-sm font-semibold text-slate-700" htmlFor="phrase-helper-input">Phrase Helper</label>
        <p className="mt-0.5 text-xs text-slate-400">Type or paste any word, phrase, or sentence for an instant explanation.</p>
      </div>
      <textarea
        id="phrase-helper-input"
        className="min-h-[110px] w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100 transition resize-none"
        placeholder="e.g. « au fur et à mesure »"
        value={text}
        onChange={(event) => onTextChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            void handleExplain();
          }
        }}
      />
      <Button className="w-full" onClick={() => void handleExplain()} disabled={isStreaming || !text.trim()}>
        {isStreaming ? (
          <span className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            Explaining…
          </span>
        ) : (
          "View Explanation"
        )}
      </Button>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 flex items-center justify-between gap-2">
          <span>{error}</span>
          <button className="font-semibold underline" onClick={() => void handleExplain()}>Retry</button>
        </div>
      )}

      {(explanation || (isStreaming && !error)) && (
        <Card className="border-slate-200 shadow-sm rounded-2xl overflow-hidden" aria-live="polite">
          <div className="border-b border-slate-100 bg-slate-50 px-4 py-2.5">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Phrase Explanation</p>
            <p className="mt-0.5 text-xs text-slate-600 line-clamp-2">« {explainedText} »</p>
          </div>
          <CardContent className="p-4 text-sm text-slate-700">
            {explanation ? (
              <MarkdownText text={explanation} />
            ) : (
              <span className="flex items-center gap-1 py-0.5" aria-label="Explanation loading">
                {[0, 150, 300].map((delay) => (
                  <span key={delay} className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: `${delay}ms` }} />
                ))}
              </span>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
