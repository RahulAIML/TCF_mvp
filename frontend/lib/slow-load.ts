"use client";

import { useEffect, useState } from "react";

/** True once a loading flag has stayed on for `ms`. The spinner should be replaced by a retry. */
export function useSlow(active: boolean, ms = 20000): boolean {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!active) {
      setSlow(false);
      return;
    }
    const timer = window.setTimeout(() => setSlow(true), ms);
    return () => window.clearTimeout(timer);
  }, [active, ms]);
  return slow;
}

export const SLOW_MESSAGE = "The service is temporarily unavailable. Please try again.";
