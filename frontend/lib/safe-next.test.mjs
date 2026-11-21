// Run: node --experimental-strip-types --test frontend/lib/safe-next.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { safeNextPath } from "./safe-next.ts";

test("allows in-app /tcf destinations", () => {
  assert.equal(safeNextPath("/tcf/dashboard"), "/tcf/dashboard");
  assert.equal(safeNextPath("%2Ftcf%2Fdashboard"), "/tcf/dashboard");
  assert.equal(safeNextPath("/tcf"), "/tcf");
  assert.equal(safeNextPath("/tcf/listening-exam?mode=practice"), "/tcf/listening-exam?mode=practice");
});

test("falls back to /tcf for anything else", () => {
  for (const bad of [
    null, undefined, "", "https://evil.example", "//evil.example", "/\\evil.example", "/tcfevil",
    "/tcf/../login", "/login", "javascript:alert(1)", "%2F%2Fevil.example", "%E0%A4%A", "/tcf/<script>"
  ]) {
    assert.equal(safeNextPath(bad), "/tcf", String(bad));
  }
});
