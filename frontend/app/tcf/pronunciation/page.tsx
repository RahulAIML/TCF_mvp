"use client";

import { useState, useCallback } from "react";
import TcfAppShell from "@/components/TcfAppShell";
import PronunciationTrainer from "@/components/PronunciationTrainer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Volume2, RefreshCw, ChevronRight } from "lucide-react";

type Language = "fr" | "en";

const SAMPLE_WORDS_FR = [
  { text: "Bonjour", phonetic: "bɔ̃ʒuʁ", level: "A1" },
  { text: "Merci beaucoup", phonetic: "mɛʁsi boku", level: "A1" },
  { text: "Je m'appelle", phonetic: "ʒə mapɛl", level: "A1" },
  { text: "S'il vous plaît", phonetic: "sil vu plɛ", level: "A1" },
  { text: "Au revoir", phonetic: "o ʁəvwaʁ", level: "A1" },
  { text: "Comment allez-vous?", phonetic: "kɔmɑ̃ tale vu", level: "A2" },
  { text: "Je voudrais un café", phonetic: "ʒə vudʁɛ œ̃ kafe", level: "A2" },
  { text: "L'environnement", phonetic: "lɑ̃viʁɔnmɑ̃", level: "B1" },
  { text: "La citoyenneté", phonetic: "la sitwajɛnte", level: "B2" },
  { text: "Le développement durable", phonetic: "lə devlɔpmɑ̃ dyʁabl", level: "B2" },
];

const SAMPLE_WORDS_EN = [
  { text: "Hello", phonetic: "hɛˈloʊ", level: "A1" },
  { text: "Thank you very much", phonetic: "θæŋk ju ˈvɛri mʌtʃ", level: "A1" },
  { text: "How are you?", phonetic: "haʊ ɑː juː", level: "A1" },
  { text: "I would like", phonetic: "aɪ wʊd laɪk", level: "A2" },
  { text: "Could you repeat that?", phonetic: "kʊd juː rɪˈpiːt ðæt", level: "A2" },
  { text: "Environmental sustainability", phonetic: "ɪnˌvaɪrənˈmɛntəl səˌsteɪnəˈbɪlɪti", level: "B2" },
];

interface PronunciationFeedback {
  accuracy: number;
  clarity: number;
  mistakes: string[];
  feedback: string;
  improved_version: string;
  user_text: string;
}

interface Attempt {
  text: string;
  feedback: PronunciationFeedback;
  timestamp: number;
}

