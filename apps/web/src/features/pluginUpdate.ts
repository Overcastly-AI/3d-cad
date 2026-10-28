/**
 * Out-of-date Build features (OPENING-UPDATE). Onshape marks a custom feature
 * whose Feature Studio has a newer version and updates it on request, one at
 * a time or all at once; Fusion badges out-of-date linked content. Loft's
 * server says which stored features have an update (`plugin_update` on the
 * row, only where the plugin maps their inputs explicitly); this module reads
 * that for the tree's badges, the editor's "Update to x.y.0" and the part's
 * one "Update all".
 */
import type { FeatureResponse } from "../api/parts";

/** One feature that can be updated, and to what. */
export interface OutOfDateFeature {
  readonly feature: FeatureResponse;
  readonly toVersion: string;
  readonly summary: string;
}

/** The row's update, or null when it is current (or not a custom feature). */
export function featureUpdate(
  feature: FeatureResponse,
): { toVersion: string; summary: string } | null {
  const update = feature.plugin_update;
  if (update === null || update === undefined) return null;
  return { toVersion: update.to_version, summary: update.summary };
}

/** Every feature of the tree that can be updated, in tree order. */
export function outOfDateFeatures(
  features: readonly FeatureResponse[],
): OutOfDateFeature[] {
  const out: OutOfDateFeature[] = [];
  for (const feature of features) {
    const update = featureUpdate(feature);
    if (update !== null) out.push({ feature, ...update });
  }
  return out;
}

/** The per-feature action's label: "Update to 1.5.0". */
export function updateToLabel(toVersion: string): string {
  return `Update to ${toVersion}`;
}

/** The tree's summary of what is out of date: "7 Build features out of date". */
export function outOfDateSentence(count: number): string {
  return count === 1
    ? "1 Build feature out of date"
    : `${count} Build features out of date`;
}

/** The part's one action, named for what it does. */
export const UPDATE_ALL_LABEL = "Update all Build features";
