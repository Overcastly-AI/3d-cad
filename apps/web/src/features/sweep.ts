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
import { fieldBlocker } from "./submitBlocker";
import { parseTwistDeg, storedTwistInput } from "./twist";

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
  /**
   * Twist along the path, degrees, as typed (TWIST-TO-SWEEP). Signed:
   * positive is RIGHT-handed about travel from the profile along the path.
   * Empty or 0 is no twist, and then the params carry NO `twist_angle_deg`
   * key, so an untwisted sweep stays byte-identical to one saved before
   * twist existed.
   */
  twistInput: string;
  /**
   * The feature's params as STORED, when this form edits an existing sweep
   * (absent on create). A PATCH replaces the whole params envelope, so
   * {@link buildSweepParams} writes the edited fields OVER these: a field the
   * editor does not show survives an edit of one it does.
   */
  stored?: SweepParams;
}

/** The default new-sweep form: add, against the given profile + path sketches. */
export function defaultSweepForm(
  profileFeatureId: string,
  pathFeatureId: string,
): SweepForm {
  return {
    profileFeatureId,
    pathFeatureId,
    operation: "add",
    merge: true,
    twistInput: "",
  };
}

/** Seed the form from an existing sweep feature for editing. */
export function formFromSweepParams(params: SweepParams): SweepForm {
  return {
    profileFeatureId: params.profile.feature_id,
    pathFeatureId: params.path.feature_id,
    operation: params.operation,
    merge: params.merge,
    // Exactly as stored (see `storedTwistInput`): a no-op Save, or an edit of
    // the path or operation alone, sends the same twist back. Dropping it
    // would straighten a twisted sweep (a loft-script helical gear) silently.
    twistInput:
      params.twist_angle_deg === undefined || params.twist_angle_deg === null
        ? ""
        : storedTwistInput(params.twist_angle_deg),
    stored: params,
  };
}

/**
 * True when the form can be submitted: a profile, a path, and the two must be
 * DIFFERENT sketches (one closed wire, one open — a single sketch can't be
 * both). The kernel enforces open/closed at rebuild; distinctness we enforce
 * here so the user can't author a self-referential sweep at all.
 */
export function canSubmitSweep(form: SweepForm): boolean {
  return sweepSubmitBlocker(form) === null;
}

/**
 * WHY the sweep cannot be created yet, or null when it can (REASON-GATE-1 — see
 * `submitBlocker.ts` for the rule and the 48-character budget).
 *
 * The "no open sketch exists at all" case is NOT here: it is a fact about the
 * part, not about this form, and `SweepEditor` states it as such before asking
 * for a path the tree cannot supply.
 */
export function sweepSubmitBlocker(form: SweepForm): string | null {
  if (form.profileFeatureId === "") return "Choose the profile sketch.";
  if (form.pathFeatureId === "") return "Choose the path sketch.";
  if (form.profileFeatureId === form.pathFeatureId) {
    return "Profile and path must be different sketches.";
  }
  // An empty twist is a valid answer (none), so only a wrong one blocks.
  return fieldBlocker(form.twistInput, parseTwistDeg(form.twistInput), "twist");
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
  // The twist is the FORM's now, so the stored one never rides along:
  // clearing the field must remove it, not leave the old helix behind.
  const kept: Partial<SweepParams> = { ...form.stored };
  delete kept.twist_angle_deg;
  const params: SweepParams = {
    ...kept,
    profile: { kind: "feature", feature_id: form.profileFeatureId },
    path: { kind: "feature", feature_id: form.pathFeatureId },
    operation: form.operation,
    // Merge is an ADD choice only (see ExtrudeEditor); a cut sends `true`.
    merge: form.operation === "add" ? form.merge : true,
  };
  const twist = parseTwistDeg(form.twistInput) ?? 0;
  // NO TWIST SENDS NO TWIST KEY (not `null`, not `0`), so an untwisted sweep's
  // params are the object they were before twist existed.
  return twist === 0 ? params : { ...params, twist_angle_deg: twist };
}
