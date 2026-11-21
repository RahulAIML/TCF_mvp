"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { AnswerOption } from "@/types/exam";
import type { ListeningQuestion } from "@/types/listening";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface ListeningQuestionCardProps {
  question: ListeningQuestion;
  questionNumber: number;
  selectedAnswer: AnswerOption | "";
  onSelect: (value: AnswerOption) => void;
  disabled?: boolean;
  maxPlays?: number;
  playCount?: number;
  onPlay?: () => void;
  /** Called when audio needs to be fetched on-demand (question loaded with defer_audio) */
  onRequestAudio?: (question: ListeningQuestion) => Promise<string | undefined>;
  showTranscript: boolean;
  onToggleTranscript?: () => void;
  onTranscriptSelect?: (text: string) => void;
  /** Side-by-side translation support */
  translationText?: string;
  onTranslate?: () => void;
  isTranslating?: boolean;
  showTranslation?: boolean;
  /** When true, Replay resets position AND immediately plays (practice mode). Default: false (exam mode — reset only). */
  replayPlays?: boolean;
  /** When true, hide the Replay button (exam mode). */
  hideReplay?: boolean;
  /** When true, hide the speed controls (exam mode). */
  hideSpeedControls?: boolean;
}

const SPEED_OPTIONS = [0.75, 1, 1.25, 1.5];

