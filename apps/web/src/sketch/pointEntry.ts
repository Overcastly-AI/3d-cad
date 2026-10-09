/**
 * Exact placement (helical-gear gap G2) — pure helpers, no store, no three.js.
 *
 * The gear test placed 24 involute fit points by reading the DRO at
 * 0.024 mm/px: there was no way to type where a point goes, and the grid step
 * was fixed at 1 mm. These answer the three questions the typed-coordinate
 * cells and the grid-step choice need: may a typed coordinate open now, and
 * for what; how does a named point move; and which grid steps to offer.
 */
import { MM_PER_UNIT, type LengthUnit } from "@loft/design";
import type { components } from "@loft/ts-client/gateway";

import { isDatumId } from "./datum";
import { namedPoints, type PointName, type SketchPick } from "./pick";
import { isProjected } from "./project";
import type { Point2D } from "./plane";
import { snapCandidates, type SnapCandidate } from "./snap";
import type { SketchEntity, SketchTool } from "./tools";

type EntityPointRef = components["schemas"]["EntityPointRef"];

/** What a typed coordinate would do, anchored where it opens. */
export interface PointEntryOpening {
  /** Where the cells hang, and the value an empty cell keeps (plane mm). */
  anchor: Point2D;
  /** The point it moves; null = it places the tool's next point. */
  target: EntityPointRef | null;
}

/** The tools whose every point is a POINT (not a size): typed at any step. */
const SEQUENCE_TOOLS: ReadonlySet<SketchTool> = new Set<SketchTool>([
  "line",
  "arc",
  "spline",
]);

/** The tools that place points at all. */
const PLACING_TOOLS: ReadonlySet<SketchTool> = new Set<SketchTool>([
  ...SEQUENCE_TOOLS,
  "rect",
  "circle",
]);

/**
 * May a typed coordinate open now, and for what?
 *
 *  - PLACING: a point-placing tool is live. Its first point always; the next
 *    point of a line, arc or spline too. A rectangle's or circle's second
 *    point is its SIZE, which the draw-time size cells own (FB-16), so it is
 *    not offered here.
 *  - MOVING: the Select tool holds exactly one point pick that is not the
 *    sketch's own frame nor projected geometry. The cells open on that point.
 *
 * Nothing opens while another typed value owns the keyboard (the size cells
 * of a shape drawn with the pointer, a dimension editor).
 */
export function pointEntryOpening(state: {
  tool: SketchTool;
  pending: readonly Point2D[];
  cursor: Point2D | null;
  selection: readonly SketchPick[];
  entities: readonly SketchEntity[];
  drawDimension: { typed: boolean } | null;
  dimensionEdit: unknown;
}): PointEntryOpening | null {
  // Size cells that take typing own the keys; a typed shape's cells do not
  // (TYPED-COORD-HIJACK): after a typed commit the next point is typed next.
  const sizing = state.drawDimension !== null && !state.drawDimension.typed;
  if (sizing || state.dimensionEdit !== null) return null;
  if (PLACING_TOOLS.has(state.tool)) {
    if (state.pending.length > 0 && !SEQUENCE_TOOLS.has(state.tool)) {
      return null;
    }
    const anchor = state.cursor ??
      state.pending[state.pending.length - 1] ?? { x: 0, y: 0 };
    return { anchor, target: null };
  }
  if (state.tool !== "select" || state.selection.length !== 1) return null;
  const pick = state.selection[0];
  if (pick === undefined || pick.kind !== "point") return null;
  if (isDatumId(pick.entity)) return null;
  const entity = state.entities.find((e) => e.id === pick.entity);
  if (entity === undefined) return null;
  // A projected point is the body's, not the user's: it cannot be moved
  // (SKETCH-PROJECT-EDGES). Break link first to make it free geometry.
  if (isProjected(entity)) return null;
  const at = namedPoints(entity).find((p) => p.point === pick.point)?.at;
  if (at === undefined) return null;
  return { anchor: at, target: { entity: pick.entity, point: pick.point } };
}

/** The value-opening keys other than `0`: a digit, a sign, a decimal point. */
const OPENS_ALWAYS = /^[1-9.-]$/;

/**
 * Does `key` open the typed coordinate `opening` offers?
 *
 * `0` opens one only when it PLACES a draw tool's point: an engineer types
 * "0 Tab 25" or "0.5" as readily as "12", and with a draw tool armed `0` is
 * no view key (see {@link zeroStartsAValue}). Moving a selected point is the
 * Select tool, where `0` stays Fit (F-11), as in Fusion; ".5" still opens.
 */
export function opensACoordinate(
  key: string,
  opening: PointEntryOpening,
): boolean {
  return OPENS_ALWAYS.test(key) || (key === "0" && opening.target === null);
}

/**
 * Is `0` a digit of a value right now, rather than the sketcher's Fit (F-11)?
 *
 * Yes whenever a value is being typed or is about to be: a draw tool is armed
 * (its next key may start a coordinate, `opensACoordinate`), the typed X / Y
 * cells are open, size cells that take typing are live (FLOW-A1), or a
 * dimension editor is open or still mounting (its first key must land).
 * Otherwise `0` is Fit, the same key as the part workspace's.
 */
