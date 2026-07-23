/**
 * Parts + feature-tree data layer — all types come from the generated
 * `@loft/ts-client` (pydantic → OpenAPI → TS; CLAUDE.md DRY rule). Errors
 * surface the server envelope's own message.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeCode, envelopeMessage } from "./envelope";

export type PartResponse = components["schemas"]["PartResponse"];
/** Document display unit — the single source is the generated contract. */
export type LengthUnit = PartResponse["length_unit"];
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
/** The sketch `plane` slot on the wire: an origin datum OR a datum FeatureRef. */
export type SketchPlaneRef = SketchParamsV1["plane"];
export type SketchParamsV1 = components["schemas"]["SketchParamsV1"];
export type DatumFeature = components["schemas"]["DatumFeature"];
/**
 * The full datum params union: an offset-from-origin plane, an on-a-face plane,
 * an offset-from-another-datum plane (chaining), or a midplane between two
 * references — discriminated on `kind` (matches the pydantic `DatumParams`
 * union; CLAUDE.md DRY rule). The `datum` create/update builders and the editor
 * author every member.
 */
export type DatumParams = DatumFeature["params"];
/** Offset-from-origin datum params (`kind: "offset"`) — base + offset + flip. */
export type DatumOffsetParams = components["schemas"]["DatumOffsetParams"];
/** Offset-from-another-datum params (`kind: "offset_from"`) — chaining. */
export type DatumOffsetFromParams =
  components["schemas"]["DatumOffsetFromParams"];
/** Midplane params (`kind: "midplane"`) — a plane midway between two sides. */
export type DatumMidplaneParams = components["schemas"]["DatumMidplaneParams"];
/** One side of a midplane: an origin datum, an earlier datum, or a picked face. */
export type MidplaneSide = DatumMidplaneParams["a"];
/** A reference to one of the three origin datum planes (XY/XZ/YZ). */
export type DatumPlaneRef = components["schemas"]["DatumPlaneRef"];
/** On-face datum params — a datum adopting a picked planar face's plane. */
export type DatumOnFaceParams = components["schemas"]["DatumOnFaceParams"];
/** Stage-1 reference to one planar face of a body-affecting feature's result. */
export type SubshapeRef = components["schemas"]["SubshapeRef"];
/** The planar-face fingerprint an overlay face carries and a datum echoes. */
export type PlanarFaceSignature = components["schemas"]["PlanarFaceSignature"];
/** One pickable face of the evaluated body (from `OverlayResult.faces`). */
export type OverlayFace = components["schemas"]["OverlayFace"];
export type ExtrudeFeature = components["schemas"]["ExtrudeFeature"];
export type ExtrudeParams = components["schemas"]["ExtrudeParamsV1"];
export type RevolveFeature = components["schemas"]["RevolveFeature"];
export type RevolveParams = components["schemas"]["RevolveParamsV1"];
export type SweepFeature = components["schemas"]["SweepFeature"];
export type SweepParams = components["schemas"]["SweepParamsV1"];
export type LoftFeature = components["schemas"]["LoftFeature"];
export type LoftParams = components["schemas"]["LoftParamsV1"];
/** One ordered section slot of a loft — a `FeatureRef` to an earlier sketch. */
export type FeatureRef = components["schemas"]["FeatureRef"];
export type FilletFeature = components["schemas"]["FilletFeature"];
export type FilletParams = components["schemas"]["FilletParamsV1"];
export type ChamferFeature = components["schemas"]["ChamferFeature"];
export type ChamferParams = components["schemas"]["ChamferParamsV1"];
/** The shared fillet/chamfer edge selector: a predicate OR picked-edge refs. */
export type EdgeSelector = FilletParams["edges"];
/** SPECIFIC picked edges named by stage-1 signature refs (`{kind:"edges"}`). */
export type PickedEdgesSelector = components["schemas"]["PickedEdgesSelector"];
/** Stage-1 reference to ONE edge of a body-affecting feature's result. */
export type EdgeSubshapeRef = components["schemas"]["EdgeSubshapeRef"];
/** The stage-1 geometric fingerprint an overlay edge carries and a ref echoes. */
export type EdgeSignature = components["schemas"]["EdgeSignature"];
export type HoleFeature = components["schemas"]["HoleFeature"];
/** A face-placed cylindrical hole — through-all or blind (slice 1). */
export type HoleParams = components["schemas"]["HoleParamsV1"];
/** The hole `depth` slot on the wire: through-all, or a blind pocket depth. */
export type HoleDepth = HoleParams["depth"];
export type ShellFeature = components["schemas"]["ShellFeature"];
export type ShellParams = components["schemas"]["ShellParamsV1"];
/** The shell's picked-face selector: the faces to leave OPEN (empty = sealed). */
export type FaceSelector = components["schemas"]["FaceSelector"];
export type DraftFeature = components["schemas"]["DraftFeature"];
export type DraftParams = components["schemas"]["DraftParamsV1"];
/** The draft neutral (parting) plane: a principal datum, offset + flipped. */
export type DraftNeutralPlane = components["schemas"]["DraftNeutralPlaneV1"];
export type BooleanFeature = components["schemas"]["BooleanFeature"];
/** Union/subtract/intersect between two independently-built bodies (§MB-1). */
export type BooleanParams = components["schemas"]["BooleanParamsV1"];
export type BooleanOperation = BooleanParams["operation"];
export type SheetMetalBaseFlangeFeature =
  components["schemas"]["SheetMetalBaseFlangeFeature"];
