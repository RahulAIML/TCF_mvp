"use client";

import { useState } from "react";
import { MessageCircle, X, Send, Loader } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

export default function FloatingAIAssistant() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      role: "assistant",
      content: "Hello! I'm your TCF study assistant. Ask me anything about grammar, vocabulary, questions, or explanations. How can I help you today?",
      timestamp: Date.now(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSendMessage = async () => {
    if (!input.trim()) return;

    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    // Simulate AI response (integrate with actual API later)
    setTimeout(() => {
      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: generateMockResponse(input),
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, aiMessage]);
      setIsLoading(false);
    }, 1000);
  };

  const generateMockResponse = (userInput: string): string => {
    const input_lower = userInput.toLowerCase();

    if (input_lower.includes("grammar")) {
      return "Grammar is the set of structural rules that govern the composition of sentences, clauses, and phrases in a language. Key areas include: tenses, subject-verb agreement, word order, and parts of speech. What specific grammar topic would you like help with?";
    }
    if (input_lower.includes("vocab") || input_lower.includes("word")) {
      return "Building vocabulary takes consistent practice. Try: reading extensively, using context clues, and practicing with sentences. Would you like me to explain a specific word or help with vocabulary building strategies?";
    }
    if (input_lower.includes("question")) {
      return "MCQ questions test your comprehension. Remember to: read the passage/listen carefully, identify the main idea, eliminate wrong answers, and choose the best match. Which question type would you like help with?";
    }
    if (input_lower.includes("explain") || input_lower.includes("help")) {
      return "I'm here to help! You can ask me about: grammar rules, word meanings, question strategies, pronunciation tips, or writing feedback. What would you like to focus on?";
    }

    return "That's a great question! To give you the best answer, could you provide more context? For example: are you working on reading, listening, speaking, or writing?";
  };

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-40 h-14 w-14 rounded-full bg-emerald-600 text-white shadow-lg hover:bg-emerald-700 transition-all duration-200 flex items-center justify-center hover:scale-110"
        title="Open AI Assistant"
      >
        <MessageCircle className="h-6 w-6" />
      </button>
    );
  }

  return (
    <Card className="fixed bottom-6 right-6 z-40 w-96 max-h-[500px] shadow-2xl rounded-2xl border border-slate-200">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <div>
          <CardTitle className="text-lg text-slate-900">AI Assistant</CardTitle>
          <p className="text-xs text-slate-500 mt-0.5">Study help & explanations</p>
        </div>
        <button
          onClick={() => setIsOpen(false)}
          className="p-1 hover:bg-slate-100 rounded-lg transition"
          title="Close"
        >
          <X className="h-4 w-4 text-slate-400" />
        </button>
      </CardHeader>

      <CardContent className="flex flex-col h-[400px] p-4">
        {/* Messages area */}
        <div className="flex-1 overflow-y-auto space-y-3 mb-4 pr-2">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`rounded-xl px-3 py-2 max-w-xs text-sm ${
                  msg.role === "user"
                    ? "bg-emerald-600 text-white"
                    : "bg-slate-100 text-slate-800"
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-slate-100 rounded-xl px-3 py-2 flex items-center gap-1">
                <Loader className="h-3 w-3 animate-spin text-slate-500" />
                <span className="text-xs text-slate-500">Thinking...</span>
              </div>
            </div>
          )}
        </div>

        {/* Input area */}
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
            placeholder="Ask me anything..."
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            disabled={isLoading}
          />
          <button
            onClick={handleSendMessage}
            disabled={isLoading || !input.trim()}
            className="p-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition"
            title="Send"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </CardContent>
    </Card>
  );
}
