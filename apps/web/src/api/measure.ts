/**
 * Measurement data layer — the selection overlay and the exact nearest-distance
 * query, both proxied through the gateway to the stateless geometry service.
 * Every type comes from the generated `@loft/ts-client` (pydantic → OpenAPI →
 * TS; CLAUDE.md DRY rule); this module only adds the typed error the 422
 * envelope codes carry, which the OpenAPI schema cannot express.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient, MESH_LINEAR_DEFLECTION_MM } from "./client";
import { envelopeCode, envelopeMessage } from "./envelope";

export type Vec3 = components["schemas"]["Vec3"];
export type EvaluateTreeRequest = components["schemas"]["EvaluateTreeRequest"];
export type OverlayRequest = components["schemas"]["OverlayRequest"];
export type OverlayResult = components["schemas"]["OverlayResult"];
export type OverlayEdge = components["schemas"]["OverlayEdge"];
export type MeasureRequest = components["schemas"]["MeasureRequest"];
export type MeasureResult = components["schemas"]["MeasureResult"];
export type MeasureTarget = MeasureRequest["a"];

/**
 * A geometry-side measurement failure (422): `overlay_failed`,
 * `tree_overlay_failed`, `edge_index_out_of_range`, `measure_failed`,
 * `tree_measure_failed`. Carries the machine code so the UI can decide, and
 * the envelope's human message so it can be shown verbatim.
 */
export class MeasureError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "MeasureError";
  }
}

/**
 * The tree the part's measure and pick requests are built from: documents'
 * own evaluation request, through the gateway — every formula resolved, the
 * rollback bar applied, and a feature whose formula no longer resolves
 * carrying its `input_error`, so geometry builds nothing for it here exactly
 * as on evaluate. Built from `GET /features` instead, a sick feature drew a
 * phantom body from its last good numbers in these tools
 * (MEASURE-FROM-EVAL-REQUEST, PART-PARAMETERS).
 *
 * `beforeFeatureId` is the Edit-feature cut: every feature before that one,
 * ignoring the stored bar (the body the feature is built on). Presentation
 * deflection matches the mesh, so overlay edges land on the drawn body.
 */
export async function fetchEvaluationRequest(
  partId: string,
  beforeFeatureId?: string,
  client: GatewayClient = gatewayClient,
): Promise<EvaluateTreeRequest> {
  const { data, error } = await client.GET(
    "/api/v1/parts/{part_id}/evaluation-request",
    {
      params: {
        path: { part_id: partId },
        query: beforeFeatureId === undefined ? {} : { before: beforeFeatureId },
      },
    },
  );
  if (error !== undefined) {
    throw new MeasureError(
      envelopeCode(error) ?? "overlay_failed",
      envelopeMessage(error, "The part could not be read to measure it."),
    );
  }
  return { ...data, linear_deflection: MESH_LINEAR_DEFLECTION_MM };
}

/** The overlay of the part as evaluated ({@link fetchEvaluationRequest}). */
export async function fetchPartOverlay(
  partId: string,
  beforeFeatureId?: string,
): Promise<OverlayResult> {
  return fetchOverlay(await fetchEvaluationRequest(partId, beforeFeatureId));
}

/**
 * The pickable selection geometry (vertices + edges) of an evaluated feature
 * tree. `tree` is the SAME `EvaluateTreeRequest` the body was built from, so
 * the returned edge list indices line up with `/measure`'s `EdgeTarget.index`.
 */
export async function fetchOverlay(
  tree: EvaluateTreeRequest,
  client: GatewayClient = gatewayClient,
): Promise<OverlayResult> {
  const { data, error } = await client.POST("/api/v1/geometry/overlay", {
    body: { tree },
  });
  if (error !== undefined) {
    throw new MeasureError(
      envelopeCode(error) ?? "overlay_failed",
      envelopeMessage(error, "The selection overlay could not be built."),
    );
  }
  return data;
}

/**
 * The exact nearest distance between two targets. `tree` is required iff either
 * target is an edge (the caller passes the same tree used for the overlay);
 * for point-point it is omitted and no body is recomputed.
 */
export async function measureTargets(
  request: MeasureRequest,
  client: GatewayClient = gatewayClient,
): Promise<MeasureResult> {
  const { data, error } = await client.POST("/api/v1/geometry/measure", {
    body: request,
  });
  if (error !== undefined) {
    throw new MeasureError(
      envelopeCode(error) ?? "measure_failed",
      envelopeMessage(error, "The measurement could not be computed."),
    );
  }
  return data;
}
