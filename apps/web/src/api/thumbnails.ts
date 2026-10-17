/**
 * Library thumbnails (LIBRARY-THUMBNAILS) — a document's picture, fetched
 * through the gateway with the session's bearer token (an `<img src>` could
 * not carry it). The gateway answers with an `ETag` and `private, no-cache`,
 * so the browser's own HTTP cache revalidates each fetch and a current picture
 * comes back from a 304 without touching geometry.
 *
 * A 422 means "draw the placeholder": `thumbnail_failed` (the document does
 * not build — never a picture of an older build) or `thumbnail_empty` (nothing
 * to draw yet). A 503 is geometry saying "busy, ask again": thumbnails render
 * only on an idle worker and never queue ahead of modelling, so the answer is a
 * typed `ThumbnailBusyError` carrying `Retry-After`, which the tile waits out.
 *
 * At most `MAX_IN_FLIGHT` thumbnail requests are in flight from one page: a
 * register is one request per row, and the browser should not stampede the
 * gateway with all of them at once (the tiles also load only when scrolled
 * into view).
 */
import type { GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeCode } from "./envelope";

export type ThumbnailKind = "part" | "assembly" | "drawing";

/** Why there is no picture: the document fails to build, or has nothing to draw. */
export type ThumbnailUnavailable = "failed" | "empty";

export type ThumbnailResult =
  | { kind: "image"; blob: Blob }
  | { kind: "unavailable"; reason: ThumbnailUnavailable };

/** The envelope codes behind a 422 (loft_wire.thumbnails). */
const FAILED_CODE = "thumbnail_failed";

/** The server is busy modelling (or rendering another tile): retry later. */
export class ThumbnailBusyError extends Error {
  constructor(readonly retryAfterMs: number) {
    super("The preview is waiting for an idle geometry worker.");
    this.name = "ThumbnailBusyError";
  }
}

/** Concurrent thumbnail requests from this page. */
export const MAX_IN_FLIGHT = 4;

let inFlight = 0;
const waiting: Array<() => void> = [];

/** Run `task` once fewer than `MAX_IN_FLIGHT` thumbnail requests are running. */
async function limited<T>(task: () => Promise<T>): Promise<T> {
  // A loop, not an `if`: a newcomer can take the slot between a release and the
  // woken waiter's turn, and the waiter must then wait again, not overshoot.
  while (inFlight >= MAX_IN_FLIGHT) {
    await new Promise<void>((resolve) => waiting.push(resolve));
  }
  inFlight += 1;
  try {
    return await task();
  } finally {
    inFlight -= 1;
    waiting.shift()?.();
  }
}

function retryAfterMs(response: Response): number {
  const seconds = Number(response.headers.get("Retry-After"));
  return Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : 2000;
}

export function fetchThumbnail(
  kind: ThumbnailKind,
  id: string,
  client: GatewayClient = gatewayClient,
): Promise<ThumbnailResult> {
  return limited(() => requestThumbnail(kind, id, client));
}

async function requestThumbnail(
  kind: ThumbnailKind,
  id: string,
  client: GatewayClient = gatewayClient,
): Promise<ThumbnailResult> {
  const options = { parseAs: "blob" as const };
  const { data, error, response } =
    kind === "part"
      ? await client.GET("/api/v1/parts/{part_id}/thumbnail", {
          ...options,
          params: { path: { part_id: id } },
        })
      : kind === "assembly"
        ? await client.GET("/api/v1/assemblies/{assembly_id}/thumbnail", {
            ...options,
            params: { path: { assembly_id: id } },
          })
        : await client.GET("/api/v1/drawings/{drawing_id}/thumbnail", {
            ...options,
            params: { path: { drawing_id: id } },
          });
  if (response.status === 422) {
    return {
      kind: "unavailable",
      reason: envelopeCode(error) === FAILED_CODE ? "failed" : "empty",
    };
  }
  if (response.status === 503) {
    throw new ThumbnailBusyError(retryAfterMs(response));
  }
  if (!response.ok || data === undefined) {
    throw new Error(`The ${kind} thumbnail could not be loaded.`);
  }
  // parseAs:"blob" makes the runtime payload a Blob (the schema says string).
  return { kind: "image", blob: data as unknown as Blob };
}
