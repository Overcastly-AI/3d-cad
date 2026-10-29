/**
 * Out-of-date Build features (OPENING-UPDATE, PLUGIN-UPDATE-ALL). Onshape
 * marks a custom feature whose Feature Studio has a newer version and updates
 * it on request, one at a time or all at once, every new parameter at its
 * default; Fusion badges out-of-date linked content. Loft's server says which
 * stored features have an update (`plugin_update` on the row, only where the
 * plugin maps their inputs explicitly), what each adds ("11 ceiling joists")
 * and what it re-lays of what the feature built ("19 joists"); this module
 * reads that for the tree's badges, the editor's "Update to x.y.0" and the
 * part's one "Update all". An update that changes no member is `quiet`: it
 * wears no badge, but Update all still takes it. One that re-lays is
 * `separate`: badged, offered on its feature alone, and left by Update all.
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
  /** What it moves of what the feature built ("19 joists"). */
  readonly relays: readonly string[];
  /** True when it re-lays: offered on its feature alone, not in Update all. */
  readonly separate: boolean;
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
    relays: update.relays ?? [],
    separate: update.separate,
  };
}

/**
 * Every feature of the tree whose update changes something, in tree order:
 * the badged rows, and what the strip counts. Quiet ones are left out here,
 * though Update all (which the server applies to every offered update but
 * a separate one) takes them along.
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

/** Whether Update all has anything to take: an offer that is not separate. */
export function updateAllTakesAny(
  features: readonly FeatureResponse[],
): boolean {
  return features.some((feature) => {
    const update = featureUpdate(feature);
    return update !== null && !update.separate;
  });
}

/** "3 pier footings and 3 post bases", or "" when it adds nothing. */
export function addsList(adds: readonly string[]): string {
  if (adds.length <= 1) return adds[0] ?? "";
  return `${adds.slice(0, -1).join(", ")} and ${adds[adds.length - 1]}`;
}

/**
 * The badge's words: "Update to 1.6.0: adds 11 ceiling joists", or for one
 * that re-lays what it built, "Update to 1.3.0 on its own: re-lays 19 joists
 * and 20 subfloor panels".
 */
export function updateBadgeTitle(update: FeatureUpdate): string {
  const label = updateToLabel(update.toVersion);
  const said: string[] = [];
  if (update.relays.length > 0) said.push(`re-lays ${addsList(update.relays)}`);
  if (update.adds.length > 0) said.push(`adds ${addsList(update.adds)}`);
  if (update.separate) return `${label} on its own: ${said.join("; ")}`;
  return said.length === 0
    ? `${label}: ${update.summary}`
    : `${label}: ${said.join("; ")}`;
}

/** The per-feature action's label: "Update to 1.5.0". */
export function updateToLabel(toVersion: string): string {
  return `Update to ${toVersion}`;
}

/**
 * The tree's summary of what is out of date: "7 Build features out of date",
 * and how many of them Update all leaves ("1 to update on its own").
 */
export function outOfDateSentence(count: number, separate = 0): string {
  const out =
    count === 1
      ? "1 Build feature out of date"
      : `${count} Build features out of date`;
  return separate > 0 ? `${out} · ${separate} to update on its own` : out;
}

/** The part's one action, named for what it does. */
export const UPDATE_ALL_LABEL = "Update all Build features";
