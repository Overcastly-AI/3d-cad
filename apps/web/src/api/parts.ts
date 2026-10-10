/**
 * Parts + feature-tree data layer — all types come from the generated
 * `@loft/ts-client` (pydantic → OpenAPI → TS; CLAUDE.md DRY rule). Errors
 * surface the server envelope's own message.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeCode, envelopeMessage } from "./envelope";

import type {
  BooleanFeature,
  BooleanParams,
  ChamferFeature,
  ChamferParams,
  DatumFeature,
  DatumOnFaceParams,
  DatumParams,
  DraftFeature,
  DraftParams,
  EvaluateTreeResult,
  ExtrudeFeature,
  ExtrudeParams,
  FeatureCreate,
  FeatureMutationResponse,
  FeatureTreeResponse,
  FeatureUpdate,
  FilletFeature,
  FilletParams,
  HoleFeature,
  HoleParams,
  LengthUnit,
  LoftFeature,
  LoftParams,
  MirrorFeature,
  MirrorParams,
  PartResponse,
  PatternFeature,
  PatternParams,
  RevolveFeature,
  RevolveParams,
  SheetMetalBaseFlangeFeature,
  SheetMetalBaseFlangeParams,
  SheetMetalCornerReliefFeature,
  SheetMetalCornerReliefParams,
  SheetMetalEdgeFlangeFeature,
  SheetMetalEdgeFlangeParams,
  SheetMetalHemFeature,
  SheetMetalHemParams,
  ShellFeature,
  ShellParams,
  SketchConstraint,
  SketchEntity,
  SketchFeature,
  SketchPlaneRef,
  SweepFeature,
  SweepParams,
} from "./partTypes";

export type * from "./partTypes";

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

/**
 * One document that still references the one a delete was refused over — the
 * generated contract type (`DocumentDependent`), never a hand-written shape.
 * The gateway DOCUMENTS this payload as the 409 body of the document deletes
 * precisely so the register can name the referents instead of guessing.
 */
export type DocumentDependent = components["schemas"]["DocumentDependent"];

/**
 * A delete was refused because other documents reference this one (409
 * `*_has_dependents`) — the cross-document sibling of the feature-tree's own
 * dependency 409.
 *
 * The `dependents` list is the reason this is a typed error rather than a
 * string: a refusal a user can act on has to say WHICH assembly or drawing is
 * holding the reference, and "referenced by 2 document(s)" is a message that
 * ends the conversation. Carried through so the register renders the list the
 * SERVER sent — a register that summarised it, or guessed at it, would be the
 * over-claiming defect this screen exists to avoid.
 */
export class DocumentHasDependentsError extends Error {
  constructor(
    readonly dependents: DocumentDependent[],
    message: string,
  ) {
    super(message);
    this.name = "DocumentHasDependentsError";
  }
}

/** Runtime narrowing of a 409 envelope's `details.dependents`, or null.
 *
 * The SHAPE comes from the generated contract (`DocumentDependent`); this only
 * checks that an `unknown` response body really is that shape before trusting
 * it, exactly as `parseErrorEnvelope` does for the envelope itself. It returns
 * null rather than a partial list if anything is off: half a dependency list is
 * worse than none, because the user would fix the entries they were shown and
 * hit the same refusal again.
 */
export function parseDependents(body: unknown): DocumentDependent[] | null {
  if (typeof body !== "object" || body === null) return null;
  const error = (body as Record<string, unknown>).error;
  if (typeof error !== "object" || error === null) return null;
  const details = (error as Record<string, unknown>).details;
  if (typeof details !== "object" || details === null) return null;
  const raw = (details as Record<string, unknown>).dependents;
  if (!Array.isArray(raw)) return null;
  const dependents: DocumentDependent[] = [];
  for (const entry of raw) {
    if (typeof entry !== "object" || entry === null) return null;
    const { id, name, kind } = entry as Record<string, unknown>;
    if (typeof id !== "string" || typeof name !== "string") return null;
    if (kind !== "assembly" && kind !== "drawing") return null;
    dependents.push({ id, name, kind });
  }
  return dependents.length > 0 ? dependents : null;
}

/**
 * Raise the typed dependency error when a delete's 409 carried a referent list.
 * Shared by all three registers' deletes (DRY) — one place decides that a
 * refusal with names is a different animal from a refusal without.
 */
