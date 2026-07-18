/**
 * Body-mesh data layer — fetches an evaluated body's content-addressed GLB
 * through the gateway proxy (feature-tree design §7.8). All types come from
 * the generated `@loft/ts-client` (CLAUDE.md DRY rule); this module only adds
 * the `mesh_not_found` narrowing the OpenAPI schema can't express.
 */
import type { GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeCode, envelopeMessage } from "./envelope";

/**
 * The `mesh_glb_id` artifact is gone from geometry's in-process LRU (§7.8):
 * a 404 `mesh_not_found`. This is NOT a hard failure — it is the re-evaluate
 * signal (§4.4). Callers re-run the evaluate to regenerate the artifact.
 */
export class MeshNotFoundError extends Error {
  constructor(readonly meshGlbId: string) {
    super(
      `The body mesh (${meshGlbId}) is no longer cached — regenerating it.`,
    );
    this.name = "MeshNotFoundError";
  }
}

/**
 * Fetch one evaluated body's GLB bytes, ready for the same GLB→mesh pipeline
 * first light uses. A 404 becomes a typed `MeshNotFoundError` (the
 * re-evaluate signal); every other non-2xx surfaces the envelope message.
 */
export async function fetchBodyMesh(
  meshGlbId: string,
  client: GatewayClient = gatewayClient,
): Promise<ArrayBuffer> {
  const { data, error, response } = await client.GET(
    "/api/v1/geometry/meshes/{mesh_glb_id}",
    {
      params: { path: { mesh_glb_id: meshGlbId } },
      parseAs: "arrayBuffer",
    },
  );
  // With parseAs:"arrayBuffer" a 404 envelope arrives as bytes, not JSON —
  // trust the status first, fall back to the code when it did parse.
  if (response.status === 404 || envelopeCode(error) === "mesh_not_found") {
    throw new MeshNotFoundError(meshGlbId);
  }
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The body mesh could not be loaded."),
    );
  }
  if (data === undefined) {
    throw new Error("The body mesh response was empty.");
  }
  // The OpenAPI schema types binary content as string; parseAs:"arrayBuffer"
  // makes the runtime payload an ArrayBuffer (openapi-fetch pass-through).
  return data as unknown as ArrayBuffer;
}
