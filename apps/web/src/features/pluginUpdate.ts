/**
 * Out-of-date Build features (OPENING-UPDATE, PLUGIN-UPDATE-ALL). Onshape
 * marks a custom feature whose Feature Studio has a newer version and updates
 * it on request, one at a time or all at once, every new parameter at its
 * default; Fusion badges out-of-date linked content. Loft's server says which
 * stored features have an update (`plugin_update` on the row, only where the
 * plugin maps their inputs explicitly) and what each adds ("11 ceiling
 * joists"); this module reads that for the tree's badges, the editor's
 * "Update to x.y.0" and the part's one "Update all". An update that changes
 * no member is `quiet`: it wears no badge, but Update all still takes it.
 */
import type { FeatureResponse } from "../api/parts";

/** A row's update, as the tree and the editor show it. */
export interface FeatureUpdate {
  readonly toVersion: string;
  readonly summary: string;
  /** What it adds, one count and noun each ("3 pier footings"). */
  readonly adds: readonly string[];
  /** True when it changes no member: no badge, but Update all takes it. */
  readonly quiet: boolean;
}

/** One feature that can be updated, and to what. */
export interface OutOfDateFeature extends FeatureUpdate {
  readonly feature: FeatureResponse;
}

/** The row's update, or null when it is current (or not a custom feature). */
export function featureUpdate(feature: FeatureResponse): FeatureUpdate | null {
  const update = feature.plugin_update;
  if (update === null || update === undefined) return null;
  return {
    toVersion: update.to_version,
    summary: update.summary,
    adds: update.adds ?? [],
    quiet: update.quiet,
  };
}

/**
 * Every feature of the tree whose update changes something, in tree order:
 * the badged rows, and what the strip counts. Quiet ones are left out here,
 * though Update all (which the server applies to every offered update)
 * takes them along.
 */
export function outOfDateFeatures(
  features: readonly FeatureResponse[],
): OutOfDateFeature[] {
  const out: OutOfDateFeature[] = [];
  for (const feature of features) {
    const update = featureUpdate(feature);
    if (update !== null && !update.quiet) out.push({ feature, ...update });
  }
  return out;
}

/** "3 pier footings and 3 post bases", or "" when it adds nothing. */
export function addsList(adds: readonly string[]): string {
  if (adds.length <= 1) return adds[0] ?? "";
  return `${adds.slice(0, -1).join(", ")} and ${adds[adds.length - 1]}`;
}

/** The badge's words: "Update to 1.6.0: adds 11 ceiling joists". */
export function updateBadgeTitle(update: FeatureUpdate): string {
  const adds = addsList(update.adds);
  return adds === ""
    ? `${updateToLabel(update.toVersion)}: ${update.summary}`
    : `${updateToLabel(update.toVersion)}: adds ${adds}`;
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
