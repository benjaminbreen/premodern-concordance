/**
 * Simple sliding-window in-memory rate limiter.
 * No external dependencies — uses a Map of IP → request timestamps.
 */

const windows = new Map<string, number[]>();

/** Prune timestamps older than `windowMs` for a given key. */
function prune(key: string, windowMs: number, now: number): number[] {
  const timestamps = windows.get(key) ?? [];
  const valid = timestamps.filter((t) => now - t < windowMs);
  if (valid.length === 0) {
    windows.delete(key);
  } else {
    windows.set(key, valid);
  }
  return valid;
}

/**
 * Check whether `ip` has exceeded `maxRequests` within the last `windowMs` ms.
 * If under the limit, records the request and returns `{ ok: true }`.
 * If over the limit, returns `{ ok: false, retryAfterSeconds }`.
 */
export function checkRateLimit(
  ip: string,
  maxRequests: number,
  windowMs = 60_000
): { ok: true } | { ok: false; retryAfterSeconds: number } {
  const now = Date.now();
  const recent = prune(ip, windowMs, now);

  if (recent.length >= maxRequests) {
    const oldest = recent[0];
    const retryAfterSeconds = Math.ceil((oldest + windowMs - now) / 1000);
    return { ok: false, retryAfterSeconds };
  }

  recent.push(now);
  windows.set(ip, recent);
  return { ok: true };
}
