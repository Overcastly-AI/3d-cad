/**
 * Extrude-feature view logic — pure functions the ExtrudeEditor and the
 * PartPage share, kept out of the component so they can be unit-tested without
 * a DOM. Param shapes come from the generated client (CLAUDE.md DRY rule); the
 * builders live in `../api/parts` alongside the sketch builders.
 */
import type { LengthUnit } from "@loft/design";

import type {
  DatumParams,
  ExtrudeParams,
  FeatureResponse,
  SketchEntity,
} from "../api/parts";
import { lengthInputValue, parsePositiveLengthMm } from "../units/length";
import { fieldBlocker } from "./submitBlocker";

export type ExtrudeOperation = ExtrudeParams["operation"];
export type ExtrudeDirection = ExtrudeParams["direction"];

/**
 * Where a sketch's plane came from — the fact that decides which way is "into
 * the material" (FB-4).
 *
 * `"face"`: the sketch is seated on a picked planar model face, through an
 * `on_face` datum. The kernel builds that plane's `z_dir` FROM the face's
 * OUTWARD normal (`services/geometry/src/geometry/kernel/faces.py`), so
 * `direction: "normal"` sweeps AWAY from the solid and `"reverse"` sweeps into
 * it. There is a material side and it is known.
 *
 * `"base"`: an origin datum (XY/XZ/YZ) or a constructed datum (offset,
 * offset-from, midplane). Those planes are free-standing — the body may sit on
 * either side of one, on both, or not exist yet — so there is no material side
 * to infer. Chained/derived datums land here too: an `offset_from` off an
 * on-face datum has been slid an arbitrary distance and may well sit outside
 * the part, so its provenance is not inherited.
 */
export type PlaneProvenance = "face" | "base";

/**
 * Where the twist axis stands: the sketch ORIGIN (the kernel's default, and a
 * gear's axis), the profile's area CENTROID (a twisted column drawn off the
 * origin), or the exact point a STORED feature already names (a loft-script
 * build), kept as it was rather than silently moved.
 */
export type TwistCentre =
  | { kind: "origin" }
  | { kind: "centroid" }
  | { kind: "point"; at: { x: number; y: number } };

/** The kernel's sanity bound on a twist, degrees (ten turns; design note §4). */
export const MAX_TWIST_DEG = 3600;

/**
 * Below this a twist is no twist: the kernel normalises `|twist| < 1e-9` deg to
 * absent (design note §4), so the form does the same rather than send a value
 * the stored row will not keep.
 */
export const MIN_TWIST_DEG = 1e-9;

/**
 * Parse the twist field to signed degrees: 0 for empty or a vanishing value
 * (no twist), or null when it is not a number or beyond ten turns.
 */
export function parseTwistDeg(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return 0;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || Math.abs(value) > MAX_TWIST_DEG) return null;
  return Math.abs(value) < MIN_TWIST_DEG ? 0 : value;
}

/** Field-level validation message for the twist, or null when it is valid. */
export function twistError(input: string): string | null {
  return parseTwistDeg(input) === null
    ? `Twist must be a number of degrees, at most ${MAX_TWIST_DEG} either way.`
    : null;
}

/** The hand of a twist, as an engineer says it, or null for none. */
export function twistHand(twistDeg: number): "Right-hand" | "Left-hand" | null {
  if (twistDeg === 0) return null;
  return twistDeg > 0 ? "Right-hand" : "Left-hand";
}

/**
 * A twist the GAUGE asked for, written into the field. Twelve significant
 * digits shed the float noise a drag leaves behind (0.1 + 0.2).
 *
 * GAUGE WRITES ONLY. A STORED twist seeds the field through
 * {@link storedTwistInput} instead: rounding it here turned 31.280937437761875
 * into 31.2809374378, so a Save that touched nothing changed the helix and
 * its rebuild cache key (review B1).
 */
