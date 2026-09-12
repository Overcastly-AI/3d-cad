/**
 * Extrude-feature view logic — pure functions the ExtrudeEditor and the
 * PartPage share, kept out of the component so they can be unit-tested without
 * a DOM. Param shapes come from the generated client (CLAUDE.md DRY rule); the
 * builders live in `../api/parts` alongside the sketch builders.
 */
import type { LengthUnit } from "@loft/design";

import type { DatumParams, ExtrudeParams, FeatureResponse } from "../api/parts";
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
}

/** The current form as a preview projection, or null while it is incomplete. */
export function extrudePreviewState(
  form: ExtrudeForm,
  unit: LengthUnit,
): ExtrudePreviewState | null {
  const distanceMm = parseDistanceMm(form.distanceInput, unit);
  if (distanceMm === null || form.profileFeatureId === "") return null;
  return {
    profileFeatureId: form.profileFeatureId,
    distanceMm,
    direction: form.direction,
    operation: form.operation,
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
  };
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
  return fieldBlocker(
    form.distanceInput,
    parseDistanceMm(form.distanceInput, unit),
    "distance",
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

/** Default profile for a NEW extrude: the last sketch in the tree, or "". */
export function defaultProfileId(features: readonly FeatureResponse[]): string {
  const sketches = profileOptions(features);
  return sketches.length > 0 ? (sketches[sketches.length - 1]?.id ?? "") : "";
}
