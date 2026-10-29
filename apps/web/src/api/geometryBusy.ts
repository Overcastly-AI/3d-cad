/**
 * Geometry's backpressure, honoured (CONC-2). A geometry worker admits one
 * rebuild at a time and queues a few; past that it answers 503
 * `service_overloaded` with a `Retry-After` it derives from its own measured
 * rebuild time, and the gateway relays both. A burst of edits (B7's 28 ft
 * edit is five writes, each a new tree version to evaluate) fills that queue
 * with rebuilds of versions nobody shows any more, so the CURRENT version's
 * evaluate is refused while they drain.
 *
 * React Query's default retry (three tries 1, 2 and 4 s apart) gave up inside
 * 7 s, long before the 10-20 s the worker asked for, and the workspace was
 * left with no body and SOLVE "—" until the next edit. The evaluation now
 * waits out the server's `Retry-After` on a busy answer, a bounded number of
 * times, and keeps the default policy for every other failure. Superseded
 * evaluates are aborted (the query's `signal`), so a refused request is not
 * also queued behind stale ones.
 */

/** A 503 `service_overloaded`: geometry is up and asks to be asked again. */
export class GeometryBusyError extends Error {
  readonly retryAfterMs: number;

  constructor(message: string, retryAfterMs: number) {
    super(message);
    this.name = "GeometryBusyError";
    this.retryAfterMs = retryAfterMs;
  }
}

/** When geometry names no `Retry-After`: about one rebuild. */
const DEFAULT_RETRY_AFTER_MS = 5_000;

/**
 * Busy answers waited out per evaluation: at the worker's 10-20 s
 * `Retry-After` this is minutes of patience, and still a bound, so a
 * permanently saturated worker ends in an error the user can read.
 */
export const MAX_BUSY_RETRIES = 8;

/** React Query's own default, for every other failure. */
const DEFAULT_RETRIES = 3;

/** The busy error a 503 *response* is, or null for any other status. */
export function geometryBusy(
  response: Response,
  message: string,
): GeometryBusyError | null {
  if (response.status !== 503) return null;
  const seconds = Number(response.headers.get("Retry-After"));
  const retryAfterMs =
    Number.isFinite(seconds) && seconds > 0
      ? seconds * 1000
      : DEFAULT_RETRY_AFTER_MS;
  return new GeometryBusyError(message, retryAfterMs);
}

/** `retry` for a geometry query: busy answers longer, others as default. */
export function geometryRetry(failureCount: number, error: Error): boolean {
  return error instanceof GeometryBusyError
    ? failureCount < MAX_BUSY_RETRIES
    : failureCount < DEFAULT_RETRIES;
}

/** `retryDelay` for a geometry query: the server's `Retry-After` when busy. */
export function geometryRetryDelay(failureCount: number, error: Error): number {
  return error instanceof GeometryBusyError
    ? error.retryAfterMs
    : Math.min(1000 * 2 ** failureCount, 30_000);
}
