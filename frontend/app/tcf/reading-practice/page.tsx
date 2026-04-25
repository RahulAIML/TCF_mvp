"use client";

import { useState } from "react";
import TcfAppShell from "@/components/TcfAppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { generateTcfQuestion, translatePassage } from "@/services/api";
import type { AnswerOption } from "@/types/exam";
import type { TcfExamQuestion } from "@/types/tcf-exam";

// Level → question number range mapping (6 CEFR levels)
const LEVEL_RANGES: Record<string, [number, number]> = {
  C2:  [1,  10],
  C1:  [11, 15],
  B2:  [16, 20],
  B1:  [21, 26],
  A2:  [31, 39],
  A1:  [31, 39], // Uses simplest available range
};

const LEVEL_LABELS: Record<string, string> = {
  C2:  "C2 — Advanced literary & analytical",
  C1:  "C1 — Complex argumentative texts",
  B2:  "B2 — Press articles & reports",
  B1:  "B1 — Informative documents",
  A2:  "A2 — Everyday documents",
  A1:  "A1 — Basic everyday documents",
};

const LEVEL_COLORS: Record<string, string> = {
  C2: "bg-rose-600",
  C1: "bg-orange-500",
  B2: "bg-amber-500",
  B1: "bg-emerald-600",
  A2: "bg-indigo-600",
  A1: "bg-slate-500",
};

function randomInRange(min: number, max: number) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