export function formatTwistInput(twistDeg: number): string {
  return String(Number(twistDeg.toPrecision(12)));
}

/**
 * A STORED twist as field text, exactly: `String` is JavaScript's shortest
 * round-trip form, so `parseTwistDeg(storedTwistInput(t)) === t` for every
 * twist the kernel accepts (1e-9 <= |t| <= 3600), and a no-op Save sends back
 * the number it was given.
 */
export function storedTwistInput(twistDeg: number): string {
  return String(twistDeg);
}

/**
 * The kernel refuses a twist whose own cost estimate exceeds this, in seconds
 * (`TWIST_COST_LIMIT_S` in services/geometry/.../kernel/twist.py; geometry QA
 * F4, design note §6.1). Held to that source by a drift guard in the tests.
 */
export const TWIST_COST_LIMIT_S = 4.5;

/**
 * A conservative UPPER BOUND of the kernel's build-cost estimate for a twist
 * of this profile, in seconds: the formula design note §6.1 publishes for the
 * UI, from the profile's edge counts alone.
 *
 *     upper(T) = T (0.0136 L + 0.0165 C + 0.195 S)
 *              + T^2 (0.0094 L + 0.0002 S + sum over arcs (0.0002 + 0.0086 theta))
 *
 * `T` is turns, `L`/`C`/`S` the line, circle-or-arc and spline edge counts,
 * `theta` each circle's or arc's angle (2 pi for a circle). It never
 * under-states the kernel's estimate on the kernel's stress set but can
 * over-state it about 2x, so a caller may say "may be slow or refused", never
 * predict the refusal: the kernel's own verdict is the authority.
 * Construction geometry and points are not edges of the profile.
 */
export function twistCostUpperS(
  twistDeg: number,
  entities: readonly SketchEntity[],
): number {
  const turns = Math.abs(twistDeg) / 360;
  let linear = 0;
  let quadratic = 0;
  for (const entity of entities) {
    if (entity.construction) continue;
    switch (entity.kind) {
      case "point":
        break;
      case "line":
        linear += 0.0136;
        quadratic += 0.0094;
        break;
      case "circle":
        linear += 0.0165;
        quadratic += 0.0002 + 0.0086 * 2 * Math.PI;
        break;
      case "arc": {
        const a0 = Math.atan2(
          entity.start.y - entity.center.y,
          entity.start.x - entity.center.x,
        );
        const a1 = Math.atan2(
          entity.end.y - entity.center.y,
          entity.end.x - entity.center.x,
        );
        // Counterclockwise from start to end (the wire's arc), in (0, 2 pi].
        let theta = a1 - a0;
        while (theta <= 0) theta += 2 * Math.PI;
        linear += 0.0165;
        quadratic += 0.0002 + 0.0086 * theta;
        break;
      }
      default:
        linear += 0.195;
        quadratic += 0.0002;
    }
  }
  return turns * linear + turns * turns * quadratic;
}

/**
 * The twist centre as a sketch-plane point, or null for the sketch origin
 * (which the params express by leaving `twist_center` out). `centroid` is the
 * profile's area centroid, supplied by the caller that can see the profile.
 */
export function twistCentrePoint(
  centre: TwistCentre,
  centroid: { x: number; y: number } | null,
): { x: number; y: number } | null {
  switch (centre.kind) {
    case "origin":
      return null;
    case "centroid":
      return centroid;
    case "point":
      return centre.at;
  }
}

