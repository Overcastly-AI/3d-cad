/**
 * The sketch POINT entity (Fusion's, SolidWorks' and Onshape's Point) — pure
 * helpers, no three.js, no store.
 *
 * A point is the one entity with no curve: every other ink layer draws
 * polylines, so without these a placed point would only be a vertex dot that
 * looks like any line's endpoint, and in a SOLVED sketch (curves only) it would
 * not be drawn at all. These answer the two questions the rest of the app asks
 * about points as ENTITIES: where to draw their station marks, and whether a
 * whole sketch is nothing but one point (a loft apex).
 */
import type { components } from "@loft/ts-client/gateway";

import { isDatumId } from "./datum";
import { planeToWorld, type PlaneBasis, type Point2D } from "./plane";
import type { SketchEntity } from "./tools";

type SketchParams = components["schemas"]["SketchParamsV1"];

/**
 * The drawn point entities, split as their ink is (profile vs construction).
 * The sketch's own origin is a point entity once materialised, but it is the
 * frame's mark (`SketchOrigin` draws it), not a station the user placed.
 */
export function pointEntityStations(entities: readonly SketchEntity[]): {
  profile: Point2D[];
  construction: Point2D[];
} {
  const profile: Point2D[] = [];
  const construction: Point2D[] = [];
  for (const entity of entities) {
    if (entity.kind !== "point" || isDatumId(entity.id)) continue;
    (entity.construction ? construction : profile).push(entity.position);
  }
  return { profile, construction };
}

/** Plane points → a flat world-space positions buffer (3 floats each). */
export function stationPositions(
  points: readonly Point2D[],
  basis: PlaneBasis,
): Float32Array {
  const positions = new Float32Array(points.length * 3);
  points.forEach((point, i) => {
    positions.set(planeToWorld(basis, point), i * 3);
  });
  return positions;
}

/**
 * True when a sketch's only profile entity is one point: the loft apex the
 * kernel reads as a single vertex section. The SAME rule as
 * `build_loft_section` (services/geometry kernel/loft.py): construction
 * geometry (the materialised sketch frame included) is ignored, and what is
 * left must be exactly one point.
 */
export function isApexSketch(params: Pick<SketchParams, "entities">): boolean {
  const profile = params.entities.filter((entity) => !entity.construction);
  return profile.length === 1 && profile[0]?.kind === "point";
}