export type SheetMetalBaseFlangeParams =
  components["schemas"]["SheetMetalBaseFlangeParamsV1"];
export type SheetMetalEdgeFlangeFeature =
  components["schemas"]["SheetMetalEdgeFlangeFeature"];
export type SheetMetalEdgeFlangeParams =
  components["schemas"]["SheetMetalEdgeFlangeParamsV1"];
export type SheetMetalHemFeature =
  components["schemas"]["SheetMetalHemFeature"];
export type SheetMetalHemParams =
  components["schemas"]["SheetMetalHemParamsV1"];
export type SheetMetalCornerReliefFeature =
  components["schemas"]["SheetMetalCornerReliefFeature"];
export type SheetMetalCornerReliefParams =
  components["schemas"]["SheetMetalCornerReliefParamsV1"];
export type MirrorFeature = components["schemas"]["MirrorFeature"];
/** Reflect the current body about a plane and union the reflection in (§7.6). */
export type MirrorParams = components["schemas"]["MirrorParamsV1"];
/**
 * The mirror `plane` slot on the wire: an origin `DatumPlaneRef` (XY/XZ/YZ) or a
 * `FeatureRef` to an earlier datum feature — the SAME `GeomRef` union a sketch's
 * plane uses (CLAUDE.md DRY rule), so the mirror reuses the plane vocabulary.
 */
export type MirrorPlaneRef = MirrorParams["plane"];
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

/**
 * The write raced another edit: the sent `expected_tree_version` no longer
 * matches the document (422 `stale_tree_version`). Typed so undo/redo can
 * resync quietly (the design doc's "soft reload", docs/design/undo-redo.md)
 * instead of surfacing a scary error — a narrowing the OpenAPI schema can't
 * express, mirroring `PartNameTakenError`.
 */
export class StaleTreeVersionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StaleTreeVersionError";
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
    // length_unit is DISPLAY metadata (docs/design/units.md §U1); new parts
    // default to canonical mm. The document-unit selector (U2) changes it via
    // the update route.
    body: { name, length_unit: "mm" },
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
  plane: SketchPlaneRef,
  entities: readonly SketchEntity[],
  constraints: readonly SketchConstraint[],
): SketchFeature {
  return {
    type: "sketch",
    version: 1,
    params: {
      plane,
      entities: [...entities],
      constraints: [...constraints],
    },
  };
}

