"use client";

import { useState } from "react";
import { Volume2, CheckCircle, AlertCircle, Loader } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import AudioRecorder from "@/components/AudioRecorder";
import { streamPronunciationEvaluation } from "@/services/speakingApi";
import type { PronunciationEvalResult } from "@/types/tcf-speaking";

interface PronunciationTrainerProps {
  targetText: string;
  language?: string;
  onFeedbackReceived?: (feedback: PronunciationEvalResult) => void;
}

/** Native pronunciation from the backend (ElevenLabs/Gemini), browser speech synthesis as a fallback. */
async function playAudio(text: string, language: string): Promise<void> {
  try {
    const res = await fetch(`/api/pronunciation/guide/${encodeURIComponent(text)}?language=${language}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    return new Promise((resolve) => {
      audio.onended = () => { URL.revokeObjectURL(url); resolve(); };
      audio.onerror = () => { URL.revokeObjectURL(url); resolve(); };
      audio.play().catch(() => { URL.revokeObjectURL(url); resolve(); });
    });
  } catch {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      return new Promise((resolve) => {
        const utt = new SpeechSynthesisUtterance(text);
        utt.lang = language === "fr" ? "fr-FR" : "en-US";
        utt.rate = 0.9;
        utt.onend = () => resolve();
        utt.onerror = () => resolve();
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utt);
      });
    }
  }
}

type Step = "ready" | "recording" | "evaluating" | "results";

const PronunciationTrainer = ({ targetText, language = "fr", onFeedbackReceived }: PronunciationTrainerProps) => {
  const [step, setStep] = useState<Step>("ready");
  const [userText, setUserText] = useState("");
  const [feedbackText, setFeedbackText] = useState("");
  const [scores, setScores] = useState<PronunciationEvalResult | null>(null);
  const [noSpeech, setNoSpeech] = useState("");
  const [error, setError] = useState("");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [recorderKey, setRecorderKey] = useState(0);

  const handlePlayNative = async () => {
    if (isPlayingAudio) return;
    setIsPlayingAudio(true);
    try {
      await playAudio(targetText, language);
    } finally {
      setIsPlayingAudio(false);
    }
  };

  const evaluatePronunciation = async () => {
    if (!audioBlob) {
      setError("Record yourself first.");
      return;
    }
    setStep("evaluating");
    setError("");
    setNoSpeech("");
    setUserText("");
    setFeedbackText("");
    setScores(null);
    let finalScores: PronunciationEvalResult | null = null;
    let feedback = "";
    try {
      await streamPronunciationEvaluation(targetText, audioBlob, language, {
        onTranscript: (text) => { setUserText(text); setStep("results"); },
        onFeedbackToken: (token) => { feedback += token; setFeedbackText(feedback); },
        onScores: (s) => { finalScores = s; setScores(s); },
        onNoSpeech: (result) => { setNoSpeech(result.feedback); },
      });
      if (finalScores) {
        const result: PronunciationEvalResult = { ...(finalScores as PronunciationEvalResult), feedback: feedback.trim() };
        onFeedbackReceived?.(result);
        setStep("results");
      } else {
        setStep("recording");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation failed. Please try again.");
      setStep(audioBlob ? "recording" : "ready");
    }
  };

  const resetTraining = () => {
    setStep("ready");
    setScores(null);
    setUserText("");
    setFeedbackText("");
    setNoSpeech("");
    setError("");
    setAudioBlob(null);
    setRecorderKey((k) => k + 1);
  };

  const accuracy = scores?.accuracy ?? 0;

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex gap-2 items-center">
          <Volume2 className="h-5 w-5 text-emerald-600" />
          Pronunciation Trainer
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-6">
        <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
          <p className="text-sm text-blue-600 mb-2">Pronounce this text:</p>
          <p className="text-xl font-semibold text-slate-900">{targetText}</p>
          <Button onClick={handlePlayNative} disabled={isPlayingAudio} variant="outline" size="sm" className="mt-3 flex gap-2">
            {isPlayingAudio
              ? <><Loader className="h-4 w-4 animate-spin" /> Playing…</>
              : <><Volume2 className="h-4 w-4" /> Play Native Pronunciation</>}
          </Button>
        </div>

        {step !== "results" && step !== "evaluating" && (
          <AudioRecorder
            key={recorderKey}
            onAudioReady={(blob) => { setAudioBlob(blob); setStep("recording"); setNoSpeech(""); }}
            onRecordingChange={(rec) => { if (rec) { setStep("recording"); setAudioBlob(null); } }}
            maxDurationMs={15000}
          />
        )}

        {error && (
          <div className="flex gap-2 p-3 bg-red-50 rounded-lg text-red-700 text-sm">
            <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            {error}
          </div>
        )}

        {noSpeech && (
          <div className="flex gap-2 p-3 bg-amber-50 rounded-lg border border-amber-200 text-amber-800 text-sm">
            <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            {noSpeech}
          </div>
        )}

        {audioBlob && step === "recording" && (
          <Button onClick={evaluatePronunciation} className="w-full bg-emerald-600 hover:bg-emerald-700">
            Evaluate Pronunciation
          </Button>
        )}

        {step === "evaluating" && (
          <div className="flex items-center gap-3 p-4 bg-slate-50 rounded-lg">
            <Loader className="h-5 w-5 animate-spin text-emerald-600" />
            <span className="text-sm text-slate-600">Listening to your recording…</span>
          </div>
        )}

        {step === "results" && (
          <div className="space-y-4">
            {userText && (
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                <p className="text-xs text-slate-600 mb-1">You said:</p>
                <p className="text-sm text-slate-900 italic">&quot;{userText}&quot;</p>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              {[{ label: "Accuracy", value: scores?.accuracy }, { label: "Clarity", value: scores?.clarity }].map(({ label, value }) => (
                <div key={label} className="p-3 bg-slate-100 rounded-lg">
                  <p className="text-xs text-slate-600">{label}</p>
                  {value === undefined
                    ? <Loader className="mt-2 h-5 w-5 animate-spin text-slate-400" />
                    : <p className="text-2xl font-bold text-slate-900">{value}/10</p>}
                </div>
              ))}
            </div>

            {scores && scores.mistakes.length > 0 && (
              <div className="p-3 bg-amber-50 rounded-lg border border-amber-200">
                <p className="text-xs text-amber-600 font-semibold mb-2">Words to work on:</p>
                <ul className="text-sm text-amber-700 space-y-1">
                  {scores.mistakes.map((m, i) => <li key={i}>• {m}</li>)}
                </ul>
              </div>
            )}

            {feedbackText && (
              <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                <p className="text-sm text-slate-900">{feedbackText}</p>
              </div>
            )}

            {scores?.improved_version && (
              <div className="p-3 bg-green-50 rounded-lg border border-green-200">
                <p className="text-xs text-green-600 font-semibold mb-2">Correct Pronunciation:</p>
                <p className="text-sm text-slate-900 font-medium">{scores.improved_version}</p>
              </div>
            )}

            {scores && (
              <div className={`p-3 rounded-lg text-center ${
                accuracy >= 8 ? "bg-green-100 text-green-700" : accuracy >= 6 ? "bg-yellow-100 text-yellow-700" : "bg-red-100 text-red-700"
              }`}>
                <div className="flex gap-2 items-center justify-center">
                  {accuracy >= 6 ? <CheckCircle className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                  <span className="font-semibold">
                    {accuracy >= 8 ? "Excellent pronunciation!" : accuracy >= 6 ? "Good, but needs improvement" : "Practice more for better results"}
                  </span>
                </div>
              </div>
            )}

            <Button onClick={resetTraining} variant="outline" className="w-full" disabled={!scores && !error}>
              Try Again
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default PronunciationTrainer;