/** The editable extrude form state (distance kept as raw text — unit input). */
export interface ExtrudeForm {
  profileFeatureId: string;
  distanceInput: string;
  operation: ExtrudeOperation;
  direction: ExtrudeDirection;
  /**
   * True once the USER has chosen a direction in this editing session — the
   * override flag that lets the operation re-default direction (FB-4) without
   * ever overwriting a deliberate choice.
   *
   * Tracked rather than inferred, because the VALUE cannot carry that meaning:
   * `"reverse"` is both the default for a cut on a face and the thing a user
   * picks by hand, so "it differs from the default" answers a different
   * question than "the user meant it". Session-scoped by design: an existing
   * feature seeds `false` (see {@link formFromParams}) so re-defaulting works
   * the same on the edit path, and it can only fire on an explicit operation or
   * profile switch — which is itself a statement of intent.
   */
  directionTouched: boolean;
  /**
   * "Merge result" (multi-body §MB-1): an ADD that fuses into the active body
   * (`true`, today's behavior) or starts a NEW body (`false`). Meaningless for
   * a cut (a cut always removes from the active body) — carried at `true` there
   * and never shown, but always sent (the wire field is required, MB-0).
   */
  merge: boolean;
  /**
   * The twist over the whole distance, degrees, as typed (helical-gear gap G1,
   * `docs/design/twisted-extrude.md`). Signed: positive is a RIGHT-hand helix
   * about the direction of travel, negative left. Empty or 0 is no twist, and
   * then the params carry NO twist fields at all, so an untwisted extrude
   * stays byte-identical to one saved before twist existed.
   */
  twistInput: string;
  /** Where the twist axis pierces the sketch plane (see {@link TwistCentre}). */
  twistCentre: TwistCentre;
  /**
   * The feature's params as STORED, when this form edits an existing extrude
   * (absent on create). The form edits five fields; the feature can carry
   * more than the editor shows (a twist authored by loft-script, d823af9), and
   * a PATCH replaces the whole envelope, so {@link extrudeParamsFromForm}
   * writes the edited fields OVER these rather than instead of them. Without
   * that, changing the depth of a twisted (helical gear) extrude, or dragging
   * its depth handle, silently straightened it.
   */
  stored?: ExtrudeParams;
}

/** A sketch the extrude may consume, as offered in the profile picker. */
export interface ProfileOption {
  id: string;
  name: string;
  /** Where this sketch's plane is seated — decides the cut default (FB-4). */
  provenance: PlaneProvenance;
}

/**
 * The live-preview projection of the extrude form (UI-REVIEW 2026-07-24 #8):
 * exactly what the viewport ghost needs to sweep the profile, or null when the
 * form has no valid profile + distance yet. Decoupled from the editor component
 * so the ghost math is unit-testable and PartPage never imports the form UI.
 */
export interface ExtrudePreviewState {
  profileFeatureId: string;
  /** Canonical mm, always positive (an empty/invalid field yields null). */
  distanceMm: number;
  direction: ExtrudeDirection;
  operation: ExtrudeOperation;
  /**
   * Signed twist, degrees; 0 = a straight prism. An invalid twist field
   * previews as 0 (the field is red and Save is gated; the ghost should not
   * vanish while you correct it).
   */
  twistDeg: number;
  /** The twist axis's sketch-plane point, or null for the sketch origin. */
  twistCentre: { x: number; y: number } | null;
}

/** The current form as a preview projection, or null while it is incomplete. */
export function extrudePreviewState(
  form: ExtrudeForm,
  unit: LengthUnit,
  centroid: { x: number; y: number } | null = null,
): ExtrudePreviewState | null {
  const distanceMm = parseDistanceMm(form.distanceInput, unit);
  if (distanceMm === null || form.profileFeatureId === "") return null;
  return {
    profileFeatureId: form.profileFeatureId,
    distanceMm,
    direction: form.direction,
    operation: form.operation,
    twistDeg: parseTwistDeg(form.twistInput) ?? 0,
    twistCentre: twistCentrePoint(form.twistCentre, centroid),
  };
}

