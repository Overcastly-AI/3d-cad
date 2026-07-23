import type { FeatureResponse } from "../api/parts";

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
    "This blind hole would break through the far side of the body. Reduce the depth, or switch to Through all.",
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
};

/**
 * The user-facing copy for a per-feature error: friendly copy for the codes we
 * humanise, otherwise the server's own message (unchanged behaviour for every
 * other feature).
 */
export function friendlyFeatureError(
  code: string,
  serverMessage: string,
): string {
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
