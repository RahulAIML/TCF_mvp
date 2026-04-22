"use client";

import { useEffect, useRef } from "react";
import { Card, CardContent } from "@/components/ui/card";
import type { TcfConversationMessage } from "@/types/tcf-speaking";

interface SpeakingChatProps {
  history: TcfConversationMessage[];
  isThinking?: boolean;
  currentTranscript?: string;
  exchangeCount?: number;
  maxExchanges?: number;
}

export default function SpeakingChat({
  history,
  isThinking,
  currentTranscript,
  exchangeCount,
  maxExchanges
}: SpeakingChatProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, isThinking]);

  return (
    <Card className="rounded-2xl border-slate-200 shadow-sm">
      <CardContent className="p-5 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Conversation</h3>
          <div className="flex items-center gap-2">
            {maxExchanges !== undefined && exchangeCount !== undefined && (
              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-500">
                {exchangeCount} / {maxExchanges} turns
              </span>
            )}
            {isThinking && (
              <span className="flex items-center gap-1.5 rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-600">
                <span className="h-1.5 w-1.5 rounded-full bg-indigo-500 animate-pulse" />
                Examiner is responding
              </span>
            )}
          </div>
        </div>

        {/* Messages */}
        <div className="max-h-[420px] space-y-3 overflow-y-auto pr-1 scroll-smooth">
          {history.length === 0 && !isThinking && (
            <p className="py-6 text-center text-sm text-slate-400">
              The examiner will speak first — press Start Practice or Start Exam to begin.
            </p>
          )}

          {history.map((message, index) => {
            const isExaminer = message.role !== "user";
            return (
              <div
                key={`${message.role}-${index}`}
                className={`flex gap-2 ${isExaminer ? "justify-start" : "justify-end"}`}
              >
                {/* Examiner avatar */}
                {isExaminer && (
                  <div className="flex-shrink-0 mt-0.5">
                    <div className="h-7 w-7 rounded-full bg-indigo-100 flex items-center justify-center">
                      <span className="text-[11px] font-bold text-indigo-700">E</span>
                    </div>
                  </div>
                )}

                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                    isExaminer
                      ? "rounded-tl-sm bg-indigo-50 text-slate-800 border border-indigo-100"
                      : "rounded-tr-sm bg-slate-800 text-white"
                  }`}
                >
                  <p className={`text-[10px] font-semibold uppercase tracking-wide mb-1 ${
                    isExaminer ? "text-indigo-400" : "text-slate-400"
                  }`}>
                    {isExaminer ? "Examiner" : "You"}
                  </p>
                  <p className="whitespace-pre-line">{message.content}</p>
                </div>

                {/* User avatar */}
                {!isExaminer && (
                  <div className="flex-shrink-0 mt-0.5">
                    <div className="h-7 w-7 rounded-full bg-slate-200 flex items-center justify-center">
                      <span className="text-[11px] font-bold text-slate-600">U</span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}

          {/* Thinking indicator */}
          {isThinking && (
            <div className="flex gap-2 justify-start">
              <div className="flex-shrink-0 mt-0.5">
                <div className="h-7 w-7 rounded-full bg-indigo-100 flex items-center justify-center">
                  <span className="text-[11px] font-bold text-indigo-700">E</span>
                </div>
              </div>
              <div className="rounded-2xl rounded-tl-sm border border-indigo-100 bg-indigo-50 px-4 py-2.5">
                <div className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-indigo-400 animate-bounce [animation-delay:0ms]" />
                  <span className="h-2 w-2 rounded-full bg-indigo-400 animate-bounce [animation-delay:150ms]" />
                  <span className="h-2 w-2 rounded-full bg-indigo-400 animate-bounce [animation-delay:300ms]" />
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Last transcript */}
        {currentTranscript && (
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1">Last Transcript</p>
            <p className="text-slate-700">{currentTranscript}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
