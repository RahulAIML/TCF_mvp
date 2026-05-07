"use client";

import Link from "next/link";
import {
  Sparkles,
  BookOpen,
  Headphones,
  Mic,
  PenSquare,
  LayoutDashboard,
  Volume2,
  BookMarked,
  ArrowRight,
} from "lucide-react";
import TcfAppShell from "@/components/TcfAppShell";

const modules = [
  {
    group: "Core",
    items: [
      {
        title: "AI Learn",
        description: "Paste text or upload a PDF — the platform builds exercises and tracks your progress.",
        href: "/tcf/learn",
        icon: Sparkles,
        accent: "bg-emerald-600",
        badge: "AI",
      },
    ],
  },
  {
    group: "TCF Canada Exam Modules",
    items: [
      {
        title: "Reading",
        description: "39-question mock exam + passage analyzer with CEFR-level progression.",
        href: "/tcf/reading",
        icon: BookOpen,
        accent: "bg-indigo-600",
      },
      {
        title: "Listening",
        description: "39 audio MCQs, progressive A1–C2. Audio plays once per question.",
        href: "/tcf/listening-exam",
        icon: Headphones,
        accent: "bg-teal-600",
      },
      {
        title: "Speaking",
        description: "Basic interaction, role-play, and opinion tasks with Gemini-powered feedback.",
        href: "/tcf/speaking",
        icon: Mic,
        accent: "bg-amber-600",
      },
      {
        title: "Writing",
        description: "3 guided tasks: short message, description, and opinion with justification.",
        href: "/tcf/writing",
        icon: PenSquare,
        accent: "bg-lime-600",
      },
    ],
  },
  {
    group: "Practice Modules",
    items: [
      {
        title: "Pronunciation",
        description: "Record yourself, get AI feedback on accuracy and clarity, replay native audio.",
        href: "/tcf/pronunciation",
        icon: Volume2,
        accent: "bg-pink-600",
        badge: "New",
      },
      {
        title: "Vocabulary Builder",
        description: "AI-generated daily vocabulary at your CEFR level with spaced repetition.",
        href: "/tcf/vocabulary",
        icon: BookMarked,
        accent: "bg-cyan-600",
        badge: "New",
      },
    ],
  },
  {
    group: "Analytics",
    items: [
      {
        title: "Dashboard",
        description: "Track scores, accuracy trends, weak areas and overall progress.",
        href: "/tcf/dashboard",
        icon: LayoutDashboard,
        accent: "bg-violet-600",
      },
    ],
  },
];

export default function TcfHomePage() {
  return (
    <TcfAppShell title="TCF Canada" subtitle="Choose a module to start training">
      <div className="space-y-10 max-w-5xl">
        {modules.map((group) => (
          <div key={group.group}>
            <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-slate-400">
              {group.group}
            </p>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {group.items.map((mod) => {
                const Icon = mod.icon;
                return (
                  <Link
                    key={mod.href}
                    href={mod.href}
                    className="group relative flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md"
                  >
                    <div className="flex items-start justify-between">
                      <div
                        className={`flex h-10 w-10 items-center justify-center rounded-xl ${mod.accent} text-white shadow-sm`}
                      >
                        <Icon className="h-5 w-5" />
                      </div>
                      {"badge" in mod && mod.badge && (
                        <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
                          {mod.badge}
                        </span>
                      )}
                    </div>

                    <div className="flex-1">
                      <h3 className="font-semibold text-slate-900">{mod.title}</h3>
                      <p className="mt-1 text-sm leading-relaxed text-slate-500">
                        {mod.description}
                      </p>
                    </div>

                    <div className="flex items-center gap-1 text-xs font-medium text-slate-400 transition-colors group-hover:text-slate-700">
                      Open module
                      <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}

        <p className="text-xs text-slate-400">
          Demo mode available — you can{" "}
          <Link href="/login" className="underline hover:text-slate-600">
            sign in
          </Link>{" "}
          to save progress across sessions.
        </p>
      </div>
    </TcfAppShell>
  );
}
