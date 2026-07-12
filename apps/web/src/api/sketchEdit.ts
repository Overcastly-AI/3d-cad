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
export type SketchOffsetRequest = components["schemas"]["SketchOffsetRequest"];
export type SketchOffsetResult = components["schemas"]["SketchOffsetResult"];
export type SketchMirrorRequest = components["schemas"]["SketchMirrorRequest"];
export type SketchMirrorResult = components["schemas"]["SketchMirrorResult"];

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

/**
 * Offset one target curve by a signed distance, ADDING a parallel copy.
 * `request.entities` is the whole sketch (so the new entity gets a fresh,
 * collision-free id); the result carries ONLY the new offset entities, which
 * the caller appends. 422 codes: `sketch_offset_zero_distance`,
 * `sketch_degenerate_result` (an inward offset that collapses the radius),
 * `sketch_unsupported_entity`, `sketch_target_not_found`.
 */
export async function offsetSketch(
  request: SketchOffsetRequest,
  client = gatewayClient,
): Promise<SketchOffsetResult> {
  const { data, error } = await client.POST("/api/v1/geometry/sketch/offset", {
    body: request,
  });
  if (error !== undefined) {
    throw new SketchEditError(
      envelopeCode(error) ?? "sketch_offset_failed",
      envelopeMessage(error, "The offset could not be applied."),
    );
  }
  return data;
}

/**
 * Mirror the `targets` about `axis`, ADDING one reflected copy per target.
 * `request.entities` is the whole sketch (so each copy gets a fresh,
 * collision-free id and a `MirrorAxisEntity` axis can be resolved); the result
 * carries ONLY the new copies, which the caller appends. Like offset, mirror
 * never rewrites the sources. 422 codes: `sketch_target_not_found`,
 * `sketch_mirror_axis_not_line`, `sketch_mirror_degenerate_axis`.
 */
export async function mirrorSketch(
  request: SketchMirrorRequest,
  client = gatewayClient,
): Promise<SketchMirrorResult> {
  const { data, error } = await client.POST("/api/v1/geometry/sketch/mirror", {
    body: request,
  });
  if (error !== undefined) {
    throw new SketchEditError(
      envelopeCode(error) ?? "sketch_mirror_failed",
      envelopeMessage(error, "The mirror could not be applied."),
    );
  }
  return data;
}