/**
 * Which way an extrude should sweep by DEFAULT, from the operation and the
 * plane the profile sits on (FB-4 — "I select a sketch do a cut it somehow
 * misses everything going a different way").
 *
 * On a face-seated sketch the plane normal is the face's OUTWARD normal, so a
 * cut along it leaves the solid immediately and removes nothing, every time —
 * the typed `cut_removed_nothing` error was firing for a default we chose, not
 * for anything the user did. A cut therefore runs `reverse`, into the material;
 * an add keeps `normal`, building off the face, which is where added metal
 * belongs.
 *
 * On a base or constructed datum there is genuinely no material side, so both
 * operations keep `normal`. Deliberately NOT guessed: a heuristic there (say,
 * "aim at the body's centroid") would be right about half the time and would
 * fight the user on the other half, which is worse than a stable default they
 * can see and flip.
 */
export function defaultExtrudeDirection(
  operation: ExtrudeOperation,
  provenance: PlaneProvenance,
): ExtrudeDirection {
  if (provenance === "face" && operation === "cut") return "reverse";
  return "normal";
}

/**
 * The default new-extrude form: 10 mm, add, and the direction the operation +
 * plane call for (an add is `normal` on either seat — the face case only bites
 * once the user switches to Cut, which {@link withOperation} handles).
 */
export function defaultExtrudeForm(
  profileFeatureId: string,
  provenance: PlaneProvenance = "base",
): ExtrudeForm {
  return {
    profileFeatureId,
    distanceInput: "10",
    operation: "add",
    direction: defaultExtrudeDirection("add", provenance),
    directionTouched: false,
    merge: true,
    twistInput: "",
    twistCentre: { kind: "origin" },
  };
}

/**
 * Seed the form from an existing extrude feature for editing (in `unit`).
 *
 * `directionTouched` starts false: the stored direction is shown as authored,
 * but if the user switches the operation in THIS session the direction
 * re-defaults with it, exactly as on the create path. The stored value carries
 * no evidence of who chose it — most were the old hardcoded default — so
 * treating it as a deliberate override would preserve the bug on the edit path.
 */
export function formFromParams(
  params: ExtrudeParams,
  unit: LengthUnit,
): ExtrudeForm {
  return {
    profileFeatureId: params.profile.feature_id,
    distanceInput: lengthInputValue(params.distance_mm, unit),
    operation: params.operation,
    direction: params.direction,
    directionTouched: false,
    merge: params.merge,
    twistInput:
      params.twist_angle_deg === undefined || params.twist_angle_deg === null
        ? ""
        : storedTwistInput(params.twist_angle_deg),
    // A stored centre is kept as the exact point it names; the sketch origin
    // is what an absent one means.
    twistCentre:
      params.twist_center === undefined || params.twist_center === null
        ? { kind: "origin" }
        : { kind: "point", at: params.twist_center },
    stored: params,
  };
}

/**
 * The params a submit writes: the edited fields OVER the stored params, so
 * every field the editor does not show (today, a loft-script twist) survives
 * the round trip. The ONE builder for every extrude write the editor makes,
 * the typed Save and the depth gauge's commit alike.
 */
export function extrudeParamsFromForm(
  form: ExtrudeForm,
  distanceMm: number,
  centroid: { x: number; y: number } | null = null,
): ExtrudeParams {
  // The twist fields are the FORM's now, so the stored ones never ride along:
  // clearing the twist must remove them, not leave the old helix behind.
  const kept: Partial<ExtrudeParams> = { ...form.stored };
  delete kept.twist_angle_deg;
  delete kept.twist_center;
  const params: ExtrudeParams = {
    ...kept,
    profile: { kind: "feature", feature_id: form.profileFeatureId },
    distance_mm: distanceMm,
    operation: form.operation,
    direction: form.direction,
    // Merge is an ADD choice only; a cut always removes from the active body,
    // so it sends the neutral `true` regardless of a stale toggle.
    merge: form.operation === "add" ? form.merge : true,
  };
  const twist = parseTwistDeg(form.twistInput) ?? 0;
  // NO TWIST SENDS NO TWIST FIELDS — not `null`, not `0`: absent keys, so an
  // untwisted extrude's params are the same object they were before twist
  // existed (design note §5, "zero twist is byte-identical").
  if (twist === 0) return params;
  const centre = twistCentrePoint(form.twistCentre, centroid);
  return centre === null
    ? { ...params, twist_angle_deg: twist }
    : { ...params, twist_angle_deg: twist, twist_center: centre };
}

