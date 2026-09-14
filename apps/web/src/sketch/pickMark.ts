/**
 * WHAT THE NEXT CLICK WILL SELECT, said out loud — the resolution behind the
 * select tool's cursor mark (SEL-2, `docs/design/pre-selection.md` §2).
 *
 * Picking already resolved a winner (`pick.ts`) and the viewport already lit it;
 * what was missing is the WORD. The founder's report was a sketch line that
 * "wouldn't even select" — the line under the cursor was very often not the
 * candidate the click was going to take, and nothing on screen said which one
 * was. So this module answers three questions about a resolved pick, and only
 * those: which mark to draw, what to call it, and where it stands.
 *
 * Pure — no store, no three.js — so the mapping is unit-testable without a
 * browser, and so the viewport cannot quietly grow a second opinion about it.
 *
 * ## Why the vocabulary is the DRAWING vocabulary
 *
 * Placement already names its candidates (`snap.ts`'s `SNAP_MARKS` /
 * `SNAP_LABELS`, UI-W5): endpoint square, centre mark, the frame's own origin
 * and axes. Selection addresses the SAME points, so it borrows the same marks
 * rather than inventing a dialect for the same objects — a user who learned the
 * square while drawing does not re-learn it while selecting. Exactly one case is
 * new, because placement has no equivalent for it: landing ON a curve between
 * its defining points, which gets the drafting pick tick (`SnapOnCurveIcon`).
 */
import {
  DATUM_LABELS,
  datumOf,
  type DatumFrame,
  type DatumKind,
  withDatums,
} from "./datum";
import { pickAnchor, type SketchPick } from "./pick";
import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";

/**
 * Which mark a pick draws. The three geometry kinds plus the frame's three,
 * which are the keys `SNAP_MARKS` already indexes — one glyph table, two tools.
 */
export type PickMarkKind = "endpoint" | "center" | "on-curve" | DatumKind;

export interface PickMark {
  kind: PickMarkKind;
  /** The word the mark carries. */
  label: string;
  /** Where the mark stands, in plane mm. */
  at: Point2D;
}

/**
 * The word for an entity pick: the entity's OWN kind, not a generic "Curve".
 * `entity.kind` is already known at zero extra cost, and "Circle" tells the user
 * something "Curve" does not — which of two overlapping things the click took.
 */
const ENTITY_LABELS: Record<SketchEntity["kind"], string> = {
  point: "Point",
  line: "Line",
  circle: "Circle",
  arc: "Arc",
  spline: "Spline",
};

/**
 * The word for a point pick, by the point's NAME — the same classes the snap
 * vocabulary uses, so the two tools agree about what a corner is called.
 *
 * A spline's `fitN` is an endpoint-class vertex (it is a defining point of the
 * curve, and picks/constrains through the identical path), but it gets its own
 * word because "Endpoint" on a fit point in the middle of a spline would be
 * false; the design spec (§2) makes the same split.
 */
function pointLabel(point: string): string {
  switch (point) {
    case "start":
    case "end":
      return "Endpoint";
    case "center":
      return "Centre";
    case "position":
      return "Point";
    default:
      return /^fit\d+$/.test(point) ? "Fit point" : "Point";
  }
}

/** Centre marks get the centre glyph; every other defining point is a vertex. */
function pointMarkKind(point: string): PickMarkKind {
  return point === "center" ? "center" : "endpoint";
}

/**
 * The mark for one resolved pick, or null when the pick does not resolve against
 * the given entities (a hover that outlived an undo). Null draws nothing —
 * a mark standing at the plane origin naming a deleted line would be worse than
 * silence, which is the whole failure this feature exists to end.
 *
 * `at` is the raw cursor point: an entity pick's mark stands at the spot on the
 * curve nearest it, which is where the hit was measured, so the mark cannot
 * drift off the ink it is naming.
 */
export function pickMark(
  pick: SketchPick,
  entities: readonly SketchEntity[],
  at: Point2D,
  frame: DatumFrame,
): PickMark | null {
  // The frame is pickable whether or not it has been materialised into the
  // buffer (`datum.ts`), so it has to be present here for the anchor to resolve
  // — otherwise hovering the origin, the one thing a user aims at on an EMPTY
  // sketch, would be the one pick that says nothing.
  const datum = datumOf(pick);
  const anchor = pickAnchor(
    pick,
    datum === null ? entities : withDatums(entities, frame),
    at,
  );
  if (anchor === null) return null;
  if (datum !== null) {
    // The frame's members are not geometry the user drew: the origin is not a
    // "Point" and an axis is not a "Line". They carry their own names, the ones
    // the DRO and the snap mark already use.
    return { kind: datum, label: DATUM_LABELS[datum], at: anchor };
  }
  if (pick.kind === "point") {
    return {
      kind: pointMarkKind(pick.point),
      label: pointLabel(pick.point),
      at: anchor,
    };
  }
  const entity = entities.find((candidate) => candidate.id === pick.id);
  if (entity === undefined) return null;
  return { kind: "on-curve", label: ENTITY_LABELS[entity.kind], at: anchor };
}
