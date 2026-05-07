"use client";

import Link from "next/link";
import { BookOpen, Headphones, Mic, PenLine, Volume2, BookMarked, ArrowRight, CheckCircle } from "lucide-react";

const FEATURES = [
  { icon: BookOpen, label: "Reading", desc: "39-question mock exam with CEFR progression", color: "bg-blue-500" },
  { icon: Headphones, label: "Listening", desc: "39 audio MCQs, A1–C2 progressive difficulty", color: "bg-teal-500" },
  { icon: Mic, label: "Speaking", desc: "Gemini-powered conversation & feedback", color: "bg-amber-500" },
  { icon: PenLine, label: "Writing", desc: "Three tasks with AI step-by-step coaching", color: "bg-emerald-500" },
  { icon: Volume2, label: "Pronunciation", desc: "Record, score, and refine your French accent", color: "bg-pink-500" },
  { icon: BookMarked, label: "Vocabulary", desc: "Spaced repetition at A1–C2 levels", color: "bg-cyan-500" },
];

const BULLETS = [
  "Full TCF Canada mock exams — Reading, Listening, Writing, Speaking",
  "AI pronunciation scoring with mistake-by-mistake feedback",
  "Vocabulary builder with ElevenLabs native audio",
  "Progress auto-saved — resume any session where you left off",
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      {/* Nav */}
      <header className="border-b border-slate-100 px-6 py-4 flex items-center justify-between max-w-6xl mx-auto w-full">
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-emerald-500 flex items-center justify-center text-white font-bold text-xs">
            TCF
          </div>
          <span className="font-semibold text-slate-900">TCF Canada Prep</span>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="text-sm font-medium text-slate-600 hover:text-slate-900 transition"
          >
            Sign in
          </Link>
          <Link
            href="/register"
            className="text-sm font-semibold bg-emerald-600 text-white px-4 py-2 rounded-lg hover:bg-emerald-700 transition"
          >
            Get started free
          </Link>
        </div>
      </header>

      {/* Hero */}
      <main className="flex-1">
        <section className="max-w-6xl mx-auto px-6 pt-20 pb-16 text-center">
          <div className="inline-flex items-center gap-2 bg-emerald-50 text-emerald-700 text-xs font-semibold px-3 py-1.5 rounded-full mb-6">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            AI-powered TCF Canada preparation
          </div>
          <h1 className="text-4xl sm:text-5xl font-bold text-slate-900 mb-5 leading-tight tracking-tight">
            Pass your TCF Canada exam<br className="hidden sm:block" /> with confidence
          </h1>
          <p className="text-lg text-slate-500 mb-8 max-w-xl mx-auto">
            Practice all four skills — Reading, Listening, Speaking, and Writing — with Gemini AI feedback and real exam conditions.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              href="/register"
              className="flex items-center gap-2 bg-emerald-600 text-white text-sm font-semibold px-6 py-3 rounded-xl hover:bg-emerald-700 transition shadow-sm"
            >
              Create free account <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/login"
              className="flex items-center gap-2 border border-slate-200 text-slate-700 text-sm font-semibold px-6 py-3 rounded-xl hover:bg-slate-50 transition"
            >
              Sign in
            </Link>
          </div>
          <p className="text-xs text-slate-400 mt-4">
            No credit card required &middot;{" "}
            <Link href="/tcf" className="underline hover:text-slate-600">
              Continue without account
            </Link>
          </p>
        </section>

        {/* What's included bullets */}
        <section className="bg-slate-50 border-y border-slate-100 py-10">
          <div className="max-w-4xl mx-auto px-6 grid sm:grid-cols-2 gap-3">
            {BULLETS.map((b) => (
              <div key={b} className="flex items-start gap-2.5">
                <CheckCircle className="h-4 w-4 text-emerald-500 mt-0.5 flex-shrink-0" />
                <span className="text-sm text-slate-700">{b}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Feature grid */}
        <section className="max-w-6xl mx-auto px-6 py-16">
          <h2 className="text-2xl font-bold text-slate-900 text-center mb-10">Everything you need to prepare</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {FEATURES.map(({ icon: Icon, label, desc, color }) => (
              <div key={label} className="border border-slate-100 rounded-2xl p-5 hover:shadow-md transition">
                <div className={`h-10 w-10 rounded-xl ${color} flex items-center justify-center mb-4`}>
                  <Icon className="h-5 w-5 text-white" />
                </div>
                <h3 className="font-semibold text-slate-900 mb-1">{label}</h3>
                <p className="text-sm text-slate-500">{desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="bg-emerald-600 py-14 text-center px-6">
          <h2 className="text-2xl font-bold text-white mb-3">Ready to start practicing?</h2>
          <p className="text-emerald-100 text-sm mb-6">Create your free account and begin your first session in seconds.</p>
          <Link
            href="/register"
            className="inline-flex items-center gap-2 bg-white text-emerald-700 text-sm font-semibold px-6 py-3 rounded-xl hover:bg-emerald-50 transition shadow-sm"
          >
            Get started free <ArrowRight className="h-4 w-4" />
          </Link>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-100 py-6 text-center text-xs text-slate-400">
        © {new Date().getFullYear()} TCF Canada Prep &middot; Powered by Gemini AI
      </footer>
    </div>
  );
}
