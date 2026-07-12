/**
 * Sketch trim/extend data layer — the "draw rough, then clean up" edits,
 * proxied through the gateway to the stateless, constraint-free geometry
 * service. Every type comes from the generated `@loft/ts-client` (pydantic →
 * OpenAPI → TS; CLAUDE.md DRY rule); this module only adds the typed error the
 * 422 envelope codes carry, which the OpenAPI schema cannot express.
 */
import type { components } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeCode, envelopeMessage } from "./envelope";

export type SketchEditRequest = components["schemas"]["SketchEditRequest"];
export type SketchEditResult = components["schemas"]["SketchEditResult"];

/** The two clean-up edits — a trim (cut at intersection) or an extend. */
export type SketchEditOp = "trim" | "extend";

/**
 * A geometry-side edit failure (422): `sketch_target_not_found`,
 * `sketch_pick_not_on_target`, `sketch_unsupported_entity`,
 * `sketch_extend_no_target`, `sketch_degenerate_result`, … Carries the machine
 * code so the UI can decide, and the envelope's human message to show verbatim.
 */
export class SketchEditError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "SketchEditError";
  }
}

/**
 * Apply a trim or extend to one target curve. `request.entities` is the whole
 * sketch (the edit rewrites the set); the result's entity list replaces it,
 * order + ids preserved (see `SketchEditResult` for how a split/delete rewrites
 * the target). The literal paths keep the generated request/response typing.
 */
export async function editSketch(
  op: SketchEditOp,
  request: SketchEditRequest,
  client = gatewayClient,
): Promise<SketchEditResult> {
  const { data, error } =
    op === "trim"
      ? await client.POST("/api/v1/geometry/sketch/trim", { body: request })
      : await client.POST("/api/v1/geometry/sketch/extend", { body: request });
  if (error !== undefined) {
    throw new SketchEditError(
      envelopeCode(error) ?? `sketch_${op}_failed`,
      envelopeMessage(error, `The ${op} could not be applied.`),
    );
  }
  return data;
}
