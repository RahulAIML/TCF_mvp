"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft, Menu } from "lucide-react";
import Link from "next/link";

interface TopNavProps {
  title: string;
  subtitle?: string;
  backHref?: string;
  onMobileMenuClick?: () => void;
}

export default function TopNav({ title, subtitle, backHref, onMobileMenuClick }: TopNavProps) {
  const router = useRouter();

  return (
    <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-slate-100 bg-white/90 backdrop-blur-sm px-4 sm:px-6 py-3.5 shadow-sm">
      {/* Mobile hamburger */}
      <button
        onClick={onMobileMenuClick}
        className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-400 transition hover:bg-slate-50 hover:text-slate-700 lg:hidden"
        aria-label="Open navigation"
      >
        <Menu className="h-4 w-4" />
      </button>

      {/* Back button */}
      {backHref && (
        <button
          onClick={() => router.push(backHref)}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-400 transition-all duration-150 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-700"
          aria-label="Go back"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
      )}

      {/* Title */}
      <div className="flex-1 min-w-0">
        <h1 className="text-base font-semibold text-slate-900 leading-tight truncate">{title}</h1>
        {subtitle && (
          <p className="text-xs text-slate-400 mt-0.5 truncate">{subtitle}</p>
        )}
      </div>

      {/* Home breadcrumb */}
      <Link
        href="/tcf"
        className="hidden sm:flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
      >
        <span className="flex h-4 w-4 items-center justify-center rounded bg-emerald-500 text-white text-[8px] font-bold">T</span>
        Home
      </Link>
    </header>
  );
}
