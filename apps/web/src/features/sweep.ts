/**
 * Sweep-feature view logic — pure functions the SweepEditor and the PartPage
 * share, kept out of the component so they can be unit-tested without a DOM
 * (the extrude/revolve module's twin). Param shapes come from the generated
 * client (CLAUDE.md DRY rule); the builders live in `../api/parts`.
 *
 * Sweep is the first feature that references TWO earlier sketches by id: a
 * closed PROFILE and an open PATH (unlike extrude/revolve, which consume the
 * one implicit preceding sketch). Both slots are `FeatureRef`s to earlier
 * SKETCH features — so the picker is two ruled selects over the tree's sketch
 * features (the revolve axis-select idiom, promoted from entities to features):
 * keyboard-first, deterministically testable, no new viewport selection layer.
 * A sketch can only fill ONE slot (a wire is either closed or open, never
 * both), so the path list excludes whatever the profile currently names.
 */
import type { FeatureResponse, SweepParams } from "../api/parts";
import { profileOptions, type ProfileOption } from "./extrude";

export { profileOptions };
export type { ProfileOption };

export type SweepOperation = SweepParams["operation"];

/** The editable sweep form state: two sketch references + the add/cut sense. */
export interface SweepForm {
  profileFeatureId: string;
  pathFeatureId: string;
  operation: SweepOperation;
  /** "Merge result" (multi-body §MB-1) — see `ExtrudeForm.merge`. */
  merge: boolean;
}

/** The default new-sweep form: add, against the given profile + path sketches. */
export function defaultSweepForm(
  profileFeatureId: string,
  pathFeatureId: string,
): SweepForm {
  return { profileFeatureId, pathFeatureId, operation: "add", merge: true };
}

/** Seed the form from an existing sweep feature for editing. */
export function formFromSweepParams(params: SweepParams): SweepForm {
  return {
    profileFeatureId: params.profile.feature_id,
    pathFeatureId: params.path.feature_id,
    operation: params.operation,
    merge: params.merge,
  };
}

/**
 * True when the form can be submitted: a profile, a path, and the two must be
 * DIFFERENT sketches (one closed wire, one open — a single sketch can't be
 * both). The kernel enforces open/closed at rebuild; distinctness we enforce
 * here so the user can't author a self-referential sweep at all.
 */
export function canSubmitSweep(form: SweepForm): boolean {
  return (
    form.profileFeatureId !== "" &&
    form.pathFeatureId !== "" &&
    form.profileFeatureId !== form.pathFeatureId
  );
}

/**
 * Sketch features eligible as the PATH: every sketch except the one currently
 * chosen as the profile (a sketch fills only one slot). Empty when no other
 * sketch exists.
 */
export function pathOptions(
  features: readonly FeatureResponse[],
  profileFeatureId: string,
): ProfileOption[] {
  return profileOptions(features).filter((s) => s.id !== profileFeatureId);
}

/** Default profile for a NEW sweep: the FIRST sketch in the tree, or "". */
export function defaultSweepProfileId(
  features: readonly FeatureResponse[],
): string {
  const sketches = profileOptions(features);
  return sketches.length > 0 ? (sketches[0]?.id ?? "") : "";
}

/** Default path: the first sketch that isn't the chosen profile, or "". */
export function defaultSweepPathId(
  features: readonly FeatureResponse[],
  profileFeatureId: string,
): string {
  const options = pathOptions(features, profileFeatureId);
  return options.length > 0 ? (options[0]?.id ?? "") : "";
}

/** How many sketch features exist — the tool needs ≥2 (a profile AND a path). */
export function sweepEligibleSketchCount(
  features: readonly FeatureResponse[],
): number {
  return profileOptions(features).length;
}

/** Build the persisted params from valid form state, or null when incomplete. */
export function buildSweepParams(form: SweepForm): SweepParams | null {
  if (!canSubmitSweep(form)) return null;
  return {
    profile: { kind: "feature", feature_id: form.profileFeatureId },
    path: { kind: "feature", feature_id: form.pathFeatureId },
    operation: form.operation,
    // Merge is an ADD choice only (see ExtrudeEditor); a cut sends `true`.
    merge: form.operation === "add" ? form.merge : true,
  };
}
