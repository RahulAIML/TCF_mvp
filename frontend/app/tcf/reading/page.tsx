"use client";

import Link from "next/link";
import { BookOpenCheck, FileSearch, ArrowRight, Clock, Target, Layers, GraduationCap } from "lucide-react";
import TcfAppShell from "@/components/TcfAppShell";
import { Card, CardContent } from "@/components/ui/card";

const modes = [
  {
    title: "Reading Mock Exam",
    description:
      "Simulate the full TCF Canada reading exam with 39 questions and a 60-minute countdown timer. Difficulty grouped by level.",
    href: "/tcf/mock-exam",
    icon: BookOpenCheck,
    accent: "bg-emerald-600",
    stats: [
      { icon: Clock, label: "60 minutes" },
      { icon: Target, label: "39 questions" },
      { icon: Layers, label: "C2 → A2" }
    ],
    cta: "Start Mock Exam"
  },
  {
    title: "Practice Mode",
    description:
      "Practice one question at a time. Choose your exact CEFR level (A2, B1, B2, C1, C2). Translation toggle included.",
    href: "/tcf/reading-practice",
    icon: GraduationCap,
    accent: "bg-indigo-600",
    stats: [
      { icon: Layers, label: "A2 – C2" },
      { icon: Target, label: "1 question at a time" },
      { icon: Clock, label: "No time limit" }
    ],
    cta: "Start Practice"
  },
  {
    title: "Passage Analyzer",
    description:
      "Generate a French passage, read it at your own pace, look up words, get instant explanations, and take a 10-question quiz.",
    href: "/tcf/passage-analyzer",
    icon: FileSearch,
    accent: "bg-teal-500",
    stats: [
      { icon: Target, label: "10 quiz questions" },
      { icon: Layers, label: "A1-C2 levels" },
      { icon: Clock, label: "No time limit" }
    ],
    cta: "Open Analyzer"
  }
];

export default function ReadingPage() {
  return (
    <TcfAppShell
      title="Reading Module"
      subtitle="Choose a reading practice mode"
      backHref="/tcf"
    >
      <div className="max-w-4xl space-y-6">
        <div className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
          <div className="flex flex-wrap items-start gap-6">
            {[
              { label: "C2",    range: "Q 1–10",  color: "bg-rose-100 text-rose-700" },
              { label: "C1/B2", range: "Q 11–20", color: "bg-amber-100 text-amber-700" },
              { label: "B1",    range: "Q 21–30", color: "bg-emerald-100 text-emerald-700" },
              { label: "A2/A1", range: "Q 31–39", color: "bg-indigo-100 text-indigo-700" },
            ].map(({ label, range, color }) => (
              <div key={label} className="flex items-center gap-2">
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${color}`}>{label}</span>
                <span className="text-xs text-slate-500">{range}</span>
              </div>
            ))}
            <p className="text-xs text-slate-400 ml-auto mt-0.5">Translation toggle available in all modes</p>
          </div>
        </div>

        <div className="grid gap-5 sm:grid-cols-3">
          {modes.map((mode) => {
            const Icon = mode.icon;
            return (
              <Card key={mode.href} className="group border-slate-200 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md">
                <CardContent className="flex flex-col gap-5 p-6">
                  <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${mode.accent} text-white shadow-sm`}>
                    <Icon className="h-5 w-5" />
                  </div>

                  <div>
                    <h2 className="font-semibold text-slate-900">{mode.title}</h2>
                    <p className="mt-1.5 text-sm leading-relaxed text-slate-500">{mode.description}</p>
                  </div>

                  <div className="flex flex-wrap gap-3">
                    {mode.stats.map(({ icon: StatIcon, label }) => (
                      <div key={label} className="flex items-center gap-1.5 rounded-lg bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600">
                        <StatIcon className="h-3.5 w-3.5 text-slate-400" />
                        {label}
                      </div>
                    ))}
                  </div>

                  <Link
                    href={mode.href}
                    className={`inline-flex items-center justify-center gap-2 rounded-xl ${mode.accent} px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-opacity hover:opacity-90`}
                  >
                    {mode.cta}
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </TcfAppShell>
  );
}
