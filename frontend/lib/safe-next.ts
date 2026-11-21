const DEFAULT_DESTINATION = "/tcf";
const ALLOWED = /^\/tcf(?:\/[A-Za-z0-9\-_/]*)?(?:\?[A-Za-z0-9=&\-_.%]*)?$/;

/** Post-login destination from a `next` parameter: only in-app /tcf paths, never another site. */
export function safeNextPath(raw: string | null | undefined): string {
  if (!raw) return DEFAULT_DESTINATION;
  let value = raw.trim();
  try {
    value = decodeURIComponent(value);
  } catch {
    return DEFAULT_DESTINATION;
  }
  if (value.startsWith("//") || value.includes("\\") || value.includes("..")) return DEFAULT_DESTINATION;
  return ALLOWED.test(value) ? value : DEFAULT_DESTINATION;
}

export function nextPathFromLocation(): string {
  if (typeof window === "undefined") return DEFAULT_DESTINATION;
  return safeNextPath(new URLSearchParams(window.location.search).get("next"));
}
