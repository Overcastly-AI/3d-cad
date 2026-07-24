import type { FeatureResponse } from "../api/parts";

/** A feature's kind on the wire (sketch / extrude / revolve / …). */
type FeatureKind = FeatureResponse["feature"]["type"];

/**
 * Friendly copy for per-feature REBUILD error codes (multi-body §MB-2). The
 * geometry service returns a stable `code` plus a technical `message`; the tree
 * panel keeps the code as an honest technical tag but shows this human copy
 * underneath it, so a modeler reads what went wrong without decoding kernel
 * jargon. Codes without an entry fall back to the server's own message — this
 * is a targeted friendliness pass, not a translation table for every error.
 *
 * `boolean_empty` covers two shapes (an intersect of non-overlapping bodies, or
 * a subtract that consumes the whole target); `boolean_disjoint` covers a
 * boolean whose result would be more than one lump (a severing subtract, an
 * intersect that meets in two regions, or a union of bodies that don't touch).
 * As of MB-4c that limit is no longer a dead end: `boolean_disjoint` names the
 * `allow_disjoint` recovery ("Keep as one body") the tree panel then offers as a
 * one-click fix, so the copy guides the modeler to the multi-lump body instead
 * of describing an unsupported operation.
 */
const FRIENDLY_FEATURE_ERROR: Record<string, string> = {
  boolean_empty:
    "These bodies don't overlap — or the subtract removes the whole body — so there's no solid left to keep.",
  boolean_disjoint:
    "This boolean makes separate pieces that don't form one connected solid. Turn on “Keep as one body” to combine them into a single multi-lump body.",
  import_no_solid:
    "This STEP file has no solid geometry to import — only surfaces, shells, or wireframe. Provide a file with at least one closed solid.",
  // Hole (slice 1) rebuild errors — readable guidance, not bare codes.
  hole_off_body:
    "The hole misses the body — no material is removed. Move the point onto solid material on the face.",
  hole_too_deep:
    "This hole would break through the far side of the body. Reduce the depth or recess, or switch to Through all.",
  hole_cbore_invalid:
    "The counterbore doesn't fit — its diameter must be wider than the bore, and it must be shallower than the material. Widen the recess or reduce its depth.",
  hole_csink_invalid:
    "The countersink doesn't fit — its mouth must be wider than the bore. Widen the countersink, or reduce its angle so the cone sits shallower.",
  no_prior_body:
    "There's no body to modify yet. Add a feature that creates a body before this one.",
  subshape_unresolved:
    "The referenced face can no longer be found — an earlier edit changed the body. Re-pick the face.",
  subshape_ambiguous:
    "The referenced face matches more than one face now. Re-pick a distinct face.",
  // Mirror (§7.6) rebuild errors — readable guidance, not bare codes.
  no_target_body:
    "There's no body to mirror yet. Add a feature that creates a body before this one.",
  reference_unresolved:
    "The mirror plane can no longer be found — its datum was removed or changed. Choose another plane.",
  mirror_failed:
    "The reflection couldn't be joined to the body — the mirrored copy doesn't meet the original across this plane. Choose a plane the body straddles.",
  // Revolve (#5b) rebuild errors — readable guidance for the axis idiom.
  no_axis:
    "The chosen axis isn't a usable line. Pick a construction centerline — or a straight profile edge with length — that lies in this sketch.",
  // Generic profile-not-closed copy — the fallback for any feature that builds
  // from a sketch profile. Feature-specific wording (a revolve's axis idiom, a
  // sweep's section, a loft's per-section rule) lives in FEATURE_SPECIFIC_ERROR
  // below so an EXTRUDE never reads revolve advice (FINDINGS #13).
  profile_not_closed:
    "This profile isn't a closed region to build. Close every gap between its edges so the sketch forms one continuous loop.",
  axis_intersects_profile:
    "The axis passes through the profile, so revolving would sweep material through itself. Move the axis to one side — a solid of revolution turns about a centerline the profile clears.",
};

/**
 * Per-feature copy for codes that ARE shared across feature types but whose one
 * generic string would misadvise — keyed `[code][featureType]` (FINDINGS #13:
 * an open-profile extrude was told to snap a revolve centerline). A feature
 * without an override here falls through to {@link FRIENDLY_FEATURE_ERROR}, so
 * this table stays a targeted set of corrections, not a full matrix.
 */
const FEATURE_SPECIFIC_ERROR: Partial<
  Record<string, Partial<Record<FeatureKind, string>>>
> = {
  profile_not_closed: {
    extrude:
      "This profile isn't a closed region to extrude. Close every gap between its edges so the sketch forms one continuous loop.",
    revolve:
      "This profile isn't a closed region to revolve. Close every gap between its edges — snap a construction centerline's two ends onto the profile's open corners on the axis so it closes the open side.",
    sweep:
      "The swept profile isn't a closed region. Close every gap between its edges so the section forms one continuous loop.",
    loft: "A loft section isn't a closed region. Close every gap so each section forms one continuous loop.",
  },
};

/**
 * The user-facing copy for a per-feature error: the feature-specific override
 * when one exists (so an extrude and a revolve read their own advice for the
 * same `profile_not_closed` code — FINDINGS #13), else the friendly copy for
 * codes we humanise, else the server's own message (unchanged for every other
 * feature).
 */
export function friendlyFeatureError(
  code: string,
  serverMessage: string,
  featureType?: FeatureKind,
): string {
  if (featureType !== undefined) {
    const specific = FEATURE_SPECIFIC_ERROR[code]?.[featureType];
    if (specific !== undefined) return specific;
  }
  return FRIENDLY_FEATURE_ERROR[code] ?? serverMessage;
}

/** The action label for the `boolean_disjoint` guided recovery — the same words
 * as the Combine editor's opt-in so the vocabulary is consistent (a control that
 * says "Keep as one body" produces the same-named recovery). */
export const KEEP_AS_ONE_BODY_ACTION = "Keep as one body";

/**
 * True when a feature's error is a `boolean_disjoint` the user can recover from
 * in place (MB-4c): the feature is a `boolean` whose `allow_disjoint` is still
 * off, so re-running it with the opt-in ON turns the disconnected pieces into
 * one multi-lump body. A boolean that ALREADY set `allow_disjoint` can't reach
 * this code, so no recovery is offered (nothing left to toggle).
 */
export function offersBooleanDisjointRecovery(
  feature: FeatureResponse,
  code: string,
): boolean {
  return (
    code === "boolean_disjoint" &&
    feature.feature.type === "boolean" &&
    feature.feature.params.allow_disjoint !== true
  );
}