export default function ListeningQuestionCard({
  question,
  questionNumber,
  selectedAnswer,
  onSelect,
  disabled,
  maxPlays,
  playCount = 0,
  onPlay,
  onRequestAudio,
  showTranscript,
  onToggleTranscript,
  onTranscriptSelect,
  translationText,
  onTranslate,
  isTranslating = false,
  showTranslation = false,
  replayPlays = false,
  hideReplay = false,
  hideSpeedControls = false,
}: ListeningQuestionCardProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const wordRefs = useRef<Array<HTMLSpanElement | null>>([]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [currentWordIndex, setCurrentWordIndex] = useState(0);
  const [autoScroll, setAutoScroll] = useState(true);
  const [isBuffering, setIsBuffering] = useState(false);
  const [audioCurrentTime, setAudioCurrentTime] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);
  const [hasStarted, setHasStarted] = useState(false);
  const [hasEnded, setHasEnded] = useState(false);
  const [audioError, setAudioError] = useState("");

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const resolveUrl = (url: string) => (url.startsWith("http") ? url : `${apiBase}${url}`);
  const [localAudioUrl, setLocalAudioUrl] = useState("");

  // A new question (new script) always starts from a clean player: deferred-audio questions all have
  // audio_url=null, so the script is what tells questions apart.
  useEffect(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    setIsPlaying(false);
    setIsBuffering(false);
    setAudioCurrentTime(0);
    setAudioDuration(0);
    setCurrentWordIndex(0);
    setHasStarted(false);
    setHasEnded(false);
    setAudioError("");
    setLocalAudioUrl("");
  }, [question.script]);

  // Audio that arrives later (background pre-generation) is adopted without interrupting playback.
  useEffect(() => {
    const url = question.audio_url;
    if (!url) return;
    setLocalAudioUrl((prev) => prev || resolveUrl(url));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question.audio_url, question.script, apiBase]);

  const audioSrc = localAudioUrl;

  const words = useMemo(() => question.script.split(/\s+/).filter(Boolean), [question.script]);

  const remainingPlays = maxPlays ? Math.max(0, maxPlays - playCount) : null;
  // Pausing mid-clip in the exam does not use up the single play: the clip can be resumed until it ends.
  const canResume = hasStarted && !hasEnded && !isPlaying;
  const canPlay = canResume || ((Boolean(audioSrc) || Boolean(onRequestAudio)) && (remainingPlays === null || remainingPlays > 0));

  useEffect(() => {
    if (!audioRef.current) return;
    audioRef.current.playbackRate = playbackRate;
  }, [playbackRate]);

  useEffect(() => {
    if (disabled && audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      setIsPlaying(false);
    }
  }, [disabled]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const handlePlay = () => {
      setIsPlaying(true);
      setAutoScroll(true);
      setIsBuffering(false);
      setHasStarted(true);
    };
    const handlePause = () => setIsPlaying(false);
    const handleEnded = () => {
      setIsPlaying(false);
      setHasEnded(true);
      setAudioCurrentTime(audio.duration || 0);
    };
    const handleCanPlay = () => setIsBuffering(false);
    const handleTimeUpdate = () => setAudioCurrentTime(audio.currentTime);
    const handleDuration = () => setAudioDuration(Number.isFinite(audio.duration) ? audio.duration : 0);

    audio.addEventListener("play", handlePlay);
    audio.addEventListener("pause", handlePause);
    audio.addEventListener("ended", handleEnded);
    audio.addEventListener("canplaythrough", handleCanPlay);
    audio.addEventListener("timeupdate", handleTimeUpdate);
    audio.addEventListener("loadedmetadata", handleDuration);
    audio.addEventListener("durationchange", handleDuration);

    return () => {
      audio.removeEventListener("play", handlePlay);
      audio.removeEventListener("pause", handlePause);
      audio.removeEventListener("ended", handleEnded);
      audio.removeEventListener("canplaythrough", handleCanPlay);
      audio.removeEventListener("timeupdate", handleTimeUpdate);
      audio.removeEventListener("loadedmetadata", handleDuration);
      audio.removeEventListener("durationchange", handleDuration);
    };
  }, []);

  useEffect(() => {
    if (!showTranscript) return;
    if (!isPlaying) return;

    const interval = setInterval(() => {
      const audio = audioRef.current;
      if (!audio || !audio.duration) return;
      const progress = audio.currentTime / audio.duration;
      const index = Math.min(words.length - 1, Math.max(0, Math.floor(progress * words.length)));
      setCurrentWordIndex(index);
    }, 120);

    return () => clearInterval(interval);
  }, [isPlaying, showTranscript, words.length]);

  useEffect(() => {
    if (!showTranscript || !autoScroll) return;
    const currentWord = wordRefs.current[currentWordIndex];
    if (currentWord && transcriptRef.current) {
      currentWord.scrollIntoView({ block: "center", behavior: "auto" });
    }
  }, [currentWordIndex, showTranscript, autoScroll]);

  const waitUntilPlayable = (audio: HTMLAudioElement) =>
    new Promise<boolean>((resolve) => {
      const done = (ok: boolean) => {
        audio.removeEventListener("canplay", onReady);
        audio.removeEventListener("error", onError);
        clearTimeout(timer);
        resolve(ok);
      };
      const onReady = () => done(true);
      const onError = () => done(false);
      const timer = setTimeout(() => done(audio.readyState >= 2), 30000);
      audio.addEventListener("canplay", onReady);
      audio.addEventListener("error", onError);
      audio.load();
    });

  const handlePlayClick = async () => {
    const audio = audioRef.current;
    if (!audio) return;
    setAudioError("");

    if (canResume) {
      try {
        await audio.play();
      } catch {
        setAudioError("The audio could not be resumed. Please try again.");
      }
      return;
    }
    if (remainingPlays !== null && remainingPlays <= 0) return;

    let effectiveSrc = audioSrc;
    if (!effectiveSrc && onRequestAudio) {
      setIsBuffering(true);
      let fetched: string | undefined;
      try {
        fetched = await onRequestAudio(question);
      } catch {
        fetched = undefined;
      }
      if (!fetched) {
        setIsBuffering(false);
        setAudioError("The audio is not available right now.");
        return;
      }
      effectiveSrc = resolveUrl(fetched);
      setLocalAudioUrl(effectiveSrc);
    }
    if (!effectiveSrc) {
      setAudioError("The audio is not available right now.");
      return;
    }

    if (audio.src !== effectiveSrc) {
      audio.src = effectiveSrc;
    }
    if (audio.readyState < 3) {
      setIsBuffering(true);
      const ok = await waitUntilPlayable(audio);
      if (!ok) {
        setIsBuffering(false);
        setAudioError("The audio could not be loaded.");
        return;
      }
    }

    try {
      await audio.play();
      onPlay?.();
    } catch {
      setIsBuffering(false);
      setAudioError("Playback was blocked by the browser. Press Play again.");
    }
  };
  const handlePauseClick = () => {
    audioRef.current?.pause();
  };
  const handleReplayClick = async () => {
    if (!audioRef.current) return;
    const audio = audioRef.current;
    audio.pause();
    audio.currentTime = 0;
    setCurrentWordIndex(0);
    setAutoScroll(true);
    setIsBuffering(false);
    setHasEnded(false);
    // In practice mode (replayPlays=true): restart playback immediately from the top.
    // In exam mode (replayPlays=false): only reset position — do not play again.
    if (replayPlays && audioSrc) {
      try {
        await audio.play();
      } catch {
        // Browser blocked autoplay or audio not ready — user can press Play manually.
      }
    }
  };
  const handleTranscriptSelection = () => {
    const selection = window.getSelection()?.toString() ?? "";
    const cleaned = selection.replace(/\s+/g, " ").trim();
    if (cleaned && onTranscriptSelect) {
      onTranscriptSelect(cleaned);
    }
  };

  return (
    <Card className="border-slate-200 shadow-sm rounded-2xl">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-slate-900">Question {questionNumber}</CardTitle>
            <CardDescription>Play the audio and answer the question.</CardDescription>
            {question.format_type && (
              <p className="mt-1 text-xs font-medium text-indigo-600">
                Format : {question.format_type.replace(/^(un|une)\s+/i, "")}
              </p>
            )}
          </div>
          {onToggleTranscript && (
            <Button variant="outline" onClick={onToggleTranscript}>
              {showTranscript ? "Hide Transcript" : "Show Transcript"}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Audio</p>

          {/* Play / Pause / Replay row */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Primary play/pause toggle */}
            <Button
              onClick={isPlaying ? handlePauseClick : () => void handlePlayClick()}
              disabled={(!canPlay && !isPlaying) || isBuffering}
              className="gap-2"
            >
              {isBuffering ? (
                <>
                  <span className="h-3 w-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  Loading…
                </>
              ) : isPlaying ? (
                <>
                  <span className="flex gap-0.5">
                    <span className="h-3.5 w-1 rounded-sm bg-current" />
                    <span className="h-3.5 w-1 rounded-sm bg-current" />
                  </span>
                  Pause
                </>
              ) : (
                <>
                  <span className="h-0 w-0 border-y-[6px] border-l-[10px] border-y-transparent border-l-current" />
                  {canResume
                    ? "Resume"
                    : remainingPlays !== null && remainingPlays <= 0
                      ? "Limit reached"
                      : remainingPlays !== null
                        ? `Play (${remainingPlays} left)`
                        : "Play"}
                </>
              )}
            </Button>

            {/* Replay from start */}
            {!hideReplay && (
              <Button
                variant="outline"
                onClick={() => void handleReplayClick()}
                disabled={!audioSrc && !isPlaying}
                title="Restart from beginning"
              >
                ↺ Replay
              </Button>
            )}

            {/* Remaining plays badge */}
            {remainingPlays !== null && remainingPlays > 0 && (
              <span className="ml-auto rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-medium text-slate-600">
                {remainingPlays} play{remainingPlays !== 1 ? "s" : ""} left
              </span>
            )}
          </div>

          {audioError && (
            <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
              <span>{audioError}</span>
              <button
                type="button"
                className="font-semibold underline"
                onClick={() => void handlePlayClick()}
              >
                Retry
              </button>
            </div>
          )}

          {/* Audio progress bar + time */}
          {audioDuration > 0 && (
            <div className="space-y-1">
              <div className="relative h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-indigo-500 transition-all"
                  style={{ width: `${(audioCurrentTime / audioDuration) * 100}%` }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-slate-400 select-none">
                <span>{Math.floor(audioCurrentTime / 60)}:{String(Math.floor(audioCurrentTime % 60)).padStart(2, "0")}</span>
                <span>{Math.floor(audioDuration / 60)}:{String(Math.floor(audioDuration % 60)).padStart(2, "0")}</span>
              </div>
            </div>
          )}

          {/* Speed segmented control — hidden in exam mode */}
          {!hideSpeedControls && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400 font-medium w-10">Speed</span>
              <div className="flex rounded-lg border border-slate-200 bg-white overflow-hidden divide-x divide-slate-200">
                {SPEED_OPTIONS.map((speed) => (
                  <button
                    key={`speed-${speed}`}
                    type="button"
                    onClick={() => setPlaybackRate(speed)}
                    className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                      playbackRate === speed
                        ? "bg-indigo-600 text-white"
                        : "text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {speed}x
                  </button>
                ))}
              </div>
            </div>
          )}

          <audio ref={audioRef} src={audioSrc || undefined} preload="auto" />
        </div>

        {showTranscript && (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-slate-700">Transcript</p>
              <div className="flex items-center gap-3">
                {!autoScroll && (
                  <button
                    type="button"
                    className="text-xs font-medium text-indigo-600 hover:text-indigo-500"
                    onClick={() => setAutoScroll(true)}
                  >
                    Resume auto-scroll
                  </button>
                )}
                {onTranslate && (
                  <button
                    type="button"
                    onClick={onTranslate}
                    disabled={isTranslating}
                    className="text-xs font-medium text-indigo-600 hover:text-indigo-800 disabled:opacity-50"
                  >
                    {isTranslating ? "Translating..." : showTranslation && translationText ? "Hide Translation" : "Show Translation"}
                  </button>
                )}
              </div>
            </div>
            {/* Side-by-side: French transcript | English translation */}
            <div className={showTranslation && translationText ? "grid grid-cols-2 gap-3" : ""}>
              <div
                ref={transcriptRef}
                className="max-h-48 overflow-y-auto rounded-xl bg-white p-3 text-sm leading-6 text-slate-700"
                onMouseUp={handleTranscriptSelection}
                onMouseEnter={() => setAutoScroll(false)}
                onWheel={() => setAutoScroll(false)}
                onScroll={() => setAutoScroll(false)}
                onPointerDown={() => setAutoScroll(false)}
                onTouchMove={() => setAutoScroll(false)}
              >
                {words.map((word, index) => (
                  <span
                    key={`word-${index}`}
                    ref={(el) => { wordRefs.current[index] = el; }}
                    className={index === currentWordIndex ? "rounded bg-yellow-200 px-1" : ""}
                  >
                    {word}{" "}
                  </span>
                ))}
              </div>
              {showTranslation && translationText && (
                <div className="border-l border-indigo-100 pl-3">
                  <p className="text-[10px] font-semibold uppercase text-indigo-400 mb-1">English</p>
                  <p className="text-sm leading-6 text-slate-600">{translationText}</p>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="space-y-3">
          <h3 className="text-base font-semibold text-slate-900">{question.question}</h3>
          <div className="mt-2 space-y-2">
            {question.options.map((option, index) => {
              const value = (["A", "B", "C", "D"][index] as AnswerOption) ?? "A";
              const isSelected = selectedAnswer === value;
              return (
                <label
                  key={`listening-${questionNumber}-${index}`}
                  className={`group flex items-start gap-3 rounded-xl border px-3 py-3 text-sm transition-all duration-150 ${
                    isSelected
                      ? "border-indigo-600 bg-indigo-600 text-white shadow-sm cursor-default"
                      : "border-slate-200 bg-white text-slate-700 hover:border-indigo-200 hover:bg-indigo-50"
                  } ${disabled ? "cursor-not-allowed opacity-70" : "cursor-pointer"}`}
                >
                  <input
                    type="radio"
                    name={`listening-question-${questionNumber}`}
                    className="sr-only"
                    value={value}
                    checked={isSelected}
                    disabled={disabled}
                    onChange={() => onSelect(value)}
                  />
                  <span className={`flex-shrink-0 h-6 w-6 rounded-md text-xs font-bold flex items-center justify-center transition-colors ${
                    isSelected ? "bg-white/20 text-white" : "bg-slate-100 text-slate-600 group-hover:bg-indigo-100 group-hover:text-indigo-700"
                  }`}>
                    {value}
                  </span>
                  <span className="mt-0.5">{option.replace(/^[A-D]\.\s*/, "")}</span>
                </label>
              );
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}