/**
 * Switch the operation, re-defaulting the direction for the new operation —
 * unless the user has already chosen one, in which case their choice stands.
 */
export function withOperation(
  form: ExtrudeForm,
  operation: ExtrudeOperation,
  provenance: PlaneProvenance,
): ExtrudeForm {
  if (form.directionTouched) return { ...form, operation };
  return {
    ...form,
    operation,
    direction: defaultExtrudeDirection(operation, provenance),
  };
}

/**
 * Retarget the profile. The new sketch may sit on a different seat (a face
 * rather than a datum), so an untouched direction re-defaults for it.
 */
export function withProfile(
  form: ExtrudeForm,
  profileFeatureId: string,
  provenance: PlaneProvenance,
): ExtrudeForm {
  if (form.directionTouched) return { ...form, profileFeatureId };
  return {
    ...form,
    profileFeatureId,
    direction: defaultExtrudeDirection(form.operation, provenance),
  };
}

/** Record the user's own direction choice — from here on it is never re-defaulted. */
export function withDirection(
  form: ExtrudeForm,
  direction: ExtrudeDirection,
): ExtrudeForm {
  return { ...form, direction, directionTouched: true };
}

/**
 * Where the sweep goes, in plain language — the caption under the Direction
 * control, so the user reads the resolved direction before committing rather
 * than discovering it from a failed cut. Says what happens to the MATERIAL on a
 * face-seated sketch (the seat where "normal" and "into the part" disagree),
 * and falls back to naming the axis on a free-standing plane, where claiming a
 * material side would be a lie.
 */
export function describeExtrudeDirection(
  operation: ExtrudeOperation,
  direction: ExtrudeDirection,
  provenance: PlaneProvenance,
): string {
  if (provenance !== "face") {
    return direction === "normal"
      ? "Along the plane normal."
      : "Against the plane normal.";
  }
  if (operation === "cut") {
    return direction === "reverse"
      ? "Cuts into the part, behind the face."
      : "Runs out from the face — nothing to remove there.";
  }
  return direction === "normal"
    ? "Builds out from the face."
    : "Builds into the part, behind the face.";
}

/**
 * Where each sketch feature's plane is seated, by feature id — an `on_face`
 * datum makes the sketch face-seated; every other plane ref is `"base"`.
 * Resolved from the tree the same way the kernel resolves the sketch plane: the
 * sketch's `plane` slot is either an origin `DatumPlaneRef` or a `FeatureRef`
 * to a datum feature, whose `kind` says how that datum was built.
 */
export function planeProvenanceById(
  features: readonly FeatureResponse[],
): Map<string, PlaneProvenance> {
  const datums = new Map<string, DatumParams>();
  for (const feature of features) {
    if (feature.feature.type === "datum") {
      datums.set(feature.id, feature.feature.params);
    }
  }
  const byId = new Map<string, PlaneProvenance>();
  for (const feature of features) {
    if (feature.feature.type !== "sketch") continue;
    const plane = feature.feature.params.plane;
    const seated =
      plane.kind === "feature" &&
      datums.get(plane.feature_id)?.kind === "on_face";
    byId.set(feature.id, seated ? "face" : "base");
  }
  return byId;
}

/** One sketch's plane seat, or `"base"` when it is unknown/unresolvable. */
export function planeProvenance(
  features: readonly FeatureResponse[],
  sketchFeatureId: string,
): PlaneProvenance {
  return planeProvenanceById(features).get(sketchFeatureId) ?? "base";
}

