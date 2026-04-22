"use client";

import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface TextHelperToolProps {
  text: string;
  onTextChange: (text: string) => void;
  onExplain: () => void;
  isLoading: boolean;
}

export default function TextHelperTool({
  text,
  onTextChange,
  onExplain,
  isLoading
}: TextHelperToolProps) {
  return (
    <div className="space-y-3">
      <div>
        <label className="text-sm font-semibold text-slate-700">Phrase Helper</label>
        <p className="mt-0.5 text-xs text-slate-400">Type or paste any word, phrase, or sentence for an instant explanation.</p>
      </div>
      <textarea
        className="min-h-[110px] w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100 transition resize-none"
        placeholder="e.g. « au fur et à mesure »"
        value={text}
        onChange={(event) => onTextChange(event.target.value)}
      />
      <Button
        className="w-full"
        onClick={onExplain}
        disabled={isLoading || !text.trim()}
      >
        {isLoading ? (
          <span className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            Analysing...
          </span>
        ) : (
          "View Explanation"
        )}
      </Button>
    </div>
  );
}
