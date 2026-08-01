/**
 * Re-anchored dimensions — reading `MeasuredDimension.anchor` and healing the
 * stored reference (topological-naming §11; audit N1 frontend half).
 *
 * When a part is edited, a dimension's stored stage-1 edge signature may no
 * longer match verbatim. Geometry then re-anchors it on the curve-kind rebuild
 * invariant and reports `anchor.tier === "durable"` plus the CURRENT signatures
 * of the edges the dimension now names. The value on the sheet is model-true
 * either way — but "your reference moved and we guessed which edge you meant"
 * is a thing the user should be told, and the returned signature is exactly what
 * is needed to make the guess permanent.
 *
 * This module is the pure half of that: is a measured dimension re-anchored, and
 * what would its params look like with the reference healed. Persisting the
 * healed params is the page's job (there is no PATCH route for a dimension, so
 * the write is an append of the healed dimension followed by a delete of the
 * stale one — in that order, so a failure can only leave a duplicate the user
 * can see and remove, never a lost dimension).
 */
import type {
  DimensionAnchor,
  DimensionParams,
  EdgeSignature,
  MeasuredDimension,
} from "../api/drawings";

/**
 * The re-anchor result for a measured dimension, or null when there is nothing
 * to confirm: no anchor at all (an unresolved dimension, or a caller-synthesised
 * value) or an `exact` match, which is the everyday case and says nothing.
 */
export function reanchoredAnchor(
  measured: MeasuredDimension | undefined,
): DimensionAnchor | null {
  const anchor = measured?.anchor ?? null;
  if (anchor === null || anchor.tier !== "durable") return null;
  return anchor;
}

/**
 * The dimension's params with every edge reference replaced by the signature the
 * anchor says it landed on — the "heal the stored ref" write. The authored
 * PLACEMENT is preserved verbatim: healing changes which edge the dimension
 * names, never where it is drawn.
 *
 * Returns null when the anchor does not carry the signature(s) this dimension
 * type needs (an angular missing its second edge, say) — the caller then offers
 * no confirm action rather than writing a half-healed reference.
 */
export function healDimensionParams(
  params: DimensionParams,
  anchor: DimensionAnchor,
): DimensionParams | null {
  const primary: EdgeSignature | null = anchor.primary ?? null;
  const secondary: EdgeSignature | null = anchor.secondary ?? null;
  if (primary === null) return null;

  switch (params.type) {
    case "diameter":
    case "radius":
      return { ...params, edge: primary };
    case "angular":
      if (secondary === null) return null;
      return { ...params, edge_a: primary, edge_b: secondary };
    case "linear": {
      const measurement = params.measurement;
      if (measurement.mode === "edge_length") {
        return {
          ...params,
          measurement: { ...measurement, edge: primary },
        };
      }
      if (secondary === null) return null;
      return {
        ...params,
        measurement: {
          ...measurement,
          a: { ...measurement.a, signature: primary },
          b: { ...measurement.b, signature: secondary },
        },
      };
    }
    default:
      return null;
  }
}
