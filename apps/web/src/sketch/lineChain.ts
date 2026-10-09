/**
 * LINE-CHAIN: the Line tool chains, as Fusion's and SolidWorks' do. Pure
 * helpers, no store, no three.js; the store's `placeAt` and
 * `commitDrawDimensions` call them.
 *
 * Each click ends one segment and starts the next at that end, so the hub's
 * 12-segment section is 13 clicks rather than 24. The joint is a coincident,
 * and it is authored by the ONE snap inference (`inferredCoincidents`): the
 * segment just drawn hands its `end` on as the next segment's snap anchor, so
 * the next segment's start is bound to it exactly as a click snapped onto that
 * end would be. Clicking the chain's first point closes the loop (the click
 * snaps onto that start, and the same inference joins it) and ends the chain
 * with the tool still armed. Escape ends an open chain the same way, through
 * the existing cancel-placement rung; a second Escape drops the tool.
 *
 * A DRAG-drawn line does not chain (SolidWorks' click-drag mode draws one
 * line): the press-drag-release gesture is a single segment, so the next drag
 * starts a fresh line rather than being joined to the last one.
 */
import type { Point2D } from "./plane";
import type { SnapAnchor } from "./snap";
import type { PlacementResult, SketchEntity, SketchTool } from "./tools";

/** Same tolerance as the placement's own degenerate test: the same point. */
const SAME_POINT_MM = 1e-9;

const samePoint = (a: Point2D, b: Point2D): boolean =>
  Math.hypot(a.x - b.x, a.y - b.y) < SAME_POINT_MM;

/** The placement sequence after a click, and the chain it belongs to. */
export interface ChainStep {
  pending: Point2D[];
  snapAnchors: SnapAnchor[];
  /** The first point of the live line chain; null when none is open. */
  chainStart: Point2D | null;
}

/** The anchor that joins the next chained segment's start to `line`'s end. */
const jointAnchor = (line: SketchEntity): SnapAnchor[] =>
  line.kind === "line"
    ? [{ at: line.end, ref: { entity: line.id, point: "end" } }]
    : [];

/**
 * Where the sequence goes after `placePoint` answered `result` for a click.
 * `anchors` are the snaps spent so far INCLUDING this click's; `chain` is false
 * for the release of a drag, which draws one segment and stops.
 */
export function chainStep(
  tool: SketchTool,
  before: readonly Point2D[],
  result: PlacementResult,
  anchors: SnapAnchor[],
  chainStart: Point2D | null,
  chain = true,
): ChainStep {
  const line = result.entities[0];
  if (line === undefined) {
    // Mid-sequence: a line's first click opens a chain at that point.
    const opened = tool === "line" && before.length === 0;
    return {
      pending: result.pending,
      snapAnchors: anchors,
      chainStart: opened ? (result.pending[0] ?? null) : chainStart,
    };
  }
  if (tool !== "line" || line.kind !== "line" || !chain) {
    return { pending: result.pending, snapAnchors: [], chainStart: null };
  }
  if (chainStart !== null && samePoint(line.end, chainStart)) {
    // The loop is closed: the chain ends, the tool stays armed.
    return { pending: [], snapAnchors: [], chainStart: null };
  }
  return {
    pending: [line.end],
    snapAnchors: jointAnchor(line),
    chainStart,
  };
}

/**
 * A typed length moved the just-drawn segment's end (FB-16 size cells). An
 * open chain continues from where that end is NOW, so the next segment still
 * starts on it and its joint still binds. Null when no chain hangs off it.
 */
export function chainAfterResize(
  tool: SketchTool,
  pending: readonly Point2D[],
  draft: { ids: readonly string[]; to: Point2D },
  entities: readonly SketchEntity[],
): Pick<ChainStep, "pending" | "snapAnchors"> | null {
  const [from] = pending;
  const { ids, to } = draft;
  if (tool !== "line" || pending.length !== 1 || ids.length !== 1) return null;
  if (from === undefined || !samePoint(from, to)) return null;
  const line = entities.find((entity) => entity.id === ids[0]);
  if (line === undefined || line.kind !== "line") return null;
  return { pending: [line.end], snapAnchors: jointAnchor(line) };
}
