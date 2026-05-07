"use client";

import { useState } from "react";
import { Volume2, Loader, CheckCircle, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import AudioRecorder from "@/components/AudioRecorder";

interface PronunciationFeedback {
  accuracy: number; // 0-10
  clarity: number; // 0-10
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

/**
 * Pronunciation Training Component
 * Records user speech, evaluates against expected text, provides feedback
 */
const PronunciationTrainer = ({
  targetText,
  language = "fr",
  onFeedbackReceived,
}: PronunciationTrainerProps) => {
  const [step, setStep] = useState<"ready" | "recording" | "evaluating" | "results">(
    "ready"
  );
  const [feedback, setFeedback] = useState<PronunciationFeedback | null>(null);
  const [error, setError] = useState("");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);

  // Play native pronunciation
  const playNativePronunciation = async () => {
    try {
      const response = await fetch(
        `/api/pronunciation/guide/${encodeURIComponent(targetText)}?language=${language}`
      );

      if (!response.ok) throw new Error("Failed to generate audio");

      const data = await response.json();
      const audio = new Audio(data.audio_url);
      audio.play();
    } catch (err) {
      console.error("Failed to play pronunciation:", err);
      setError("Failed to generate pronunciation guide");
    }
  };

  // Evaluate pronunciation
  const evaluatePronunciation = async () => {
    if (!audioBlob) {
      setError("No audio recorded");
      return;
    }

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
        const errorData = await response.json();
        throw new Error(errorData.detail || "Evaluation failed");
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

  // Reset and try again
  const resetTraining = () => {
    setStep("ready");
    setFeedback(null);
    setError("");
    setAudioBlob(null);
  };

  const handleAudioReady = (blob: Blob) => {
    setAudioBlob(blob);
    setStep("recording");
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
            onClick={playNativePronunciation}
            variant="outline"
            size="sm"
            className="mt-3 flex gap-2"
          >
            <Volume2 className="h-4 w-4" />
            Play Native Pronunciation
          </Button>
        </div>

        {/* Audio Recorder */}
        {step !== "results" && (
          <AudioRecorder
            onAudioReady={handleAudioReady}
            onRecordingChange={(isRecording) => {
              if (isRecording) setStep("recording");
            }}
            maxDurationMs={15000}
          />
        )}

        {/* Error Display */}
        {error && (
          <div className="flex gap-2 p-3 bg-red-50 rounded-lg text-red-700 text-sm">
            <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            {error}
          </div>
        )}

        {/* Evaluate Button */}
        {audioBlob && step === "recording" && (
          <Button
            onClick={evaluatePronunciation}
            disabled={step === "evaluating"}
            className="w-full bg-emerald-600 hover:bg-emerald-700"
          >
            {step === "evaluating" ? (
              <>
                <Loader className="h-4 w-4 animate-spin mr-2" />
                Evaluating...
              </>
            ) : (
              "Evaluate Pronunciation"
            )}
          </Button>
        )}

        {/* Results Display */}
        {step === "results" && feedback && (
          <div className="space-y-4">
            {/* Scores */}
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-slate-100 rounded-lg">
                <p className="text-xs text-slate-600">Accuracy</p>
                <p className="text-2xl font-bold text-slate-900">
                  {feedback.accuracy}/10
                </p>
              </div>
              <div className="p-3 bg-slate-100 rounded-lg">
                <p className="text-xs text-slate-600">Clarity</p>
                <p className="text-2xl font-bold text-slate-900">
                  {feedback.clarity}/10
                </p>
              </div>
            </div>

            {/* What You Said */}
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
              <p className="text-xs text-slate-600 mb-1">You said:</p>
              <p className="text-sm text-slate-900 italic">
                &quot;{feedback.user_text}&quot;
              </p>
            </div>

            {/* Feedback */}
            {feedback.mistakes.length > 0 && (
              <div className="p-3 bg-amber-50 rounded-lg border border-amber-200">
                <p className="text-xs text-amber-600 font-semibold mb-2">
                  Mistakes detected:
                </p>
                <ul className="text-sm text-amber-700 space-y-1">
                  {feedback.mistakes.map((mistake, idx) => (
                    <li key={idx}>• {mistake}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Feedback Text */}
            <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
              <p className="text-sm text-slate-900">{feedback.feedback}</p>
            </div>

            {/* Improvement Guide */}
            <div className="p-3 bg-green-50 rounded-lg border border-green-200">
              <p className="text-xs text-green-600 font-semibold mb-2">
                Correct Pronunciation:
              </p>
              <p className="text-sm text-slate-900 font-medium">
                {feedback.improved_version}
              </p>
            </div>

            {/* Overall Assessment */}
            <div
              className={`p-3 rounded-lg text-center ${
                feedback.accuracy >= 8
                  ? "bg-green-100 text-green-700"
                  : feedback.accuracy >= 6
                    ? "bg-yellow-100 text-yellow-700"
                    : "bg-red-100 text-red-700"
              }`}
            >
              <div className="flex gap-2 items-center justify-center">
                {feedback.accuracy >= 6 ? (
                  <CheckCircle className="h-4 w-4" />
                ) : (
                  <AlertCircle className="h-4 w-4" />
                )}
                <span className="font-semibold">
                  {feedback.accuracy >= 8
                    ? "Excellent pronunciation!"
                    : feedback.accuracy >= 6
                      ? "Good, but needs improvement"
                      : "Practice more for better results"}
                </span>
              </div>
            </div>

            {/* Try Again Button */}
            <Button
              onClick={resetTraining}
              variant="outline"
              className="w-full"
            >
              Try Again
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default PronunciationTrainer;