/**
 * The save payload for a locally buffered sketch (entities + constraints).
 * `plane` is the resolved `GeomRef` — an origin `DatumPlaneRef` (the one-click
 * common case) OR a `FeatureRef` to an authored offset `datum` feature (#2b).
 * Pure — unit-tested against the generated types.
 */
export function sketchFeatureCreate(
  name: string,
  plane: SketchPlaneRef,
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
  plane: SketchPlaneRef,
  entities: readonly SketchEntity[],
  constraints: readonly SketchConstraint[],
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: sketchFeatureEnvelope(plane, entities, constraints),
  };
}

/** The `{type, version, params}` envelope shared by datum create and update. */
function datumFeatureEnvelope(params: DatumFeature["params"]): DatumFeature {
  return { type: "datum", version: 1, params };
}

/**
 * The create payload for an ON-FACE datum feature: a construction plane adopted
 * from a picked planar model face (`kind: "on_face"`), named by a stage-1
 * `SubshapeRef` signature (docs/design/datum-planes.md §7). Like an offset
 * datum it seats a later sketch via a `FeatureRef` plane slot; unlike it, it can
 * fail per-feature if the referenced face no longer resolves. Pure — unit-tested
 * against the generated types.
 */
export function datumOnFaceFeatureCreate(
  name: string,
  params: DatumOnFaceParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: datumFeatureEnvelope(params),
  };
}

/**
 * The create payload for a datum feature: a construction plane parallel to an
 * origin datum, offset a signed distance along its normal (docs/design/
 * datum-planes.md §3). Non-body-affecting — it produces a plane a later sketch
 * sits on via a `FeatureRef`. Pure — unit-tested against the generated types.
 */
