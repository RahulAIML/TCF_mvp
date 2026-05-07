"use client";

import { useEffect, useState } from "react";
import { Volume2, Loader, CheckCircle, X, Bookmark, BookmarkCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import PronunciationTrainer from "@/components/PronunciationTrainer";

interface VocabularyWord {
  word: string;
  meaning: string;
  example: string;
  example_translation?: string;
  phonetic?: string;
  audio_url?: string;
}


interface VocabularyPracticeProps {
  level?: string; // A1, A2, B1, B2, C1, C2
  topic?: string;
  language?: string;
  count?: number;
}

type Step = "generating" | "selecting" | "learning" | "practicing" | "completed";

/**
 * Vocabulary Practice Component
 * Generates vocabulary, provides audio, tracks learning progress
 */
const VocabularyPractice = ({
  level = "A2",
  topic,
  language = "fr",
  count = 5,
}: VocabularyPracticeProps) => {
  const [step, setStep] = useState<Step>("generating");
  const [words, setWords] = useState<VocabularyWord[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [learned, setLearned] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [practicing, setPracticing] = useState(false);

  // Generate vocabulary words
  useEffect(() => {
    const generateVocabulary = async () => {
      try {
        setStep("generating");
        setError("");

        const response = await fetch("/api/pronunciation/vocabulary/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            level,
            count,
            topic,
            language,
          }),
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || "Failed to generate vocabulary");
        }

        const data = await response.json();
        setWords(data.words);
        setStep("selecting");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Generation failed");
      }
    };

    generateVocabulary();
  }, [level, count, topic, language]);

  if (error) {
    return (
      <Card className="w-full">
        <CardContent className="pt-6">
          <div className="flex gap-2 p-3 bg-red-50 rounded-lg text-red-700">
            <X className="h-4 w-4 flex-shrink-0 mt-0.5" />
            {error}
          </div>
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
            <p className="text-slate-600">Generating vocabulary...</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const currentWord = words[currentIndex];
  const progress = Math.round(((currentIndex + 1) / words.length) * 100);

  return (
    <div className="space-y-6">
      {/* Progress Bar */}
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-slate-600">
            Word {currentIndex + 1} of {words.length}
          </span>
          <span className="text-emerald-600 font-semibold">{progress}%</span>
        </div>
        <div className="w-full bg-slate-200 rounded-full h-2">
          <div
            className="bg-emerald-600 h-2 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Current Word Card */}
      {!practicing ? (
        <Card className="w-full">
          <CardHeader>
            <CardTitle className="text-2xl">{currentWord.word}</CardTitle>
          </CardHeader>

          <CardContent className="space-y-4">
            {/* Pronunciation Button */}
            {currentWord.audio_url && (
              <Button
                onClick={() => {
                  const audio = new Audio(currentWord.audio_url);
                  audio.play();
                }}
                variant="outline"
                className="w-full flex gap-2 h-10"
              >
                <Volume2 className="h-5 w-5" />
                Listen to Pronunciation
              </Button>
            )}

            {/* Phonetic Guide */}
            {currentWord.phonetic && (
              <div className="p-3 bg-slate-100 rounded-lg">
                <p className="text-xs text-slate-600 mb-1">Pronunciation:</p>
                <p className="text-sm font-mono text-slate-900">
                  {currentWord.phonetic}
                </p>
              </div>
            )}

            {/* Meaning */}
            <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
              <p className="text-xs text-blue-600 mb-1">Meaning:</p>
              <p className="text-sm text-slate-900">{currentWord.meaning}</p>
            </div>

            {/* Example */}
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
              <p className="text-xs text-slate-600 mb-1">Example:</p>
              <p className="text-sm italic text-slate-900">
                &quot;{currentWord.example}&quot;
              </p>
              {currentWord.example_translation && (
                <p className="text-xs text-slate-600 mt-2">
                  &quot;{currentWord.example_translation}&quot;
                </p>
              )}
            </div>

            {/* Practice Pronunciation Button */}
            <Button
              onClick={() => setPracticing(true)}
              className="w-full bg-emerald-600 hover:bg-emerald-700 flex gap-2"
            >
              <Volume2 className="h-4 w-4" />
              Practice Pronunciation
            </Button>

            {/* Mark as Learned */}
            <Button
              onClick={() => {
                const newLearned = new Set(learned);
                newLearned.add(currentWord.word);
                setLearned(newLearned);
              }}
              variant={learned.has(currentWord.word) ? "default" : "outline"}
              className="w-full flex gap-2"
            >
              {learned.has(currentWord.word) ? (
                <>
                  <BookmarkCheck className="h-4 w-4" />
                  Marked as Learned
                </>
              ) : (
                <>
                  <Bookmark className="h-4 w-4" />
                  Mark as Learned
                </>
              )}
            </Button>

            {/* Navigation */}
            <div className="flex gap-2">
              <Button
                onClick={() => setCurrentIndex(Math.max(0, currentIndex - 1))}
                disabled={currentIndex === 0}
                variant="outline"
                className="flex-1"
              >
                Previous
              </Button>

              <Button
                onClick={() => {
                  if (currentIndex < words.length - 1) {
                    setCurrentIndex(currentIndex + 1);
                  } else {
                    setStep("completed");
                  }
                }}
                className="flex-1 bg-emerald-600 hover:bg-emerald-700"
              >
                {currentIndex === words.length - 1 ? "Finish" : "Next"}
              </Button>
            </div>

            {/* Learned Counter */}
            {learned.size > 0 && (
              <div className="p-3 bg-green-50 rounded-lg text-center text-sm text-green-700">
                <CheckCircle className="h-4 w-4 inline mr-2" />
                {learned.size} of {words.length} words marked as learned
              </div>
            )}
          </CardContent>
        </Card>
      ) : (
        /* Pronunciation Practice Mode */
        <div>
          <Button
            onClick={() => setPracticing(false)}
            variant="outline"
            className="mb-4"
          >
            Back
          </Button>
          <PronunciationTrainer
            targetText={currentWord.word}
            language={language}
            onFeedbackReceived={(feedback) => {
              if (feedback.accuracy >= 7) {
                const newLearned = new Set(learned);
                newLearned.add(currentWord.word);
                setLearned(newLearned);
              }
            }}
          />
        </div>
      )}

      {/* Completion Screen */}
      {step === "completed" && (
        <Card className="w-full">
          <CardContent className="pt-6 text-center space-y-4">
            <div className="text-4xl">🎉</div>
            <h3 className="text-xl font-bold text-slate-900">
              Vocabulary Session Complete!
            </h3>
            <p className="text-slate-600">
              You marked {learned.size} of {words.length} words as learned.
            </p>
            <Button
              onClick={() => {
                setCurrentIndex(0);
                setLearned(new Set());
                setStep("selecting");
              }}
              className="w-full bg-emerald-600 hover:bg-emerald-700"
            >
              Start New Session
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default VocabularyPractice;
