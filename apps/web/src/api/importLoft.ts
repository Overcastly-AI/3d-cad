/**
 * `.loft` import data layer (docs/FILE-FORMAT.md) — the route and its types come
 * from the generated `@loft/ts-client` (pydantic → OpenAPI → TS; CLAUDE.md DRY).
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeMessage } from "./envelope";

export type LoftImportResponse = components["schemas"]["LoftImportResponse"];
export type LoftWarning = components["schemas"]["LoftWarning"];

/**
 * Import a `.loft` file as a NEW part (`POST /api/v1/parts/import`). The raw
 * file bytes are the request body (`application/octet-stream`). The server
 * rebuilds the part from the file's tree and answers with the part plus any
 * warnings it did not refuse over; a refusal (a damaged file, a file from a
 * newer Loft) is its envelope message, surfaced verbatim.
 */
export async function importLoftFile(
  bytes: ArrayBuffer,
  client: GatewayClient = gatewayClient,
): Promise<LoftImportResponse> {
  const { data, error } = await client.POST("/api/v1/parts/import", {
    // The generated schema types the octet-stream body as `string`; the raw
    // bytes pass straight through, as on the STEP upload (`api/parts.ts`).
    body: bytes as unknown as string,
    bodySerializer: (raw: unknown) => raw as BodyInit,
    headers: { "Content-Type": "application/octet-stream" },
  });
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The .loft file could not be imported."),
    );
  }
  return data;
}
