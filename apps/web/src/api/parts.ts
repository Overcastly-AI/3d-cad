/**
 * Parts + feature-tree data layer — all types come from the generated
 * `@loft/ts-client` (pydantic → OpenAPI → TS; CLAUDE.md DRY rule). Errors
 * surface the server envelope's own message.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeCode, envelopeMessage } from "./envelope";

export type PartResponse = components["schemas"]["PartResponse"];
export type FeatureTreeResponse = components["schemas"]["FeatureTreeResponse"];
export type FeatureResponse = components["schemas"]["FeatureResponse"];
export type FeatureCreate = components["schemas"]["FeatureCreate"];
export type FeatureMutationResponse =
  components["schemas"]["FeatureMutationResponse"];
export type EvaluateTreeResult = components["schemas"]["EvaluateTreeResult"];
export type FeatureResult = components["schemas"]["FeatureResult"];
export type SolvedSketchData = components["schemas"]["SolvedSketchData"];
export type SketchFeature = components["schemas"]["SketchFeature"];
export type SketchEntity =
  components["schemas"]["SketchParamsV1"]["entities"][number];
export type SketchConstraint =
  components["schemas"]["SketchParamsV1"]["constraints"][number];
export type FeatureUpdate = components["schemas"]["FeatureUpdate"];
export type DatumPlaneName = components["schemas"]["DatumPlaneRef"]["plane"];
export type ExtrudeFeature = components["schemas"]["ExtrudeFeature"];
export type ExtrudeParams = components["schemas"]["ExtrudeParamsV1"];
export type RevolveFeature = components["schemas"]["RevolveFeature"];
export type RevolveParams = components["schemas"]["RevolveParamsV1"];
export type PatternFeature = components["schemas"]["PatternFeature"];
export type PatternParams = components["schemas"]["PatternParamsV1"];
export type LinearPatternParams =
  components["schemas"]["LinearPatternParamsV1"];
export type CircularPatternParams =
  components["schemas"]["CircularPatternParamsV1"];
export type Vec3 = components["schemas"]["Vec3"];

export type PartCreate = components["schemas"]["PartCreate"];

/**
 * The chosen name already belongs to another of the caller's parts (documents
 * enforces a per-owner unique index → gateway 409 `part_name_taken`). Typed so
 * the register can surface it on the name field, not as a generic banner —
 * mirrors `MeshNotFoundError`: a narrowing the OpenAPI schema can't express.
 */
export class PartNameTakenError extends Error {
  constructor(
    readonly partName: string,
    message: string,
  ) {
    super(message);
    this.name = "PartNameTakenError";
  }
}

/** The caller's parts, oldest first (register order). */
export async function fetchParts(
  client: GatewayClient = gatewayClient,
): Promise<PartResponse[]> {
  const { data, error } = await client.GET("/api/v1/parts");
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "Your parts could not be loaded."));
  }
  return data.parts;
}

/**
 * Create a part owned by the caller (201). A duplicate name is a 409
 * `part_name_taken` — thrown as a typed `PartNameTakenError` so the form can
 * pin the message to the name field; every other failure surfaces its message.
 */
export async function createPart(
  name: string,
  client: GatewayClient = gatewayClient,
): Promise<PartResponse> {
  const { data, error } = await client.POST("/api/v1/parts", {
    body: { name },
  });
  if (error !== undefined) {
    if (envelopeCode(error) === "part_name_taken") {
      throw new PartNameTakenError(
        name,
        envelopeMessage(error, `A part named "${name}" already exists.`),
      );
    }
    throw new Error(envelopeMessage(error, "The part could not be created."));
  }
  return data;
}

/** Delete one of the caller's parts (204; 404 for unknown/foreign ids). */
export async function deletePart(
  partId: string,
  client: GatewayClient = gatewayClient,
): Promise<void> {
  const { error } = await client.DELETE("/api/v1/parts/{part_id}", {
    params: { path: { part_id: partId } },
  });
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The part could not be deleted."));
  }
}

/** One of the caller's parts. */
export async function fetchPart(
  partId: string,
  client: GatewayClient = gatewayClient,
): Promise<PartResponse> {
  const { data, error } = await client.GET("/api/v1/parts/{part_id}", {
    params: { path: { part_id: partId } },
  });
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The part could not be loaded."));
  }
  return data;
}

/** The part's ordered feature tree + its concurrency token. */
export async function fetchFeatureTree(
  partId: string,
  client: GatewayClient = gatewayClient,
): Promise<FeatureTreeResponse> {
  const { data, error } = await client.GET("/api/v1/parts/{part_id}/features", {
    params: { path: { part_id: partId } },
  });
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The feature tree could not be loaded."),
    );
  }
  return data;
}

/**
 * Evaluate the part's current tree; the result carries per-feature statuses
 * and SOLVED sketch geometry (`FeatureResult.data`) — the sketcher renders
 * those solved positions, never its own input echo, so constraints (#5)
 * change the picture without changing this code path.
 */
export async function evaluatePart(
  partId: string,
  client: GatewayClient = gatewayClient,
): Promise<EvaluateTreeResult> {
  const { data, error } = await client.POST(
    "/api/v1/parts/{part_id}/evaluate",
    { params: { path: { part_id: partId } } },
  );
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The part could not be evaluated."));
  }
  return data;
}

