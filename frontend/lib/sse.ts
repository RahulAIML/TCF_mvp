import { API_BASE_URL, authHeaders, friendlyErrorMessage, friendlyNetworkError } from "@/services/api";

export type SSEEvent = Record<string, unknown>;

/**
 * POST `body` to a backend SSE endpoint and call `onEvent` for every `data: {...}` event until `[DONE]`.
 * Throws a student-friendly Error on HTTP or network failure. Abort with `signal`.
 */
export async function streamSSE(
  path: string,
  body: unknown,
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
      cache: "no-store",
      signal,
    });
  } catch (err) {
    if (signal?.aborted) throw err;
    throw friendlyNetworkError(err);
  }
  if (!res.ok || !res.body) {
    throw new Error(await friendlyErrorMessage(res));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const handleLine = (line: string): boolean => {
    if (!line.startsWith("data: ")) return false;
    const raw = line.slice(6).trim();
    if (raw === "[DONE]") return true;
    try {
      onEvent(JSON.parse(raw) as SSEEvent);
    } catch {
      // Ignore a malformed chunk rather than aborting the whole answer.
    }
    return false;
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (handleLine(line)) {
          await reader.cancel().catch(() => undefined);
          return;
        }
      }
    }
    if (buffer) handleLine(buffer);
  } catch (err) {
    if (signal?.aborted) throw err;
    throw friendlyNetworkError(err);
  }
}

/**
 * Stream a plain token endpoint. `onText` receives the full text so far after each token.
 * Resolves with the final text; an `{"error"}` event becomes a thrown Error.
 */
export async function streamText(
  path: string,
  body: unknown,
  onText: (textSoFar: string) => void,
  signal?: AbortSignal
): Promise<string> {
  let text = "";
  let error = "";
  await streamSSE(
    path,
    body,
    (event) => {
      if (typeof event.token === "string") {
        text += event.token;
        onText(text);
      } else if (typeof event.error === "string") {
        error = event.error;
      }
    },
    signal
  );
  if (error && !text) throw new Error(error);
  return text;
}
