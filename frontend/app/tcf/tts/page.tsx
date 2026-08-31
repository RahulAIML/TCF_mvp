"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Mic, MicOff, Loader2, Volume2, Download, RotateCcw,
  CheckCircle2, AlertCircle, Type, AudioLines,
} from "lucide-react";
import TcfAppShell from "@/components/TcfAppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
const MAX_RECORD_SECS = 60;

type InputMode = "type" | "record";
type RecordState = "idle" | "recording" | "recorded";

function ScoreRing({ value, label }: { value: number; label: string }) {
  const color = value >= 8 ? "#059669" : value >= 5 ? "#d97706" : "#dc2626";
  const radius = 26;
  const circ = 2 * Math.PI * radius;
  const dash = (value / 10) * circ;
  return (
    <div className="flex flex-col items-center gap-1.5">
      <svg width="64" height="64" viewBox="0 0 64 64">
        <circle cx="32" cy="32" r={radius} fill="none" stroke="#e2e8f0" strokeWidth="6" />
        <circle
          cx="32" cy="32" r={radius}
          fill="none" stroke={color} strokeWidth="6"
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
          transform="rotate(-90 32 32)"
        />
        <text x="32" y="37" textAnchor="middle" fill={color} fontSize="13" fontWeight="700">
          {value.toFixed(1)}
        </text>
      </svg>
      <span className="text-xs text-slate-500 font-medium">{label}</span>
    </div>
  );
}

function HighlightedText({ text, mistakes }: { text: string; mistakes: string[] }) {
  if (!mistakes.length) return <span className="text-slate-700">{text}</span>;
  const lowerMistakes = mistakes.map((m) => m.toLowerCase().replace(/[.,!?;:]/g, ""));
  const words = text.split(/(\s+)/);
  return (
    <>
      {words.map((w, i) => {
        const clean = w.toLowerCase().replace(/[.,!?;:]/g, "");
        return lowerMistakes.includes(clean) ? (
          <mark key={i} className="bg-red-100 text-red-700 rounded px-0.5">{w}</mark>
        ) : (
          <span key={i}>{w}</span>
        );
      })}
    </>
  );
}

