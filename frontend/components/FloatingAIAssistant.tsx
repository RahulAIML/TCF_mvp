"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { MessageCircle, X, Send, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MarkdownText } from "@/lib/markdown";
import { streamSSE } from "@/lib/sse";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  isError?: boolean;
}

const MAX_HISTORY = 16;

const WELCOME: Message = {
  id: "welcome",
  role: "assistant",
  content: "Bonjour! I'm your French expert. Ask me anything — translations, grammar, pronunciation, TCF tips. I give direct answers.",
  timestamp: Date.now(),
};

export default function FloatingAIAssistant() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const handleClear = useCallback(() => {
    abortRef.current?.abort();
    setMessages([WELCOME]);
    setIsLoading(false);
  }, []);

  const handleSendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    const history = messages
      .filter((m) => m.id !== WELCOME.id && !m.isError && m.content.trim())
      .slice(-MAX_HISTORY)
      .map(({ role, content }) => ({ role, content }));

    const userMsg: Message = { id: `u-${Date.now()}`, role: "user", content: text, timestamp: Date.now() };
    const aiMsgId = `a-${Date.now()}`;
    setMessages((prev) => [...prev, userMsg, { id: aiMsgId, role: "assistant", content: "", timestamp: Date.now() }]);
    setInput("");
    setIsLoading(true);

    const controller = new AbortController();
    abortRef.current = controller;
    const update = (fn: (m: Message) => Message) =>
      setMessages((prev) => prev.map((m) => (m.id === aiMsgId ? fn(m) : m)));

    try {
      await streamSSE(
        "/api/ai/chat/stream",
        { message: text, history },
        (event) => {
          if (typeof event.token === "string") {
            const token = event.token;
            update((m) => ({ ...m, content: m.content + token }));
          } else if (typeof event.error === "string") {
            const error = event.error;
            update((m) => ({ ...m, content: m.content || error, isError: !m.content }));
          }
        },
        controller.signal
      );
    } catch (err) {
      if (controller.signal.aborted) return;
      const message = err instanceof Error ? err.message : "Connection problem. Please try again.";
      update((m) => ({ ...m, content: message, isError: true }));
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setIsLoading(false);
      }
    }
  }, [input, isLoading, messages]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void handleSendMessage();
      }
    },
    [handleSendMessage]
  );

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-40 h-14 w-14 rounded-full bg-emerald-600 text-white shadow-lg hover:bg-emerald-700 transition-all duration-200 flex items-center justify-center hover:scale-110"
        title="Open French Expert Assistant"
        aria-label="Open AI assistant"
      >
        <MessageCircle className="h-6 w-6" />
      </button>
    );
  }

  return (
    <Card className="fixed bottom-6 right-6 z-40 w-96 max-w-[calc(100vw-3rem)] shadow-2xl rounded-2xl border border-slate-200 flex flex-col overflow-hidden"
      style={{ maxHeight: "min(520px, calc(100vh - 96px))" }}>
      <CardHeader className="flex flex-row items-center justify-between pb-3 flex-shrink-0">
        <div>
          <CardTitle className="text-base text-slate-900">French Expert</CardTitle>
          <p className="text-[11px] text-slate-500 mt-0.5">TCF/TEF Coach · Direct answers</p>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleClear}
            className="p-1.5 hover:bg-slate-100 rounded-lg transition text-slate-400 hover:text-slate-600"
            title="Clear chat"
            aria-label="Clear conversation"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="p-1.5 hover:bg-slate-100 rounded-lg transition text-slate-400 hover:text-slate-600"
            title="Close"
            aria-label="Close assistant"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </CardHeader>

      <CardContent className="flex flex-col flex-1 min-h-0 p-4 pt-0">
        <div className="flex-1 overflow-y-auto space-y-3 mb-4 pr-1 min-h-0" aria-live="polite">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`rounded-xl px-3 py-2 text-sm leading-relaxed break-words ${
                  msg.role === "user"
                    ? "bg-emerald-600 text-white max-w-[85%] whitespace-pre-wrap"
                    : msg.isError
                      ? "bg-rose-50 text-rose-700 border border-rose-100 max-w-[90%]"
                      : "bg-slate-100 text-slate-800 max-w-[90%]"
                }`}
              >
                {msg.role === "assistant" && msg.content === "" && isLoading ? (
                  <span className="flex items-center gap-1 py-0.5" aria-label="Assistant is typing">
                    {[0, 150, 300].map((delay) => (
                      <span
                        key={delay}
                        className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce"
                        style={{ animationDelay: `${delay}ms` }}
                      />
                    ))}
                  </span>
                ) : msg.role === "assistant" ? (
                  <MarkdownText text={msg.content} />
                ) : (
                  msg.content
                )}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {messages.length === 1 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {["Translate 'bonjour'", "Qu'est-ce que le passé composé ?", "Formal vs informal"].map((s) => (
              <button
                key={s}
                onClick={() => { setInput(s); inputRef.current?.focus(); }}
                className="text-[11px] rounded-full border border-slate-200 px-2.5 py-1 text-slate-500 hover:border-emerald-400 hover:text-emerald-700 transition"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        <div className="flex gap-2 flex-shrink-0">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything in French or English…"
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 min-w-0"
            disabled={isLoading}
            aria-label="Message input"
          />
          <button
            onClick={() => void handleSendMessage()}
            disabled={isLoading || !input.trim()}
            className="p-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-40 transition flex-shrink-0"
            title="Send message"
            aria-label="Send"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </CardContent>
    </Card>
  );
}
