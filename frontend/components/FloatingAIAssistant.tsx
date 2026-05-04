"use client";

import { useState, useRef, useEffect } from "react";
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
      content: "Bonjour! I'm your TCF/TEF French expert. Ask me anything about vocabulary, grammar, writing, speaking, or exam strategies. I always give direct answers. What can I help with?",
      timestamp: Date.now(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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

  // Intent routing: detect query type and determine response mode
  const detectIntent = (query: string): string => {
    const q = query.toLowerCase();

    // Vocabulary intent (translate, meaning, what is)
    if (q.match(/translate|meaning|what is|what's|definition|how do you say/i)) {
      return "vocabulary";
    }

    // Grammar intent (grammar, tense, rule, conjugation)
    if (q.match(/grammar|tense|conjugat|rule|agree|subject-verb|accord|subjonctif|conditionnel/i)) {
      return "grammar";
    }

    // Writing intent (correct, improve, rewrite, feedback)
    if (q.match(/correct|improve|rewrite|fix|feedback|mistake|error|wrong/i)) {
      return "writing";
    }

    // Speaking intent (how to say, speak, conversation, introduce, dialogue)
    if (q.match(/how to say|speak|conversation|introduce|hello|dialogue|pronounce|pronunciation/i)) {
      return "speaking";
    }

    // Listening/Reading intent (understand, listen, read, comprehend)
    if (q.match(/listen|understand|read|comprehend|passage|audio/i)) {
      return "listening";
    }

    return "general";
  };

  const generateMockResponse = (userInput: string): string => {
    const intent = detectIntent(userInput);
    const query = userInput.toLowerCase();

    // ============================================
    // VOCABULARY RESPONSES
    // ============================================
    if (intent === "vocabulary") {
      // "What is good morning in French?"
      if (query.includes("good morning")) {
        return "Good morning in French is **'Bonjour'**. It's used in both formal and informal situations (literally 'good day'). In evening, use 'Bonsoir'. Pronunciation: bon-ZHOOR.";
      }
      // "What is thank you in French?"
      if (query.includes("thank") || query.includes("merci")) {
        return "Thank you = **'Merci'** (formal: 'Merci beaucoup' = Thank you very much). Pronunciation: MAIR-see. For 'You're welcome': De rien (duh ree-YAN) or Je vous en prie (formal).";
      }
      // "Translate I am happy"
      if (query.includes("translate") && (query.includes("happy") || query.includes("i am"))) {
        return "**'Je suis heureux'** (masculine) or **'Je suis heureuse'** (feminine). Pronunciation: zhuh SWEE uh-RUH (m) / uh-RUZ (f). Example: 'Je suis heureux de vous rencontrer' = 'I'm happy to meet you'.";
      }
      // Generic word/vocabulary
      if (query.includes("word") || query.includes("vocabulary") || query.includes("meaning")) {
        return "To help with vocabulary, tell me the word or phrase you need translated. For example: 'What is cat in French?' or 'Translate: the blue house'. I'll give you the translation, pronunciation, and usage examples.";
      }
      return "I'm your French vocabulary expert. Ask me for translations, word meanings, pronunciation guides, or how to use words in sentences. For example: 'What is book in French?' or 'Translate: I love reading'.";
    }

    // ============================================
    // GRAMMAR RESPONSES
    // ============================================
    if (intent === "grammar") {
      // Passé composé
      if (query.includes("passé composé") || query.includes("passe compose")) {
        return "**Passé Composé** = past tense for completed actions.\n\nStructure: **avoir/être + past participle**\n\nExamples:\n- Je **suis allé** au marché (I went to the market)\n- J'**ai mangé** une pomme (I ate an apple)\n- Elle **est venue** hier (She came yesterday)\n\nUse 'être' with movement verbs (aller, venir, arriver, partir, entrer, sortir, monter, descendre, rester, naître, mourir).";
      }
      // Present tense / conjugation
      if (query.includes("conjugat") || query.includes("present") || query.includes("aller") || query.includes("être")) {
        return "French verbs change based on the subject pronoun:\n\n**Example (Aller = to go):**\n- Je vais (I go)\n- Tu vas (You go - informal)\n- Il/Elle/On va (He/She goes)\n- Nous allons (We go)\n- Vous allez (You go - formal/plural)\n- Ils/Elles vont (They go)\n\nTell me which verb or tense you want to learn!";
      }
      // Subject-verb agreement
      if (query.includes("agreement") || query.includes("accord")) {
        return "**Subject-Verb Agreement in French:**\nThe verb changes to match the subject pronoun.\n\n- Je suis (I am)\n- Tu es (You are - informal)\n- Il est (He is)\n- Elle est (She is)\n- Nous sommes (We are)\n- Vous êtes (You are - formal)\n- Ils sont (They are)\n\nEvery subject has a unique verb form. Practice recognizing which form matches which subject!";
      }
      // Generic grammar
      return "I'm your French grammar expert. Ask me about tenses (present, past, future), conjugations, verb groups, agreements, or any grammatical rules. For example: 'How do I conjugate avoir in passé composé?' or 'What's the difference between imparfait and passé composé?'.";
    }

    // ============================================
    // WRITING RESPONSES
    // ============================================
    if (intent === "writing") {
      // Correct: "je suis allé hier marché"
      if (query.includes("je suis allé") || query.includes("marche")) {
        return "**Corrected:** 'Je suis allé au marché hier.'\n\n**Explanation:**\n- 'au marché' (not 'marché') - needs article 'au' (à le)\n- Word order: place time at the end (hier)\n- Passé composé is correct: suis + allé (movement verb)\n\n**Natural sentence:** 'Je suis allé au marché hier pour acheter des fruits.' (I went to the market yesterday to buy fruit.)";
      }
      // Generic correction request
      return "Give me the French text you want corrected, and I'll fix it and explain the grammar. For example: 'Correct this: je vais a l'école demain'. I'll show you the correct version and explain the mistakes.";
    }

    // ============================================
    // SPEAKING RESPONSES
    // ============================================
    if (intent === "speaking") {
      // "How to introduce myself"
      if (query.includes("introduce") || query.includes("meet")) {
        return "**Basic French Introduction:**\n\n'Bonjour, je m'appelle [Your Name]. Enchanté(e). Je suis étudiant(e) en French. Ça va?' \n\n**Translation:** 'Hello, my name is [Your Name]. Pleased to meet you. I'm a French student. How are you?'\n\n**Natural flow:**\n- Bonjour (Hello)\n- Je m'appelle X (My name is X)\n- Enchanté(e) (Pleased to meet you - add e for female)\n- Et toi? (And you?)";
      }
      // "How to say" or "Speak" request
      if (query.includes("how to say") || query.includes("speak")) {
        return "Tell me the English phrase you want to say in French, and I'll give you:\n1. The French translation\n2. Pronunciation guide\n3. Example in context\n\nFor example: 'How do I say I'm studying French?' → 'Je suis en train d'étudier le français.'";
      }
      return "I can help you speak French naturally. Ask me for natural responses, conversations, or how to say specific phrases. For example: 'How do I ask for directions in French?' or 'What do I say in a restaurant?'.";
    }

    // ============================================
    // LISTENING/READING RESPONSES
    // ============================================
    if (intent === "listening") {
      return "For listening and reading comprehension, tell me:\n1. What you listened to or read\n2. What you don't understand\n3. What specific part confused you\n\nExample: 'In this passage, what does \"néanmoins\" mean?' I'll explain and give you similar usage patterns.";
    }

    // ============================================
    // GENERAL RESPONSES
    // ============================================
    // Default: always provide helpful guidance
    return "I'm your TCF/TEF French expert. I can help with:\n✓ Vocabulary & translations\n✓ Grammar & conjugations\n✓ Writing feedback\n✓ Speaking practice\n✓ Listening/reading tips\n\nJust ask directly! For example: 'Translate happy to French', 'Explain passé composé', or 'Correct this sentence'.";
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
          <CardTitle className="text-lg text-slate-900">French Expert</CardTitle>
          <p className="text-xs text-slate-500 mt-0.5">TCF/TEF Coach - Direct answers</p>
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
          <div ref={messagesEndRef} />
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
