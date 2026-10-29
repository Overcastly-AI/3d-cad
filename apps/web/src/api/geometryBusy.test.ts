import { describe, expect, it } from "vitest";

import {
  GeometryBusyError,
  geometryBusy,
  geometryRetry,
  geometryRetryDelay,
  MAX_BUSY_RETRIES,
} from "./geometryBusy";

function response(status: number, retryAfter?: string): Response {
  return new Response(null, {
    status,
    headers: retryAfter === undefined ? {} : { "Retry-After": retryAfter },
  });
}

describe("geometry's backpressure (CONC-2)", () => {
  it("reads a 503 as busy, with the worker's own Retry-After", () => {
    const busy = geometryBusy(response(503, "21"), "Busy.");
    expect(busy).toBeInstanceOf(GeometryBusyError);
    expect(busy?.retryAfterMs).toBe(21_000);
    expect(busy?.message).toBe("Busy.");
    expect(geometryBusy(response(503), "Busy.")?.retryAfterMs).toBe(5_000);
    expect(geometryBusy(response(422, "21"), "Refused.")).toBeNull();
  });

  it("waits out a busy worker longer than React Query's 7 s default", () => {
    const busy = new GeometryBusyError("Busy.", 15_000);
    expect(geometryRetryDelay(0, busy)).toBe(15_000);
    expect(geometryRetry(MAX_BUSY_RETRIES - 1, busy)).toBe(true);
    expect(geometryRetry(MAX_BUSY_RETRIES, busy)).toBe(false);
    // Total patience: minutes, not the 1 + 2 + 4 s that gave up before.
    expect(MAX_BUSY_RETRIES * 15_000).toBeGreaterThan(60_000);
  });

  it("keeps the default policy for every other failure", () => {
    const other = new Error("The part could not be evaluated.");
    expect(geometryRetry(2, other)).toBe(true);
    expect(geometryRetry(3, other)).toBe(false);
    expect([0, 1, 2].map((n) => geometryRetryDelay(n, other))).toEqual([
      1_000, 2_000, 4_000,
    ]);
  });
});