const fmt = (s: number) =>
  `${Math.floor(s / 60).toString().padStart(2, "0")}:${(s % 60).toString().padStart(2, "0")}`;

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

  // TTS
  const [generating, setGenerating] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [ttsError, setTtsError] = useState("");

  // Evaluation
  const [evaluating, setEvaluating] = useState(false);
  const [evalResult, setEvalResult] = useState<PronunciationEvalResult | null>(null);
  const [evalError, setEvalError] = useState("");

  useEffect(() => {
    getTtsVoices()
      .then((v) => { setVoices(v); if (v.length) setSelectedVoice(v[0].id); })
      .catch(() => {});
  }, []);

  const stopRecording = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (mediaRef.current && mediaRef.current.state !== "inactive") mediaRef.current.stop();
  }, []);

  const startRecording = useCallback(async () => {
    setTranscriptError("");
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
          if (s + 1 >= MAX_RECORD_SECS) { stopRecording(); }
          return s + 1;
        });
      }, 1000);
    } catch {
      setTranscriptError("Microphone access denied. Please allow microphone in your browser.");
    }
  }, [stopRecording]);

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
  const scoreLabel =
    overallScore === null ? ""
    : overallScore >= 8 ? "Excellent"
    : overallScore >= 6 ? "Good"
    : overallScore >= 4 ? "Fair"
    : "Needs work";
  const scoreLabelColor =
    overallScore === null ? ""
    : overallScore >= 8 ? "text-emerald-600"
    : overallScore >= 6 ? "text-amber-600"
    : "text-red-600";

  return (
    <TcfAppShell
      title="Text-to-Speech"
      subtitle="Type or record French text — generate audio and evaluate your pronunciation"
      backHref="/tcf"
    >
      <div className="max-w-2xl space-y-5">

        {/* Voice selector */}
        <Card className="border-slate-200 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm text-slate-700 flex items-center gap-2">
              <AudioLines className="h-4 w-4 text-indigo-500" />
              Select Voice
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="flex flex-wrap gap-2">
              {voices.map((v) => (
                <button
                  key={v.id}
                  onClick={() => setSelectedVoice(v.id)}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                    selectedVoice === v.id
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {v.gender === "male" ? "♂ " : "♀ "}
                  {v.label}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Input card */}
        <Card className="border-slate-200 shadow-sm overflow-hidden">
          {/* Tab toggle */}
          <div className="flex border-b border-slate-200">
            {(["type", "record"] as InputMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => setInputMode(mode)}
                className={`flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 transition-colors ${
                  inputMode === mode
                    ? "text-indigo-600 border-b-2 border-indigo-600 bg-indigo-50/50"
                    : "text-slate-500 hover:text-slate-700 hover:bg-slate-50"
                }`}
              >
                {mode === "type" ? <Type className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                {mode === "type" ? "Type Text" : "Record Voice"}
              </button>
            ))}
          </div>

          <CardContent className="pt-4 space-y-3">
            {/* Record controls */}
            {inputMode === "record" && (
              <div className="space-y-3">
                {recordState === "idle" && (
                  <button
                    onClick={startRecording}
                    className="w-full py-5 rounded-xl border-2 border-dashed border-slate-300 hover:border-indigo-400 text-slate-400 hover:text-indigo-500 flex flex-col items-center gap-2 transition-all"
                  >
                    <Mic className="h-7 w-7" />
                    <span className="text-sm font-medium">Click to start recording</span>
                  </button>
                )}

                {recordState === "recording" && (
                  <div className="flex flex-col items-center gap-3 py-4">
                    <div className="relative">
                      <span className="absolute inset-0 rounded-full bg-red-400 animate-ping opacity-30" />
                      <button
                        onClick={stopRecording}
                        className="relative w-14 h-14 rounded-full bg-red-500 hover:bg-red-600 flex items-center justify-center shadow-md transition-colors"
                      >
                        <MicOff className="h-5 w-5 text-white" />
                      </button>
                    </div>
                    <span className="font-mono text-sm text-red-500 font-medium">
                      {fmt(recordSecs)} / {fmt(MAX_RECORD_SECS)}
                    </span>
                    <span className="text-xs text-slate-400">Tap to stop</span>
                  </div>
                )}

                {recordState === "recorded" && recordUrl && (
                  <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-500 font-medium">Your recording ({fmt(recordSecs)})</span>
                      <button
                        onClick={resetRecording}
                        className="text-xs text-slate-400 hover:text-red-500 flex items-center gap-1 transition-colors"
                      >
                        <RotateCcw className="h-3 w-3" /> Re-record
                      </button>
                    </div>
                    <audio src={recordUrl} controls className="w-full h-8" />
                    <button
                      onClick={handleTranscribe}
                      disabled={transcribing}
                      className="w-full py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium flex items-center justify-center gap-2 transition-colors"
                    >
                      {transcribing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Volume2 className="h-4 w-4" />}
                      {transcribing ? "Transcribing…" : "Transcribe to Text"}
                    </button>
                    {transcriptError && (
                      <p className="text-xs text-red-500 flex items-center gap-1">
                        <AlertCircle className="h-3 w-3 shrink-0" /> {transcriptError}
                      </p>
                    )}
                  </div>
                )}

                {transcriptError && recordState === "idle" && (
                  <p className="text-xs text-red-500 flex items-center gap-1">
                    <AlertCircle className="h-3 w-3 shrink-0" /> {transcriptError}
                  </p>
                )}
              </div>
            )}

            {/* Textarea */}
            <div className="space-y-1">
              {inputMode === "record" && text && (
                <p className="text-xs text-slate-500 font-medium">Transcript (editable)</p>
              )}
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value.slice(0, MAX_CHARS))}
                placeholder={
                  inputMode === "type"
                    ? "Entrez votre texte en français…"
                    : "Transcript will appear here after recording…"
                }
                rows={5}
                className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
              />
              <p className={`text-right text-xs ${text.length > MAX_CHARS * 0.9 ? "text-amber-500" : "text-slate-400"}`}>
                {text.length} / {MAX_CHARS}
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Generate button */}
        <button
          onClick={handleGenerate}
          disabled={!text.trim() || generating}
          className="w-full py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold flex items-center justify-center gap-2 transition-colors shadow-sm"
        >
          {generating ? <Loader2 className="h-5 w-5 animate-spin" /> : <Volume2 className="h-5 w-5" />}
          {generating ? "Generating…" : "Generate Audio"}
        </button>

        {ttsError && (
          <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-red-600 text-sm">
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
            {ttsError}
          </div>
        )}

        {/* Audio player */}
        {audioUrl && (
          <Card className="border-slate-200 shadow-sm">
            <CardContent className="pt-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-slate-700 flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  Generated Audio
                </p>
                <button
                  onClick={handleDownload}
                  className="text-xs text-slate-400 hover:text-indigo-600 flex items-center gap-1.5 transition-colors"
                >
                  <Download className="h-3.5 w-3.5" /> Download MP3
                </button>
              </div>
              <audio key={audioUrl} src={audioUrl} controls className="w-full" />
            </CardContent>
          </Card>
        )}

        {/* Pronunciation evaluation panel */}
        {recordBlob && (
          <Card className="border-slate-200 shadow-sm">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm text-slate-700">Pronunciation Evaluation</CardTitle>
                  <p className="text-xs text-slate-400 mt-0.5">Compare your recording against the target text</p>
                </div>
                <button
                  onClick={handleEvaluate}
                  disabled={!text.trim() || evaluating}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
                >
                  {evaluating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
                  {evaluating ? "Evaluating…" : "Evaluate"}
                </button>
              </div>
            </CardHeader>

            {!text.trim() && (
              <CardContent className="pt-0">
                <p className="text-xs text-slate-400">Add text above to evaluate against your recording.</p>
              </CardContent>
            )}

            {evalError && (
              <CardContent className="pt-0">
                <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-red-600 text-xs">
                  <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  {evalError}
                </div>
              </CardContent>
            )}

            {evalResult && (
              <CardContent className="pt-0 space-y-4">
                {/* Scores */}
                <div className="flex items-center justify-around rounded-xl bg-slate-50 border border-slate-200 py-4 px-2">
                  <ScoreRing value={evalResult.accuracy} label="Accuracy" />
                  <div className="text-center">
                    <p className="text-3xl font-bold text-slate-800">{overallScore?.toFixed(1)}</p>
                    <p className="text-xs text-slate-500 mt-0.5">Overall</p>
                    <p className={`text-xs font-semibold mt-1 ${scoreLabelColor}`}>{scoreLabel}</p>
                  </div>
                  <ScoreRing value={evalResult.clarity} label="Clarity" />
                </div>

                {/* What you said */}
                {evalResult.user_text && (
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 space-y-1">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">What you said</p>
                    <p className="text-sm leading-relaxed">
                      <HighlightedText text={evalResult.user_text} mistakes={evalResult.mistakes} />
                    </p>
                  </div>
                )}

                {/* Mistakes */}
                {evalResult.mistakes.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Problem words</p>
                    <div className="flex flex-wrap gap-1.5">
                      {evalResult.mistakes.map((m, i) => (
                        <span key={i} className="px-2 py-0.5 rounded-full bg-red-100 text-red-600 text-xs font-medium border border-red-200">
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-emerald-600 text-sm font-medium">
                    <CheckCircle2 className="h-4 w-4" />
                    No pronunciation mistakes detected!
                  </div>
                )}

                {/* Feedback */}
                {evalResult.feedback && (
                  <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 space-y-1">
                    <p className="text-xs font-semibold text-blue-600 uppercase tracking-wide">Coach Feedback</p>
                    <p className="text-sm text-slate-700 leading-relaxed">{evalResult.feedback}</p>
                  </div>
                )}

                {/* Improvement guide */}
                {evalResult.improved_version && (
                  <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-3 space-y-1">
                    <p className="text-xs font-semibold text-emerald-600 uppercase tracking-wide">Improvement Guide</p>
                    <p className="text-sm text-slate-700 leading-relaxed">{evalResult.improved_version}</p>
                  </div>
                )}
              </CardContent>
            )}
          </Card>
        )}
      </div>
    </TcfAppShell>
  );
}
