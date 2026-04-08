"use client";

import type { ReactNode } from "react";
import TcfSidebar from "@/components/TcfSidebar";
import TopNav from "@/components/TopNav";
import StudyAssistant from "@/components/GlobalAIChat";

interface TcfAppShellProps {
  title: string;
  subtitle-: string;
  backHref-: string;
  children: ReactNode;
}

export default function TcfAppShell({ title, subtitle, backHref, children }: TcfAppShellProps) {
  return (
    <div className="min-h-screen bg-slate-50">
      <div className="flex min-h-screen">
        <TcfSidebar />
        <div className="flex min-h-screen flex-1 flex-col">
          <TopNav title={title} subtitle={subtitle} backHref={backHref} />
          <main className="flex-1 p-6">
            {children}
          </main>
        </div>
      </div>
      <StudyAssistant />
    </div>
  );
}
