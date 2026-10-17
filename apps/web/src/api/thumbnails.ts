/**
 * Library thumbnails (LIBRARY-THUMBNAILS) — a document's picture, fetched
 * through the gateway with the session's bearer token (an `<img src>` could
 * not carry it). The gateway answers with an `ETag` and `private, no-cache`,
 * so the browser's own HTTP cache revalidates each fetch and a current picture
 * comes back from a 304 without touching geometry.
 *
 * A 422 means "draw the placeholder": `thumbnail_failed` (the document does
 * not build — never a picture of an older build) or `thumbnail_empty` (nothing
 * to draw yet). Anything else is an ordinary error the caller may retry.
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

export async function fetchThumbnail(
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
  if (!response.ok || data === undefined) {
    throw new Error(`The ${kind} thumbnail could not be loaded.`);
  }
  // parseAs:"blob" makes the runtime payload a Blob (the schema says string).
  return { kind: "image", blob: data as unknown as Blob };
}
