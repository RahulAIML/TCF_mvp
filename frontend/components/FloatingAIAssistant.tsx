"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { MessageCircle, X, Send, Loader, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

function renderMarkdown(md: string): React.ReactNode {
  const lines = md.split("\n");
  const nodes: React.ReactNode[] = [];
  let listItems: string[] = [];

  const flushList = () => {
    if (listItems.length) {
      nodes.push(
        <ul key={`ul-${nodes.length}`} className="list-disc list-outside ml-4 space-y-0.5 my-1">
          {listItems.map((item, i) => (
            <li key={i}>{inlineFormat(item)}</li>
          ))}
        </ul>
      );
      listItems = [];
    }
  };

  const inlineFormat = (text: string): React.ReactNode => {
    // bold + italic pass — split on ** and *
    const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**"))
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      if (part.startsWith("*") && part.endsWith("*"))
        return <em key={i}>{part.slice(1, -1)}</em>;
      return part;
    });
  };

  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (/^[*-] /.test(trimmed)) {
      listItems.push(trimmed.replace(/^[*-] /, ""));
    } else {
      flushList();
      if (!trimmed) {
        if (nodes.length) nodes.push(<div key={`sp-${idx}`} className="h-1" />);
      } else {
        nodes.push(<p key={idx}>{inlineFormat(trimmed)}</p>);
      }
    }
  });
  flushList();
  return <>{nodes}</>;
}

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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  const handleOpen = useCallback(() => {
    // Clear stale conversation state when re-opening after a long gap
    setIsOpen(true);
  }, []);

  const handleClear = useCallback(() => {
    setMessages([WELCOME]);
  }, []);

  const handleSendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE_URL}/ai/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        cache: "no-store",
      });

      if (!res.ok) throw new Error(`Status ${res.status}`);

      const data = await res.json() as { response: string };
      const aiMsg: Message = {
        id: `a-${Date.now()}`,
        role: "assistant",
        content: data.response,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch {
      const errMsg: Message = {
        id: `e-${Date.now()}`,
        role: "assistant",
        content: "Connection error. Please check the server and try again.",
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage();
      }
    },
    [handleSendMessage]
  );

  if (!isOpen) {
    return (
      <button
        onClick={handleOpen}
        className="fixed bottom-6 right-6 z-40 h-14 w-14 rounded-full bg-emerald-600 text-white shadow-lg hover:bg-emerald-700 transition-all duration-200 flex items-center justify-center hover:scale-110"
        title="Open French Expert Assistant"
        aria-label="Open AI assistant"
      >
        <MessageCircle className="h-6 w-6" />
      </button>
    );
  }

  return (
    <Card className="fixed bottom-6 right-6 z-40 w-96 shadow-2xl rounded-2xl border border-slate-200 flex flex-col overflow-hidden"
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
        {/* Messages area */}
        <div className="flex-1 overflow-y-auto space-y-3 mb-4 pr-1 min-h-0">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`rounded-xl px-3 py-2 text-sm leading-relaxed break-words ${
                  msg.role === "user"
                    ? "bg-emerald-600 text-white max-w-[85%] whitespace-pre-wrap"
                    : "bg-slate-100 text-slate-800 max-w-[90%]"
                }`}
              >
                {msg.role === "assistant" ? renderMarkdown(msg.content) : msg.content}
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-slate-100 rounded-xl px-3 py-2 flex items-center gap-2">
                <Loader className="h-3 w-3 animate-spin text-slate-500" />
                <span className="text-xs text-slate-500">Thinking…</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Quick suggestions */}
        {messages.length === 1 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {["Translate 'bonjour'", "What is passé composé?", "Formal vs informal"].map((s) => (
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

        {/* Input area */}
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
            onClick={handleSendMessage}
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