/** The `{type, version, params}` envelope shared by create and update. */
function sketchFeatureEnvelope(
  plane: DatumPlaneName,
  entities: readonly SketchEntity[],
  constraints: readonly SketchConstraint[],
): SketchFeature {
  return {
    type: "sketch",
    version: 1,
    params: {
      plane: { kind: "datum_plane", plane },
      entities: [...entities],
      constraints: [...constraints],
    },
  };
}

/**
 * The save payload for a locally buffered sketch (entities + constraints)
 * on a v1 datum plane. Pure — unit-tested against the generated types.
 */
export function sketchFeatureCreate(
  name: string,
  plane: DatumPlaneName,
  entities: readonly SketchEntity[],
  constraints: readonly SketchConstraint[],
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: sketchFeatureEnvelope(plane, entities, constraints),
  };
}

/**
 * The re-save payload of the live parametric loop: every constraint or
 * dimension edit PATCHes the bound feature's whole sketch envelope (the
 * feature `type` is immutable; params are replaced wholesale).
 */
export function sketchFeatureUpdate(
  plane: DatumPlaneName,
  entities: readonly SketchEntity[],
  constraints: readonly SketchConstraint[],
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: sketchFeatureEnvelope(plane, entities, constraints),
  };
}

/** The `{type, version, params}` envelope shared by extrude create and update. */
function extrudeFeatureEnvelope(params: ExtrudeParams): ExtrudeFeature {
  return { type: "extrude", version: 1, params };
}

/**
 * The create payload for an extrude feature: a linear cut of an EARLIER
 * sketch's profile (design §2.2). Pure — unit-tested against the generated
 * types, matching `sketchFeatureCreate`.
 */
export function extrudeFeatureCreate(
  name: string,
  params: ExtrudeParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: extrudeFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing extrude (no rename). */
export function extrudeFeatureUpdate(
  params: ExtrudeParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: extrudeFeatureEnvelope(params),
  };
}

/** The `{type, version, params}` envelope shared by revolve create and update. */
function revolveFeatureEnvelope(params: RevolveParams): RevolveFeature {
  return { type: "revolve", version: 1, params };
}

/**
 * The create payload for a revolve feature: a swept revolution of an EARLIER
 * sketch's profile about a sketch-line axis (design §4.3, the extrude sibling).
 * Pure — unit-tested against the generated types, matching `extrudeFeatureCreate`.
 */
export function revolveFeatureCreate(
  name: string,
  params: RevolveParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: revolveFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing revolve (no rename). */
export function revolveFeatureUpdate(
  params: RevolveParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: revolveFeatureEnvelope(params),
  };
}

/** The `{type, version, params}` envelope shared by pattern create and update. */
function patternFeatureEnvelope(params: PatternParams): PatternFeature {
  return { type: "pattern", version: 1, params };
}

/**
 * The create payload for a pattern feature: repeat the current single body into
 * a linear row or circular ring, unioning the copies (design §7.6, the
 * revolve/fillet sibling — no `FeatureRef`, it acts on the implicit body chain
 * at its point in the tree). Pure — unit-tested against the generated types.
 */
export function patternFeatureCreate(
  name: string,
  params: PatternParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: patternFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing pattern (no rename). */
export function patternFeatureUpdate(
  params: PatternParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: patternFeatureEnvelope(params),
  };
}

/**
 * Move the rollback bar (design §3): `rollbackFeatureId` names the last
 * INCLUDED feature, or null for the tip (everything included). Returns the
 * renumbered tree + its new concurrency token.
 */
export async function moveRollbackBar(
  partId: string,
  rollbackFeatureId: string | null,
  expectedTreeVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<FeatureTreeResponse> {
  const { data, error } = await client.PUT("/api/v1/parts/{part_id}/rollback", {
    params: { path: { part_id: partId } },
    body: {
      rollback_feature_id: rollbackFeatureId,
      expected_tree_version: expectedTreeVersion,
    },
  });
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The rollback bar could not be moved."),
    );
  }
  return data;
}

/** Replace a feature's params (200; 422 on stale version). */
export async function updateFeature(
  partId: string,
  featureId: string,
  body: FeatureUpdate,
  client: GatewayClient = gatewayClient,
): Promise<FeatureMutationResponse> {
  const { data, error } = await client.PATCH(
    "/api/v1/parts/{part_id}/features/{feature_id}",
    {
      params: { path: { part_id: partId, feature_id: featureId } },
      body,
    },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(
        error,
        "The sketch could not be saved — reload and try again.",
      ),
    );
  }
  return data;
}

/** Create a feature at the tip of the tree (201; 422 on stale version). */
export async function createFeature(
  partId: string,
  body: FeatureCreate,
  client: GatewayClient = gatewayClient,
): Promise<FeatureMutationResponse> {
  const { data, error } = await client.POST(
    "/api/v1/parts/{part_id}/features",
    { params: { path: { part_id: partId } }, body },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(
        error,
        "The sketch could not be saved — reload and try again.",
      ),
    );
  }
  return data;
}
