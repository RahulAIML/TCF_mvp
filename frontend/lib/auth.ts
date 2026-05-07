const COOKIE_NAME = "tcf_auth";

/** Parse the `exp` epoch (ms) from a JWT payload. Returns null on failure. */
export function parseTokenExpiry(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return typeof payload.exp === "number" ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

/** Returns true when the token has expired or is within 60 s of expiry. */
export function isTokenExpired(token: string): boolean {
  const expiry = parseTokenExpiry(token);
  if (expiry === null) return true; // malformed → treat as expired
  return Date.now() >= expiry - 60_000;
}

function setCookie(value: string, expiryMs: number | null): void {
  if (typeof document === "undefined") return;
  const expStr = expiryMs ? `; expires=${new Date(expiryMs).toUTCString()}` : "";
  document.cookie = `${COOKIE_NAME}=${encodeURIComponent(value)}${expStr}; path=/; SameSite=Lax`;
}

function deleteCookie(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${COOKIE_NAME}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax`;
}

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("tcf_token");
}

/** Write token to localStorage AND sync cookie with the JWT's own expiry. */
export function setAuthToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem("tcf_token", token);
  setCookie(token, parseTokenExpiry(token)); // cookie expires when JWT expires
}

export function clearAuthToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem("tcf_token");
  deleteCookie();
}
