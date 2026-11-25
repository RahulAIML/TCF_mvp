"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Mic, MicOff, Loader2, Volume2, Download, RotateCcw,
  CheckCircle2, AlertCircle, Type, AudioLines, Trash2, History, Languages,
} from "lucide-react";
import TcfAppShell from "@/components/TcfAppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  deleteTtsHistoryItem,
  startTtsJob,
  pollTtsJob,
  getTtsHistory,
  getTtsVoices,
} from "@/services/api";
import { streamPronunciationEvaluation, transcribeRecording } from "@/services/speakingApi";
import type { PronunciationEvalResult } from "@/types/tcf-speaking";
import type { TtsHistoryItem, TtsVoice } from "@/types/tts";
import { getAuthToken } from "@/lib/auth";
import { SLOW_MESSAGE, useSlow } from "@/lib/slow-load";
import { createRecorder, microphoneErrorMessage, recordedMime } from "@/lib/audio-mime";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const FALLBACK_VOICES: TtsVoice[] = [
  { id: "fr-FR-male-1", label: "French Male", language: "fr", gender: "male" },
  { id: "fr-FR-male-2", label: "French Male 2", language: "fr", gender: "male" },
  { id: "fr-FR-female-1", label: "French Female", language: "fr", gender: "female" },
  { id: "fr-FR-female-2", label: "French Female 2", language: "fr", gender: "female" },
];
const MAX_CHARS = 40000;
const EVAL_MAX_CHARS = 2000;
const MAX_RECORD_SECS = 60;
const HISTORY_KEY = "tts_audio_history_guest";
const MAX_HISTORY = 20;

// The four languages text can be spoken in. Names are shown in the language itself.
const LANGUAGES = [
  { code: "fr", label: "Français", placeholder: "Entrez votre texte en français…" },
  { code: "en", label: "English", placeholder: "Enter your text in English…" },
  { code: "es", label: "Español", placeholder: "Escribe tu texto en español…" },
  { code: "pt", label: "Português", placeholder: "Digite seu texto em português…" },
] as const;
type LanguageCode = (typeof LANGUAGES)[number]["code"];

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
const fmt = (s: number) =>
  `${Math.floor(s / 60).toString().padStart(2, "0")}:${(s % 60).toString().padStart(2, "0")}`;

// localStorage shape matches TtsHistoryItem but id is a string for guests
function loadGuestHistory(): TtsHistoryItem[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function saveGuestHistory(entries: TtsHistoryItem[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(entries.slice(0, MAX_HISTORY)));
  } catch {}
}

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
        <circle cx="32" cy="32" r={radius} fill="none" stroke={color} strokeWidth="6"
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round" transform="rotate(-90 32 32)" />
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
  const lower = mistakes.map((m) => m.toLowerCase().replace(/[.,!?;:]/g, ""));
  const words = text.split(/(\s+)/);
  return (
    <>
      {words.map((w, i) => {
        const clean = w.toLowerCase().replace(/[.,!?;:]/g, "");
        return lower.includes(clean)
          ? <mark key={i} className="bg-red-100 text-red-700 rounded px-0.5">{w}</mark>
          : <span key={i}>{w}</span>;
      })}
    </>
  );
}

function HistoryAudioPlayer({ src }: { src: string }) {
  const [expired, setExpired] = useState(false);
  // preload="none": the page must not download every saved recording just by opening.
  if (expired) {
    return (
      <p className="text-xs text-slate-400 italic flex items-center gap-1 py-1">
        <AlertCircle className="h-3 w-3 text-amber-400 shrink-0" />
        This recording is no longer available. Generate it again.
      </p>
    );
  }
  return (
    <audio
      src={src}
      controls
      preload="none"
      className="w-full"
      onError={() => setExpired(true)}
    />
  );
}

