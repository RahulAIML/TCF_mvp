"use client";

import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface WordLookupProps {
  word: string;
  onWordChange: (word: string) => void;
  onExplain: () => void;
  isLoading: boolean;
}

export default function WordLookup({
  word,
  onWordChange,
  onExplain,
  isLoading
}: WordLookupProps) {
  return (
    <div className="space-y-3">
      <label className="text-sm font-medium text-slate-800">Text Helper Tool</label>
      <Input
        placeholder="Select a word or phrase to explain"
        value={word}
        onChange={(event) => onWordChange(event.target.value)}
      />
      <Button className="w-full" onClick={onExplain} disabled={isLoading || !word.trim()}>
        {isLoading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Explaining...
          </>
        ) : (
          "Explain Text"
        )}
      </Button>
    </div>
  );
}
