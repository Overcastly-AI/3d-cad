/**
 * Open profile ends — where the kernel will find a gap (helical-gear gap G8).
 *
 * The product test drew a gear-tooth gap whose arc ends missed the line and
 * spline ends by 0.285 um and 6.998 um. Nothing in the sketcher said so: the
 * sketch read "OK", and the loft failed later with PROFILE_NOT_CLOSED, naming
 * neither the section nor the gap. Finding it took a read-only API call.
 *
 * This module answers the kernel's question before the kernel asks it: which
 * curve ends does NO other curve end meet? The rules mirror how the geometry
 * service assembles a profile (`services/geometry/src/geometry/kernel/
 * extrude.py`, `build_profile_wires`), so the marks mean what the kernel will
 * do rather than what the pixels suggest:
 *
 *  - construction geometry and the sketch's own frame are not profile, so
 *    their ends are never reported;
 *  - wires chain at END POINTS only (`Wire.combine`), so an end that lands on
 *    another curve's interior (a T-junction) is still an open end;
 *  - an ARC is built from its centre, its START radius and the two end
 *    ANGLES, so its geometric end is the stored end projected onto the circle
 *    through its start. A stored end that "snapped" onto a line's end but is a
 *    few microns off that circle leaves a gap the stored coordinates hide,
 *    which is exactly the gear test's 0.285 um;
 *  - two ends join when they are within the kernel's wire tolerance.
 *
 * Pure: no three.js, no store.
 */
import { arcFrame, arcPointAt } from "./geometry";
import { isDatumId } from "./datum";
import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";

/**
 * The geometry service's profile wire tolerance, in mm: `PROFILE_WIRE_TOLERANCE`
 * in `services/geometry/src/geometry/kernel/extrude.py` (the kernel's linear
 * tolerance, 1e-7 m). Two ends closer than this chain; anything wider is a gap.
 */
export const PROFILE_JOIN_TOLERANCE_MM = 1e-4;

/**
 * An open end closer than this to its neighbour is a NEAR MISS: two ends meant
 * to join that did not, by less than any zoom anyone works at shows (a
 * hundredth of a millimetre is ~1 px at the gear test's 0.0183 mm/px). The
 * gear's two gaps, 0.285 um and 6.998 um, are both far inside it. A wider gap
 * is visible on its own and simply not joined yet.
 */
export const NEAR_MISS_MM = 0.01;

export interface OpenEnd {
  /** The entity whose end is open. */
  entity: string;
  /** Which end. */
  point: "start" | "end";
  /** Where the kernel will put that end (plane mm). */
  at: Point2D;
  /**
   * Distance to the nearest OTHER curve end, in mm, or null when the profile
   * has no other end at all. A tiny number is a near miss; a large one is an
   * end that was simply never joined.
   */
  gapMm: number | null;
}

interface CurveEnd {
  entity: string;
  point: "start" | "end";
  at: Point2D;
}

/** The two ends of a curve where the kernel will build them, or none. */
function curveEnds(entity: SketchEntity): CurveEnd[] {
  switch (entity.kind) {
    case "line":
      return [
        { entity: entity.id, point: "start", at: entity.start },
        { entity: entity.id, point: "end", at: entity.end },
      ];
    case "arc": {
      const frame = arcFrame(entity);
      return [
        { entity: entity.id, point: "start", at: entity.start },
        { entity: entity.id, point: "end", at: arcPointAt(frame, 1) },
      ];
    }
    case "spline": {
      const first = entity.points[0];
      const last = entity.points[entity.points.length - 1];
      if (first === undefined || last === undefined) return [];
      return [
        { entity: entity.id, point: "start", at: first },
        { entity: entity.id, point: "end", at: last },
      ];
    }
    case "circle":
    case "point":
      return [];
  }
}

/** Every profile curve end no other profile curve end meets. */
export function openEnds(entities: readonly SketchEntity[]): OpenEnd[] {
  const ends = entities
    .filter((entity) => !entity.construction && !isDatumId(entity.id))
    .flatMap(curveEnds);
  const open: OpenEnd[] = [];
  ends.forEach((end, index) => {
    let nearest: number | null = null;
    ends.forEach((other, otherIndex) => {
      if (otherIndex === index) return;
      const gap = Math.hypot(other.at.x - end.at.x, other.at.y - end.at.y);
      if (nearest === null || gap < nearest) nearest = gap;
    });
    if (nearest === null || nearest > PROFILE_JOIN_TOLERANCE_MM) {
      open.push({ ...end, gapMm: nearest });
    }
  });
  return open;
}

/**
 * The strip's reading of the open ends, or null when the profile has none:
 * the count, whether any is a near miss, and a sentence naming the narrowest
 * gap (the one to close first).
 */
export function describeOpenEnds(
  entities: readonly SketchEntity[],
): { label: string; title: string; nearMiss: boolean } | null {
  const open = openEnds(entities);
  if (open.length === 0) return null;
  const gaps = open.flatMap((end) => (end.gapMm === null ? [] : [end.gapMm]));
  const narrowest = gaps.length === 0 ? null : Math.min(...gaps);
  const nearMiss = narrowest !== null && narrowest < NEAR_MISS_MM;
  const label = `${open.length} open ${open.length === 1 ? "end" : "ends"}`;
  const title =
    narrowest === null
      ? "The profile has loose ends; an extrude or loft needs a closed loop."
      : nearMiss
        ? `Two ends miss each other by ${describeGapMm(narrowest)}, too small to see. Make them coincident to close the loop.`
        : `The narrowest gap between open ends is ${describeGapMm(narrowest)}.`;
  return { label, title, nearMiss };
}

/** A gap as the user reads it, in mm: "1.250 mm", or "0.00029 mm". */
export function describeGapMm(gapMm: number): string {
  if (gapMm >= 0.01) return `${gapMm.toFixed(3)} mm`;
  // Sub-hundredth gaps are the dangerous ones (invisible at any zoom anyone
  // works at), so they keep enough digits to be read as NOT zero.
  return `${gapMm.toPrecision(2)} mm`;
}
