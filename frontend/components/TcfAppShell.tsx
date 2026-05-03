"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import TcfSidebar from "@/components/TcfSidebar";
import TopNav from "@/components/TopNav";
import FloatingAIAssistant from "@/components/FloatingAIAssistant";
import {
  LayoutDashboard, BookOpen, Headphones, Mic, PenSquare, Sparkles, X
} from "lucide-react";

const mobileNavItems = [
  { href: "/tcf/learn",          label: "AI Learn",   icon: Sparkles,        color: "text-emerald-500" },
  { href: "/tcf/reading",        label: "Reading",    icon: BookOpen,        color: "text-indigo-500"  },
  { href: "/tcf/listening-exam", label: "Listening",  icon: Headphones,      color: "text-teal-500"    },
  { href: "/tcf/speaking",       label: "Speaking",   icon: Mic,             color: "text-amber-500"   },
  { href: "/tcf/writing",        label: "Writing",    icon: PenSquare,       color: "text-lime-500"    },
  { href: "/tcf/dashboard",      label: "Dashboard",  icon: LayoutDashboard, color: "text-violet-500"  }
];

const parentMap: Record<string, string> = {
  "/tcf/mock-exam":        "/tcf/reading",
  "/tcf/passage-analyzer": "/tcf/reading",
  "/tcf/reading-practice": "/tcf/reading"
};

interface TcfAppShellProps {
  title: string;
  subtitle?: string;
  backHref?: string;
  children: ReactNode;
}

export default function TcfAppShell({ title, subtitle, backHref, children }: TcfAppShellProps) {
  const pathname = usePathname();
  const activePath = parentMap[pathname] ?? pathname;
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Desktop sidebar (fixed positioning) */}
      <TcfSidebar />

      <div className="flex min-h-screen lg:ml-56">
        {/* Main content area with margin for fixed sidebar */}

        {/* Mobile drawer overlay */}
        {mobileOpen && (
          <div
            className="fixed inset-0 z-40 bg-slate-900/50 lg:hidden"
            onClick={() => setMobileOpen(false)}
          />
        )}

        {/* Mobile drawer */}
        <aside
          className={`fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 transition-transform duration-300 lg:hidden ${
            mobileOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500 text-white text-[10px] font-bold">
                TCF
              </div>
              <div>
                <p className="text-sm font-semibold text-white">TCF Canada</p>
                <p className="text-[10px] text-slate-500">Exam Preparation</p>
              </div>
            </div>
            <button
              onClick={() => setMobileOpen(false)}
              className="rounded-lg p-1.5 text-slate-400 hover:text-white transition"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <nav className="flex-1 space-y-1 px-3 py-4">
            {mobileNavItems.map((item) => {
              const isActive = activePath === item.href || pathname.startsWith(item.href + "/");
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileOpen(false)}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                    isActive
                      ? "bg-slate-800 text-white"
                      : "text-slate-400 hover:bg-slate-800/60 hover:text-white"
                  }`}
                >
                  <Icon className={`h-4 w-4 ${isActive ? item.color : "text-slate-500"}`} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </aside>

        {/* Main content area (with flex-1 since sidebar is now fixed) */}
        <div className="flex flex-1 flex-col min-w-0 w-full">
          <TopNav
            title={title}
            subtitle={subtitle}
            backHref={backHref}
            onMobileMenuClick={() => setMobileOpen(true)}
          />
          <main className="flex-1 p-4 sm:p-6">
            {children}
          </main>
        </div>
      </div>

      {/* Floating AI Assistant - Available on all pages */}
      <FloatingAIAssistant />
    </div>
  );
}
