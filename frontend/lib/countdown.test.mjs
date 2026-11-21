// Run: node --experimental-strip-types --test frontend/lib/countdown.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { createCountdown, remainingSeconds, setRunning, takeExpiry } from "./countdown.ts";

test("counts down from real time, not from ticks", () => {
  let c = setRunning(createCountdown(60), true, 1_000);
  assert.equal(remainingSeconds(c, 1_000), 60);
  // A backgrounded tab may not tick for 40 s: the time left is still exact.
  assert.equal(remainingSeconds(c, 41_000), 20);
  assert.equal(remainingSeconds(c, 61_000), 0);
  assert.equal(remainingSeconds(c, 99_000), 0);
});

test("rounds up so the display never shows 0 early", () => {
  const c = setRunning(createCountdown(10), true, 0);
  assert.equal(remainingSeconds(c, 9_001), 1);
  assert.equal(remainingSeconds(c, 10_000), 0);
});

test("pause keeps the exact time left and resume continues from it", () => {
  let c = setRunning(createCountdown(100), true, 0);
  c = setRunning(c, false, 30_500); // paused with 69.5 s left
  assert.equal(remainingSeconds(c, 500_000), 70); // frozen while paused
  c = setRunning(c, true, 1_000_000);
  assert.equal(remainingSeconds(c, 1_000_000), 70);
  assert.equal(remainingSeconds(c, 1_069_500), 0);
});

test("repeated start/pause calls are idempotent", () => {
  let c = setRunning(createCountdown(30), true, 0);
  const again = setRunning(c, true, 10_000);
  assert.equal(again, c, "a second start must not move the deadline");
  c = setRunning(c, false, 5_000);
  assert.equal(setRunning(c, false, 9_000), c);
});

test("expiry fires exactly once, only after the deadline, only while running", () => {
  let c = createCountdown(5);
  assert.equal(takeExpiry(c, 10_000).fire, false, "not started");
  c = setRunning(c, true, 0);
  assert.equal(takeExpiry(c, 4_999).fire, false);
  let r = takeExpiry(c, 5_000);
  assert.equal(r.fire, true);
  r = takeExpiry(r.state, 6_000);
  assert.equal(r.fire, false);
});

test("a zero-length countdown expires as soon as it runs", () => {
  const c = setRunning(createCountdown(0), true, 0);
  assert.equal(takeExpiry(c, 0).fire, true);
});
