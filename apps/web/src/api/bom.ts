/**
 * Assembly bill-of-materials data layer — the flat, direct-instance BOM read
 * model, proxied through the gateway. Types come from the generated
 * `@loft/ts-client` (pydantic → OpenAPI → TS; CLAUDE.md DRY rule); this module
 * never hand-writes an API shape and surfaces the server envelope's own message
 * on failure.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeMessage } from "./envelope";

export type AssemblyBomResponse = components["schemas"]["AssemblyBomResponse"];
export type BomLine = components["schemas"]["BomLine"];
/** part | assembly — the group's referenced-document kind. */
export type RefDocumentKind = BomLine["ref_document_kind"];

/**
 * The assembly's bill of materials: one line per referenced document,
 * quantity = shared-reference count, deterministically ordered by the service
 * (resolved name, then ref_document_id) — the frontend preserves that order.
 * A referenced document deleted while still instanced surfaces as a line with
 * `missing: true` and `name: null`; the read never 500s on a dangling ref.
 */
export async function fetchAssemblyBom(
  assemblyId: string,
  client: GatewayClient = gatewayClient,
): Promise<AssemblyBomResponse> {
  const { data, error } = await client.GET(
    "/api/v1/assemblies/{assembly_id}/bom",
    { params: { path: { assembly_id: assemblyId } } },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The bill of materials could not be loaded."),
    );
  }
  return data;
}