export function datumFeatureCreate(
  name: string,
  params: DatumParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: datumFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing datum plane (no rename). */
export function datumFeatureUpdate(
  params: DatumParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: datumFeatureEnvelope(params),
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

/** The `{type, version, params}` envelope shared by sweep create and update. */
function sweepFeatureEnvelope(params: SweepParams): SweepFeature {
  return { type: "sweep", version: 1, params };
}

/**
 * The create payload for a sweep feature: sweep an EARLIER sketch's closed
 * profile along a SECOND earlier sketch's open path (design §4.3, the
 * revolve sibling — but with a second `FeatureRef`). Pure — unit-tested
 * against the generated types, matching `revolveFeatureCreate`.
 */
export function sweepFeatureCreate(
  name: string,
  params: SweepParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: sweepFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing sweep (no rename). */
export function sweepFeatureUpdate(
  params: SweepParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: sweepFeatureEnvelope(params),
  };
}

/** The `{type, version, params}` envelope shared by loft create and update. */
function loftFeatureEnvelope(params: LoftParams): LoftFeature {
  return { type: "loft", version: 1, params };
}

/**
 * The create payload for a loft feature: skin a solid THROUGH an ordered list
 * of earlier sketch sections (≥2), blended in list order (design §4.3, the
 * sweep sibling — but with an ordered LIST of `FeatureRef`s rather than a
 * profile + a path). Pure — unit-tested against the generated types.
 */
export function loftFeatureCreate(
  name: string,
  params: LoftParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: loftFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing loft (no rename). */
export function loftFeatureUpdate(
  params: LoftParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: loftFeatureEnvelope(params),
  };
}

/** The `{type, version, params}` envelope for a boolean feature. */
function booleanFeatureEnvelope(params: BooleanParams): BooleanFeature {
  return { type: "boolean", version: 1, params };
}

/**
 * The create payload for a boolean feature: fuse (union — the only op wired in
 * MB-1) two independently-built bodies named by their base features (design
 * §Decisions-3). Unlike extrude/revolve it consumes no sketch — it combines two
 * existing bodies. The result takes over the TARGET's identity and the TOOL body
 * is removed. Pure — unit-tested against the generated types.
 */
export function booleanFeatureCreate(
  name: string,
  params: BooleanParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: booleanFeatureEnvelope(params),
  };
}

/** The `{type, version, params}` envelope shared by fillet create and update. */
function filletFeatureEnvelope(params: FilletParams): FilletFeature {
  return { type: "fillet", version: 1, params };
}

/**
 * The create payload for a fillet feature: round selected edges of the current
 * body chain with a constant radius (design §7.6, the extrude-cut sibling — no
 * `FeatureRef`, it acts on the implicit body chain at its point in the tree).
 * Pure — unit-tested against the generated types.
 */
export function filletFeatureCreate(
  name: string,
  params: FilletParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: filletFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing fillet (no rename). */
export function filletFeatureUpdate(
  params: FilletParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: filletFeatureEnvelope(params),
  };
}

/** The `{type, version, params}` envelope shared by chamfer create and update. */
function chamferFeatureEnvelope(params: ChamferParams): ChamferFeature {
  return { type: "chamfer", version: 1, params };
}

/**
 * The create payload for a chamfer feature: bevel selected edges of the current
 * body chain with a symmetric distance (the fillet twin — same `EdgeSelector`
 * plumbing, same implicit-body-chain dependency). Pure.
 */
export function chamferFeatureCreate(
  name: string,
  params: ChamferParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: chamferFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing chamfer (no rename). */
export function chamferFeatureUpdate(
  params: ChamferParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: chamferFeatureEnvelope(params),
  };
}

/** The `{type, version, params}` envelope shared by shell create and update. */
function shellFeatureEnvelope(params: ShellParams): ShellFeature {
  return { type: "shell", version: 1, params };
}

/**
 * The create payload for a shell feature: hollow the current body chain to a
 * uniform inward wall, leaving the picked faces open (design §7.6, the
 * fillet/chamfer sibling — no `FeatureRef`, it acts on the implicit body chain
 * at its point in the tree; the picked openings ARE named face refs). An empty
 * `faces` list is a valid sealed hollow. Pure — unit-tested against the types.
 */
export function shellFeatureCreate(
  name: string,
  params: ShellParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: shellFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing shell (no rename). */
export function shellFeatureUpdate(
  params: ShellParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: shellFeatureEnvelope(params),
  };
}

/** The `{type, version, params}` envelope shared by hole create and update. */
function holeFeatureEnvelope(params: HoleParams): HoleFeature {
  return { type: "hole", version: 1, params };
}

/**
 * The create payload for a hole feature: drill a cylinder of `diameter_mm` into
 * the current body at a point on a picked planar face, through-all or blind
 * (design §7.6, the shell/draft sibling — no whole-feature `FeatureRef`, it acts
 * on the implicit body chain at its point in the tree; the placement face IS a
 * named stage-1 `SubshapeRef`, the SAME the on_face datum / shell openings use).
 * Pure — unit-tested against the generated types.
 */
export function holeFeatureCreate(
  name: string,
  params: HoleParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: holeFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing hole (no rename). */
export function holeFeatureUpdate(
  params: HoleParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: holeFeatureEnvelope(params),
  };
}

/** The `{type, version, params}` envelope shared by draft create and update. */
function draftFeatureEnvelope(params: DraftParams): DraftFeature {
  return { type: "draft", version: 1, params };
}

/**
 * The create payload for a draft feature: taper the picked faces of the current
 * body chain by a constant angle about a neutral (parting) plane — the mold-
 * release primitive (design §4.3, the shell/fillet sibling: no `FeatureRef`, it
 * acts on the implicit body chain at its point in the tree; the tapered faces
 * ARE named face refs). Unlike shell, an empty face set is a `no_draft_faces`
 * rebuild error, so the editor guards it. Pure — unit-tested against the types.
 */
export function draftFeatureCreate(
  name: string,
  params: DraftParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: draftFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing draft (no rename). */
export function draftFeatureUpdate(
  params: DraftParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: draftFeatureEnvelope(params),
  };
}

/** The `{type, version, params}` envelope shared by base-flange create/update. */
function baseFlangeFeatureEnvelope(
  params: SheetMetalBaseFlangeParams,
): SheetMetalBaseFlangeFeature {
  return { type: "sheet_metal_base_flange", version: 1, params };
}

/**
 * The create payload for a base-flange feature: the sheet-metal part's first
 * body — an EARLIER sketch profile thickened to gauge (sheet-metal.md §4.1, the
 * extrude sibling, but carrying the part's gauge / K / default bend radius).
 * Pure — unit-tested against the generated types.
 */
export function baseFlangeFeatureCreate(
  name: string,
  params: SheetMetalBaseFlangeParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: baseFlangeFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing base flange (no rename). */
export function baseFlangeFeatureUpdate(
  params: SheetMetalBaseFlangeParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: baseFlangeFeatureEnvelope(params),
  };
}

/** The `{type, version, params}` envelope shared by edge-flange create/update. */
function edgeFlangeFeatureEnvelope(
  params: SheetMetalEdgeFlangeParams,
): SheetMetalEdgeFlangeFeature {
  return { type: "sheet_metal_edge_flange", version: 1, params };
}

/**
 * The create payload for an edge-flange feature: a leg folded off a straight
 * edge of the sheet body (sheet-metal.md §4.2, the fillet sibling — a named
 * `EdgeSubshapeRef` against the current sheet body, inheriting the part's gauge
 * defaults). Pure — unit-tested against the generated types.
 */
export function edgeFlangeFeatureCreate(
  name: string,
  params: SheetMetalEdgeFlangeParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: edgeFlangeFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing edge flange (no rename). */
export function edgeFlangeFeatureUpdate(
  params: SheetMetalEdgeFlangeParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: edgeFlangeFeatureEnvelope(params),
  };
}

/** The `{type, version, params}` envelope shared by hem create/update. */
function hemFeatureEnvelope(params: SheetMetalHemParams): SheetMetalHemFeature {
  return { type: "sheet_metal_hem", version: 1, params };
}

/**
 * The create payload for a closed-hem feature: the picked straight edge of the
 * sheet folded ~180° back flat onto the parent face (sheet-metal parity §2 —
 * mechanically an edge flange with the fold angle FIXED at 180°, a named
 * `EdgeSubshapeRef` against the current sheet body, inheriting the part's gauge
 * defaults). Pure — unit-tested against the generated types.
 */
export function hemFeatureCreate(
  name: string,
  params: SheetMetalHemParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: hemFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing hem (no rename). */
export function hemFeatureUpdate(
  params: SheetMetalHemParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: hemFeatureEnvelope(params),
  };
}

/** The `{type, version, params}` envelope shared by corner-relief create/update. */
function cornerReliefFeatureEnvelope(
  params: SheetMetalCornerReliefParams,
): SheetMetalCornerReliefFeature {
  return { type: "sheet_metal_corner_relief", version: 1, params };
}

/**
 * The create payload for a corner-relief feature: a rectangular notch cut at the
 * shared corner of TWO adjacent edge flanges so the corner develops into a
 * single non-overlapping flat blank (sheet-metal parity §4.4). Unlike an edge
 * pick it names the two bends by `FeatureRef` (the earlier edge-flange features
 * that created them). Pure — unit-tested against the generated types.
 */
export function cornerReliefFeatureCreate(
  name: string,
  params: SheetMetalCornerReliefParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: cornerReliefFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing corner relief (no rename). */
export function cornerReliefFeatureUpdate(
  params: SheetMetalCornerReliefParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: cornerReliefFeatureEnvelope(params),
  };
}

/** The `{type, version, params}` envelope shared by mirror create and update. */
function mirrorFeatureEnvelope(params: MirrorParams): MirrorFeature {
  return { type: "mirror", version: 1, params };
}

/**
 * The create payload for a mirror feature: reflect the current body chain about
 * `plane` and boolean-union the reflection back in — the reflective sibling of
 * pattern (design §7.6, acting on the implicit body chain at its point in the
 * tree, no whole-feature `FeatureRef`). `plane` is the SAME `GeomRef` a sketch's
 * plane uses. Pure — unit-tested against the generated types.
 */
export function mirrorFeatureCreate(
  name: string,
  params: MirrorParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: mirrorFeatureEnvelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing mirror (no rename). */
export function mirrorFeatureUpdate(
  params: MirrorParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: mirrorFeatureEnvelope(params),
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

/**
 * Undo one feature-tree history step (docs/design/undo-redo.md): restore the
 * previous snapshot, ids verbatim. Undo IS a document edit — it takes the
 * client's `expected_tree_version` and returns the restored tree + the new
 * token; at the ring's floor it's a clean 200 no-op echoing the current tree
 * (version unchanged). A stale version throws the typed
 * `StaleTreeVersionError` so the caller can soft-reload instead of erroring.
 */
export async function undoPart(
  partId: string,
  expectedTreeVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<FeatureTreeResponse> {
  const { data, error } = await client.POST("/api/v1/parts/{part_id}/undo", {
    params: { path: { part_id: partId } },
    body: { expected_tree_version: expectedTreeVersion },
  });
  if (error !== undefined) {
    throw historyStepError(error, "The last edit could not be undone.");
  }
  return data;
}

/** Redo one feature-tree history step — `undoPart`'s mirror, same contract. */
export async function redoPart(
  partId: string,
  expectedTreeVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<FeatureTreeResponse> {
  const { data, error } = await client.POST("/api/v1/parts/{part_id}/redo", {
    params: { path: { part_id: partId } },
    body: { expected_tree_version: expectedTreeVersion },
  });
  if (error !== undefined) {
    throw historyStepError(error, "The edit could not be redone.");
  }
  return data;
}

/** Shared undo/redo failure mapping: stale → typed, everything else verbatim. */
function historyStepError(error: unknown, fallback: string): Error {
  const message = envelopeMessage(error, fallback);
  return envelopeCode(error) === "stale_tree_version"
    ? new StaleTreeVersionError(message)
    : new Error(message);
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

/**
 * Change the part's document display unit (docs/design/units.md §U2). DISPLAY
 * metadata only — the server never touches a stored mm value, so this is a pure
 * re-label; it bumps `tree_version` under the OCC guard like any part edit. The
 * route + types are generated (`@loft/ts-client`); the server envelope surfaces
 * verbatim on a stale version (422) or unknown part (404).
 */
export async function updatePartUnit(
  partId: string,
  lengthUnit: LengthUnit,
  expectedTreeVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<PartResponse> {
  const { data, error } = await client.PATCH("/api/v1/parts/{part_id}", {
    params: { path: { part_id: partId } },
    body: {
      length_unit: lengthUnit,
      expected_tree_version: expectedTreeVersion,
    },
  });
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The document unit could not be changed."),
    );
  }
  return data;
}

/**
 * Import a STEP file as the part's BASE body: the raw file bytes ARE the
 * request body (`application/octet-stream`, §2b), with the current tree version
 * as the optimistic-concurrency guard and the file's base name as the feature
 * name. The route + response type are generated (`@loft/ts-client`, CLAUDE.md
 * DRY rule); this only streams the bytes and surfaces the server envelope on
 * rejection (`import_too_large` / `import_empty` / `import_not_step` /
 * `import_with_prior_body`), never swallowing it.
 */
export async function importStep(
  partId: string,
  bytes: ArrayBuffer,
  name: string,
  expectedTreeVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<FeatureMutationResponse> {
  const { data, error } = await client.POST(
    "/api/v1/parts/{part_id}/features/import",
    {
      params: {
        path: { part_id: partId },
        query: { expected_tree_version: expectedTreeVersion, name },
      },
      // The generated schema types the octet-stream body as `string`; the raw
      // bytes pass straight through via a byte-identity serializer, and the
      // content-type is set explicitly so the default JSON header isn't sent.
      body: bytes as unknown as string,
      bodySerializer: (raw: unknown) => raw as BodyInit,
      headers: { "Content-Type": "application/octet-stream" },
    },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The STEP file could not be imported."),
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