function throwIfDependents(error: unknown, fallback: string): void {
  const dependents = parseDependents(error);
  if (dependents !== null) {
    throw new DocumentHasDependentsError(
      dependents,
      envelopeMessage(error, fallback),
    );
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
  lengthUnit: LengthUnit = "mm",
  /**
   * File it into this folder on creation (#WS2), or null for unfiled. ONE call
   * on purpose: a create-then-move pair could fail between the two and leave a
   * document somewhere the user did not put it.
   */
  folderId: string | null = null,
  client: GatewayClient = gatewayClient,
): Promise<PartResponse> {
  const { data, error } = await client.POST("/api/v1/parts", {
    // length_unit is DISPLAY metadata (docs/design/units.md §U1) stamped at
    // creation. The default is canonical mm; the caller passes the user's
    // "units for new documents" preference (#58) when there is one, and the
    // document-unit selector (U2) changes it afterwards via the update route.
    body: { name, length_unit: lengthUnit, folder_id: folderId },
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

/**
 * Rename one of the caller's parts under the optimistic-concurrency guard.
 *
 * A rename is a real document write, not a label change: it goes through the
 * same `expected_tree_version` check as every other part edit, so a name typed
 * against a stale row is refused (422) rather than silently overwriting an edit
 * made elsewhere. It cannot orphan anything — assembly instances and drawing
 * views reference a part by ID, never by name — so there is no dependency check
 * here, and the referring documents pick up the new name on their next read.
 */
export async function renamePart(
  partId: string,
  name: string,
  expectedTreeVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<PartResponse> {
  const { data, error } = await client.PATCH("/api/v1/parts/{part_id}", {
    params: { path: { part_id: partId } },
    body: { name, expected_tree_version: expectedTreeVersion },
  });
  if (error !== undefined) {
    if (envelopeCode(error) === "part_name_taken") {
      throw new PartNameTakenError(
        name,
        envelopeMessage(error, `A part named "${name}" already exists.`),
      );
    }
    if (envelopeCode(error) === "stale_tree_version") {
      throw new StaleTreeVersionError(
        envelopeMessage(
          error,
          "This part changed somewhere else. Reopen the register and try again.",
        ),
      );
    }
    throw new Error(envelopeMessage(error, "The part could not be renamed."));
  }
  return data;
}

/**
 * Copy a part and its whole feature tree at its current version (201).
 *
 * Sends no body: the copy's name is the SERVER'S ("Bracket copy", then
 * "Bracket copy 2"), and the created part comes back, so the register shows the
 * name that was actually taken. A client that predicted the name would be
 * wrong the moment two copies raced, which is the class of over-claim this
 * screen is being held to.
 */
export async function duplicatePart(
  partId: string,
  client: GatewayClient = gatewayClient,
): Promise<PartResponse> {
  const { data, error } = await client.POST(
    "/api/v1/parts/{part_id}/duplicate",
    {
      params: { path: { part_id: partId } },
    },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The part could not be duplicated."),
    );
  }
  return data;
}

/**
 * Delete one of the caller's parts (204; 404 for unknown/foreign ids).
 *
 * A part still instanced by an assembly or projected by a drawing is refused
 * with a 409 that NAMES those documents — thrown as `DocumentHasDependentsError`
 * so the register can list them. Never a silent orphan.
 */
export async function deletePart(
  partId: string,
  client: GatewayClient = gatewayClient,
): Promise<void> {
  const { error } = await client.DELETE("/api/v1/parts/{part_id}", {
    params: { path: { part_id: partId } },
  });
  if (error !== undefined) {
    throwIfDependents(error, "The part could not be deleted.");
    throw new Error(envelopeMessage(error, "The part could not be deleted."));
  }
}

/**
 * File a part into a folder, or un-file it with `folderId: null` (#WS2).
 *
 * The RESPONSE is the part as stored, and callers render that rather than
 * assuming the click landed: a move that reported success while the document
 * was still in the old place is the defect this whole row is being held to.
 *
 * No `expected_tree_version`: filing is not a document edit (it moves neither
 * the version nor `updated_at`), so it cannot collide with a modeling write and
 * has nothing to guard against. A folder that already holds a part of this name
 * refuses with 409 `part_name_taken` — names are unique per folder.
 */
export async function movePart(
  partId: string,
  folderId: string | null,
  client: GatewayClient = gatewayClient,
): Promise<PartResponse> {
  const { data, error } = await client.POST("/api/v1/parts/{part_id}/move", {
    params: { path: { part_id: partId } },
    body: { folder_id: folderId },
  });
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The part could not be moved."));
  }
  return data;
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
  /**
   * Evaluate only the features strictly BEFORE this one: the body it is
   * built on, for an Edit preview (FILLET-EDIT-REPICK). Read-only: the stored
   * stop and `tree_version` do not move, and the stored stop is ignored.
   */
  before?: string,
): Promise<EvaluateTreeResult> {
  const { data, error } = await client.POST(
    "/api/v1/parts/{part_id}/evaluate",
    {
      params: {
        path: { part_id: partId },
        ...(before === undefined ? {} : { query: { before } }),
      },
    },
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
 * profile along a SECOND earlier sketch's path, open or closed (design §4.3, the
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
 * The tree order was refused because the permutation would put a feature BEFORE
 * something it is built on (422 `reference_not_earlier`). Typed, and carrying
 * BOTH ids the server named, for the same reason `FeatureHasDependentsError` is
 * typed: a refusal a user can act on has to say which pair is wrong. Reducing
 * it to a string would leave the tree unable to offer the repair.
 */
export class FeatureOrderRefusedError extends Error {
  constructor(
    readonly featureId: string,
    readonly referencesFeatureId: string,
    message: string,
  ) {
    super(message);
    this.name = "FeatureOrderRefusedError";
  }
}

/** Runtime narrowing of the reorder 422's `details` pair, or null. */
export function parseOrderRefusal(
  body: unknown,
): { featureId: string; referencesFeatureId: string } | null {
  if (typeof body !== "object" || body === null) return null;
  const error = (body as Record<string, unknown>).error;
  if (typeof error !== "object" || error === null) return null;
  const details = (error as Record<string, unknown>).details;
  if (typeof details !== "object" || details === null) return null;
  const { feature_id: featureId, references_feature_id: referencesFeatureId } =
    details as Record<string, unknown>;
  if (
    typeof featureId !== "string" ||
    typeof referencesFeatureId !== "string"
  ) {
    return null;
  }
  return { featureId, referencesFeatureId };
}

/**
 * Reorder the whole feature tree (docs/design/feature-tree.md §2.2) — the
 * payload is the COMPLETE permutation of the part's feature ids in the desired
 * evaluation order, so the server can re-check every backward-only reference
 * under the new order before renumbering. A history-recording, undoable tree
 * edit under the same optimistic-concurrency guard as every write.
 *
 * Two refusals are typed rather than flattened to a message, because the tree
 * acts on both: `stale_tree_version` (soft-resync and retry, as every other
 * write does) and `reference_not_earlier` (name the pair and offer the legal
 * seat). `order_not_permutation` is a client bug, not a user-facing state, so
 * it surfaces as the server's own message.
 */
export async function reorderFeatures(
  partId: string,
  order: readonly string[],
  expectedTreeVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<FeatureTreeResponse> {
  const { data, error } = await client.PUT(
    "/api/v1/parts/{part_id}/features/order",
    {
      params: { path: { part_id: partId } },
      body: { order: [...order], expected_tree_version: expectedTreeVersion },
    },
  );
  if (error !== undefined) {
    const message = envelopeMessage(
      error,
      "The feature order could not be changed.",
    );
    if (envelopeCode(error) === "stale_tree_version") {
      throw new StaleTreeVersionError(message);
    }
    const refusal = parseOrderRefusal(error);
    if (envelopeCode(error) === "reference_not_earlier" && refusal !== null) {
      throw new FeatureOrderRefusedError(
        refusal.featureId,
        refusal.referencesFeatureId,
        message,
      );
    }
    throw new Error(message);
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
 * Flip ONLY a feature's suppress flag (feature-tree.md §4.3a). A dedicated,
 * minimal mutation — distinct from `updateFeature` — so suppressing never
 * touches `params`: it sets the envelope-level `suppressed` flag and bumps
 * `tree_version` under the SAME optimistic-concurrency guard as every write. A
 * suppressed feature is SKIPPED at rebuild (the body is built from the
 * non-suppressed prefix), so this changes what evaluating the part means and is
 * an undoable, history-recording tree edit. The route + types are generated
 * (`@loft/ts-client`, CLAUDE.md DRY rule). A stale `expected_tree_version`
 * throws the typed `StaleTreeVersionError` so the caller can soft-resync and
 * retry quietly; every other failure surfaces the server envelope's message.
 */
export async function suppressFeature(
  partId: string,
  featureId: string,
  suppressed: boolean,
  expectedTreeVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<FeatureMutationResponse> {
  const { data, error } = await client.PATCH(
    "/api/v1/parts/{part_id}/features/{feature_id}/suppress",
    {
      params: { path: { part_id: partId, feature_id: featureId } },
      body: { expected_tree_version: expectedTreeVersion, suppressed },
    },
  );
  if (error !== undefined) {
    const message = envelopeMessage(
      error,
      "The feature could not be suppressed — reload and try again.",
    );
    throw envelopeCode(error) === "stale_tree_version"
      ? new StaleTreeVersionError(message)
      : new Error(message);
  }
  return data;
}

/**
 * One thing that breaks if a feature is deleted — a later FEATURE of this part,
 * or a DRAWING whose section view cuts on it. The generated contract type; the
 * union is closed server-side (an assembly instances a whole part, never a
 * feature), so a consumer may switch on `kind` exhaustively.
 */
export type FeatureDependent = components["schemas"]["FeatureDependent"];

/**
 * What breaks if this feature is deleted — asked BEFORE the delete is offered
 * (UI-REVIEW 2026-07-30 F3).
 *
 * A read, answered by the SAME documents-side query that builds the delete's
 * 409, which is the property that matters: a confirmation saying "nothing
 * depends on this" and a refusal naming two features cannot both be right, and
 * one query makes that impossible rather than unlikely.
 *
 * An empty list is the honest common answer, not a guarantee: another client
 * could add a reference a moment later, and the delete re-checks under the row
 * lock. The UI therefore still handles the 409.
 */
export async function fetchFeatureDependents(
  partId: string,
  featureId: string,
  client: GatewayClient = gatewayClient,
): Promise<FeatureDependent[]> {
  const { data, error } = await client.GET(
    "/api/v1/parts/{part_id}/features/{feature_id}/dependents",
    { params: { path: { part_id: partId, feature_id: featureId } } },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "What depends on this feature could not be read."),
    );
  }
  return data.dependents;
}

/**
 * A feature delete was refused because other features or drawings reference it
 * (409 `feature_has_dependents`) — the feature-level sibling of
 * `DocumentHasDependentsError`, and typed for the same reason: the refusal has
 * to NAME what breaks.
 */
export class FeatureHasDependentsError extends Error {
  constructor(
    readonly dependents: FeatureDependent[],
    message: string,
  ) {
    super(message);
    this.name = "FeatureHasDependentsError";
  }
}

/** Runtime narrowing of a feature 409's `details.dependents`, or null. */
export function parseFeatureDependents(
  body: unknown,
): FeatureDependent[] | null {
  if (typeof body !== "object" || body === null) return null;
  const error = (body as Record<string, unknown>).error;
  if (typeof error !== "object" || error === null) return null;
  const details = (error as Record<string, unknown>).details;
  if (typeof details !== "object" || details === null) return null;
  const raw = (details as Record<string, unknown>).dependents;
  if (!Array.isArray(raw)) return null;
  const dependents: FeatureDependent[] = [];
  for (const entry of raw) {
    if (typeof entry !== "object" || entry === null) return null;
    const { id, name, kind } = entry as Record<string, unknown>;
    if (typeof id !== "string" || typeof name !== "string") return null;
    if (kind !== "feature" && kind !== "drawing") return null;
    dependents.push({ id, name, kind });
  }
  return dependents.length > 0 ? dependents : null;
}

/**
 * Delete a feature from the tree (200; 422 on stale version). A history-
 * recording, undoable tree edit under the SAME optimistic-concurrency guard as
 * every write; downstream features rebuild off the shortened tree. The route +
 * types are generated (`@loft/ts-client`, CLAUDE.md DRY rule). A stale
 * `expected_tree_version` throws the typed `StaleTreeVersionError` so the caller
 * can soft-resync and retry; every other failure surfaces the server envelope.
 */
export async function deleteFeature(
  partId: string,
  featureId: string,
  expectedTreeVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<FeatureTreeResponse> {
  const { data, error } = await client.DELETE(
    "/api/v1/parts/{part_id}/features/{feature_id}",
    {
      params: {
        path: { part_id: partId, feature_id: featureId },
        query: { expected_tree_version: expectedTreeVersion },
      },
    },
  );
  if (error !== undefined) {
    const message = envelopeMessage(
      error,
      "The feature could not be deleted — reload and try again.",
    );
    if (envelopeCode(error) === "stale_tree_version") {
      throw new StaleTreeVersionError(message);
    }
    // The refusal NAMES what breaks (F3). Thrown typed so the tree renders the
    // list the server sent rather than the message's prose.
    const dependents = parseFeatureDependents(error);
    if (dependents !== null) {
      throw new FeatureHasDependentsError(dependents, message);
    }
    throw new Error(message);
  }
  return data;
}

/**
 * Rename a feature (200; 422 on stale version). A minimal PATCH that sends ONLY
 * the new `name` — the feature `params` are untouched (the update envelope's
 * `feature` is optional), so a rename never re-solves geometry. Same OCC guard
 * and typed stale-version error as every tree edit.
 */
export async function renameFeature(
  partId: string,
  featureId: string,
  name: string,
  expectedTreeVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<FeatureMutationResponse> {
  const { data, error } = await client.PATCH(
    "/api/v1/parts/{part_id}/features/{feature_id}",
    {
      params: { path: { part_id: partId, feature_id: featureId } },
      body: { expected_tree_version: expectedTreeVersion, name },
    },
  );
  if (error !== undefined) {
    const message = envelopeMessage(
      error,
      "The feature could not be renamed — reload and try again.",
    );
    throw envelopeCode(error) === "stale_tree_version"
      ? new StaleTreeVersionError(message)
      : new Error(message);
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
