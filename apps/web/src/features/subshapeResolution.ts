/**
 * WHEN A PICKED EDGE MOVED, AND THE FEATURE SHOULD SAY SO (EDGE-RESOLVE-WARN-1).
 *
 * The kernel re-finds every picked reference on each rebuild, in tiers, and
 * reports which tier fired (`FeatureResult.subshape_resolution`):
 *
 *   - `exact`: the edge is where it was picked. Certain.
 *   - `named`: it moved, and was re-found by its history-based name: "the
 *     edge between Extrude1's side from sketch line e2 and its side from e1"
 *     (DESIGN-INTENT-REFS). That is how Fusion and SolidWorks carry a pick
 *     through an edit, and the kernel only takes it when exactly one edge
 *     holds the name and no geometric tier contradicts it. This surface says
 *     nothing.
 *   - `durable`: it moved along its own line, or a face kept its plane. This
 *     fires ROUTINELY on correct rebuilds. Two tree goldens report it with no
 *     edit at all (a second hole on a face the first one already changed), so
 *     it can fire on a fresh create. topological-naming.md §15 recommends
 *     against warning on it, and this surface says nothing.
 *   - `adjacent`: the edge left its line, and was re-found as the edge its two
 *     stored neighbouring faces share. That tier inherits the face matcher's
 *     whole silent-retarget surface (§14): it can land on the WRONG edge
 *     without an error. It is the one that gets a notice.
 *
 * Adjacent is edge-only, so the notice speaks of edges. It never fires on a
 * fresh create: a pick made on the body it is resolved against matches
 * exactly (asserted end to end in `edge-resolve-warn.spec.ts`).
 */
import type { FeatureResponse, FeatureResult } from "../api/parts";

export interface MovedEdgeWarning {
  /** Picked edges the kernel re-found by adjacency. */
  readonly moved: number;
  /** Every picked reference the feature resolved. */
  readonly total: number;
  /** The notice's sentence: what happened, then what to do. */
  readonly sentence: string;
  /**
   * What a dismissal is remembered against: this feature, the resolution it
   * reported, and the state of every feature BEFORE it. A downstream edit does
   * not change what this feature was built on, so it keeps the dismissal; an
   * upstream edit is a new re-match, so it brings the notice back.
   */
  readonly key: string;
}

/** The notice's stamp: two words, tracked caps (the `Notice` lead). */
export const MOVED_EDGE_LABEL = "Edge moved";

/** The re-pick action, one name wherever it is offered. */
export const REPICK_EDGES_ACTION = "Re-pick edges";

/**
 * The warning for `feature`, or null when there is nothing to say: no result,
 * a failed build (its error already speaks), no picked reference, or a worst
 * tier better than adjacent.
 */
export function movedEdgeWarning(
  feature: FeatureResponse,
  features: readonly FeatureResponse[],
  result: FeatureResult | undefined,
): MovedEdgeWarning | null {
  const summary = result?.subshape_resolution;
  if (result?.status !== "ok" || summary === null || summary === undefined) {
    return null;
  }
  if (summary.worst_tier !== "adjacent" || summary.adjacent === 0) return null;
  const moved = summary.adjacent;
  const total =
    summary.exact + summary.named + summary.durable + summary.adjacent;
  const one = moved === 1;
  const sentence =
    `${moved} of ${total} picked edges moved in an earlier edit and ` +
    `${one ? "was" : "were"} re-found by ${one ? "its" : "their"} ` +
    `neighbouring faces. Check ${feature.name} is on the ` +
    `${one ? "edge" : "edges"} you meant, or re-pick ${one ? "it" : "them"}.`;
  const at = features.findIndex((f) => f.id === feature.id);
  const upstream = features
    .slice(0, at < 0 ? features.length : at)
    .map((f) => `${f.id}@${f.updated_at}`)
    .join(",");
  const key = [
    feature.id,
    feature.updated_at,
    `${summary.exact}/${summary.named}/${summary.durable}/${summary.adjacent}`,
    upstream,
  ].join("|");
  return { moved, total, sentence, key };
}

/**
 * WHEN A PROJECTED EDGE IS GONE (SKETCH-PROJECT-EDGES).
 *
 * A sketch entity projected from a body edge re-finds that edge on every
 * rebuild. When it cannot (the edge was cut away, the shell was closed), the
 * entity is SICK, as Fusion calls it: the sketch keeps its last position and
 * still builds, so its row reads OK and nothing downstream fails. That is the
 * right behaviour and also a silent one, so the row says it.
 */
export interface ProjectionWarning {
  /** Projected entities whose edge no longer resolves. */
  readonly sick: number;
  /** Every projected entity in the sketch. */
  readonly total: number;
  /** The notice's sentence: what happened, then what it means. */
  readonly sentence: string;
  /** What a dismissal is remembered against (this feature, as it is now). */
  readonly key: string;
}

/** The notice's stamp. */
export const PROJECTION_LOST_LABEL = "Projection lost";

/**
 * The warning for a sketch `result`, or null: not a solved sketch, nothing
 * projected, or every projection followed its edge.
 */
export function projectionWarning(
  feature: FeatureResponse,
  result: FeatureResult | undefined,
): ProjectionWarning | null {
  if (result?.status !== "ok" || result.data?.kind !== "solved_sketch") {
    return null;
  }
  const statuses = result.data.projections ?? [];
  const sick = statuses.filter((status) => status.state === "sick");
  if (sick.length === 0) return null;
  const one = sick.length === 1;
  const sentence =
    `${sick.length} projected ${one ? "edge no longer exists" : "edges no longer exist"}; ` +
    `the sketch keeps ${one ? "its" : "their"} last position.`;
  const key = [
    "projection",
    feature.id,
    feature.updated_at,
    sick.map((status) => `${status.entity}:${status.reason ?? ""}`).join(","),
  ].join("|");
  return { sick: sick.length, total: statuses.length, sentence, key };
}
