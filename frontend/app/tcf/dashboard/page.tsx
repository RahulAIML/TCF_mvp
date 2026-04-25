"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  BookOpen, Headphones, Mic, PenSquare, Sparkles,
  TrendingUp, AlertTriangle, CheckCircle2,
  RefreshCw, ArrowRight, BarChart2, Activity, Zap,
  Award, Clock, Flame
} from "lucide-react";
import TcfAppShell from "@/components/TcfAppShell";
import DashboardCharts from "@/components/DashboardCharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { getDashboardSummary } from "@/services/api";
import type { DashboardSummaryResponse } from "@/types/dashboard";

/* ─── Helpers ──────────────────────────────────────────────────── */

function scoreColor(val: number, max = 100) {
  const pct = (val / max) * 100;
  if (pct >= 75) return "text-emerald-600";
  if (pct >= 50) return "text-amber-500";
  return "text-rose-500";
}

function scoreLabel(val: number, max = 100): { label: string; variant: "emerald" | "amber" | "rose" } {
  const pct = (val / max) * 100;
  if (pct >= 75) return { label: "On track", variant: "emerald" };
  if (pct >= 50) return { label: "Improving", variant: "amber" };
  return { label: "Needs work", variant: "rose" };
}

/* ─── Skeleton loader ───────────────────────────────────────────── */

function SkeletonCard() {
  return (
    <div className="rounded-2xl border border-slate-100 bg-white p-5 space-y-3 shadow-sm animate-pulse">
      <div className="h-3 w-24 rounded-full bg-slate-100" />
      <div className="h-8 w-16 rounded-lg bg-slate-100" />
      <div className="h-2 w-full rounded-full bg-slate-100" />
    </div>
  );
}

/* ─── Stat card ─────────────────────────────────────────────────── */

function StatCard({
  label, value, sub, icon: Icon, gradient, pct, badgeVariant, badgeLabel
}: {
  label: string;
  value: string;
  sub: string;
  icon: React.ComponentType<{ className?: string }>;
  gradient: string;
  pct?: number;
  badgeVariant?: "emerald" | "amber" | "rose";
  badgeLabel?: string;
}) {
  return (
    <Card className="relative overflow-hidden border-slate-100 shadow-sm hover:shadow-md transition-shadow duration-200">
      <div className={`absolute inset-x-0 top-0 h-0.5 ${gradient}`} />
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${gradient} text-white shadow-sm`}>
            <Icon className="h-5 w-5" />
          </div>
          {badgeVariant && badgeLabel && (
            <Badge variant={badgeVariant} className="text-[10px] px-2 py-0.5 mt-0.5">
              {badgeLabel}
            </Badge>
          )}
        </div>
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</p>
          <p className="mt-0.5 text-2xl font-bold text-slate-900 leading-tight">{value}</p>
          <p className="mt-0.5 text-xs text-slate-400">{sub}</p>
        </div>
        {pct !== undefined && (
          <Progress
            value={pct}
            className="mt-3 h-1.5"
            indicatorClassName={
              pct >= 75 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-400" : "bg-rose-400"
            }
          />
        )}
      </CardContent>
    </Card>
  );
}

/* ─── Module performance row ────────────────────────────────────── */

function ModuleRow({
  label, score, max, sessions, href, icon: Icon, barColor, dotGradient
}: {
  label: string; score: number; max: number; sessions: number;
  href: string; icon: React.ComponentType<{ className?: string }>;
  barColor: string; dotGradient: string;
}) {
  const pct = Math.min(100, (score / max) * 100);
  const { label: statusLabel, variant } = scoreLabel(score, max);
  return (
    <Link
      href={href}
      className="group flex items-center gap-4 rounded-xl px-3 py-3 transition-all duration-150 hover:bg-slate-50"
    >
      <div className={`h-9 w-9 flex-shrink-0 rounded-xl ${dotGradient} flex items-center justify-center shadow-sm`}>
        <Icon className="h-4 w-4 text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <span className="text-sm font-medium text-slate-700">{label}</span>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Badge variant={variant} className="text-[10px] px-1.5 py-0">{statusLabel}</Badge>
            <span className={`text-sm font-bold tabular-nums ${scoreColor(score, max)}`}>
              {score.toFixed(1)}{max === 10 ? "/10" : "%"}
            </span>
          </div>
        </div>
        <Progress value={pct} className="h-1.5" indicatorClassName={barColor} />
        <p className="mt-1 text-[11px] text-slate-400">
          {sessions} session{sessions !== 1 ? "s" : ""}
        </p>
      </div>
      <ArrowRight className="h-3.5 w-3.5 flex-shrink-0 text-slate-200 transition-all duration-150 group-hover:text-slate-400 group-hover:translate-x-0.5" />
    </Link>
  );
}

/* ─── Recommendation item ───────────────────────────────────────── */

function RecommendationItem({
  icon: Icon, iconClass, bgClass, title, body
}: {
  icon: React.ComponentType<{ className?: string }>;
  iconClass: string; bgClass: string;
  title: string; body: string;
}) {
  return (
    <div className={`flex gap-3 rounded-xl ${bgClass} p-3`}>
      <Icon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${iconClass}`} />
      <div>
        <p className={`text-xs font-semibold ${iconClass}`}>{title}</p>
        <p className={`text-xs mt-0.5 ${iconClass} opacity-80`}>{body}</p>
      </div>
    </div>
  );
}

