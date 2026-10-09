/**
 * Parts + feature-tree wire types: aliases of the generated `@loft/ts-client`
 * schemas (pydantic -> OpenAPI -> TS). Split out of `parts.ts` for the
 * file-size ratchet; `parts.ts` re-exports every name, so imports are unchanged.
 */
import type { components } from "@loft/ts-client/gateway";

export type PartResponse = components["schemas"]["PartResponse"];
/** Document display unit — the single source is the generated contract. */
export type LengthUnit = PartResponse["length_unit"];
/**
 * The part's REBUILD HEALTH as a verdict the UI may act on now: `never` | `ok` |
 * `failed` | `stale`. Derived SERVER-SIDE by one shared fold over the stored
 * record and the part's current `tree_version` (`derive_part_eval_state`,
 * loft_wire) precisely so nobody re-derives it here — a client that compared
 * timestamps would reinvent the skew bug the version comparison exists to
 * avoid. Read this field; never recompute it.
 */
export type PartEvalState = PartResponse["eval_state"];
/**
 * HOW MUCH of the tree the live verdict covers — a SECOND, ORTHOGONAL axis
 * beside `eval_state`, not a fifth state (audit J3): `whole` (the entire tree
 * ran) or `rolled_back` (the travel stop held features out, so the verdict
 * describes a PREFIX). The two combine, and the asymmetry is the point — a
 * `failed` prefix still means broken, an `ok` prefix is NOT a claim that the
 * part builds.
 *
 * `null`/absent means the question does not arise (`never`/`stale` have no
 * live verdict to qualify) or the record predates scope tracking. **Null must
 * never be read as `whole`** — that is precisely the over-claim the field
 * exists to prevent.
 */
export type PartEvalScope = PartResponse["eval_scope"];
/**
 * The RAW recorded outcome of the last evaluate. Useful only alongside
 * `eval_state`: on its own it cannot say whether it still applies to the tree
 * as it stands, which is the whole reason `eval_state` exists.
 */
export type PartLastEvalStatus = PartResponse["last_eval_status"];
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
/** A plane through a line at an angle from a reference (DATUM-PLANE-ANGLE). */
export type DatumAngleParams = components["schemas"]["DatumAngleParams"];
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
/**
 * The optional COSMETIC thread callout that makes a hole TAPPED — a sibling of
 * `type`, not a member of it (threading is orthogonal to the recess, so a
 * counterbored tapped hole sets both). Carries no geometry: `diameter_mm` is
 * the tap-drill bore.
 */
export type IsoMetricThread = components["schemas"]["IsoMetricThread"];
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
