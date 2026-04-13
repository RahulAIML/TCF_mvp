"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { sendTcfWritingAssistant } from "@/services/api";
import type { TcfWritingAssistantAction, TcfWritingTranslationDirection } from "@/types/tcf-writing";

interface LearnAssistantPanelProps {
  passageText?: string;
  topic?: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

type ActionKey = TcfWritingAssistantAction | "ask";

const ACTIONS: { key: ActionKey; label: string; placeholder: string }[] = [
  { key: "ask",         label: "💬 Ask",        placeholder: "Ask anything about the passage or exercise..." },
  { key: "translate",   label: "🌐 Translate",   placeholder: "Paste French text to translate to English..." },
  { key: "grammar",     label: "✏️ Grammar",     placeholder: "Paste your French text to get grammar corrections..." },
  { key: "suggestions", label: "💡 Suggestions", placeholder: "Paste your answer to get improvement suggestions..." },
  { key: "example",     label: "📝 Example",     placeholder: "Describe the exercise and get a model answer..." },
];

export default function LearnAssistantPanel({ passageText, topic }: LearnAssistantPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content: "Bonjour! I'm your AI learning assistant. Ask me anything about the passage, get translations, grammar corrections, suggestions, or model answers.",
    },
  ]);
  const [input, setInput] = useState("");
  const [action, setAction] = useState<ActionKey>("ask");
  const [direction, setDirection] = useState<TcfWritingTranslationDirection>("fr-en");
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const context = passageText
    ? `Topic: ${topic ?? ""}.\n\nPassage:\n${passageText.slice(0, 1200)}`
    : topic
    ? `Topic: ${topic}`
    : undefined;

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    const userMsg: ChatMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      // "ask" uses suggestions action but with a free question framing
      const apiAction: TcfWritingAssistantAction =
        action === "ask" ? "suggestions" : (action as TcfWritingAssistantAction);

      const message =
        action === "ask"
          ? `Answer this question about the French passage or exercise:\n${text}`
          : text;

      const response = await sendTcfWritingAssistant({
        message,
        action: apiAction,
        direction: action === "translate" ? direction : undefined,
        context,
      });
      setMessages((prev) => [...prev, { role: "assistant", content: response.reply }]);
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Assistant failed. Please try again.";
      setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ ${errMsg}` }]);
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

  const currentAction = ACTIONS.find((a) => a.key === action)!;

  return (
    <Card className="border-indigo-200 shadow-sm flex flex-col h-full">
      <CardHeader className="pb-2 border-b border-indigo-100">
        <CardTitle className="flex items-center gap-2 text-base text-indigo-900">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-100 text-sm">🤖</span>
          AI Learning Assistant
        </CardTitle>
        <p className="text-xs text-slate-500 mt-1">Ask about the passage, get corrections, translations or model answers</p>
      </CardHeader>

      <CardContent className="flex flex-col gap-3 p-4 flex-1">
        {/* Mode selector */}
        <div className="flex flex-wrap gap-1.5">
          {ACTIONS.map((a) => (
            <button
              key={a.key}
              onClick={() => setAction(a.key)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                action === a.key
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>

        {/* Direction toggle for translate */}
        {action === "translate" && (
          <div className="flex gap-2">
            <button
              onClick={() => setDirection("fr-en")}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                direction === "fr-en" ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              FR → EN
            </button>
            <button
              onClick={() => setDirection("en-fr")}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                direction === "en-fr" ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              EN → FR
            </button>
          </div>
        )}

        {/* Chat messages */}
        <div className="flex-1 min-h-[220px] max-h-[340px] overflow-y-auto space-y-2 pr-1">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`rounded-xl px-3 py-2 text-sm ${
                msg.role === "user"
                  ? "bg-indigo-600 text-white ml-4"
                  : "bg-slate-100 text-slate-800 mr-4"
              }`}
            >
              <p className="text-[10px] uppercase tracking-wide opacity-60 mb-0.5">
                {msg.role === "user" ? "You" : "Assistant"}
              </p>
              <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
            </div>
          ))}
          {isLoading && (
            <div className="rounded-xl bg-slate-100 px-3 py-2 text-sm text-slate-500 mr-4 animate-pulse">
              Assistant is thinking...
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={currentAction.placeholder}
          rows={3}
          className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none"
        />

        <div className="flex items-center gap-2">
          <Button
            onClick={() => void handleSend()}
            disabled={!input.trim() || isLoading}
            className="bg-indigo-600 hover:bg-indigo-700 text-white"
          >
            {isLoading ? "Working..." : "Send"}
          </Button>
          {passageText && (
            <button
              onClick={() => setInput(passageText.slice(0, 600))}
              disabled={isLoading}
              className="text-xs text-indigo-500 hover:text-indigo-700 underline"
            >
              Use passage
            </button>
          )}
          {messages.length > 1 && (
            <button
              onClick={() =>
                setMessages([{
                  role: "assistant",
                  content: "Chat cleared. How can I help you?",
                }])
              }
              className="ml-auto text-xs text-slate-400 hover:text-slate-600 underline"
            >
              Clear chat
            </button>
          )}
        </div>
        <p className="text-[10px] text-slate-400">Press Enter to send · Shift+Enter for new line</p>
      </CardContent>
    </Card>
  );
}