export function zeroStartsAValue(state: {
  tool: SketchTool;
  pointEntry: unknown;
  drawDimension: { typed: boolean } | null;
  dimensionEdit: unknown;
}): boolean {
  if (state.pointEntry !== null || state.dimensionEdit !== null) return true;
  if (state.drawDimension !== null && !state.drawDimension.typed) return true;
  return PLACING_TOOLS.has(state.tool);
}

/**
 * A typed coordinate this close to a drawn point IS that point. Not a user
 * tolerance: it only absorbs a solved coordinate's last-digit noise (a corner
 * solved to 29.9999999997 that the user types as 30).
 */
export const TYPED_JOIN_MM = 1e-6;

/**
 * TYPED-POLYLINE-UNJOINED: the drawn point a typed coordinate lands on, as the
 * snap a click there would have taken, or null. The typed path places with
 * every snap held off (a typed value is never moved), so without this a line
 * whose end is typed onto another line's end shares the coordinate but not the
 * point, and the first dimension tears the profile open. Handing the placement
 * this candidate makes it bank the same anchor a snapped click banks, so the
 * one inference (`inferredCoincidents`) authors the coincident: Fusion and
 * SolidWorks join a typed point to the point it lands on.
 *
 * Only addressable points join (endpoints, centres, fit points and, given its
 * label, the plane's origin, which a click there grounds to as well); a
 * midpoint, an axis or an intersection has no address and joins nothing.
 */
export function typedJoin(
  entities: readonly SketchEntity[],
  at: Point2D,
  originLabel: string | null,
): SnapCandidate | null {
  const origin =
    originLabel === null ? null : { label: originLabel, gridStepMm: 0 };
  const hit = snapCandidates(entities, at, null, TYPED_JOIN_MM, origin).find(
    (candidate) => candidate.ref !== undefined,
  );
  return hit ?? null;
}

/**
 * The entity with its named point moved to `to`, or null when it has no such
 * point. A line keeps its other end, an arc its centre and other end (the
 * solver reconciles the radius), a spline its other fit points.
 */
export function withNamedPointAt(
  entity: SketchEntity,
  point: PointName,
  to: Point2D,
): SketchEntity | null {
  switch (entity.kind) {
    case "point":
      return point === "position" ? { ...entity, position: to } : null;
    case "line":
      if (point === "start") return { ...entity, start: to };
      if (point === "end") return { ...entity, end: to };
      return null;
    case "circle":
      return point === "center" ? { ...entity, center: to } : null;
    case "arc":
      if (point === "center") return { ...entity, center: to };
      if (point === "start") return { ...entity, start: to };
      if (point === "end") return { ...entity, end: to };
      return null;
    case "spline": {
      const match = /^fit(0|[1-9][0-9]*)$/.exec(point);
      const index = match === null ? -1 : Number(match[1]);
      if (index < 0 || index >= entity.points.length) return null;
      return {
        ...entity,
        points: entity.points.map((p, i) => (i === index ? to : p)),
      };
    }
  }
}

export interface GridStepOption {
  /** The step in canonical mm (the store's `snapStepMm`). */
  mm: number;
  /** As the user reads it, in the document's unit. */
  label: string;
}

/**
 * Round steps in each unit, finest first: metric in decades with the half
 * step engineers use, imperial in the fractions a rule is marked in.
 */
const STEPS_IN_UNIT: Readonly<Record<LengthUnit, readonly number[]>> = {
  mm: [0.01, 0.1, 0.5, 1, 5, 10],
  cm: [0.01, 0.1, 0.5, 1],
  m: [0.001, 0.01, 0.1],
  in: [0.001, 0.01, 0.0625, 0.1, 0.125, 0.25, 1],
  ft: [0.01, 0.1, 0.25, 1],
};

/** Up to 6 significant digits, trailing zeros trimmed: "0.5", "0.0625". */
const plain = (value: number): string => String(Number(value.toPrecision(6)));

/**
 * The grid steps offered in `unit`. The CURRENT step is always an option, so
 * the control can never claim a value the grid is not using: a step chosen in
 * another unit (or left at the 1 mm default in an inch document) is listed as
 * itself, in this unit.
 */
export function gridStepOptions(
  unit: LengthUnit,
  currentMm: number,
): GridStepOption[] {
  const perUnit = MM_PER_UNIT[unit];
  const options = STEPS_IN_UNIT[unit].map((step) => ({
    mm: step * perUnit,
    label: `${plain(step)} ${unit}`,
  }));
  const listed = options.some((o) => Math.abs(o.mm - currentMm) < 1e-9);
  if (!listed) {
    // Named to three significant figures: "0.0394 in", not "0.0393701 in".
    // The value underneath is still exactly the step in use. Six figures made
    // the longest label 14 characters, which spilled out of the DRO's fixed
    // GRID column over the canvas (review B1 on `e3bd6aa`).
    options.push({
      mm: currentMm,
      label: `${String(Number((currentMm / perUnit).toPrecision(3)))} ${unit}`,
    });
    options.sort((a, b) => a.mm - b.mm);
  }
  return options;
}