/* ─── Main Page ─────────────────────────────────────────────────── */

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const fetchSummary = async () => {
    setLoading(true);
    setError("");
    try {
      setSummary(await getDashboardSummary());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void fetchSummary(); }, []);

  const overview = summary
    ? (() => {
        const r = summary.reading.average_accuracy;
        const l = summary.listening.average_accuracy;
        const w = summary.writing.average_score * 10;
        const le = (summary.learning.average_score ?? 0) * 10;
        const counts = [r, l, w, le].filter((v) => v > 0);
        const overall = counts.length ? counts.reduce((a, b) => a + b, 0) / counts.length : 0;
        const totalSessions =
          summary.reading.recent_exams.length +
          summary.listening.recent_exams.length +
          summary.writing.recent_submissions.length +
          summary.learning.recent_sessions.length;
        const weakModules = [
          { label: "Reading", val: r },
          { label: "Listening", val: l },
          { label: "Writing", val: w },
          { label: "AI Learn", val: le }
        ].filter((m) => m.val > 0).sort((a, b) => a.val - b.val);
        const strongModules = [...weakModules].sort((a, b) => b.val - a.val);
        return { overall, totalSessions, weakest: weakModules[0] ?? null, strongest: strongModules[0] ?? null };
      })()
    : null;

  return (
    <TcfAppShell title="TCF Dashboard" subtitle="Track your progress across all modules">
      <div className="max-w-6xl space-y-6">

        {/* Error banner */}
        {error && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* Loading skeleton */}
        {loading && !summary && (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[1, 2, 3, 4].map((i) => <SkeletonCard key={i} />)}
            </div>
            <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
              <div className="h-64 animate-pulse rounded-2xl bg-slate-100" />
              <div className="h-64 animate-pulse rounded-2xl bg-slate-100" />
            </div>
          </div>
        )}

        {summary && overview && (
          <>
            {/* ── KPI cards ── */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                label="Overall Score"
                value={`${overview.overall.toFixed(0)}%`}
                sub="Across all modules"
                icon={TrendingUp}
                gradient="bg-gradient-to-br from-indigo-500 to-indigo-600"
                pct={overview.overall}
              />
              <StatCard
                label="Sessions"
                value={String(overview.totalSessions)}
                sub="Total practice sessions"
                icon={Activity}
                gradient="bg-gradient-to-br from-teal-500 to-teal-600"
              />
              <StatCard
                label="Best Module"
                value={overview.strongest?.label ?? "—"}
                sub={overview.strongest ? `${overview.strongest.val.toFixed(0)}% score` : "Keep practicing"}
                icon={Award}
                gradient="bg-gradient-to-br from-emerald-500 to-emerald-600"
                badgeVariant="emerald"
                badgeLabel="Strongest"
              />
              <StatCard
                label="Focus Area"
                value={overview.weakest?.label ?? "—"}
                sub={overview.weakest ? `${overview.weakest.val.toFixed(0)}% score` : "All areas good"}
                icon={Zap}
                gradient="bg-gradient-to-br from-amber-500 to-amber-600"
                badgeVariant="amber"
                badgeLabel="Needs work"
              />
            </div>

            {/* ── Main content tabs ── */}
            <Tabs defaultValue="overview" className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <TabsList className="bg-white border border-slate-200 shadow-sm">
                  <TabsTrigger value="overview" className="gap-1.5">
                    <BarChart2 className="h-3.5 w-3.5" />
                    Overview
                  </TabsTrigger>
                  <TabsTrigger value="analytics" className="gap-1.5">
                    <Activity className="h-3.5 w-3.5" />
                    Analytics
                  </TabsTrigger>
                  <TabsTrigger value="history" className="gap-1.5">
                    <Clock className="h-3.5 w-3.5" />
                    History
                  </TabsTrigger>
                </TabsList>

                <button
                  onClick={() => void fetchSummary()}
                  disabled={loading}
                  className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 disabled:opacity-50"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                  Refresh
                </button>
              </div>

              {/* ── Overview tab ── */}
              <TabsContent value="overview">
                <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
                  {/* Module performance card */}
                  <Card className="border-slate-100 shadow-sm">
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between">
                        <div>
                          <CardTitle className="text-sm font-semibold text-slate-800">
                            Module Performance
                          </CardTitle>
                          <CardDescription className="text-xs">
                            Click a module to start practicing
                          </CardDescription>
                        </div>
                        <Badge variant="outline" className="text-xs text-slate-500 border-slate-200">
                          {overview.totalSessions} sessions total
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="divide-y divide-slate-50 pb-2">
                      <ModuleRow
                        label="Reading"
                        score={summary.reading.average_accuracy}
                        max={100}
                        sessions={summary.reading.recent_exams.length}
                        href="/tcf/reading"
                        icon={BookOpen}
                        barColor="bg-indigo-500"
                        dotGradient="bg-gradient-to-br from-indigo-500 to-indigo-600"
                      />
                      <ModuleRow
                        label="Listening"
                        score={summary.listening.average_accuracy}
                        max={100}
                        sessions={summary.listening.recent_exams.length}
                        href="/tcf/listening-exam"
                        icon={Headphones}
                        barColor="bg-teal-500"
                        dotGradient="bg-gradient-to-br from-teal-500 to-teal-600"
                      />
                      <ModuleRow
                        label="Writing"
                        score={summary.writing.average_score}
                        max={10}
                        sessions={summary.writing.recent_submissions.length}
                        href="/tcf/writing"
                        icon={PenSquare}
                        barColor="bg-amber-400"
                        dotGradient="bg-gradient-to-br from-amber-500 to-amber-600"
                      />
                      <ModuleRow
                        label="AI Learn"
                        score={summary.learning.average_score}
                        max={10}
                        sessions={summary.learning.recent_sessions.length}
                        href="/tcf/learn"
                        icon={Sparkles}
                        barColor="bg-emerald-500"
                        dotGradient="bg-gradient-to-br from-emerald-500 to-emerald-600"
                      />
                    </CardContent>
                  </Card>

                  {/* Recommendations card */}
                  <Card className="border-slate-100 shadow-sm">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                        <Flame className="h-4 w-4 text-orange-500" />
                        Smart Recommendations
                      </CardTitle>
                      <CardDescription className="text-xs">
                        AI-powered insights based on your performance
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-2.5">
                      {summary.reading.weakest_question_type &&
                       summary.reading.weakest_question_type !== "Not enough data" && (
                        <RecommendationItem
                          icon={AlertTriangle}
                          iconClass="text-rose-600"
                          bgClass="bg-rose-50"
                          title="Weak reading area"
                          body={summary.reading.weakest_question_type}
                        />
                      )}
                      {summary.reading.average_accuracy < 60 && (
                        <RecommendationItem
                          icon={AlertTriangle}
                          iconClass="text-amber-700"
                          bgClass="bg-amber-50"
                          title="Boost Reading accuracy"
                          body="Try the Passage Analyzer to build comprehension skills."
                        />
                      )}
                      {summary.writing.average_score < 6 && summary.writing.recent_submissions.length > 0 && (
                        <RecommendationItem
                          icon={AlertTriangle}
                          iconClass="text-amber-700"
                          bgClass="bg-amber-50"
                          title="Improve Writing score"
                          body="Use AI Learn to practice sentence structure and vocabulary."
                        />
                      )}
                      {summary.learning.recent_sessions.length === 0 && (
                        <RecommendationItem
                          icon={Sparkles}
                          iconClass="text-emerald-700"
                          bgClass="bg-emerald-50"
                          title="Try AI Learn"
                          body="Paste any French text to generate custom exercises."
                        />
                      )}
                      {overview.overall >= 75 && (
                        <RecommendationItem
                          icon={CheckCircle2}
                          iconClass="text-emerald-700"
                          bgClass="bg-emerald-50"
                          title="Excellent progress!"
                          body="Keep pushing with harder exam simulations."
                        />
                      )}
                      {summary.reading.recent_exams.length === 0 &&
                       summary.listening.recent_exams.length === 0 &&
                       summary.writing.recent_submissions.length === 0 &&
                       summary.learning.recent_sessions.length === 0 && (
                        <p className="text-sm text-slate-400 text-center py-6">
                          Complete a module to see recommendations.
                        </p>
                      )}
                    </CardContent>
                  </Card>
                </div>

                {/* Quick access cards */}
                <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  {[
                    { href: "/tcf/reading",        label: "Practice Reading",   icon: BookOpen,   gradient: "from-indigo-500 to-indigo-600",  sub: "Mock exam + Passage Analyzer" },
                    { href: "/tcf/listening-exam", label: "Practice Listening", icon: Headphones, gradient: "from-teal-500 to-teal-600",     sub: "Audio MCQ, A1-C2 levels"       },
                    { href: "/tcf/speaking",       label: "Practice Speaking",  icon: Mic,        gradient: "from-amber-500 to-amber-600",   sub: "Live examiner conversation"    },
                    { href: "/tcf/writing",        label: "Practice Writing",   icon: PenSquare,  gradient: "from-lime-500 to-lime-600",     sub: "3 guided writing tasks"        },
                  ].map((item) => {
                    const Icon = item.icon;
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        className="group flex flex-col gap-3 rounded-2xl border border-slate-100 bg-white p-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:border-slate-200"
                      >
                        <div className={`flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br ${item.gradient} text-white shadow-sm`}>
                          <Icon className="h-4 w-4" />
                        </div>
                        <div>
                          <p className="text-sm font-semibold text-slate-800">{item.label}</p>
                          <p className="text-xs text-slate-400 mt-0.5">{item.sub}</p>
                        </div>
                        <div className="flex items-center gap-1 text-xs font-medium text-slate-300 transition-colors group-hover:text-indigo-500">
                          Go practice
                          <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </TabsContent>

              {/* ── Analytics tab ── */}
              <TabsContent value="analytics">
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-slate-700">Detailed Analytics</p>
                    <Badge variant="outline" className="text-xs text-slate-400 border-slate-200">
                      Charts & trends
                    </Badge>
                  </div>
                  <DashboardCharts summary={summary} />
                </div>
              </TabsContent>

              {/* ── History tab ── */}
              <TabsContent value="history">
                <div className="grid gap-6 lg:grid-cols-2">
                  {/* Reading history */}
                  <Card className="border-slate-100 shadow-sm">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                        <BookOpen className="h-4 w-4 text-indigo-500" />
                        Reading Exams
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {summary.reading.recent_exams.length === 0 ? (
                        <p className="text-xs text-slate-400 py-4 text-center">No exams taken yet</p>
                      ) : (
                        summary.reading.recent_exams.slice(0, 5).map((exam) => (
                          <div key={exam.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2.5">
                            <div>
                              <p className="text-xs font-medium text-slate-700">Exam #{exam.id}</p>
                              <p className="text-[11px] text-slate-400">
                                Score: {exam.score} · {new Date(exam.created_at).toLocaleDateString()}
                              </p>
                            </div>
                            <Badge variant={exam.accuracy >= 75 ? "emerald" : exam.accuracy >= 50 ? "amber" : "rose"}>
                              {exam.accuracy.toFixed(0)}%
                            </Badge>
                          </div>
                        ))
                      )}
                    </CardContent>
                  </Card>

                  {/* Listening history */}
                  <Card className="border-slate-100 shadow-sm">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                        <Headphones className="h-4 w-4 text-teal-500" />
                        Listening Exams
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {summary.listening.recent_exams.length === 0 ? (
                        <p className="text-xs text-slate-400 py-4 text-center">No exams taken yet</p>
                      ) : (
                        summary.listening.recent_exams.slice(0, 5).map((exam) => (
                          <div key={exam.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2.5">
                            <div>
                              <p className="text-xs font-medium text-slate-700">Attempt #{exam.id}</p>
                              <p className="text-[11px] text-slate-400">
                                Score: {exam.score} · {new Date(exam.created_at).toLocaleDateString()}
                              </p>
                            </div>
                            <Badge variant={exam.accuracy >= 75 ? "emerald" : exam.accuracy >= 50 ? "amber" : "rose"}>
                              {exam.accuracy.toFixed(0)}%
                            </Badge>
                          </div>
                        ))
                      )}
                    </CardContent>
                  </Card>

                  {/* Writing history */}
                  <Card className="border-slate-100 shadow-sm">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                        <PenSquare className="h-4 w-4 text-amber-500" />
                        Writing Submissions
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {summary.writing.recent_submissions.length === 0 ? (
                        <p className="text-xs text-slate-400 py-4 text-center">No submissions yet</p>
                      ) : (
                        summary.writing.recent_submissions.slice(0, 5).map((item) => (
                          <div key={item.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2.5">
                            <div>
                              <p className="text-xs font-medium text-slate-700">Submission #{item.id}</p>
                              <p className="text-[11px] text-slate-400">
                                {new Date(item.created_at).toLocaleDateString()}
                              </p>
                            </div>
                            <Badge variant={item.average_score >= 7.5 ? "emerald" : item.average_score >= 5 ? "amber" : "rose"}>
                              {item.average_score.toFixed(1)}/10
                            </Badge>
                          </div>
                        ))
                      )}
                    </CardContent>
                  </Card>

                  {/* AI Learn history */}
                  <Card className="border-slate-100 shadow-sm">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                        <Sparkles className="h-4 w-4 text-emerald-500" />
                        AI Learn Sessions
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {summary.learning.recent_sessions.length === 0 ? (
                        <p className="text-xs text-slate-400 py-4 text-center">No sessions yet</p>
                      ) : (
                        summary.learning.recent_sessions.slice(0, 5).map((session) => (
                          <div key={session.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2.5">
                            <div className="min-w-0 flex-1 mr-2">
                              <p className="text-xs font-medium text-slate-700 truncate">
                                {session.topic ?? "Untitled session"}
                              </p>
                              <p className="text-[11px] text-slate-400">
                                {session.level ?? "—"} · {session.exercises_completed}/{session.exercises_total} exercises
                              </p>
                            </div>
                            {session.score != null && (
                              <Badge variant={session.score >= 7.5 ? "emerald" : session.score >= 5 ? "amber" : "rose"}>
                                {session.score.toFixed(1)}/10
                              </Badge>
                            )}
                          </div>
                        ))
                      )}
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>
            </Tabs>
          </>
        )}
      </div>
    </TcfAppShell>
  );
}
