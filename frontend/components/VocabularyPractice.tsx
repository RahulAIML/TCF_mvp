"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Volume2, Loader, CheckCircle, X, Bookmark, BookmarkCheck, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import PronunciationTrainer from "@/components/PronunciationTrainer";
import { generateVocabularySet, getLearnerId } from "@/services/speakingApi";
import type { VocabularyItem } from "@/types/tcf-speaking";

interface VocabularyPracticeProps {
  level?: string;
  topic?: string;
  language?: string;
  count?: number;
}

type Step = "generating" | "learning" | "completed" | "error";

async function playWordAudio(word: string, language: string): Promise<void> {
  try {
    const res = await fetch(`/api/pronunciation/guide/${encodeURIComponent(word)}?language=${language}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    return new Promise((resolve) => {
      audio.onended = () => { URL.revokeObjectURL(url); resolve(); };
      audio.onerror = () => { URL.revokeObjectURL(url); resolve(); };
      audio.play().catch(() => { URL.revokeObjectURL(url); resolve(); });
    });
  } catch {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      return new Promise((resolve) => {
        const utt = new SpeechSynthesisUtterance(word);
        utt.lang = language === "fr" ? "fr-FR" : "en-US";
        utt.rate = 0.85;
        utt.onend = () => resolve();
        utt.onerror = () => resolve();
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utt);
      });
    }
  }
}

/** Vocabulary sets that never repeat for this learner; the next set is prefetched while this one is studied. */
const VocabularyPractice = ({ level = "A2", topic, language = "fr", count = 5 }: VocabularyPracticeProps) => {
  const [step, setStep] = useState<Step>("generating");
  const [words, setWords] = useState<VocabularyItem[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [learned, setLearned] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [practicing, setPracticing] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const nextSetRef = useRef<Promise<VocabularyItem[]> | null>(null);

  const requestSet = useCallback(
    () => generateVocabularySet({ level, count, topic, language, sessionId: getLearnerId() }),
    [level, count, topic, language],
  );

  const prefetchNext = useCallback(() => {
    const pending = requestSet();
    pending.catch(() => undefined);
    nextSetRef.current = pending;
  }, [requestSet]);

  const loadSet = useCallback(async () => {
    setStep("generating");
    setError("");
    setPracticing(false);
    const prefetched = nextSetRef.current;
    nextSetRef.current = null;
    try {
      let next: VocabularyItem[];
      try {
        next = prefetched ? await prefetched : await requestSet();
      } catch {
        next = await requestSet();
      }
      setWords(next);
      setCurrentIndex(0);
      setLearned(new Set());
      setStep("learning");
      prefetchNext();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Vocabulary could not be generated. Please try again.");
      setStep("error");
    }
  }, [prefetchNext, requestSet]);

  useEffect(() => {
    nextSetRef.current = null;
    void loadSet();
  }, [loadSet]);

  const handlePlayWord = useCallback(async (word: string) => {
    if (isPlayingAudio) return;
    setIsPlayingAudio(true);
    try {
      await playWordAudio(word, language);
    } finally {
      setIsPlayingAudio(false);
    }
  }, [isPlayingAudio, language]);

  const markLearned = (word: string) => setLearned((prev) => new Set(prev).add(word));

  if (step === "error") {
    return (
      <Card className="w-full">
        <CardContent className="pt-6 space-y-3">
          <div className="flex gap-2 p-3 bg-red-50 rounded-lg text-red-700 text-sm">
            <X className="h-4 w-4 flex-shrink-0 mt-0.5" />
            {error}
          </div>
          <Button onClick={() => void loadSet()} variant="outline" className="w-full flex gap-2">
            <RefreshCw className="h-4 w-4" /> Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (step === "generating") {
    return (
      <Card className="w-full">
        <CardContent className="pt-6 flex items-center justify-center min-h-40">
          <div className="text-center space-y-3">
            <Loader className="h-8 w-8 animate-spin mx-auto text-emerald-600" />
            <p className="text-slate-600">Preparing your words…</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (step === "completed") {
    return (
      <Card className="w-full">
        <CardContent className="pt-6 text-center space-y-4">
          <div className="text-4xl">🎉</div>
          <h3 className="text-xl font-bold text-slate-900">Vocabulary Session Complete!</h3>
          <p className="text-slate-600">You marked {learned.size} of {words.length} words as learned.</p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button onClick={() => { setCurrentIndex(0); setStep("learning"); }} variant="outline" className="flex-1">
              Review These Words
            </Button>
            <Button onClick={() => void loadSet()} className="flex-1 bg-emerald-600 hover:bg-emerald-700">
              Start New Session
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  const currentWord = words[currentIndex];
  const progress = Math.round(((currentIndex + 1) / words.length) * 100);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-slate-600">Word {currentIndex + 1} of {words.length}</span>
          <span className="text-emerald-600 font-semibold">{progress}%</span>
        </div>
        <div className="w-full bg-slate-200 rounded-full h-2">
          <div className="bg-emerald-600 h-2 rounded-full transition-all duration-300" style={{ width: `${progress}%` }} />
        </div>
      </div>

      {!practicing ? (
        <Card className="w-full">
          <CardHeader>
            <CardTitle className="text-2xl">{currentWord.word}</CardTitle>
          </CardHeader>

          <CardContent className="space-y-4">
            <Button onClick={() => handlePlayWord(currentWord.word)} disabled={isPlayingAudio} variant="outline" className="w-full flex gap-2 h-10">
              {isPlayingAudio
                ? <><Loader className="h-4 w-4 animate-spin" /> Playing…</>
                : <><Volume2 className="h-5 w-5" /> Listen to Pronunciation</>}
            </Button>

            {currentWord.phonetic && (
              <div className="p-3 bg-slate-100 rounded-lg">
                <p className="text-xs text-slate-600 mb-1">Pronunciation:</p>
                <p className="text-sm font-mono text-slate-900">{currentWord.phonetic}</p>
              </div>
            )}

            <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
              <p className="text-xs text-blue-600 mb-1">Meaning:</p>
              <p className="text-sm text-slate-900">{currentWord.meaning}</p>
            </div>

            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
              <p className="text-xs text-slate-600 mb-1">Example:</p>
              <p className="text-sm italic text-slate-900">&quot;{currentWord.example}&quot;</p>
              {currentWord.example_translation && (
                <p className="text-xs text-slate-600 mt-2">&quot;{currentWord.example_translation}&quot;</p>
              )}
            </div>

            <Button onClick={() => setPracticing(true)} className="w-full bg-emerald-600 hover:bg-emerald-700 flex gap-2">
              <Volume2 className="h-4 w-4" />
              Practice Pronunciation
            </Button>

            <Button
              onClick={() => markLearned(currentWord.word)}
              variant={learned.has(currentWord.word) ? "default" : "outline"}
              className="w-full flex gap-2"
            >
              {learned.has(currentWord.word)
                ? <><BookmarkCheck className="h-4 w-4" /> Marked as Learned</>
                : <><Bookmark className="h-4 w-4" /> Mark as Learned</>}
            </Button>

            <div className="flex gap-2">
              <Button onClick={() => setCurrentIndex(Math.max(0, currentIndex - 1))} disabled={currentIndex === 0} variant="outline" className="flex-1">
                Previous
              </Button>
              <Button
                onClick={() => (currentIndex < words.length - 1 ? setCurrentIndex(currentIndex + 1) : setStep("completed"))}
                className="flex-1 bg-emerald-600 hover:bg-emerald-700"
              >
                {currentIndex === words.length - 1 ? "Finish" : "Next"}
              </Button>
            </div>

            {learned.size > 0 && (
              <div className="p-3 bg-green-50 rounded-lg text-center text-sm text-green-700">
                <CheckCircle className="h-4 w-4 inline mr-2" />
                {learned.size} of {words.length} words marked as learned
              </div>
            )}
          </CardContent>
        </Card>
      ) : (
        <div>
          <Button onClick={() => setPracticing(false)} variant="outline" className="mb-4">Back</Button>
          <PronunciationTrainer
            key={currentWord.word}
            targetText={currentWord.word}
            language={language}
            onFeedbackReceived={(feedback) => {
              if (feedback.accuracy >= 7) markLearned(currentWord.word);
            }}
          />
        </div>
      )}
    </div>
  );
};

export default VocabularyPractice;
