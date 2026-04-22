"use client";

import { useState } from "react";
import TcfAppShell from "@/components/TcfAppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { generateTcfQuestion, translatePassage } from "@/services/api";
import type { AnswerOption } from "@/types/exam";
import type { TcfExamQuestion } from "@/types/tcf-exam";

// Level → question number range mapping
const LEVEL_RANGES: Record<string, [number, number]> = {
  C2:     [1,  10],
  C1:     [11, 15],
  B2:     [16, 20],
  B1:     [21, 26],
  A2:     [31, 39],
};

const LEVEL_LABELS: Record<string, string> = {
  C2:  "C2 — Advanced literary & analytical",
  C1:  "C1 — Complex argumentative texts",
  B2:  "B2 — Press articles & reports",
  B1:  "B1 — Informative documents",
  A2:  "A2 — Everyday documents",
};

const LEVEL_COLORS: Record<string, string> = {
  C2: "bg-rose-600",
  C1: "bg-orange-500",
  B2: "bg-amber-500",
  B1: "bg-emerald-600",
  A2: "bg-indigo-600",
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
              {/* Passage with translation toggle */}
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold text-white ${LEVEL_COLORS[selectedLevel!]}`}>
                    {selectedLevel}
                  </span>
                  <button
                    onClick={() => void handleTranslate()}
                    disabled={isTranslating}
                    className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-indigo-600 hover:bg-indigo-50 transition disabled:opacity-50"
                  >
                    {isTranslating ? "Translating..." : showTranslation ? "Hide Translation" : "Show Translation"}
                  </button>
                </div>

                {/* Side-by-side layout when translation is shown */}
                <div className={showTranslation && translation ? "grid grid-cols-2 gap-4" : ""}>
                  <div>
                    <p className="text-[10px] font-semibold uppercase text-slate-400 mb-2">Passage (French)</p>
                    <p className="text-sm leading-7 text-slate-800">{question.text}</p>
                  </div>
                  {showTranslation && translation && (
                    <div className="border-l border-indigo-100 pl-4">
                      <p className="text-[10px] font-semibold uppercase text-indigo-400 mb-2">Translation (English)</p>
                      <p className="text-sm leading-7 text-slate-600">{translation}</p>
                    </div>
                  )}
                </div>
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
                        className={`flex cursor-pointer items-start gap-3 rounded-xl border px-4 py-3 text-sm transition ${
                          isCorrect
                            ? "border-emerald-500 bg-emerald-50 text-emerald-800"
                            : isWrong
                            ? "border-rose-400 bg-rose-50 text-rose-800"
                            : isSelected
                            ? "border-emerald-600 bg-emerald-600 text-white"
                            : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"
                        } ${revealed ? "cursor-default" : "cursor-pointer"}`}
                      >
                        <input
                          type="radio"
                          name="practice-answer"
                          value={value}
                          checked={isSelected}
                          onChange={() => handleAnswer(value)}
                          disabled={revealed}
                          className="mt-1"
                        />
                        <span>{option}</span>
                        {isCorrect && <span className="ml-auto font-semibold">✓</span>}
                        {isWrong && <span className="ml-auto font-semibold">✗</span>}
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

            {/* Explanation sidebar */}
            <div className="space-y-4">
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
                    <p className="text-sm font-medium text-slate-700">How it works</p>
                    <ul className="mt-3 space-y-2 text-sm text-slate-500">
                      <li>• Select a CEFR level above</li>
                      <li>• Read the French passage</li>
                      <li>• Use &quot;Show Translation&quot; if needed</li>
                      <li>• Answer and check immediately</li>
                      <li>• Track your accuracy score</li>
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
