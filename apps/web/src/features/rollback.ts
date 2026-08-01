/**
 * Travel-stop view math — pure functions the bottom TimelineStrip uses to place
 * the stop and translate a slot into the documents API's `rollback_feature_id`
 * (design §3: the id of the LAST INCLUDED feature, or null for the tip). Kept
 * out of the component for unit testing.
 *
 * The slot math is deliberately ORIENTATION-AGNOSTIC — it was written for a
 * vertical bar between tree rows and carried over UNCHANGED when rollback became
 * a horizontal machine way (UI-W1): a slot is an index along the build order,
 * and which axis the build order is drawn on is presentation.
 */
import type { FeatureResponse } from "../api/parts";

/**
 * The slot index the bar currently occupies. Slots sit AFTER each feature:
 * slot i lies just below feature i (0-based). `null` (bar at the tip) maps to
 * the last slot; an unknown id also falls through to the tip.
 */
export function barSlotIndex(
  features: readonly FeatureResponse[],
  rollbackFeatureId: string | null,
): number {
  if (rollbackFeatureId === null) return features.length - 1;
  const index = features.findIndex((f) => f.id === rollbackFeatureId);
  return index === -1 ? features.length - 1 : index;
}

/**
 * The `rollback_feature_id` to send when the user drops the bar after feature
 * `slotIndex`. The last slot means "include everything" → null (the API's tip
 * sentinel); any earlier slot names that feature as the last included one.
 */
export function rollbackIdForSlot(
  features: readonly FeatureResponse[],
  slotIndex: number,
): string | null {
  if (slotIndex >= features.length - 1) return null; // tip = all included
  return features[slotIndex]?.id ?? null;
}

/**
 * Which slot a dragged travel stop should land in: the slot whose anchor (its
 * centre x on the way, in client px) is nearest the pointer. A tie takes the
 * EARLIER slot — dragging left across a midpoint should commit to the smaller
 * build, never overshoot back toward the tip.
 *
 * Anchors arrive already measured (`getBoundingClientRect`) so this stays pure
 * and testable; an empty way has no slot to land in, hence -1.
 */
export function nearestSlotIndex(
  anchors: readonly number[],
  clientX: number,
): number {
  let best = -1;
  let bestDistance = Number.POSITIVE_INFINITY;
  anchors.forEach((anchor, index) => {
    const distance = Math.abs(anchor - clientX);
    if (distance < bestDistance) {
      best = index;
      bestDistance = distance;
    }
  });
  return best;
}

/** True when feature `index` sits below the bar (excluded from evaluation). */
export function isRolledBack(
  features: readonly FeatureResponse[],
  rollbackFeatureId: string | null,
  index: number,
): boolean {
  return index > barSlotIndex(features, rollbackFeatureId);
}
