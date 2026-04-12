"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

const ACTION_LABELS: Record<TcfWritingAssistantAction, string> = {
  translate: "Translate",
  grammar: "Grammar",
  suggestions: "Suggestions",
  example: "Example"
};

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

  const canUseDraft = Boolean(draftText && draftText.trim().length > 0);
  const assistantContext = useMemo(() => {
    if (!contextText) return undefined;
    return contextText.trim();
  }, [contextText]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    const userMessage: ChatMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
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
      const message = err instanceof Error ? err.message : "Assistant failed to respond.";
      setMessages((prev) => [...prev, { role: "assistant", content: message }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className="border-slate-200 shadow-sm h-full">
      <CardHeader>
        <CardTitle>AI Assistant</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Mode</p>
          <div className="flex flex-wrap gap-2">
            {(Object.keys(ACTION_LABELS) as TcfWritingAssistantAction[]).map((key) => (
              <Button
                key={key}
                size="sm"
                variant={action === key ? "default" : "outline"}
                onClick={() => setAction(key)}
              >
                {ACTION_LABELS[key]}
              </Button>
            ))}
          </div>
          {action === "translate" && (
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant={direction === "fr-en" ? "default" : "outline"}
                onClick={() => setDirection("fr-en")}
              >
                FR to EN
              </Button>
              <Button
                size="sm"
                variant={direction === "en-fr" ? "default" : "outline"}
                onClick={() => setDirection("en-fr")}
              >
                EN to FR
              </Button>
            </div>
          )}
        </div>

        {assistantContext && (
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
            <p className="font-semibold text-slate-700">Context</p>
            <p className="mt-1 line-clamp-4">{contextLabel ? `${contextLabel}: ` : ""}{assistantContext}</p>
          </div>
        )}

        <div className="space-y-2 max-h-[320px] overflow-y-auto pr-1">
          {messages.length === 0 && (
            <p className="text-sm text-slate-500">Ask for translations, corrections, suggestions, or examples.</p>
          )}
          {messages.map((msg, index) => (
            <div
              key={`msg-${index}`}
              className={msg.role === "user"
                ? "rounded-xl bg-indigo-600 text-white px-3 py-2 text-sm"
                : "rounded-xl bg-slate-100 text-slate-700 px-3 py-2 text-sm"}
            >
              <p className="text-xs uppercase tracking-wide opacity-70">
                {msg.role === "user" ? "You" : "Assistant"}
              </p>
              <p className="mt-1 whitespace-pre-wrap">{msg.content}</p>
            </div>
          ))}
          {isLoading && (
            <div className="rounded-xl bg-slate-100 text-slate-700 px-3 py-2 text-sm">
              Assistant is thinking...
            </div>
          )}
        </div>

        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type your request or paste your text..."
          rows={4}
          className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300 resize-none"
        />

        <div className="flex flex-wrap gap-2">
          <Button onClick={handleSend} disabled={!input.trim() || isLoading}>
            {isLoading ? "Working..." : "Send"}
          </Button>
          {canUseDraft && (
            <Button
              variant="secondary"
              onClick={() => setInput(draftText ?? "")}
              disabled={isLoading}
            >
              Use Current Draft
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
