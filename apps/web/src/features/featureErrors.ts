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
 * intersect that meets in two regions, or a union of bodies that don't touch) —
 * a single connected solid per body is the v1 invariant.
 */
const FRIENDLY_FEATURE_ERROR: Record<string, string> = {
  boolean_empty:
    "These bodies don't overlap — or the subtract removes the whole body — so there's no solid left to keep.",
  boolean_disjoint:
    "This boolean splits the body into separate pieces, which isn't supported yet — a body must stay one connected solid.",
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
