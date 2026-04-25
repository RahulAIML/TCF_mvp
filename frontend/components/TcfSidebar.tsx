"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  BookOpen,
  Headphones,
  Mic,
  PenSquare,
  Sparkles,
  ChevronRight,
  ChevronLeft,
  GraduationCap
} from "lucide-react";

const groups = [
  {
    label: "Core",
    items: [
      { href: "/tcf/learn", label: "AI Learn", icon: Sparkles, color: "text-emerald-400" }
    ]
  },
  {
    label: "TCF Modules",
    items: [
      { href: "/tcf/reading",       label: "Reading",   icon: BookOpen,        color: "text-indigo-400" },
      { href: "/tcf/listening-exam",label: "Listening", icon: Headphones,      color: "text-teal-400"   },
      { href: "/tcf/speaking",      label: "Speaking",  icon: Mic,             color: "text-amber-400"  },
      { href: "/tcf/writing",       label: "Writing",   icon: PenSquare,       color: "text-lime-400"   }
    ]
  },
  {
    label: "Analytics",
    items: [
      { href: "/tcf/dashboard", label: "Dashboard", icon: LayoutDashboard, color: "text-violet-400" }
    ]
  }
];

const parentMap: Record<string, string> = {
  "/tcf/mock-exam":         "/tcf/reading",
  "/tcf/passage-analyzer":  "/tcf/reading",
  "/tcf/reading-practice":  "/tcf/reading"
};

export default function TcfSidebar() {
  const pathname = usePathname();
  const activePath = parentMap[pathname] ?? pathname;
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={`hidden lg:flex flex-col bg-slate-900 h-screen flex-shrink-0 transition-all duration-300 ease-in-out relative ${
        collapsed ? "w-16" : "w-56"
      }`}
    >
      {/* Logo */}
      <div className={`flex items-center gap-3 border-b border-slate-800/70 py-5 ${collapsed ? "justify-center px-2" : "px-5"}`}>
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-emerald-500 text-white text-[10px] font-bold shadow-sm">
          TCF
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white leading-tight truncate">TCF Canada</p>
            <p className="text-[10px] text-slate-500 truncate">Exam Preparation</p>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden py-4 px-2 space-y-5">
        {groups.map((group) => (
          <div key={group.label}>
            {!collapsed && (
              <p className="mb-1.5 px-2 text-[9px] font-semibold uppercase tracking-widest text-slate-600">
                {group.label}
              </p>
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const isActive = activePath === item.href || pathname.startsWith(item.href + "/");
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    title={collapsed ? item.label : undefined}
                    className={`group flex items-center rounded-lg text-sm font-medium transition-all duration-150 ${
                      collapsed ? "justify-center p-2.5" : "gap-3 px-3 py-2.5"
                    } ${
                      isActive
                        ? "bg-slate-800 text-white"
                        : "text-slate-400 hover:bg-slate-800/60 hover:text-white"
                    }`}
                  >
                    <Icon
                      className={`h-4 w-4 flex-shrink-0 transition-colors ${
                        isActive
                          ? item.color
                          : "text-slate-500 group-hover:text-slate-300"
                      }`}
                    />
                    {!collapsed && (
                      <>
                        <span className="flex-1 truncate">{item.label}</span>
                        {isActive && (
                          <ChevronRight className="h-3 w-3 flex-shrink-0 text-slate-500" />
                        )}
                      </>
                    )}
                    {collapsed && isActive && (
                      <span className="absolute left-14 rounded-md bg-slate-700 px-2 py-1 text-xs text-white opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 transition-opacity">
                        {item.label}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed((p) => !p)}
        className="absolute -right-3 top-[72px] flex h-6 w-6 items-center justify-center rounded-full border border-slate-700 bg-slate-800 text-slate-400 shadow-md transition-all hover:bg-slate-700 hover:text-white z-10"
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? (
          <ChevronRight className="h-3 w-3" />
        ) : (
          <ChevronLeft className="h-3 w-3" />
        )}
      </button>

      {/* Footer */}
      <div className={`border-t border-slate-800/70 py-4 ${collapsed ? "px-2 text-center" : "px-5"}`}>
        {collapsed ? (
          <GraduationCap className="h-4 w-4 text-slate-600 mx-auto" />
        ) : (
          <p className="text-[10px] text-slate-600">A1 – C2 · All levels covered</p>
        )}
      </div>
    </aside>
  );
}