export default function PronunciationPage() {
  const [language, setLanguage] = useState<Language>("fr");
  const [customText, setCustomText] = useState("");
  const [activeText, setActiveText] = useState<string | null>(null);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [levelFilter, setLevelFilter] = useState<string>("all");

  const samples = language === "fr" ? SAMPLE_WORDS_FR : SAMPLE_WORDS_EN;
  const filtered = levelFilter === "all" ? samples : samples.filter((s) => s.level === levelFilter);

  const levels = ["all", ...Array.from(new Set(samples.map((s) => s.level)))];

  const handleFeedback = useCallback((feedback: PronunciationFeedback) => {
    setAttempts((prev) => [
      { text: activeText ?? "", feedback, timestamp: Date.now() },
      ...prev.slice(0, 9),
    ]);
  }, [activeText]);

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = customText.trim();
    if (text) {
      setActiveText(text);
      setCustomText("");
    }
  };

  const scoreColor = (score: number) => {
    if (score >= 8) return "text-emerald-600";
    if (score >= 5) return "text-amber-600";
    return "text-red-600";
  };

  const scoreBg = (score: number) => {
    if (score >= 8) return "bg-emerald-50 border-emerald-200";
    if (score >= 5) return "bg-amber-50 border-amber-200";
    return "bg-red-50 border-red-200";
  };

  return (
    <TcfAppShell
      title="Pronunciation Practice"
      subtitle="Record, evaluate, and improve your French and English pronunciation"
      backHref="/tcf"
    >
      <div className="max-w-5xl space-y-6">
        {/* Language selector */}
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium text-slate-700">Language:</span>
          <div className="flex rounded-lg border border-slate-200 bg-white overflow-hidden">
            {(["fr", "en"] as Language[]).map((lang) => (
              <button
                key={lang}
                onClick={() => { setLanguage(lang); setActiveText(null); }}
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

        <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
          {/* Left: trainer area */}
          <div className="space-y-4">
            {/* Custom text input */}
            <Card className="border-slate-200 shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Practice any phrase</CardTitle>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleCustomSubmit} className="flex gap-2">
                  <input
                    type="text"
                    value={customText}
                    onChange={(e) => setCustomText(e.target.value)}
                    placeholder={language === "fr" ? "Type a French phrase…" : "Type an English phrase…"}
                    className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                  <button
                    type="submit"
                    disabled={!customText.trim()}
                    className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-40 transition"
                  >
                    Practice <ChevronRight className="h-4 w-4" />
                  </button>
                </form>
              </CardContent>
            </Card>

            {/* Active pronunciation trainer */}
            {activeText ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slate-700">Now practicing:</h3>
                  <button
                    onClick={() => setActiveText(null)}
                    className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition"
                  >
                    <RefreshCw className="h-3 w-3" /> Choose different
                  </button>
                </div>
                <div className="rounded-xl bg-slate-50 border border-slate-200 px-4 py-3 text-lg font-semibold text-slate-800">
                  {activeText}
                </div>
                <PronunciationTrainer
                  targetText={activeText}
                  language={language}
                  onFeedbackReceived={handleFeedback}
                />
              </div>
            ) : (
              <Card className="border-slate-200 shadow-sm border-dashed">
                <CardContent className="flex flex-col items-center justify-center py-12 text-slate-400 gap-3">
                  <Volume2 className="h-8 w-8" />
                  <p className="text-sm">Select a word below or type your own phrase above</p>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Right: sample words + history */}
          <div className="space-y-4">
            {/* Sample words */}
            <Card className="border-slate-200 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">Sample words</CardTitle>
                  <div className="flex gap-1">
                    {levels.map((lvl) => (
                      <button
                        key={lvl}
                        onClick={() => setLevelFilter(lvl)}
                        className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium transition ${
                          levelFilter === lvl
                            ? "bg-slate-800 text-white"
                            : "text-slate-500 hover:bg-slate-100"
                        }`}
                      >
                        {lvl === "all" ? "All" : lvl}
                      </button>
                    ))}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-2 pt-0">
                {filtered.map((sample) => (
                  <button
                    key={sample.text}
                    onClick={() => setActiveText(sample.text)}
                    className={`w-full text-left rounded-xl border px-3 py-2.5 transition ${
                      activeText === sample.text
                        ? "border-emerald-500 bg-emerald-50"
                        : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-800">{sample.text}</span>
                      <Badge variant="outline" className="text-[10px]">{sample.level}</Badge>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-0.5 font-mono">{sample.phonetic}</p>
                  </button>
                ))}
              </CardContent>
            </Card>

            {/* Recent attempts */}
            {attempts.length > 0 && (
              <Card className="border-slate-200 shadow-sm">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">Recent attempts</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 pt-0">
                  {attempts.slice(0, 5).map((attempt, i) => (
                    <div
                      key={i}
                      className={`rounded-xl border px-3 py-2.5 ${scoreBg(attempt.feedback.accuracy)}`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-slate-700 truncate max-w-[140px]">{attempt.text}</span>
                        <div className="flex gap-2 flex-shrink-0">
                          <span className={`text-xs font-bold ${scoreColor(attempt.feedback.accuracy)}`}>
                            A: {attempt.feedback.accuracy}/10
                          </span>
                          <span className={`text-xs font-bold ${scoreColor(attempt.feedback.clarity)}`}>
                            C: {attempt.feedback.clarity}/10
                          </span>
                        </div>
                      </div>
                      {attempt.feedback.mistakes.length > 0 && (
                        <p className="text-[11px] text-slate-500">{attempt.feedback.mistakes[0]}</p>
                      )}
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </TcfAppShell>
  );
}
