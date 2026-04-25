"use client";

import { Card, CardContent } from "@/components/ui/card";

interface ReadingPanelProps {
  title: string;
  passage: string;
  onTextHighlight?: (text: string) => void;
}

function normalizeSelection(rawSelection: string): string {
  return rawSelection.replace(/\s+/g, " ").trim();
}

export default function ReadingPanel({
  title,
  passage,
  onTextHighlight
}: ReadingPanelProps) {
  const handleMouseUp = () => {
    const selection = window.getSelection()?.toString() ?? "";
    const chosenText = normalizeSelection(selection);
    if (chosenText && onTextHighlight) {
      onTextHighlight(chosenText);
    }
  };

  return (
    <Card className="border-slate-200 shadow-sm rounded-2xl overflow-hidden">
      <div className="border-b border-slate-100 bg-slate-50 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
        <p className="text-[11px] text-slate-400 mt-0.5">Select any word or phrase → explanation appears on the right</p>
      </div>
      <CardContent className="p-0">
        <div
          className="max-h-[420px] overflow-y-auto p-5 text-[1.02rem] leading-8 text-slate-800 selection:bg-indigo-100 cursor-text"
          onMouseUp={handleMouseUp}
        >
          {passage}
        </div>
      </CardContent>
    </Card>
  );
}