/**
 * Parse the distance field to a positive CANONICAL millimetre value in the
 * document `unit`, or null when empty, non-numeric, or non-positive (an extrude
 * of zero depth is no solid). A bare number reads in `unit`; a suffix (`2in`)
 * overrides it — the storage value is always mm.
 */
export function parseDistanceMm(
  input: string,
  unit: LengthUnit,
): number | null {
  return parsePositiveLengthMm(input, unit);
}

/** Field-level validation message for the distance, or null when it is valid. */
export function distanceError(input: string, unit: LengthUnit): string | null {
  if (input.trim() === "") return null; // empty is pending, not yet wrong
  return parseDistanceMm(input, unit) === null
    ? "Distance must be a positive length."
    : null;
}

/**
 * WHY the extrude cannot be created yet, or null when it can (REASON-GATE-1 —
 * see `submitBlocker.ts` for the rule and the 48-character budget).
 */
export function extrudeSubmitBlocker(
  form: ExtrudeForm,
  unit: LengthUnit,
): string | null {
  if (form.profileFeatureId === "") return "Choose a sketch profile.";
  return (
    fieldBlocker(
      form.distanceInput,
      parseDistanceMm(form.distanceInput, unit),
      "distance",
    ) ??
    // An empty twist is a valid answer (none), so only a wrong one blocks.
    fieldBlocker(form.twistInput, parseTwistDeg(form.twistInput), "twist")
  );
}

/** True when the form can be submitted — the blocker, read as a verdict. */
export function canSubmitExtrude(form: ExtrudeForm, unit: LengthUnit): boolean {
  return extrudeSubmitBlocker(form, unit) === null;
}

/** The sketch features a new extrude may consume, in build order. */
export function profileOptions(
  features: readonly FeatureResponse[],
): ProfileOption[] {
  const provenance = planeProvenanceById(features);
  return features
    .filter((f) => f.feature.type === "sketch")
    .map((f) => ({
      id: f.id,
      name: f.name,
      provenance: provenance.get(f.id) ?? "base",
    }));
}

/** The seat of the sketch `profileFeatureId` names, from offered options. */
export function optionProvenance(
  profiles: readonly ProfileOption[],
  profileFeatureId: string,
): PlaneProvenance {
  return profiles.find((p) => p.id === profileFeatureId)?.provenance ?? "base";
}

/**
 * WHICH PROFILE A NEW EXTRUDE OPENS ON, given what the caller named.
 *
 * Three answers, and the middle one is the W2 review's third finding:
 *
 *  · nothing named — the tree's default (the band's Extrude button);
 *  · a name the tree still offers — that one (the proposal chip, a scripted
 *    call, anything that knows its noun);
 *  · a name the tree does NOT offer — **null, meaning refuse**. It used to
 *    fall back to the default, so a chip whose accessible name said "Extrude
 *    Sketch2" could open the editor holding a different sketch. Silently. A
 *    seed goes stale for ordinary reasons — a tree refetch landing between the
 *    chip's render and the click, a rollback, an undo — and the caller that
 *    passed it is the only one that knows what it meant, so the honest answer
 *    is to do nothing rather than to guess a noun.
 *
 * A caller with no seed can never be refused, which is what keeps the band's
 * own button unaffected.
 */
export function seededProfileId(
  profiles: readonly ProfileOption[],
  features: readonly FeatureResponse[],
  seed: string | null,
): string | null {
  if (seed === null) {
    const fallback = defaultProfileId(features);
    return fallback === "" ? null : fallback;
  }
  if (!profiles.some((option) => option.id === seed)) return null;
  return seed;
}

/** Default profile for a NEW extrude: the last sketch in the tree, or "". */
export function defaultProfileId(features: readonly FeatureResponse[]): string {
  const sketches = profileOptions(features);
  return sketches.length > 0 ? (sketches[sketches.length - 1]?.id ?? "") : "";
}