export default function TtsPage() {
  const [voices, setVoices] = useState<TtsVoice[]>(FALLBACK_VOICES);
  const [language, setLanguage] = useState<LanguageCode>("fr");
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

  // Voices
  const [voicesError, setVoicesError] = useState("");
  const [voicesLoading, setVoicesLoading] = useState(true);
  const voicesSlow = useSlow(voicesLoading);

  // TTS
  const [generating, setGenerating] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [ttsError, setTtsError] = useState("");
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [notice, setNotice] = useState("");
  const [trimmed, setTrimmed] = useState(false);

  // Inventory
  const [history, setHistory] = useState<TtsHistoryItem[]>([]);

  // Evaluation
  const [evaluating, setEvaluating] = useState(false);
  const [evalResult, setEvalResult] = useState<PronunciationEvalResult | null>(null);
  const [evalUserText, setEvalUserText] = useState("");
  const [evalFeedback, setEvalFeedback] = useState("");
  const [evalError, setEvalError] = useState("");
  const [evalNotice, setEvalNotice] = useState("");

  // Download
  const [downloadError, setDownloadError] = useState("");

  const loadVoices = useCallback(() => {
    setVoicesLoading(true);
    setVoicesError("");
    getTtsVoices()
      .then((v) => {
        setVoices(v);
        const first = v.find((x) => x.language === "fr") ?? v[0];
        if (first) setSelectedVoice(first.id);
      })
      .catch((e: unknown) => {
        setVoices((current) => (current.length ? current : FALLBACK_VOICES));
        setVoicesError(e instanceof Error ? e.message : SLOW_MESSAGE);
      })
      .finally(() => setVoicesLoading(false));
  }, []);

  useEffect(() => {
    loadVoices();

    if (getAuthToken()) {
      getTtsHistory().then(setHistory).catch(() => setHistory(loadGuestHistory()));
    } else {
      setHistory(loadGuestHistory());
    }
  }, [loadVoices]);

  const languageVoices = voices.filter((v) => v.language === language);
  const currentLanguage = LANGUAGES.find((l) => l.code === language) ?? LANGUAGES[0];

  // Changing the language switches to that language's first voice (a voice speaks one language here).
  const handleLanguageChange = useCallback((code: LanguageCode) => {
    setLanguage(code);
    const first = voices.find((v) => v.language === code);
    if (first) setSelectedVoice(first.id);
  }, [voices]);

  // --- Recording ---
  const stopRecording = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (mediaRef.current && mediaRef.current.state !== "inactive") mediaRef.current.stop();
  }, []);

  const startRecording = useCallback(async () => {
    setTranscriptError("");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setTranscriptError(microphoneErrorMessage(null));
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = createRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: recordedMime(mr, chunksRef.current) });
        setRecordBlob(blob);
        setRecordUrl(URL.createObjectURL(blob));
        setRecordState("recorded");
      };
      mr.start(100);
      mediaRef.current = mr;
      setRecordSecs(0);
      setRecordState("recording");
      timerRef.current = setInterval(() => {
        setRecordSecs((s) => { if (s + 1 >= MAX_RECORD_SECS) stopRecording(); return s + 1; });
      }, 1000);
    } catch (err) {
      setTranscriptError(microphoneErrorMessage(err));
    }
  }, [stopRecording]);

  const resetRecording = useCallback(() => {
    stopRecording();
    setRecordBlob(null); setRecordUrl(null);
    setRecordState("idle"); setRecordSecs(0);
    setTranscriptError(""); setEvalResult(null); setEvalError("");
    setEvalUserText(""); setEvalFeedback(""); setEvalNotice("");
  }, [stopRecording]);

  const handleTranscribe = useCallback(async () => {
    if (!recordBlob) return;
    setTranscribing(true); setTranscriptError("");
    try {
      const result = await transcribeRecording(recordBlob, language);
      if (result.no_speech || !result.transcript) {
        setTranscriptError(result.message ?? "Aucune parole détectée. Parlez plus près du micro et réessayez.");
        return;
      }
      setText(result.transcript.slice(0, MAX_CHARS));
    } catch (e: unknown) {
      setTranscriptError(e instanceof Error ? e.message : "Transcription failed");
    } finally { setTranscribing(false); }
  }, [recordBlob, language]);

  // --- TTS generation (polling-based to bypass proxy timeout) ---
  // Waits for a job. A server restart (network errors, or a job the server no longer knows) is not a failure:
  // keep asking, and if the job was lost, start it again once.
  const waitForJob = useCallback(async (jobId: string, totalParts: number) => {
    const started = Date.now();
    const maxTotalMs = Math.max(180_000, totalParts * 45_000);
    const maxOutageMs = 180_000;
    let outageSince: number | null = null;
    for (;;) {
      await sleep(2000);
      if (Date.now() - started > maxTotalMs) throw new Error("Generation is taking too long. Try a shorter text.");
      try {
        const job = await pollTtsJob(jobId);
        outageSince = null;
        setNotice("");
        if (job.total_parts && job.total_parts > 1) setProgress({ done: job.done_parts ?? 0, total: job.total_parts });
        if (job.status === "done" && job.audio_url) return job.audio_url;
        if (job.status === "error") throw Object.assign(new Error(job.error ?? "failed"), { fromJob: true });
      } catch (e) {
        if (e instanceof Error && (e as Error & { fromJob?: boolean }).fromJob) throw e;
        outageSince ??= Date.now();
        setNotice("Reconnecting to the server…");
        if (Date.now() - outageSince > maxOutageMs) {
          throw new Error("The connection to the server was lost. Please try again.");
        }
      }
    }
  }, []);

  const handleGenerate = useCallback(async () => {
    if (!text.trim()) return;
    setGenerating(true); setTtsError(""); setAudioUrl(null); setProgress(null); setNotice("");
    setEvalResult(null); setEvalError("");
    try {
      const voice = voices.find((v) => v.id === selectedVoice);
      let audioPath: string | null = null;
      for (let attempt = 0; attempt < 2 && !audioPath; attempt++) {
        const { job_id, total_parts } = await startTtsJob({ text, voice_id: selectedVoice });
        try {
          audioPath = await waitForJob(job_id, total_parts ?? 1);
        } catch (e) {
          const interrupted = e instanceof Error && e.message === "interrupted";
          if (!interrupted || attempt === 1) {
            throw interrupted ? new Error("The server restarted while generating. Please try again.") : e;
          }
          setProgress(null);
          setNotice("The server restarted. Starting again…");
        }
      }
      if (!audioPath) throw new Error("Generation failed. Please try again.");
      const url = `${API_BASE_URL}${audioPath}`;
      setAudioUrl(url);
      if (getAuthToken()) {
        getTtsHistory().then(setHistory).catch(() => {});
      } else {
        const entry: TtsHistoryItem = {
          id: Date.now(),
          audio_url: url,
          voice_id: selectedVoice,
          voice_label: voice?.label ?? selectedVoice,
          text_preview: text.trim().slice(0, 200),
          created_at: new Date().toISOString(),
        };
        setHistory((prev) => {
          const next = [entry, ...prev].slice(0, MAX_HISTORY);
          saveGuestHistory(next);
          return next;
        });
      }
    } catch (e: unknown) {
      setTtsError(e instanceof Error ? e.message : "Generation failed. Please try again.");
    } finally { setGenerating(false); setProgress(null); setNotice(""); }
  }, [text, selectedVoice, voices, waitForJob]);

  const handleDownload = useCallback(async (url: string, voiceId: string) => {
    setDownloadError("");
    try {
      const head = await fetch(url, { method: "HEAD" });
      if (head.status === 404) throw new Error("This audio file is no longer available. Generate it again to download it.");
      if (!head.ok) throw new Error("The download failed. Please try again.");
      const a = document.createElement("a");
      a.href = `${url}${url.includes("?") ? "&" : "?"}download=1`;
      a.download = `tts_${voiceId}_${Date.now()}`;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e: unknown) {
      setDownloadError(
        e instanceof TypeError
          ? "Connection problem. Check your internet connection and try again."
          : e instanceof Error ? e.message : "The download failed. Please try again.",
      );
    }
  }, []);

  const handleDeleteHistory = useCallback(async (id: number) => {
    if (getAuthToken()) {
      try { await deleteTtsHistoryItem(id); } catch {}
    }
    setHistory((prev) => {
      const next = prev.filter((e) => e.id !== id);
      if (!getAuthToken()) saveGuestHistory(next);
      return next;
    });
  }, []);

  const handleClearHistory = useCallback(async () => {
    if (getAuthToken()) {
      await Promise.allSettled(history.map((e) => deleteTtsHistoryItem(e.id)));
    } else {
      saveGuestHistory([]);
    }
    setHistory([]);
  }, [history]);

  // --- Evaluation ---
  const handleEvaluate = useCallback(async () => {
    if (!recordBlob || !text.trim()) return;
    if (text.length > EVAL_MAX_CHARS) {
      setEvalError(`Pronunciation evaluation works on up to ${EVAL_MAX_CHARS.toLocaleString()} characters. Shorten the text to the passage you read.`);
      return;
    }
    setEvaluating(true); setEvalError(""); setEvalResult(null);
    setEvalUserText(""); setEvalFeedback(""); setEvalNotice("");
    let feedback = "";
    try {
      await streamPronunciationEvaluation(text, recordBlob, language, {
        onTranscript: setEvalUserText,
        onFeedbackToken: (token) => { feedback += token; setEvalFeedback(feedback); },
        onScores: setEvalResult,
        onNoSpeech: (result) => setEvalNotice(result.feedback),
      });
    } catch (e: unknown) {
      setEvalError(e instanceof Error ? e.message : "Evaluation failed. Please try again.");
    } finally { setEvaluating(false); }
  }, [recordBlob, text, language]);

  const overallScore = evalResult ? (evalResult.accuracy + evalResult.clarity) / 2 : null;
  const scoreLabel = overallScore === null ? "" : overallScore >= 8 ? "Excellent" : overallScore >= 6 ? "Good" : overallScore >= 4 ? "Fair" : "Needs work";
  const scoreLabelColor = overallScore === null ? "" : overallScore >= 8 ? "text-emerald-600" : overallScore >= 6 ? "text-amber-600" : "text-red-600";

  const chars = text.length;
  const nearLimit = chars > MAX_CHARS * 0.9;

  return (
    <TcfAppShell
      title="Text-to-Speech"
      subtitle="Type or record text in French, English, Spanish or Portuguese — generate an MP3 and evaluate your pronunciation"
      backHref="/tcf"
    >
      <div className="max-w-2xl space-y-5">

        {/* Language selector */}
        <Card className="border-slate-200 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm text-slate-700 flex items-center gap-2">
              <Languages className="h-4 w-4 text-indigo-500" />
              Language
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="flex flex-wrap gap-2" role="group" aria-label="Language">
              {LANGUAGES.map((l) => (
                <button key={l.code} onClick={() => handleLanguageChange(l.code)}
                  aria-pressed={language === l.code}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                    language === l.code ? "bg-indigo-600 text-white shadow-sm" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}>
                  {l.label}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Voice selector */}
        <Card className="border-slate-200 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm text-slate-700 flex items-center gap-2">
              <AudioLines className="h-4 w-4 text-indigo-500" />
              Select Voice
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {voicesLoading && !voicesSlow && (
              <p className="text-xs text-slate-400 flex items-center gap-1.5">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading voices…
              </p>
            )}
            {voicesSlow && (
              <div className="mb-2 flex items-center justify-between gap-3 rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800" role="alert">
                <span>{SLOW_MESSAGE}</span>
                <button onClick={loadVoices} className="font-medium underline">Retry</button>
              </div>
            )}
            {voicesError && (
              <div className="flex items-center justify-between gap-3 rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-600">
                <span className="flex items-center gap-1.5"><AlertCircle className="h-3.5 w-3.5 shrink-0" /> {voicesError}</span>
                <button onClick={loadVoices} className="font-medium underline hover:text-red-700">Retry</button>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              {languageVoices.map((v) => (
                <button key={v.id} onClick={() => setSelectedVoice(v.id)}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                    selectedVoice === v.id ? "bg-indigo-600 text-white shadow-sm" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}>
                  {v.gender === "male" ? "♂ " : "♀ "}{v.label}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Input card */}
        <Card className="border-slate-200 shadow-sm overflow-hidden">
          <div className="flex border-b border-slate-200">
            {(["type", "record"] as InputMode[]).map((mode) => (
              <button key={mode} onClick={() => setInputMode(mode)}
                className={`flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 transition-colors ${
                  inputMode === mode
                    ? "text-indigo-600 border-b-2 border-indigo-600 bg-indigo-50/50"
                    : "text-slate-500 hover:text-slate-700 hover:bg-slate-50"
                }`}>
                {mode === "type" ? <Type className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                {mode === "type" ? "Type Text" : "Record Voice"}
              </button>
            ))}
          </div>

          <CardContent className="pt-4 space-y-3">
            {inputMode === "record" && (
              <div className="space-y-3">
                {recordState === "idle" && (
                  <button onClick={startRecording}
                    className="w-full py-5 rounded-xl border-2 border-dashed border-slate-300 hover:border-indigo-400 text-slate-400 hover:text-indigo-500 flex flex-col items-center gap-2 transition-all">
                    <Mic className="h-7 w-7" />
                    <span className="text-sm font-medium">Click to start recording</span>
                  </button>
                )}
                {recordState === "recording" && (
                  <div className="flex flex-col items-center gap-3 py-4">
                    <div className="relative">
                      <span className="absolute inset-0 rounded-full bg-red-400 animate-ping opacity-30" />
                      <button onClick={stopRecording}
                        className="relative w-14 h-14 rounded-full bg-red-500 hover:bg-red-600 flex items-center justify-center shadow-md transition-colors">
                        <MicOff className="h-5 w-5 text-white" />
                      </button>
                    </div>
                    <span className="font-mono text-sm text-red-500 font-medium">{fmt(recordSecs)} / {fmt(MAX_RECORD_SECS)}</span>
                    <span className="text-xs text-slate-400">Tap to stop</span>
                  </div>
                )}
                {recordState === "recorded" && recordUrl && (
                  <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-500 font-medium">Your recording ({fmt(recordSecs)})</span>
                      <button onClick={resetRecording} className="text-xs text-slate-400 hover:text-red-500 flex items-center gap-1 transition-colors">
                        <RotateCcw className="h-3 w-3" /> Re-record
                      </button>
                    </div>
                    <audio src={recordUrl} controls className="w-full h-8" />
                    <button onClick={handleTranscribe} disabled={transcribing}
                      className="w-full py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium flex items-center justify-center gap-2 transition-colors">
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

            <div className="space-y-1">
              {inputMode === "record" && text && (
                <p className="text-xs text-slate-500 font-medium">Transcript (editable)</p>
              )}
              <textarea
                value={text}
                onChange={(e) => {
                  const val = e.target.value;
                  setTrimmed(val.length > MAX_CHARS);
                  setText(val.slice(0, MAX_CHARS));
                }}
                placeholder={inputMode === "type" ? currentLanguage.placeholder : "Transcript will appear here after recording…"}
                rows={5}
                className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
              />
              <p className={`text-right text-xs ${chars >= MAX_CHARS ? "text-red-500" : nearLimit ? "text-amber-500" : "text-slate-400"}`}>
                {chars.toLocaleString()} / {MAX_CHARS.toLocaleString()} characters
              </p>
              {trimmed && (
                <p className="text-right text-xs text-amber-600">
                  The text was longer than {MAX_CHARS.toLocaleString()} characters and has been shortened.
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Generate button */}
        <button onClick={handleGenerate} disabled={!text.trim() || generating || voices.length === 0}
          className="w-full py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold flex items-center justify-center gap-2 transition-colors shadow-sm">
          {generating ? <Loader2 className="h-5 w-5 animate-spin" /> : <Volume2 className="h-5 w-5" />}
          {generating
            ? progress && progress.total > 1
              ? `Generating part ${Math.min(progress.done + 1, progress.total)} of ${progress.total}…`
              : "Generating…"
            : "Generate Audio"}
        </button>

        {generating && notice && (
          <p className="text-xs text-amber-600 flex items-center gap-1.5">
            <Loader2 className="h-3 w-3 animate-spin" /> {notice}
          </p>
        )}
        {generating && progress && progress.total > 1 && (
          <div className="h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
            <div
              className="h-full rounded-full bg-emerald-500 transition-all"
              style={{ width: `${Math.round((progress.done / progress.total) * 100)}%` }}
            />
          </div>
        )}

        {ttsError && (
          <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-red-600 text-sm">
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" /> {ttsError}
          </div>
        )}

        {downloadError && (
          <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 p-3 text-amber-700 text-sm">
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" /> {downloadError}
          </div>
        )}

        {/* Current audio player */}
        {audioUrl && (
          <Card className="border-emerald-200 shadow-sm bg-emerald-50/30">
            <CardContent className="pt-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-slate-700 flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  Generated Audio
                </p>
                <button onClick={() => handleDownload(audioUrl, selectedVoice)}
                  className="text-xs text-slate-400 hover:text-indigo-600 flex items-center gap-1.5 transition-colors">
                  <Download className="h-3.5 w-3.5" /> Download MP3
                </button>
              </div>
              <audio key={audioUrl} src={audioUrl} controls className="w-full" />
            </CardContent>
          </Card>
        )}

        {/* Audio inventory */}
        {history.length > 0 && (
          <Card className="border-slate-200 shadow-sm">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm text-slate-700 flex items-center gap-2">
                  <History className="h-4 w-4 text-slate-400" />
                  Audio History ({history.length})
                </CardTitle>
                <button onClick={handleClearHistory}
                  className="text-xs text-slate-400 hover:text-red-500 flex items-center gap-1 transition-colors">
                  <Trash2 className="h-3 w-3" /> Clear all
                </button>
              </div>
            </CardHeader>
            <CardContent className="pt-0 space-y-2">
              {history.map((entry) => (
                <div key={entry.id} className="rounded-lg border border-slate-200 bg-slate-50 p-3 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-xs text-slate-700 truncate font-medium">{entry.text_preview}</p>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        {entry.voice_label} · {new Date(entry.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </p>
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <button onClick={() => handleDownload(entry.audio_url.startsWith("http") ? entry.audio_url : `${API_BASE_URL}${entry.audio_url}`, entry.voice_id)}
                        title="Download"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors">
                        <Download className="h-3.5 w-3.5" />
                      </button>
                      <button onClick={() => handleDeleteHistory(entry.id)}
                        title="Remove from history"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                  <HistoryAudioPlayer src={entry.audio_url.startsWith("http") ? entry.audio_url : `${API_BASE_URL}${entry.audio_url}`} />
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Pronunciation evaluation */}
        {recordBlob && (
          <Card className="border-slate-200 shadow-sm">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm text-slate-700">Pronunciation Evaluation</CardTitle>
                  <p className="text-xs text-slate-400 mt-0.5">Compare your recording against the target text</p>
                </div>
                <button onClick={handleEvaluate} disabled={!text.trim() || evaluating}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors">
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
                  <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" /> {evalError}
                </div>
              </CardContent>
            )}

            {evalNotice && (
              <CardContent className="pt-0">
                <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 p-3 text-amber-700 text-xs">
                  <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" /> {evalNotice}
                </div>
              </CardContent>
            )}

            {evalUserText && !evalResult && (
              <CardContent className="pt-0 space-y-3">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 space-y-1">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">What you said</p>
                  <p className="text-sm leading-relaxed text-slate-700">{evalUserText}</p>
                </div>
                {evalFeedback && (
                  <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 space-y-1">
                    <p className="text-xs font-semibold text-blue-600 uppercase tracking-wide">Coach Feedback</p>
                    <p className="text-sm text-slate-700 leading-relaxed">{evalFeedback}</p>
                  </div>
                )}
                <p className="text-xs text-slate-400 flex items-center gap-1.5">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Scoring…
                </p>
              </CardContent>
            )}

            {evalResult && (
              <CardContent className="pt-0 space-y-4">
                <div className="flex items-center justify-around rounded-xl bg-slate-50 border border-slate-200 py-4 px-2">
                  <ScoreRing value={evalResult.accuracy} label="Accuracy" />
                  <div className="text-center">
                    <p className="text-3xl font-bold text-slate-800">{overallScore?.toFixed(1)}</p>
                    <p className="text-xs text-slate-500 mt-0.5">Overall</p>
                    <p className={`text-xs font-semibold mt-1 ${scoreLabelColor}`}>{scoreLabel}</p>
                  </div>
                  <ScoreRing value={evalResult.clarity} label="Clarity" />
                </div>

                {(evalResult.user_text || evalUserText) && (
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 space-y-1">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">What you said</p>
                    <p className="text-sm leading-relaxed">
                      <HighlightedText text={evalResult.user_text || evalUserText} mistakes={evalResult.mistakes} />
                    </p>
                  </div>
                )}

                {evalResult.mistakes.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Problem words</p>
                    <div className="flex flex-wrap gap-1.5">
                      {evalResult.mistakes.map((m, i) => (
                        <span key={i} className="px-2 py-0.5 rounded-full bg-red-100 text-red-600 text-xs font-medium border border-red-200">{m}</span>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-emerald-600 text-sm font-medium">
                    <CheckCircle2 className="h-4 w-4" /> No pronunciation mistakes detected!
                  </div>
                )}

                {(evalFeedback || evalResult.feedback) && (
                  <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 space-y-1">
                    <p className="text-xs font-semibold text-blue-600 uppercase tracking-wide">Coach Feedback</p>
                    <p className="text-sm text-slate-700 leading-relaxed">{evalFeedback || evalResult.feedback}</p>
                  </div>
                )}

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
