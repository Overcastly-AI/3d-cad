/**
 * THE DROP RULE for the feature tree — "may this feature sit here?", answered
 * before the request rather than after it.
 *
 * A reorder is refused server-side (`reference_not_earlier`,
 * `services/documents/.../features.py`) when the permutation would put a
 * feature BEFORE something it is built on. A drag affordance that can only
 * learn that from a round trip has no live drop rule and no reason to give at
 * the moment the user is deciding, so the same question is asked here — and the
 * SERVER stays authoritative: `FeatureTreePanel` still sends the write and
 * still surfaces a server refusal through this module's vocabulary, so the two
 * answers converge on one sentence.
 *
 * WHY THIS IS NOT A SECOND SOURCE OF TRUTH (CLAUDE.md DRY rule). The server's
 * reorder check reads `feature_dependencies` — the edges documents materialises
 * from `feature_references()`. That function is itself *self-checked against*
 * py-kit's generic `iter_feature_refs` walk ("if a schema gains a ref-bearing
 * field this mapping misses, the mismatch raises"), and every ref kind
 * (`FeatureRef` / `SubshapeRef` / `EdgeSubshapeRef`) joins the graph by exactly
 * one field: `feature_id`. So the edge SET is, by the server's own invariant,
 * "every `feature_id` reachable in the params" — which is what
 * `featureReferenceIds` computes. What is deliberately NOT duplicated here is
 * the slot/type rule table (`allowed_types`): reorder does not consult it, and
 * copying it would be the duplication the rule forbids.
 */
import type { FeatureResponse } from "../api/parts";

/** Every `feature_id` reachable in a value — the generic ref walk, in TS. */
function collectFeatureIds(value: unknown, out: Set<string>): void {
  if (Array.isArray(value)) {
    for (const item of value) collectFeatureIds(item, out);
    return;
  }
  if (typeof value !== "object" || value === null) return;
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    if (key === "feature_id" && typeof item === "string") {
      out.add(item);
    } else {
      collectFeatureIds(item, out);
    }
  }
}

/**
 * The ids this feature is BUILT ON — the outgoing edges of the dependency
 * graph. Every one of them has to stay strictly earlier in the tree.
 */
export function featureReferenceIds(feature: FeatureResponse): string[] {
  const found = new Set<string>();
  collectFeatureIds(feature.feature, found);
  // A self-reference is not expressible through the write API (rule 2 refuses
  // it), but dropping it here costs nothing and keeps a malformed row from
  // presenting as an unfixable conflict.
  found.delete(feature.id);
  return [...found];
}

/** One violated edge, named on both ends — never an id the user cannot read. */
export interface OrderConflict {
  /** The feature that would end up before something it is built on. */
  readonly dependentId: string;
  readonly dependentName: string;
  /** The thing it is built on, which has to stay above it. */
  readonly referenceId: string;
  readonly referenceName: string;
}

/**
 * The first edge this order violates, or null when the whole order is legal.
 *
 * "First" is by the DEPENDENT's position, so the conflict reported is the one
 * nearest the top of the tree — the one a user scanning downward meets first.
 */
export function firstOrderConflict(
  order: readonly FeatureResponse[],
): OrderConflict | null {
  const positionById = new Map<string, number>();
  order.forEach((feature, index) => positionById.set(feature.id, index));
  const nameById = new Map<string, string>();
  for (const feature of order) nameById.set(feature.id, feature.name);

  for (const [index, feature] of order.entries()) {
    for (const referenceId of featureReferenceIds(feature)) {
      const referencePosition = positionById.get(referenceId);
      // A ref to a feature that is not in this list is not an ORDER problem
      // (the write rules refuse a cross-part id at authoring time); saying
      // nothing is the honest answer here.
      if (referencePosition === undefined) continue;
      if (referencePosition >= index) {
        return {
          dependentId: feature.id,
          dependentName: feature.name,
          referenceId,
          referenceName: nameById.get(referenceId) ?? referenceId,
        };
      }
    }
  }
  return null;
}

/** The list with `fromIndex` lifted out and re-seated at `toIndex`. */
export function movedOrder(
  features: readonly FeatureResponse[],
  fromIndex: number,
  toIndex: number,
): FeatureResponse[] {
  const next = [...features];
  const [moved] = next.splice(fromIndex, 1);
  if (moved === undefined) return [...features];
  next.splice(Math.max(0, Math.min(toIndex, next.length)), 0, moved);
  return next;
}

/**
 * The seat nearest the one asked for that the tree will actually accept,
 * searching back toward where the feature started. Equals `fromIndex` when
 * there is no legal seat in that direction at all — i.e. there is no repair to
 * offer, only a refusal to explain.
 */
export function nearestLegalIndex(
  features: readonly FeatureResponse[],
  fromIndex: number,
  toIndex: number,
): number {
  const step = toIndex > fromIndex ? -1 : 1;
  for (let seat = toIndex; seat !== fromIndex; seat += step) {
    if (firstOrderConflict(movedOrder(features, fromIndex, seat)) === null) {
      return seat;
    }
  }
  return fromIndex;
}

/**
 * The refusal, in the interface's voice: it names both features and says which
 * way round they have to be. One sentence covers both directions of travel —
 * dragging a feature above its reference and dragging a reference below its
 * dependent are the same broken relationship seen from two ends.
 */
export function conflictMessage(conflict: OrderConflict): string {
  return `${conflict.dependentName} is built on ${conflict.referenceName}, so ${conflict.referenceName} has to stay above it.`;
}

/**
 * The label of the one-click repair — "Move Hole1 after Extrude1". Named by the
 * NEIGHBOUR it would land under rather than by a row number, because a row
 * number is the thing that is about to change.
 */
export function repairLabel(
  features: readonly FeatureResponse[],
  fromIndex: number,
  legalIndex: number,
): string {
  const moved = features[fromIndex];
  if (moved === undefined) return "Move it";
  const seated = movedOrder(features, fromIndex, legalIndex);
  const above = seated[legalIndex - 1];
  return above === undefined
    ? `Move ${moved.name} to the top`
    : `Move ${moved.name} after ${above.name}`;
}
