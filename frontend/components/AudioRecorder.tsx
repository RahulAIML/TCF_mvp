"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Mic, Square, RotateCcw, Play, Pause } from "lucide-react";
import { Button } from "@/components/ui/button";
import { createRecorder, microphoneErrorMessage, recordedMime } from "@/lib/audio-mime";

interface AudioRecorderProps {
  onRecordingChange?: (isRecording: boolean) => void;
  onAudioReady?: (blob: Blob) => void;
  maxDurationMs?: number;
}

/** MediaRecorder-based recorder with replay; the blob is labelled with the format actually recorded. */
const AudioRecorder = ({
  onRecordingChange,
  onAudioReady,
  maxDurationMs = 30000,
}: AudioRecorderProps) => {
  const [isRecording, setIsRecording] = useState(false);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState("");

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recordingStartRef = useRef<number>(0);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const playbackUrlRef = useRef<string | null>(null);

  const clearTimer = useCallback(() => {
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }
  }, []);

  useEffect(() => () => {
    clearTimer();
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    if (playbackUrlRef.current) URL.revokeObjectURL(playbackUrlRef.current);
  }, [clearTimer]);

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
  }, []);

  const startRecording = useCallback(async () => {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError(microphoneErrorMessage(null));
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = createRecorder(stream);
      mediaRecorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      // Runs for manual stops and for the automatic stop at maxDurationMs alike.
      recorder.onstop = () => {
        clearTimer();
        stream.getTracks().forEach((track) => track.stop());
        setIsRecording(false);
        onRecordingChange?.(false);
        if (chunksRef.current.length === 0) return;
        const blob = new Blob(chunksRef.current, { type: recordedMime(recorder, chunksRef.current) });
        setRecordedBlob(blob);
        onAudioReady?.(blob);
      };

      recorder.start(250);
      recordingStartRef.current = Date.now();
      setRecordedBlob(null);
      setIsRecording(true);
      onRecordingChange?.(true);

      setDuration(0);
      durationTimerRef.current = setInterval(() => {
        const elapsed = Math.floor((Date.now() - recordingStartRef.current) / 1000);
        setDuration(elapsed);
        if (elapsed >= maxDurationMs / 1000) stopRecording();
      }, 200);
    } catch (err) {
      setError(microphoneErrorMessage(err));
    }
  }, [clearTimer, maxDurationMs, onAudioReady, onRecordingChange, stopRecording]);

  const playRecording = useCallback(() => {
    if (!recordedBlob || !audioRef.current) return;
    if (playbackUrlRef.current) URL.revokeObjectURL(playbackUrlRef.current);
    const url = URL.createObjectURL(recordedBlob);
    playbackUrlRef.current = url;
    audioRef.current.src = url;
    audioRef.current.onended = () => setIsPlaying(false);
    audioRef.current.play().then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
  }, [recordedBlob]);

  const pausePlayback = useCallback(() => {
    audioRef.current?.pause();
    setIsPlaying(false);
  }, []);

  const resetRecording = useCallback(() => {
    setRecordedBlob(null);
    setDuration(0);
    setIsPlaying(false);
    chunksRef.current = [];
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.removeAttribute("src");
    }
  }, []);

  const remaining = Math.max(0, Math.ceil(maxDurationMs / 1000) - duration);

  return (
    <div className="space-y-4 p-4 bg-slate-50 rounded-lg border border-slate-200">
      <div className="flex gap-2">
        {!isRecording ? (
          <Button onClick={startRecording} disabled={isPlaying} className="flex gap-2 bg-red-600 hover:bg-red-700">
            <Mic className="h-4 w-4" />
            {recordedBlob ? "Record Again" : "Start Recording"}
          </Button>
        ) : (
          <Button onClick={stopRecording} className="flex gap-2 bg-red-600 hover:bg-red-700">
            <Square className="h-4 w-4" />
            Stop Recording
          </Button>
        )}

        {recordedBlob && !isRecording && (
          <Button onClick={resetRecording} variant="outline" className="flex gap-2">
            <RotateCcw className="h-4 w-4" />
            Clear
          </Button>
        )}
      </div>

      {isRecording && (
        <div className="text-sm text-slate-600">
          Recording… {duration}s <span className="text-slate-400">({remaining}s left)</span>
        </div>
      )}

      {error && (
        <div className="flex gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      {recordedBlob && !isRecording && (
        <div className="flex gap-2 items-center">
          {!isPlaying ? (
            <Button onClick={playRecording} variant="outline" size="sm" className="flex gap-2">
              <Play className="h-4 w-4" />
              Replay
            </Button>
          ) : (
            <Button onClick={pausePlayback} variant="outline" size="sm" className="flex gap-2">
              <Pause className="h-4 w-4" />
              Pause
            </Button>
          )}
          <span className="text-sm text-green-600 font-medium">✓ Recording ready ({duration}s)</span>
        </div>
      )}
      <audio ref={audioRef} className="hidden" />
    </div>
  );
};

export default AudioRecorder;
