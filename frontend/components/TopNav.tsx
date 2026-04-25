"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";

interface TopNavProps {
  title: string;
  subtitle?: string;
  backHref?: string;
}

export default function TopNav({ title, subtitle, backHref }: TopNavProps) {
  const router = useRouter();

  return (
    <div className="flex flex-wrap items-center gap-4 border-b border-slate-100 bg-white px-6 py-3.5">
      {backHref && (
        <button
          onClick={() => router.push(backHref)}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-400 transition-all duration-150 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-700"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
      )}
      <div className="flex-1">
        <h1 className="text-base font-semibold text-slate-900 leading-tight">{title}</h1>
        {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
      </div>
    </div>
  );
}
