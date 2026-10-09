/**
 * PROJECT BODY EDGES INTO THE SKETCH (SKETCH-PROJECT-EDGES, the web half).
 *
 * Fusion 360's Project and SolidWorks' Convert Entities: a body edge picked
 * while sketching becomes a sketch entity LINKED to that edge. The entity is
 * fixed (the solver holds it, 0 DOF), drawn in its own purple ink, and on every
 * rebuild the kernel re-finds the edge and re-projects it, so a lip sketched on
 * a rim follows the rim when the base is widened. When the edge no longer
 * resolves the entity goes SICK: it keeps its last good position and says why.
 *
 * Pure functions, no store and no three.js (a picked overlay edge becomes an
 * entity in `projectEdge.ts`, kept apart so the constraint layer, which the
 * shortcut registry loads in Node, never pulls in the plane geometry):
 *
 *  - {@link isProjected} / {@link projectedRefusal} / {@link allProjected}: the
 *    constraint gate's questions.
 *  - {@link breakLinks}: Fusion's Break Link — the geometry stays, the link
 *    goes, and the entity is ordinary free geometry from then on.
 */
import type { components } from "@loft/ts-client/gateway";

import type { EdgeSignature } from "../api/parts";
import { isDatumId } from "./datum";
import type { SketchPick } from "./pick";
import type { SketchEntity } from "./tools";

export type SketchProjection = components["schemas"]["SketchProjection"];
export type SketchProjectionStatus =
  components["schemas"]["SketchProjectionStatus"];
export type ProjectionSickReason = NonNullable<
  SketchProjectionStatus["reason"]
>;

/** Does this entity follow a body edge? */
export function isProjected(entity: SketchEntity | undefined): boolean {
  return (
    entity !== undefined &&
    "projection" in entity &&
    entity.projection !== null &&
    entity.projection !== undefined
  );
}

/** The ids of every projected entity in `entities`. */
export function projectedIds(entities: readonly SketchEntity[]): Set<string> {
  return new Set(entities.filter(isProjected).map((e) => e.id));
}

/** The picked edge's identity, as a projection stores it. */
export function projectionOf(
  entity: SketchEntity | undefined,
): SketchProjection | null {
  if (entity === undefined || !("projection" in entity)) return null;
  return entity.projection ?? null;
}

/**
 * Every picked signature already projected into this sketch — what the edge
 * overlay lights as "picked", so an edge you have brought in reads as taken.
 */
export function projectedSignatures(
  entities: readonly SketchEntity[],
): EdgeSignature[] {
  return entities.flatMap((entity) => {
    const projection = projectionOf(entity);
    return projection === null ? [] : [projection.edge.selector.signature];
  });
}

/** A sentence for each sick reason — the hazard's tooltip, in plain words. */
export const SICK_REASON_TEXT: Readonly<Record<ProjectionSickReason, string>> =
  {
    unresolved:
      "Its body edge no longer exists. It keeps its last position; Break link to edit it.",
    ambiguous:
      "More than one body edge matches the one it was projected from. It keeps its last position.",
    no_body:
      "There is no body before this sketch to project from. It keeps its last position.",
    unsupported_curve:
      "Its edge is no longer a line or a circle seen face-on. It keeps its last position.",
    degenerate: "Its edge now projects to a point. It keeps its last position.",
    kind_changed:
      "Its edge changed kind (a line became an arc, or the reverse). It keeps its last position.",
  };

/** The sick statuses of the last solve, by entity id. */
export function sickProjections(
  statuses: readonly SketchProjectionStatus[],
): Map<string, ProjectionSickReason> {
  const sick = new Map<string, ProjectionSickReason>();
  for (const status of statuses) {
    if (status.state === "sick") {
      sick.set(status.entity, status.reason ?? "unresolved");
    }
  }
  return sick;
}

// ---------------------------------------------------------------------------
// The constraint gate
// ---------------------------------------------------------------------------

/** The entity a pick addresses (a point names its owning entity). */
const pickEntity = (pick: SketchPick): string =>
  pick.kind === "entity" ? pick.id : pick.entity;

/** Does any pick address projected geometry? */
export function selectionTouchesProjected(
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
): boolean {
  const ids = projectedIds(entities);
  return selection.some((pick) => ids.has(pickEntity(pick)));
}

/**
 * Is every subject FIXED (projected, or the sketch frame) with at least one of
 * them projected? Then a relation between them is already decided by the body:
 * a dimension can only measure it (driven), and a geometric constraint can only
 * be redundant with the fixes.
 */
export function allProjected(
  ids: readonly string[],
  entities: readonly SketchEntity[],
): boolean {
  const projected = projectedIds(entities);
  return (
    ids.length > 0 &&
    ids.some((id) => projected.has(id)) &&
    ids.every((id) => projected.has(id) || isDatumId(id))
  );
}

/** The hint every refused verb on projected geometry answers with. */
export const PROJECTED_SUBJECT_HINT =
  "Projected geometry follows the body and is fixed. Constrain or dimension other geometry TO it, or Break link to edit it.";

/** Verbs whose subject must be free geometry — refused outright on a projected one. */
const PROJECTED_SUBJECT_REFUSED = new Set(["horizontal", "vertical", "fixed"]);

/** Dimension verbs: on all-projected geometry they are created driven, not refused. */
const DIMENSION_VERBS = new Set(["distance", "radius", "diameter", "angle"]);

/**
 * The projected half of the subject gate, or null when the verb may go on.
 * `action` is one of DATUM_SUBJECT_REFUSED's verbs or any other: H / V / Fixed
 * on projected geometry are refused (it is already fixed, by the body); any
 * other non-dimension verb is refused only when EVERY subject is fixed (two
 * projected points made coincident is redundant with both fixes).
 */
export function projectedRefusal(
  action: string,
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
): string | null {
  if (!selectionTouchesProjected(selection, entities)) return null;
  if (PROJECTED_SUBJECT_REFUSED.has(action)) return PROJECTED_SUBJECT_HINT;
  if (DIMENSION_VERBS.has(action)) return null;
  const ids = [...new Set(selection.map(pickEntity))];
  return ids.length > 1 && allProjected(ids, entities)
    ? PROJECTED_SUBJECT_HINT
    : null;
}

// ---------------------------------------------------------------------------
// Break link
// ---------------------------------------------------------------------------

/**
 * Drop the link from every selected projected entity, keeping its geometry
 * where it is. Null when nothing selected is projected (nothing to break).
 */
export function breakLinks(
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
): { entities: SketchEntity[]; broken: number } | null {
  const targets = new Set(selection.map(pickEntity));
  let broken = 0;
  const next = entities.map((entity) => {
    if (!targets.has(entity.id) || !isProjected(entity)) return entity;
    broken += 1;
    // Absent, not null: an unlinked entity dumps byte-identically to one that
    // was never projected.
    const free: Record<string, unknown> = { ...entity };
    delete free["projection"];
    return free as SketchEntity;
  });
  return broken === 0 ? null : { entities: next, broken };
}
