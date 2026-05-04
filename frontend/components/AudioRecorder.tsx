"use client";

import { useCallback, useRef, useState } from "react";
import { Mic, Square, RotateCcw, Play, Pause } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface AudioRecorderHandle {
  getAudioBlob: () => Blob | null;
  reset: () => void;
  startRecording: () => void;
  stopRecording: () => void;
}

interface AudioRecorderProps {
  onRecordingChange?: (isRecording: boolean) => void;
  onAudioReady?: (blob: Blob) => void;
  maxDurationMs?: number; // Auto-stop after duration
}

/**
 * MediaRecorder-based audio recording component
 * Replaces browser speech recognition with direct audio blob storage
 */
const AudioRecorder = ({
  onRecordingChange,
  onAudioReady,
  maxDurationMs = 30000, // 30 seconds default
}: AudioRecorderProps) => {
  const [isRecording, setIsRecording] = useState(false);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0); // Recording duration in seconds

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recordingStartRef = useRef<number>(0);
  const durationTimerRef = useRef<NodeJS.Timeout | null>(null);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      mediaRecorderRef.current = new MediaRecorder(stream);
      chunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      mediaRecorderRef.current.onstop = () => {
        // Combine chunks into blob
        const blob = new Blob(chunksRef.current, { type: "audio/webm;codecs=opus" });
        setRecordedBlob(blob);
        onAudioReady?.(blob);

        // Stop all audio tracks
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorderRef.current.start();
      recordingStartRef.current = Date.now();
      setIsRecording(true);
      onRecordingChange?.(true);

      // Start duration timer
      setDuration(0);
      durationTimerRef.current = setInterval(() => {
        const elapsed = Math.floor((Date.now() - recordingStartRef.current) / 1000);
        setDuration(elapsed);

        // Auto-stop if max duration reached
        if (elapsed >= maxDurationMs / 1000) {
          stopRecording();
        }
      }, 100);
    } catch (error) {
      console.error("Failed to start recording:", error);
      alert("Microphone access denied. Please allow microphone access.");
    }
  }, [maxDurationMs, onAudioReady, onRecordingChange]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      onRecordingChange?.(false);

      if (durationTimerRef.current) {
        clearInterval(durationTimerRef.current);
      }
    }
  }, [isRecording, onRecordingChange]);

  const playRecording = useCallback(() => {
    if (!recordedBlob || !audioRef.current) return;

    const url = URL.createObjectURL(recordedBlob);
    audioRef.current.src = url;
    audioRef.current.play();
    setIsPlaying(true);

    audioRef.current.onended = () => {
      setIsPlaying(false);
      URL.revokeObjectURL(url);
    };
  }, [recordedBlob]);

  const pausePlayback = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      setIsPlaying(false);
    }
  }, []);

  const resetRecording = useCallback(() => {
    setRecordedBlob(null);
    setDuration(0);
    setIsPlaying(false);
    chunksRef.current = [];
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
    }
  }, []);

  const getAudioBlob = useCallback(() => {
    return recordedBlob;
  }, [recordedBlob]);

  return (
    <div className="space-y-4 p-4 bg-slate-50 rounded-lg border border-slate-200">
      {/* Recording Controls */}
      <div className="flex gap-2">
        {!isRecording ? (
          <Button
            onClick={startRecording}
            disabled={isPlaying}
            className="flex gap-2 bg-red-600 hover:bg-red-700"
          >
            <Mic className="h-4 w-4" />
            Start Recording
          </Button>
        ) : (
          <Button
            onClick={stopRecording}
            className="flex gap-2 bg-red-600 hover:bg-red-700"
          >
            <Square className="h-4 w-4" />
            Stop Recording
          </Button>
        )}

        {recordedBlob && (
          <Button
            onClick={resetRecording}
            variant="outline"
            className="flex gap-2"
          >
            <RotateCcw className="h-4 w-4" />
            Clear
          </Button>
        )}
      </div>

      {/* Duration Display */}
      {isRecording && (
        <div className="text-sm text-slate-600">
          Recording... {duration}s
        </div>
      )}

      {/* Playback Controls */}
      {recordedBlob && !isRecording && (
        <div className="space-y-2">
          <div className="flex gap-2 items-center">
            {!isPlaying ? (
              <Button
                onClick={playRecording}
                variant="outline"
                size="sm"
                className="flex gap-2"
              >
                <Play className="h-4 w-4" />
                Replay
              </Button>
            ) : (
              <Button
                onClick={pausePlayback}
                variant="outline"
                size="sm"
                className="flex gap-2"
              >
                <Pause className="h-4 w-4" />
                Pause
              </Button>
            )}
            <span className="text-sm text-slate-600">
              {recordedBlob.size} bytes
            </span>
          </div>
          <audio ref={audioRef} />
        </div>
      )}

      {/* Status */}
      {recordedBlob && (
        <div className="text-sm text-green-600 font-medium">
          ✓ Audio recorded and ready
        </div>
      )}
    </div>
  );
};

export default AudioRecorder;
