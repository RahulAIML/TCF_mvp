/**
 * Lightweight pub/sub for cross-module auth events.
 * api.ts emits; auth-context subscribes — no circular imports.
 */
type Listener = () => void;
const listeners = new Set<Listener>();

export function onAuthFailure(cb: Listener): void {
  listeners.add(cb);
}

export function offAuthFailure(cb: Listener): void {
  listeners.delete(cb);
}

export function emitAuthFailure(): void {
  listeners.forEach((cb) => cb());
}
