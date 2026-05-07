"use client";

import { useState } from "react";
import { Volume2, CheckCircle, AlertCircle, Loader } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import AudioRecorder from "@/components/AudioRecorder";

interface PronunciationFeedback {
  accuracy: number;
  clarity: number;
  mistakes: string[];
  feedback: string;
  improved_version: string;
  user_text: string;
}

interface PronunciationTrainerProps {
  targetText: string;
  language?: string;
  onFeedbackReceived?: (feedback: PronunciationFeedback) => void;
}

/** Play text via ElevenLabs (backend) with browser speechSynthesis as fallback. */
async function playAudio(text: string, language: string): Promise<void> {
  try {
    const res = await fetch(
      `/api/pronunciation/guide/${encodeURIComponent(text)}?language=${language}`
    );
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
    // Fallback: browser built-in TTS
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

const PronunciationTrainer = ({
  targetText,
  language = "fr",
  onFeedbackReceived,
}: PronunciationTrainerProps) => {
  const [step, setStep] = useState<"ready" | "recording" | "evaluating" | "results">("ready");
  const [feedback, setFeedback] = useState<PronunciationFeedback | null>(null);
  const [error, setError] = useState("");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);

  const handlePlayNative = async () => {
    if (isPlayingAudio) return;
    setIsPlayingAudio(true);
    setError("");
    try {
      await playAudio(targetText, language);
    } finally {
      setIsPlayingAudio(false);
    }
  };

  const evaluatePronunciation = async () => {
    if (!audioBlob) { setError("No audio recorded"); return; }
    setStep("evaluating");
    setError("");
    try {
      const formData = new FormData();
      formData.append("target_text", targetText);
      formData.append("audio_file", audioBlob, "recording.webm");
      formData.append("language", language);

      const response = await fetch("/api/pronunciation/evaluate", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error((errorData as { detail?: string }).detail || "Evaluation failed");
      }

      const result: PronunciationFeedback = await response.json();
      setFeedback(result);
      setStep("results");
      onFeedbackReceived?.(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation failed");
      setStep("recording");
    }
  };

  const resetTraining = () => {
    setStep("ready");
    setFeedback(null);
    setError("");
    setAudioBlob(null);
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex gap-2 items-center">
          <Volume2 className="h-5 w-5 text-emerald-600" />
          Pronunciation Trainer
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Target Text */}
        <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
          <p className="text-sm text-blue-600 mb-2">Pronounce this text:</p>
          <p className="text-xl font-semibold text-slate-900">{targetText}</p>
          <Button
            onClick={handlePlayNative}
            disabled={isPlayingAudio}
            variant="outline"
            size="sm"
            className="mt-3 flex gap-2"
          >
            {isPlayingAudio
              ? <><Loader className="h-4 w-4 animate-spin" /> Playing…</>
              : <><Volume2 className="h-4 w-4" /> Play Native Pronunciation</>
            }
          </Button>
        </div>

        {/* Audio Recorder */}
        {step !== "results" && (
          <AudioRecorder
            onAudioReady={(blob) => { setAudioBlob(blob); setStep("recording"); }}
            onRecordingChange={(rec) => { if (rec) setStep("recording"); }}
            maxDurationMs={15000}
          />
        )}

        {error && (
          <div className="flex gap-2 p-3 bg-red-50 rounded-lg text-red-700 text-sm">
            <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            {error}
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
            <span className="text-sm text-slate-600">Evaluating your pronunciation…</span>
          </div>
        )}

        {step === "results" && feedback && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-slate-100 rounded-lg">
                <p className="text-xs text-slate-600">Accuracy</p>
                <p className="text-2xl font-bold text-slate-900">{feedback.accuracy}/10</p>
              </div>
              <div className="p-3 bg-slate-100 rounded-lg">
                <p className="text-xs text-slate-600">Clarity</p>
                <p className="text-2xl font-bold text-slate-900">{feedback.clarity}/10</p>
              </div>
            </div>

            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
              <p className="text-xs text-slate-600 mb-1">You said:</p>
              <p className="text-sm text-slate-900 italic">&quot;{feedback.user_text}&quot;</p>
            </div>

            {feedback.mistakes.length > 0 && (
              <div className="p-3 bg-amber-50 rounded-lg border border-amber-200">
                <p className="text-xs text-amber-600 font-semibold mb-2">Mistakes detected:</p>
                <ul className="text-sm text-amber-700 space-y-1">
                  {feedback.mistakes.map((m, i) => <li key={i}>• {m}</li>)}
                </ul>
              </div>
            )}

            <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
              <p className="text-sm text-slate-900">{feedback.feedback}</p>
            </div>

            <div className="p-3 bg-green-50 rounded-lg border border-green-200">
              <p className="text-xs text-green-600 font-semibold mb-2">Correct Pronunciation:</p>
              <p className="text-sm text-slate-900 font-medium">{feedback.improved_version}</p>
            </div>

            <div className={`p-3 rounded-lg text-center ${
              feedback.accuracy >= 8 ? "bg-green-100 text-green-700"
              : feedback.accuracy >= 6 ? "bg-yellow-100 text-yellow-700"
              : "bg-red-100 text-red-700"
            }`}>
              <div className="flex gap-2 items-center justify-center">
                {feedback.accuracy >= 6
                  ? <CheckCircle className="h-4 w-4" />
                  : <AlertCircle className="h-4 w-4" />}
                <span className="font-semibold">
                  {feedback.accuracy >= 8 ? "Excellent pronunciation!"
                    : feedback.accuracy >= 6 ? "Good, but needs improvement"
                    : "Practice more for better results"}
                </span>
              </div>
            </div>

            <Button onClick={resetTraining} variant="outline" className="w-full">
              Try Again
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default PronunciationTrainer;
