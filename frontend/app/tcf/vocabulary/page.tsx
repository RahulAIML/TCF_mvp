"use client";

import { useState, useCallback } from "react";
import TcfAppShell from "@/components/TcfAppShell";
import VocabularyPractice from "@/components/VocabularyPractice";
import { Card, CardContent } from "@/components/ui/card";
import { BookMarked, Star, TrendingUp, RefreshCw } from "lucide-react";

type Level = "A1" | "A2" | "B1" | "B2" | "C1" | "C2";
type Lang = "fr" | "en";

const LEVELS: Level[] = ["A1", "A2", "B1", "B2", "C1", "C2"];

const TOPICS_FR = [
  "famille et relations",
  "alimentation et cuisine",
  "travail et carrière",
  "voyage et transport",
  "santé et bien-être",
  "culture et loisirs",
  "environnement",
  "technologie",
  "société et politique",
  "éducation",
];

const TOPICS_EN = [
  "family and relationships",
  "food and cooking",
  "work and career",
  "travel and transport",
  "health and wellness",
  "culture and leisure",
  "environment",
  "technology",
  "society and politics",
  "education",
];

const levelColors: Record<Level, string> = {
  A1: "bg-green-100 text-green-700 border-green-200",
  A2: "bg-emerald-100 text-emerald-700 border-emerald-200",
  B1: "bg-blue-100 text-blue-700 border-blue-200",
  B2: "bg-indigo-100 text-indigo-700 border-indigo-200",
  C1: "bg-violet-100 text-violet-700 border-violet-200",
  C2: "bg-rose-100 text-rose-700 border-rose-200",
};

const levelDesc: Record<Level, string> = {
  A1: "Beginner — everyday words and basic phrases",
  A2: "Elementary — common situations and simple topics",
  B1: "Intermediate — familiar topics and opinions",
  B2: "Upper-Intermediate — complex topics and nuances",
  C1: "Advanced — abstract ideas, professional register",
  C2: "Mastery — near-native, rare vocabulary",
};

