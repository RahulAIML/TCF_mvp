"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Menu, LogOut, LogIn, ChevronDown } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";

interface TopNavProps {
  title: string;
  subtitle?: string;
  backHref?: string;
  onMobileMenuClick?: () => void;
}

export default function TopNav({ title, subtitle, backHref, onMobileMenuClick }: TopNavProps) {
  const router = useRouter();
  const { user, logout, isLoading } = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleLogout = () => {
    logout();
    setDropdownOpen(false);
    router.push("/login");
  };

  const displayName = user?.name || user?.email?.split("@")[0] || "User";
  const initials = displayName.slice(0, 2).toUpperCase();

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

      {/* Auth section */}
      {!isLoading && (
        user ? (
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setDropdownOpen((p) => !p)}
              className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-800"
              aria-expanded={dropdownOpen}
            >
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500 text-white text-[10px] font-bold flex-shrink-0">
                {initials}
              </span>
              <span className="hidden sm:block max-w-[120px] truncate">{displayName}</span>
              <ChevronDown className={`h-3 w-3 flex-shrink-0 transition-transform ${dropdownOpen ? "rotate-180" : ""}`} />
            </button>

            {dropdownOpen && (
              <div className="absolute right-0 top-full mt-2 w-48 rounded-xl border border-slate-200 bg-white shadow-lg py-1 z-50">
                <div className="px-3 py-2 border-b border-slate-100">
                  <p className="text-xs font-medium text-slate-900 truncate">{displayName}</p>
                  <p className="text-[11px] text-slate-500 truncate">{user.email}</p>
                </div>
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50 transition"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  Sign out
                </button>
              </div>
            )}
          </div>
        ) : (
          <Link
            href="/login"
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-500 transition hover:bg-emerald-50 hover:border-emerald-300 hover:text-emerald-700"
          >
            <LogIn className="h-3.5 w-3.5" />
            <span className="hidden sm:block">Sign in</span>
          </Link>
        )
      )}
    </header>
  );
}
