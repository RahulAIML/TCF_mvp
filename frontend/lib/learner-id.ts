/** A stable id for this browser, sent on every content request so the server can remember what was served.

 * localStorage is the primary store. A cookie is written as well so a request still carries the id
 * if storage is blocked after the id was created, and so the server can read it without a header.
 */
const STORAGE_KEY = "tcf_learner_id";
const COOKIE = "tcf_learner_id";

function readCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|; )tcf_learner_id=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function writeCookie(id: string): void {
  if (typeof document === "undefined") return;
  document.cookie = `${COOKIE}=${encodeURIComponent(id)}; Max-Age=31536000; Path=/; SameSite=Lax`;
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}-${Math.random().toString(16).slice(2)}`;
}

export function getLearnerId(): string {
  if (typeof window === "undefined") return "";
  try {
    const existing = window.localStorage.getItem(STORAGE_KEY) || readCookie();
    if (existing && existing.length >= 8) {
      window.localStorage.setItem(STORAGE_KEY, existing);
      writeCookie(existing);
      return existing;
    }
    const created = newId();
    window.localStorage.setItem(STORAGE_KEY, created);
    writeCookie(created);
    return created;
  } catch {
    const fromCookie = readCookie();
    if (fromCookie) return fromCookie;
    const created = newId();
    writeCookie(created);
    return created;
  }
}
