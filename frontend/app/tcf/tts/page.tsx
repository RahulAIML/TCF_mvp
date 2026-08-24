"use client";

import { useEffect, useRef, useState } from "react";
import TcfAppShell from "@/components/TcfAppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { generateTts, getTtsVoices } from "@/services/api";
import type { TtsVoice } from "@/types/tts";
import { Download, Loader2, Mic2, Play, Volume2 } from "lucide-react";

const MAX_CHARS = 2000;
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function TtsPage() {
  const [voices, setVoices] = useState<TtsVoice[]>([]);
  const [selectedVoiceId, setSelectedVoiceId] = useState<string>("fr-FR-male-1");
  const [text, setText] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Load voices on mount
  useEffect(() => {
    getTtsVoices()
      .then((v) => {
        setVoices(v);
        if (v.length > 0) setSelectedVoiceId(v[0].id);
      })
      .catch(() => {
        // fallback — show built-in default
        setVoices([{ id: "fr-FR-male-1", label: "French Male", language: "fr", gender: "male" }]);
      });
  }, []);

  const charsLeft = MAX_CHARS - text.length;
  const canGenerate = text.trim().length > 0 && !isGenerating;

  async function handleGenerate() {
    setError(null);
    setAudioUrl(null);
    setIsGenerating(true);
    try {
      const res = await generateTts({ text, voice_id: selectedVoiceId });
      // Resolve relative backend URL through Next.js rewrite
      const resolved = res.audio_url.startsWith("/audio/")
        ? res.audio_url
        : res.audio_url;
      setAudioUrl(resolved);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Generation failed. Please try again.");
    } finally {
      setIsGenerating(false);
    }
  }

  function handlePlay() {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
  }

  async function handleDownload() {
    if (!audioUrl) return;
    try {
      const fullUrl = audioUrl.startsWith("http") ? audioUrl : `${API_BASE_URL}${audioUrl}`;
      const res = await fetch(fullUrl);
      if (!res.ok) throw new Error("Download failed.");
      const blob = await res.blob();
      const ext = audioUrl.endsWith(".wav") ? "wav" : "mp3";
      const fileName = `tcf-tts-${selectedVoiceId}-${Date.now()}.${ext}`;
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = fileName;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch {
      setError("Download failed. Please try again.");
    }
  }

  const selectedVoice = voices.find((v) => v.id === selectedVoiceId);

  return (
    <TcfAppShell
      title="Text-to-Speech"
      subtitle="Convert French text to MP3 audio using native voices"
      backHref="/tcf"
    >
      <div className="max-w-2xl space-y-6">
        {/* Voice selector */}
        <Card>
          <CardContent className="p-5">
            <h2 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <Mic2 className="h-4 w-4 text-indigo-500" />
              Voice
            </h2>
            <div className="flex flex-wrap gap-2">
              {voices.map((v) => (
                <button
                  key={v.id}
                  onClick={() => setSelectedVoiceId(v.id)}
                  className={`rounded-full border px-4 py-1.5 text-sm font-medium transition ${
                    selectedVoiceId === v.id
                      ? "bg-indigo-600 text-white border-indigo-600"
                      : "border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  {v.label}
                </button>
              ))}
            </div>
            {selectedVoice && (
              <p className="mt-2 text-xs text-slate-400">
                {selectedVoice.gender === "male" ? "♂" : "♀"}&nbsp;
                {selectedVoice.gender.charAt(0).toUpperCase() + selectedVoice.gender.slice(1)} ·{" "}
                {selectedVoice.language.toUpperCase()}
              </p>
            )}
          </CardContent>
        </Card>

        {/* Text input */}
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                <Volume2 className="h-4 w-4 text-emerald-500" />
                French Text
              </h2>
              <span
                className={`text-xs ${
                  charsLeft < 100
                    ? charsLeft < 0
                      ? "text-red-500 font-semibold"
                      : "text-amber-500"
                    : "text-slate-400"
                }`}
              >
                {charsLeft} chars remaining
              </span>
            </div>
            <textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setAudioUrl(null);
                setError(null);
              }}
              placeholder="Entrez ou collez votre texte français ici…"
              rows={7}
              maxLength={MAX_CHARS}
              className="w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100 transition"
            />

            {error && (
              <p className="mt-2 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
            )}

            <div className="mt-3 flex justify-end">
              <Button
                onClick={handleGenerate}
                disabled={!canGenerate}
                className="bg-indigo-600 hover:bg-indigo-700 text-white px-6"
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Generating…
                  </>
                ) : (
                  "Generate MP3"
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Audio player */}
        {audioUrl && (
          <Card className="border-emerald-200 bg-emerald-50/40">
            <CardContent className="p-5">
              <h2 className="text-sm font-semibold text-slate-700 mb-4">Audio Preview</h2>

              {/* Hidden HTML audio element — drives play state */}
              <audio
                ref={audioRef}
                src={audioUrl}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onEnded={() => setIsPlaying(false)}
                preload="metadata"
              />

              {/* Native controls as primary player */}
              <audio
                src={audioUrl}
                controls
                className="w-full h-10 rounded-lg"
                preload="metadata"
              />

              <div className="mt-4 flex items-center gap-3">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handlePlay}
                  className="flex items-center gap-1.5 border-emerald-300 text-emerald-700 hover:bg-emerald-100"
                >
                  <Play className="h-3.5 w-3.5" />
                  {isPlaying ? "Pause" : "Play"}
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDownload}
                  className="flex items-center gap-1.5 border-slate-300 text-slate-700 hover:bg-slate-100"
                >
                  <Download className="h-3.5 w-3.5" />
                  Download MP3
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Empty state hint */}
        {!audioUrl && !isGenerating && (
          <p className="text-center text-xs text-slate-400">
            Enter French text above and click &ldquo;Generate MP3&rdquo; to create audio.
          </p>
        )}
      </div>
    </TcfAppShell>
  );
}
