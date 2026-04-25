"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { sendTcfWritingAssistant } from "@/services/api";
import type {
  TcfWritingAssistantAction,
  TcfWritingTranslationDirection
} from "@/types/tcf-writing";

interface WritingAssistantPanelProps {
  contextLabel?: string;
  contextText?: string;
  draftText?: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

const ACTIONS: { key: TcfWritingAssistantAction; label: string; hint: string }[] = [
  { key: "grammar",     label: "Grammar",     hint: "Paste your French text for corrections" },
  { key: "translate",   label: "Translate",   hint: "Paste text to translate" },
  { key: "suggestions", label: "Improve",     hint: "Paste your writing for improvement tips" },
  { key: "example",     label: "Example",     hint: "Describe the task and get a model answer" },
];

export default function WritingAssistantPanel({
  contextLabel,
  contextText,
  draftText
}: WritingAssistantPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [action, setAction] = useState<TcfWritingAssistantAction>("grammar");
  const [direction, setDirection] = useState<TcfWritingTranslationDirection>("fr-en");
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const canUseDraft = Boolean(draftText?.trim());
  const assistantContext = useMemo(() => contextText?.trim() || undefined, [contextText]);
  const currentHint = ACTIONS.find((a) => a.key === action)?.hint ?? "";

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isLoading) return;
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setIsLoading(true);
    try {
      const response = await sendTcfWritingAssistant({
        message: text,
        action,
        direction: action === "translate" ? direction : undefined,
        context: assistantContext
      });
      setMessages((prev) => [...prev, { role: "assistant", content: response.reply }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Assistant failed to respond.";
      setMessages((prev) => [...prev, { role: "assistant", content: `⚠ ${msg}` }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  return (
    <Card className="border-slate-200 shadow-sm flex flex-col h-full">
      {/* Panel header */}
      <div className="border-b border-slate-100 px-4 py-3.5 flex items-center gap-2">
        <div className="h-6 w-6 rounded-md bg-indigo-100 flex items-center justify-center flex-shrink-0">
          <span className="text-[11px] font-bold text-indigo-600">W</span>
        </div>
        <div>
          <p className="text-sm font-semibold text-slate-800">Writing Support</p>
          <p className="text-[10px] text-slate-400">Grammar · Translation · Examples</p>
        </div>
      </div>

      <CardContent className="flex flex-col gap-3 p-4 flex-1 min-h-0">
        {/* Mode selector */}
        <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 gap-0.5">
          {ACTIONS.map((a) => (
            <button
              key={a.key}
              onClick={() => setAction(a.key)}
              className={`flex-1 rounded-md py-1.5 text-xs font-medium transition-all duration-150 ${
                action === a.key
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>

        {/* Translation direction */}
        {action === "translate" && (
          <div className="flex gap-1.5">
            {(["fr-en", "en-fr"] as TcfWritingTranslationDirection[]).map((d) => (
              <button
                key={d}
                onClick={() => setDirection(d)}
                className={`rounded-lg px-3 py-1 text-xs font-medium transition-all duration-150 ${
                  direction === d
                    ? "bg-indigo-600 text-white"
                    : "border border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                }`}
              >
                {d === "fr-en" ? "FR → EN" : "EN → FR"}
              </button>
            ))}
          </div>
        )}

        {/* Context badge */}
        {assistantContext && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-[10px] font-semibold uppercase text-slate-400 mb-0.5">
              {contextLabel ?? "Context"}
            </p>
            <p className="text-xs text-slate-600 line-clamp-2">{assistantContext}</p>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 min-h-[160px] max-h-[280px] overflow-y-auto space-y-2 pr-0.5">
          {messages.length === 0 && (
            <div className="flex h-full items-center justify-center py-8 text-center">
              <div>
                <p className="text-xs font-medium text-slate-500">Ask for help with your writing</p>
                <p className="text-[11px] text-slate-400 mt-1">{currentHint}</p>
              </div>
            </div>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`rounded-xl px-3 py-2.5 text-sm ${
                msg.role === "user"
                  ? "bg-indigo-600 text-white ml-4"
                  : "bg-slate-100 text-slate-800 mr-4"
              }`}
            >
              <p className="text-[10px] uppercase tracking-wide opacity-60 mb-0.5">
                {msg.role === "user" ? "You" : "Support"}
              </p>
              <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
            </div>
          ))}
          {isLoading && (
            <div className="rounded-xl bg-slate-100 px-3 py-2.5 mr-4">
              <div className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:0ms]" />
                <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:150ms]" />
                <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={currentHint}
          rows={3}
          className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100 transition resize-none"
        />

        <div className="flex items-center gap-2">
          <Button
            onClick={() => void handleSend()}
            disabled={!input.trim() || isLoading}
            className="bg-indigo-600 hover:bg-indigo-700 text-white"
            size="sm"
          >
            {isLoading ? "Working…" : "Send"}
          </Button>
          {canUseDraft && (
            <button
              onClick={() => setInput(draftText ?? "")}
              disabled={isLoading}
              className="text-xs text-indigo-500 hover:text-indigo-700 underline disabled:opacity-50 transition"
            >
              Use draft
            </button>
          )}
          {messages.length > 0 && (
            <button
              onClick={() => setMessages([])}
              className="ml-auto text-xs text-slate-400 hover:text-slate-600 transition"
            >
              Clear
            </button>
          )}
        </div>
        <p className="text-[10px] text-slate-400">Enter to send · Shift+Enter for new line</p>
      </CardContent>
    </Card>
  );
}
