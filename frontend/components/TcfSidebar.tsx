"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  BookOpen,
  Headphones,
  Mic,
  PenSquare,
  Sparkles,
  ChevronRight
} from "lucide-react";

const groups = [
  {
    label: "Core",
    items: [
      { href: "/tcf/learn", label: "AI Learn", icon: Sparkles }
    ]
  },
  {
    label: "TCF Modules",
    items: [
      { href: "/tcf/reading", label: "Reading", icon: BookOpen },
      { href: "/tcf/listening-exam", label: "Listening", icon: Headphones },
      { href: "/tcf/speaking", label: "Speaking", icon: Mic },
      { href: "/tcf/writing", label: "Writing", icon: PenSquare }
    ]
  },
  {
    label: "Analytics",
    items: [
      { href: "/tcf/dashboard", label: "Dashboard", icon: LayoutDashboard }
    ]
  }
];

const parentMap: Record<string, string> = {
  "/tcf/mock-exam": "/tcf/reading",
  "/tcf/passage-analyzer": "/tcf/reading",
  "/tcf/reading-practice": "/tcf/reading"
};

export default function TcfSidebar() {
  const pathname = usePathname();
  const activePath = parentMap[pathname] ?? pathname;

  return (
    <aside className="hidden w-56 flex-col bg-slate-900 lg:flex h-screen flex-shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-3 border-b border-slate-800 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500 text-white text-xs font-bold shadow-sm">
          TCF
        </div>
        <div>
          <p className="text-sm font-semibold text-white leading-tight">TCF Canada</p>
          <p className="text-[10px] text-slate-500">Exam Preparation</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-5">
        {groups.map((group) => (
          <div key={group.label}>
            <p className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-widest text-slate-600">
              {group.label}
            </p>
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const isActive = activePath === item.href || pathname.startsWith(item.href + "/");
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`group flex items-center justify-between rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150 ${
                      isActive
                        ? "bg-emerald-600 text-white"
                        : "text-slate-400 hover:bg-slate-800 hover:text-white"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <Icon className={`h-4 w-4 ${isActive ? "text-white" : "text-slate-500 group-hover:text-slate-300"}`} />
                      {item.label}
                    </div>
                    {isActive && <ChevronRight className="h-3 w-3 text-emerald-300" />}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-slate-800 px-5 py-4">
        <p className="text-[10px] text-slate-600">A1 – C2 · All levels covered</p>
      </div>
    </aside>
  );
}
