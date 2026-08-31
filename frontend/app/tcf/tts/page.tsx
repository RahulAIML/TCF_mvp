"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, MicOff, Loader2, Volume2, Download, RotateCcw, CheckCircle2, AlertCircle, AudioLines, Type } from "lucide-react";
import {
  evaluatePronunciationAudio,
  generateTts,
  getTtsVoices,
  transcribeAudio,
  type PronunciationEvalResult,
} from "@/services/api";
import type { TtsVoice } from "@/types/tts";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MAX_CHARS = 2000;
const MAX_RECORD_MS = 60_000;

type InputMode = "type" | "record";
type RecordState = "idle" | "recording" | "recorded";

function ScoreCircle({ value, label, color }: { value: number; label: string; color: string }) {
  const pct = Math.round((value / 10) * 100);
  const radius = 28;
  const circ = 2 * Math.PI * radius;
  const dash = (pct / 100) * circ;
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r={radius} fill="none" stroke="#334155" strokeWidth="6" />
        <circle
          cx="36"
          cy="36"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
          transform="rotate(-90 36 36)"
        />
        <text x="36" y="40" textAnchor="middle" fill="white" fontSize="14" fontWeight="700">
          {value.toFixed(1)}
        </text>
      </svg>
      <span className="text-xs text-slate-400 font-medium">{label}</span>
    </div>
  );
}

function MistakesHighlight({ text, mistakes }: { text: string; mistakes: string[] }) {
  if (!mistakes.length) return <p className="text-slate-300 text-sm">{text}</p>;
  const lower = mistakes.map((m) => m.toLowerCase());
  const words = text.split(/(\s+)/);
  return (
    <p className="text-slate-300 text-sm leading-relaxed">
      {words.map((w, i) => {
        const isWrong = lower.includes(w.toLowerCase().replace(/[.,!?;:]/g, ""));
        return isWrong ? (
          <mark key={i} className="bg-red-900/60 text-red-200 rounded px-0.5">
            {w}
          </mark>
        ) : (
          <span key={i}>{w}</span>
        );
      })}
    </p>
  );
}

