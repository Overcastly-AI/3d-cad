/**
 * Rollback-bar view math — pure functions the FeatureTreePanel uses to place
 * the bar and translate a clicked slot into the documents API's
 * `rollback_feature_id` (design §3: the id of the LAST INCLUDED feature, or
 * null for the tip). Kept out of the component for unit testing.
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

/** True when feature `index` sits below the bar (excluded from evaluation). */
export function isRolledBack(
  features: readonly FeatureResponse[],
  rollbackFeatureId: string | null,
  index: number,
): boolean {
  return index > barSlotIndex(features, rollbackFeatureId);
}
