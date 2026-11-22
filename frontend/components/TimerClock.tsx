"use client";

import { useEffect, useRef, useState } from "react";
import { createCountdown, remainingSeconds, setRunning, takeExpiry, type Countdown } from "@/lib/countdown";

interface TimerClockProps {
  durationSeconds: number;
  isActive: boolean;
  resetKey: number;
  onExpire?: () => void;
  /** Called with the exact seconds left (at least once a second while running). */
  onTick?: (secondsLeft: number) => void;
  /** Shown instead of the clock while the exam is waiting or paused. */
  holdLabel?: string;
}

function formatTime(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

export default function TimerClock({
  durationSeconds,
  isActive,
  resetKey,
  onExpire,
  onTick,
  holdLabel
}: TimerClockProps) {
  const [remaining, setRemaining] = useState(durationSeconds);
  const label = formatTime(remaining);
  const countdownRef = useRef<Countdown>(createCountdown(durationSeconds));
  const resetRef = useRef(`${resetKey}:${durationSeconds}`);
  // Latest callbacks without restarting the clock when the parent re-renders with new function identities.
  const onExpireRef = useRef(onExpire);
  const onTickRef = useRef(onTick);
  onExpireRef.current = onExpire;
  onTickRef.current = onTick;

  useEffect(() => {
    const now = Date.now();
    const reset = `${resetKey}:${durationSeconds}`;
    if (resetRef.current !== reset) {
      resetRef.current = reset;
      countdownRef.current = createCountdown(durationSeconds);
    }
    countdownRef.current = setRunning(countdownRef.current, isActive, now);
    const left = remainingSeconds(countdownRef.current, now);
    setRemaining(left);
    onTickRef.current?.(left);
  }, [durationSeconds, resetKey, isActive]);

  useEffect(() => {
    if (!isActive) return;
    const update = () => {
      const now = Date.now();
      const left = remainingSeconds(countdownRef.current, now);
      setRemaining(left);
      onTickRef.current?.(left);
      const { state, fire } = takeExpiry(countdownRef.current, now);
      countdownRef.current = state;
      if (fire) onExpireRef.current?.();
    };
    update();
    const id = window.setInterval(update, 250);
    const onVisible = () => {
      if (document.visibilityState === "visible") update();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [isActive, resetKey, durationSeconds]);

  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm">
      <p className="text-xs font-medium uppercase text-slate-400">Time Remaining</p>
      <p className={`text-base font-semibold ${!holdLabel && remaining <= 60 ? "text-rose-600" : "text-slate-900"}`}>
        {holdLabel ?? label}
      </p>
    </div>
  );
}