export default function ReadingPracticePage() {
  const [selectedLevel, setSelectedLevel] = useState<string | null>(null);
  const [question, setQuestion] = useState<TcfExamQuestion | null>(null);
  const [selectedAnswer, setSelectedAnswer] = useState<AnswerOption | "">("");
  const [revealed, setRevealed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Translation state
  const [translation, setTranslation] = useState("");
  const [showTranslation, setShowTranslation] = useState(false);
  const [isTranslating, setIsTranslating] = useState(false);

  const [count, setCount] = useState(0);
  const [correct, setCorrect] = useState(0);

  const loadQuestion = async (level: string) => {
    setLoading(true);
    setError("");
    setQuestion(null);
    setSelectedAnswer("");
    setRevealed(false);
    setTranslation("");
    setShowTranslation(false);

    const [min, max] = LEVEL_RANGES[level];
    const qNum = randomInRange(min, max);

    try {
      const q = await generateTcfQuestion({ question_number: qNum });
      setQuestion(q);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate question.");
    } finally {
      setLoading(false);
    }
  };

  const handleLevelSelect = (level: string) => {
    setSelectedLevel(level);
    void loadQuestion(level);
  };

  const handleAnswer = (value: AnswerOption) => {
    if (revealed) return;
    setSelectedAnswer(value);
  };

  const handleReveal = () => {
    if (!selectedAnswer || !question) return;
    setRevealed(true);
    setCount((c) => c + 1);
    if (selectedAnswer === question.correct_answer) setCorrect((c) => c + 1);
  };

  const handleNext = () => {
    if (selectedLevel) void loadQuestion(selectedLevel);
  };

  const handleTranslate = async () => {
    if (!question) return;
    if (translation) {
      setShowTranslation((p) => !p);
      return;
    }
    setIsTranslating(true);
    try {
      const result = await translatePassage(question.text);
      setTranslation(result);
      setShowTranslation(true);
    } catch {
      setError("Translation failed.");
    } finally {
      setIsTranslating(false);
    }
  };

  const accuracy = count > 0 ? Math.round((correct / count) * 100) : null;

  return (
    <TcfAppShell
      title="Reading Practice"
      subtitle="Select your level and practice one question at a time"
      backHref="/tcf/reading"
    >
      <div className="max-w-5xl space-y-6">
        {/* Level Selector */}
        <Card className="border-slate-200 shadow-sm">
          <CardContent className="p-6">
            <p className="mb-3 text-sm font-semibold text-slate-700">Select CEFR Level</p>
            <div className="flex flex-wrap gap-2">
              {Object.keys(LEVEL_RANGES).map((level) => (
                <button
                  key={level}
                  onClick={() => handleLevelSelect(level)}
                  disabled={loading}
                  className={`rounded-full px-4 py-1.5 text-sm font-semibold text-white transition-opacity ${LEVEL_COLORS[level]} ${
                    selectedLevel === level ? "ring-2 ring-offset-2 ring-slate-800" : "opacity-80 hover:opacity-100"
                  } disabled:opacity-50`}
                >
                  {level}
                </button>
              ))}
            </div>
            {selectedLevel && (
              <p className="mt-2 text-xs text-slate-500">{LEVEL_LABELS[selectedLevel]}</p>
            )}
          </CardContent>
        </Card>

        {/* Score Strip */}
        {count > 0 && (
          <div className="flex flex-wrap gap-4 rounded-2xl border border-slate-200 bg-slate-50 px-5 py-3">
            {[
              { label: "Attempted", val: count },
              { label: "Correct", val: correct },
              { label: "Accuracy", val: `${accuracy}%` },
            ].map(({ label, val }) => (
              <div key={label} className="text-center">
                <p className="text-xs uppercase text-slate-400">{label}</p>
                <p className="text-lg font-bold text-slate-900">{val}</p>
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        {loading && (
          <div className="rounded-2xl border border-slate-200 bg-white px-6 py-10 text-center text-sm text-slate-500 animate-pulse">
            Generating question...
          </div>
        )}

        {question && !loading && (
          <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
            {/* Main question column */}
            <div className="space-y-4">
              {/* Passage — French only; translation goes in the right panel */}
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold text-white ${LEVEL_COLORS[selectedLevel!]}`}>
                    {selectedLevel}
                  </span>
                  <button
                    onClick={() => void handleTranslate()}
                    disabled={isTranslating}
                    className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-indigo-600 hover:bg-indigo-50 transition-all duration-150 disabled:opacity-50"
                  >
                    {isTranslating ? (
                      <><span className="h-3 w-3 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin" />Translating…</>
                    ) : showTranslation && translation ? "Hide Translation →" : "Show Translation →"}
                  </button>
                </div>
                <p className="text-[10px] font-semibold uppercase text-slate-400 mb-2">Passage (French)</p>
                <p className="text-sm leading-7 text-slate-800">{question.text}</p>
              </div>

              {/* Question + Options */}
              <div className="space-y-3">
                <h3 className="text-base font-semibold text-slate-900">{question.question}</h3>
                <div className="space-y-2">
                  {question.options.map((option, index) => {
                    const value = (["A", "B", "C", "D"][index] as AnswerOption);
                    const isSelected = selectedAnswer === value;
                    const isCorrect = revealed && value === question.correct_answer;
                    const isWrong = revealed && isSelected && value !== question.correct_answer;
                    return (
                      <label
                        key={value}
                        onClick={() => handleAnswer(value)}
                        className={`group flex items-start gap-3 rounded-xl border px-3 py-3 text-sm transition-all duration-150 ${
                          isCorrect
                            ? "border-emerald-500 bg-emerald-50 text-emerald-800 cursor-default"
                            : isWrong
                            ? "border-rose-400 bg-rose-50 text-rose-800 cursor-default"
                            : isSelected
                            ? "border-indigo-600 bg-indigo-600 text-white cursor-default"
                            : "border-slate-200 bg-white text-slate-700 hover:border-indigo-200 hover:bg-indigo-50 cursor-pointer"
                        } ${revealed ? "cursor-default" : ""}`}
                      >
                        <input
                          type="radio"
                          name="practice-answer"
                          value={value}
                          checked={isSelected}
                          onChange={() => handleAnswer(value)}
                          disabled={revealed}
                          className="sr-only"
                        />
                        <span className={`flex-shrink-0 h-6 w-6 rounded-md text-xs font-bold flex items-center justify-center transition-colors ${
                          isCorrect ? "bg-emerald-100 text-emerald-700"
                            : isWrong ? "bg-rose-100 text-rose-700"
                            : isSelected ? "bg-white/20 text-white"
                            : "bg-slate-100 text-slate-600 group-hover:bg-indigo-100 group-hover:text-indigo-700"
                        }`}>
                          {value}
                        </span>
                        <span className="mt-0.5 flex-1">{option.replace(/^[A-D]\.\s*/, "")}</span>
                        {isCorrect && <span className="ml-auto font-bold text-emerald-600">✓</span>}
                        {isWrong && <span className="ml-auto font-bold text-rose-500">✗</span>}
                      </label>
                    );
                  })}
                </div>

                <div className="flex gap-3 pt-2">
                  {!revealed && (
                    <Button onClick={handleReveal} disabled={!selectedAnswer}>
                      Check Answer
                    </Button>
                  )}
                  {revealed && (
                    <Button onClick={handleNext}>
                      Next Question
                    </Button>
                  )}
                </div>
              </div>
            </div>

            {/* Right panel: translation + explanation */}
            <div className="space-y-4">
              {/* Translation panel — right side only, hidden by default */}
              {showTranslation && translation && (
                <Card className="border-indigo-200 bg-indigo-50 shadow-sm">
                  <CardContent className="p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="text-[10px] font-semibold uppercase tracking-wide text-indigo-500">English Translation</p>
                      <button
                        onClick={() => setShowTranslation(false)}
                        className="text-xs text-indigo-400 hover:text-indigo-600 transition"
                      >
                        ✕ Hide
                      </button>
                    </div>
                    <p className="text-sm leading-6 text-slate-700">{translation}</p>
                  </CardContent>
                </Card>
              )}

              {/* Answer explanation */}
              {revealed && (
                <Card className={`border shadow-sm ${selectedAnswer === question.correct_answer ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50"}`}>
                  <CardContent className="p-5 space-y-3">
                    <p className={`text-sm font-bold ${selectedAnswer === question.correct_answer ? "text-emerald-700" : "text-rose-700"}`}>
                      {selectedAnswer === question.correct_answer ? "✓ Correct!" : "✗ Incorrect"}
                    </p>
                    <p className="text-sm text-slate-700">
                      <span className="font-semibold">Correct Answer: </span>
                      {question.correct_answer}
                    </p>
                    {question.explanation && (
                      <div className="rounded-xl bg-white/70 px-4 py-3">
                        <p className="text-xs font-semibold uppercase text-slate-400 mb-1">Explanation</p>
                        <p className="text-sm text-slate-700">{question.explanation}</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {!selectedLevel && (
                <Card className="border-slate-200 shadow-sm">
                  <CardContent className="p-5">
                    <p className="text-sm font-semibold text-slate-700 mb-3">How it works</p>
                    <ul className="space-y-2 text-sm text-slate-500">
                      <li className="flex gap-2"><span className="text-slate-300">1.</span>Select a CEFR level above</li>
                      <li className="flex gap-2"><span className="text-slate-300">2.</span>Read the French passage</li>
                      <li className="flex gap-2"><span className="text-slate-300">3.</span>Use &quot;Show Translation →&quot; to reveal English in this panel</li>
                      <li className="flex gap-2"><span className="text-slate-300">4.</span>Answer and check immediately</li>
                      <li className="flex gap-2"><span className="text-slate-300">5.</span>Track your accuracy score</li>
                    </ul>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}
      </div>
    </TcfAppShell>
  );
}