export default function TtsPage() {
  const [voices, setVoices] = useState<TtsVoice[]>([]);
  const [selectedVoice, setSelectedVoice] = useState("fr-FR-male-1");
  const [inputMode, setInputMode] = useState<InputMode>("type");
  const [text, setText] = useState("");

  // Recording
  const [recordState, setRecordState] = useState<RecordState>("idle");
  const [recordBlob, setRecordBlob] = useState<Blob | null>(null);
  const [recordUrl, setRecordUrl] = useState<string | null>(null);
  const [recordSecs, setRecordSecs] = useState(0);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Transcription
  const [transcribing, setTranscribing] = useState(false);
  const [transcriptError, setTranscriptError] = useState("");

  // TTS generation
  const [generating, setGenerating] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [ttsError, setTtsError] = useState("");

  // Evaluation
  const [evaluating, setEvaluating] = useState(false);
  const [evalResult, setEvalResult] = useState<PronunciationEvalResult | null>(null);
  const [evalError, setEvalError] = useState("");

  useEffect(() => {
    getTtsVoices()
      .then((v) => {
        setVoices(v);
        if (v.length) setSelectedVoice(v[0].id);
      })
      .catch(() => {});
  }, []);

  // --- Recording ---

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm;codecs=opus" });
        setRecordBlob(blob);
        setRecordUrl(URL.createObjectURL(blob));
        setRecordState("recorded");
      };
      mr.start(100);
      mediaRef.current = mr;
      setRecordSecs(0);
      setRecordState("recording");
      timerRef.current = setInterval(() => {
        setRecordSecs((s) => {
          if (s + 1 >= MAX_RECORD_MS / 1000) {
            stopRecording();
            return s + 1;
          }
          return s + 1;
        });
      }, 1000);
    } catch {
      setTranscriptError("Microphone access denied. Please allow microphone in your browser.");
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (mediaRef.current && mediaRef.current.state !== "inactive") {
      mediaRef.current.stop();
    }
  }, []);

  const resetRecording = useCallback(() => {
    stopRecording();
    setRecordBlob(null);
    setRecordUrl(null);
    setRecordState("idle");
    setRecordSecs(0);
    setTranscriptError("");
    setEvalResult(null);
    setEvalError("");
  }, [stopRecording]);

  const handleTranscribe = useCallback(async () => {
    if (!recordBlob) return;
    setTranscribing(true);
    setTranscriptError("");
    try {
      const { transcript } = await transcribeAudio(recordBlob);
      setText(transcript);
    } catch (e: unknown) {
      setTranscriptError(e instanceof Error ? e.message : "Transcription failed");
    } finally {
      setTranscribing(false);
    }
  }, [recordBlob]);

  // --- TTS generation ---

  const handleGenerate = useCallback(async () => {
    if (!text.trim()) return;
    setGenerating(true);
    setTtsError("");
    setAudioUrl(null);
    setEvalResult(null);
    setEvalError("");
    try {
      const res = await generateTts({ text, voice_id: selectedVoice });
      setAudioUrl(`${API_BASE_URL}${res.audio_url}`);
    } catch (e: unknown) {
      setTtsError(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  }, [text, selectedVoice]);

  const handleDownload = useCallback(async () => {
    if (!audioUrl) return;
    const r = await fetch(audioUrl);
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `tts_${selectedVoice}.mp3`;
    a.click();
  }, [audioUrl, selectedVoice]);

  // --- Pronunciation evaluation ---

  const handleEvaluate = useCallback(async () => {
    if (!recordBlob || !text.trim()) return;
    setEvaluating(true);
    setEvalError("");
    setEvalResult(null);
    try {
      const result = await evaluatePronunciationAudio(text, recordBlob);
      setEvalResult(result);
    } catch (e: unknown) {
      setEvalError(e instanceof Error ? e.message : "Evaluation failed");
    } finally {
      setEvaluating(false);
    }
  }, [recordBlob, text]);

  const overallScore = evalResult ? (evalResult.accuracy + evalResult.clarity) / 2 : null;
  const scoreColor = overallScore === null ? "#64748b"
    : overallScore >= 8 ? "#22c55e"
    : overallScore >= 5 ? "#f59e0b"
    : "#ef4444";

  const formatSecs = (s: number) => `${Math.floor(s / 60).toString().padStart(2, "0")}:${(s % 60).toString().padStart(2, "0")}`;

  const canEvaluate = !!recordBlob && !!text.trim();
  const canGenerate = !!text.trim() && !generating;

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <AudioLines className="w-6 h-6 text-indigo-400" />
          Text-to-Speech
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Type or record French text — generate audio and evaluate your pronunciation.
        </p>
      </div>

      {/* Voice selector */}
      <div className="bg-slate-800/60 rounded-xl p-4 space-y-3">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Voice</p>
        <div className="flex flex-wrap gap-2">
          {voices.map((v) => (
            <button
              key={v.id}
              onClick={() => setSelectedVoice(v.id)}
              className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                selectedVoice === v.id
                  ? "bg-indigo-600 text-white shadow-lg shadow-indigo-900/40"
                  : "bg-slate-700 text-slate-300 hover:bg-slate-600"
              }`}
            >
              {v.gender === "male" ? "♂ " : "♀ "}
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {/* Input mode toggle + content */}
      <div className="bg-slate-800/60 rounded-xl overflow-hidden">
        {/* Tabs */}
        <div className="flex border-b border-slate-700">
          <button
            onClick={() => setInputMode("type")}
            className={`flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 transition-colors ${
              inputMode === "type"
                ? "bg-slate-700/60 text-white border-b-2 border-indigo-500"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Type className="w-4 h-4" />
            Type Text
          </button>
          <button
            onClick={() => setInputMode("record")}
            className={`flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 transition-colors ${
              inputMode === "record"
                ? "bg-slate-700/60 text-white border-b-2 border-indigo-500"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Mic className="w-4 h-4" />
            Record Voice
          </button>
        </div>

        <div className="p-4 space-y-3">
          {/* Record panel */}
          {inputMode === "record" && (
            <div className="space-y-3">
              {recordState === "idle" && (
                <button
                  onClick={startRecording}
                  className="w-full py-4 rounded-xl border-2 border-dashed border-slate-600 hover:border-indigo-500 text-slate-400 hover:text-indigo-400 flex flex-col items-center gap-2 transition-all"
                >
                  <Mic className="w-8 h-8" />
                  <span className="text-sm">Click to start recording</span>
                </button>
              )}

              {recordState === "recording" && (
                <div className="flex flex-col items-center gap-3 py-4">
                  <div className="relative">
                    <span className="absolute inset-0 rounded-full bg-red-500 animate-ping opacity-40" />
                    <button
                      onClick={stopRecording}
                      className="relative w-14 h-14 rounded-full bg-red-600 hover:bg-red-700 flex items-center justify-center shadow-lg"
                    >
                      <MicOff className="w-6 h-6 text-white" />
                    </button>
                  </div>
                  <span className="text-red-400 font-mono text-sm">{formatSecs(recordSecs)} / {formatSecs(MAX_RECORD_MS / 1000)}</span>
                  <span className="text-slate-500 text-xs">Tap to stop</span>
                </div>
              )}

              {recordState === "recorded" && recordUrl && (
                <div className="space-y-3">
                  <div className="bg-slate-700/50 rounded-lg p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-400">Your recording ({formatSecs(recordSecs)})</span>
                      <button onClick={resetRecording} className="text-xs text-slate-500 hover:text-red-400 flex items-center gap-1">
                        <RotateCcw className="w-3 h-3" /> Re-record
                      </button>
                    </div>
                    <audio src={recordUrl} controls className="w-full h-8" style={{ colorScheme: "dark" }} />
                  </div>
                  <button
                    onClick={handleTranscribe}
                    disabled={transcribing}
                    className="w-full py-2.5 rounded-lg bg-sky-700 hover:bg-sky-600 disabled:opacity-60 text-white text-sm font-medium flex items-center justify-center gap-2 transition-colors"
                  >
                    {transcribing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Volume2 className="w-4 h-4" />}
                    {transcribing ? "Transcribing…" : "Transcribe to Text"}
                  </button>
                  {transcriptError && <p className="text-red-400 text-xs">{transcriptError}</p>}
                </div>
              )}
            </div>
          )}

          {/* Text area — shown in both modes */}
          <div className="space-y-1">
            {inputMode === "record" && text && (
              <p className="text-xs text-slate-400">Transcript (editable)</p>
            )}
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value.slice(0, MAX_CHARS))}
              placeholder={inputMode === "type" ? "Entrez votre texte en français…" : "Transcript will appear here after recording…"}
              rows={5}
              className="w-full bg-slate-900/60 border border-slate-600 rounded-lg p-3 text-slate-100 text-sm placeholder:text-slate-500 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <div className={`text-right text-xs ${text.length > MAX_CHARS * 0.9 ? "text-amber-400" : "text-slate-500"}`}>
              {text.length} / {MAX_CHARS}
            </div>
          </div>
        </div>
      </div>

      {/* Generate button */}
      <button
        onClick={handleGenerate}
        disabled={!canGenerate}
        className="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold flex items-center justify-center gap-2 transition-colors shadow-lg"
      >
        {generating ? <Loader2 className="w-5 h-5 animate-spin" /> : <Volume2 className="w-5 h-5" />}
        {generating ? "Generating…" : "Generate Audio"}
      </button>

      {ttsError && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-300 text-sm flex items-start gap-2">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {ttsError}
        </div>
      )}

      {/* TTS audio player */}
      {audioUrl && (
        <div className="bg-slate-800/60 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-300 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-green-400" />
              Generated Audio
            </p>
            <button
              onClick={handleDownload}
              className="text-xs text-slate-400 hover:text-indigo-400 flex items-center gap-1.5 transition-colors"
            >
              <Download className="w-3.5 h-3.5" /> Download MP3
            </button>
          </div>
          <audio key={audioUrl} src={audioUrl} controls className="w-full" style={{ colorScheme: "dark" }} />
        </div>
      )}

      {/* Pronunciation evaluation — only visible when user has a recording */}
      {recordBlob && (
        <div className="bg-slate-800/60 rounded-xl p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-slate-200">Pronunciation Evaluation</p>
              <p className="text-xs text-slate-500 mt-0.5">Compare your recording against the target text</p>
            </div>
            <button
              onClick={handleEvaluate}
              disabled={!canEvaluate || evaluating}
              className="px-4 py-2 rounded-lg bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium flex items-center gap-2 transition-colors"
            >
              {evaluating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mic className="w-4 h-4" />}
              {evaluating ? "Evaluating…" : "Evaluate"}
            </button>
          </div>

          {!canEvaluate && (
            <p className="text-xs text-slate-500">
              {!text.trim() ? "Add text above to evaluate against your recording." : ""}
            </p>
          )}

          {evalError && (
            <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-300 text-xs flex items-start gap-2">
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              {evalError}
            </div>
          )}

          {evalResult && (
            <div className="space-y-4">
              {/* Score circles */}
              <div className="flex items-center justify-around bg-slate-900/40 rounded-xl p-4">
                <ScoreCircle value={evalResult.accuracy} label="Accuracy" color={scoreColor} />
                <div className="text-center">
                  <p className="text-3xl font-bold text-white">{overallScore?.toFixed(1)}</p>
                  <p className="text-xs text-slate-400 mt-1">Overall</p>
                  <p className="text-xs mt-1" style={{ color: scoreColor }}>
                    {overallScore! >= 8 ? "Excellent" : overallScore! >= 6 ? "Good" : overallScore! >= 4 ? "Fair" : "Needs work"}
                  </p>
                </div>
                <ScoreCircle value={evalResult.clarity} label="Clarity" color={scoreColor} />
              </div>

              {/* What you said */}
              {evalResult.user_text && (
                <div className="bg-slate-900/40 rounded-lg p-3 space-y-1">
                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">What you said</p>
                  <MistakesHighlight text={evalResult.user_text} mistakes={evalResult.mistakes} />
                </div>
              )}

              {/* Mistakes */}
              {evalResult.mistakes.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Problem words</p>
                  <div className="flex flex-wrap gap-1.5">
                    {evalResult.mistakes.map((m, i) => (
                      <span key={i} className="px-2 py-0.5 rounded bg-red-900/50 text-red-300 text-xs border border-red-800">
                        {m}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {evalResult.mistakes.length === 0 && (
                <div className="flex items-center gap-2 text-green-400 text-sm">
                  <CheckCircle2 className="w-4 h-4" /> No pronunciation mistakes detected!
                </div>
              )}

              {/* Feedback */}
              {evalResult.feedback && (
                <div className="bg-blue-900/20 border border-blue-800/40 rounded-lg p-3 space-y-1">
                  <p className="text-xs font-semibold text-blue-400 uppercase tracking-wide">Coach Feedback</p>
                  <p className="text-slate-300 text-sm leading-relaxed">{evalResult.feedback}</p>
                </div>
              )}

              {/* Improved version */}
              {evalResult.improved_version && (
                <div className="bg-emerald-900/20 border border-emerald-800/40 rounded-lg p-3 space-y-1">
                  <p className="text-xs font-semibold text-emerald-400 uppercase tracking-wide">Improvement Guide</p>
                  <p className="text-slate-300 text-sm leading-relaxed">{evalResult.improved_version}</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