export default function VocabularyPage() {
  const [language, setLanguage] = useState<Lang>("fr");
  const [selectedLevel, setSelectedLevel] = useState<Level | null>(null);
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [wordCount, setWordCount] = useState(5);
  const [sessionKey, setSessionKey] = useState(0);
  const [isActive, setIsActive] = useState(false);

  const topics = language === "fr" ? TOPICS_FR : TOPICS_EN;

  const handleStart = useCallback(() => {
    if (!selectedLevel) return;
    setSessionKey((k) => k + 1);
    setIsActive(true);
  }, [selectedLevel]);

  const handleRestart = useCallback(() => {
    setIsActive(false);
    setSelectedLevel(null);
    setSelectedTopic(null);
  }, []);

  return (
    <TcfAppShell
      title="Vocabulary Builder"
      subtitle="Smart daily vocabulary with pronunciation, examples, and spaced repetition"
      backHref="/tcf"
    >
      <div className="max-w-5xl space-y-6">
        {!isActive ? (
          <>
            {/* Language selector */}
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm font-medium text-slate-700">Language:</span>
              <div className="flex rounded-lg border border-slate-200 bg-white overflow-hidden">
                {(["fr", "en"] as Lang[]).map((lang) => (
                  <button
                    key={lang}
                    onClick={() => { setLanguage(lang); setSelectedTopic(null); }}
                    className={`px-4 py-2 text-sm font-medium transition ${
                      language === lang
                        ? "bg-emerald-600 text-white"
                        : "text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {lang === "fr" ? "🇫🇷 French" : "🇬🇧 English"}
                  </button>
                ))}
              </div>
            </div>

            {/* Level picker */}
            <div>
              <h2 className="text-sm font-semibold text-slate-700 mb-3">Choose your level</h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {LEVELS.map((level) => (
                  <button
                    key={level}
                    onClick={() => setSelectedLevel(level)}
                    className={`relative rounded-xl border-2 p-4 text-left transition-all ${
                      selectedLevel === level
                        ? "border-emerald-500 shadow-sm"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-bold ${levelColors[level]}`}>
                        {level}
                      </span>
                      {selectedLevel === level && (
                        <Star className="h-4 w-4 text-emerald-500 fill-emerald-500" />
                      )}
                    </div>
                    <p className="text-[11px] text-slate-500 leading-snug">{levelDesc[level]}</p>
                  </button>
                ))}
              </div>
            </div>

            {/* Topic picker */}
            <div>
              <h2 className="text-sm font-semibold text-slate-700 mb-3">
                Topic <span className="font-normal text-slate-400">(optional)</span>
              </h2>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => setSelectedTopic(null)}
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                    !selectedTopic
                      ? "bg-slate-800 text-white border-slate-800"
                      : "border-slate-200 text-slate-600 hover:border-slate-300"
                  }`}
                >
                  Any topic
                </button>
                {topics.map((topic) => (
                  <button
                    key={topic}
                    onClick={() => setSelectedTopic(selectedTopic === topic ? null : topic)}
                    className={`rounded-full border px-3 py-1.5 text-xs font-medium transition capitalize ${
                      selectedTopic === topic
                        ? "bg-emerald-600 text-white border-emerald-600"
                        : "border-slate-200 text-slate-600 hover:border-emerald-300 hover:text-emerald-700"
                    }`}
                  >
                    {topic}
                  </button>
                ))}
              </div>
            </div>

            {/* Word count */}
            <div>
              <h2 className="text-sm font-semibold text-slate-700 mb-3">Words per session</h2>
              <div className="flex gap-2">
                {[5, 8, 10, 15].map((count) => (
                  <button
                    key={count}
                    onClick={() => setWordCount(count)}
                    className={`rounded-lg border px-4 py-2 text-sm font-medium transition ${
                      wordCount === count
                        ? "bg-slate-800 text-white border-slate-800"
                        : "border-slate-200 text-slate-600 hover:border-slate-300"
                    }`}
                  >
                    {count}
                  </button>
                ))}
              </div>
            </div>

            {/* Start button */}
            <button
              onClick={handleStart}
              disabled={!selectedLevel}
              className="flex items-center gap-2 rounded-xl bg-emerald-600 px-6 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed transition shadow-sm"
            >
              <TrendingUp className="h-4 w-4" />
              Start Vocabulary Session
            </button>

            {/* Info cards */}
            <div className="grid gap-4 sm:grid-cols-3">
              {[
                { icon: BookMarked, title: "Smart generation", desc: "AI generates real-world vocabulary tailored to your CEFR level — no duplicates." },
                { icon: Star, title: "Track progress", desc: "Mark words as learned or favorite. Weak words reappear automatically." },
                { icon: TrendingUp, title: "Practice pronunciation", desc: "Hear native audio for every word and record yourself to get scored feedback." },
              ].map(({ icon: Icon, title, desc }) => (
                <Card key={title} className="border-slate-200 shadow-sm">
                  <CardContent className="p-4 flex gap-3">
                    <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-emerald-100 text-emerald-600">
                      <Icon className="h-4 w-4" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-900">{title}</p>
                      <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{desc}</p>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <span className={`inline-block rounded-full border px-3 py-1 text-xs font-bold mr-2 ${levelColors[selectedLevel!]}`}>
                  {selectedLevel}
                </span>
                {selectedTopic && (
                  <span className="text-xs text-slate-500 capitalize">{selectedTopic}</span>
                )}
              </div>
              <button
                onClick={handleRestart}
                className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 transition"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Change settings
              </button>
            </div>

            <VocabularyPractice
              key={sessionKey}
              level={selectedLevel!}
              topic={selectedTopic ?? undefined}
              language={language}
              count={wordCount}
            />
          </div>
        )}
      </div>
    </TcfAppShell>
  );
}
