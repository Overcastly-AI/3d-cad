/**
 * Dimension PLACEMENT — the pure math + ghost geometry behind the sheet's
 * place-as-you-author stage (REACH-3).
 *
 * `DimensionPlacement.offset_mm` / `text_pos` have been in the contract, and
 * fully honoured by the composer, since drawings v1 — and the app has never sent
 * either, so every dimension a user could author landed wherever the auto engine
 * put it. Nudging one afterwards was not merely awkward, it was impossible. This
 * module is the client half of that field: it turns a pointer on the paper into
 * the SAME signed offset the composer will read back, and draws the ghost that
 * shows where the dimension is about to land.
 *
 * Two facts make it exact rather than approximate:
 *
 *  - **The sheet is 1:1 with the composer's placement space.** `view_transform`
 *    (compose.py) is a translation plus ONE y-flip — an isometry — so a
 *    millimetre measured on the composed sheet IS a millimetre of `offset_mm`.
 *    No scale factor, no round trip through the projection.
 *  - **The outward normal is reproducible.** `_place_linear_between` measures a
 *    positive offset along `away`, the edge normal pointing away from the view
 *    centre; {@link awayNormal} reconstructs that same vector from composed
 *    coordinates (see its note on the y-flip and the degenerate tie).
 *
 * Everything here is pure and unit-tested: no React, no DOM, no fetch. The sheet
 * renders {@link PlacementGhost} verbatim, exactly as it renders a composed
 * dimension verbatim.
 */
import { drawing } from "@loft/design";

import type { Point2D } from "./layout";

// --- small vector helpers (mirroring compose.py's, in sheet-SVG space) -----
const sub = (a: Point2D, b: Point2D): Point2D => ({
  x: a.x - b.x,
  y: a.y - b.y,
});
const add = (a: Point2D, b: Point2D): Point2D => ({
  x: a.x + b.x,
  y: a.y + b.y,
});
const mul = (a: Point2D, k: number): Point2D => ({ x: a.x * k, y: a.y * k });
const neg = (a: Point2D): Point2D => ({ x: -a.x, y: -a.y });
const dot = (a: Point2D, b: Point2D): number => a.x * b.x + a.y * b.y;
const hyp = (a: Point2D): number => Math.hypot(a.x, a.y);
const mid = (a: Point2D, b: Point2D): Point2D => mul(add(a, b), 0.5);

/** Unit vector, or null for a degenerate (zero-length) span. */
function unit(a: Point2D): Point2D | null {
  const len = hyp(a);
  return len < 1e-9 ? null : { x: a.x / len, y: a.y / len };
}

/**
 * The composer's canonical outward normal for the span `a`→`b`, in FINAL
 * sheet-SVG space (mm, y-DOWN).
 *
 * `_place_linear_between` works in PROJECTED space (y-UP) and starts from
 * `n0 = (-dy, dx)`, keeping it when it points away from the view centre and
 * negating it otherwise. The single view transform between the two spaces is a
 * y-flip, which maps a direction `(u, v)` to `(u, -v)`: a REFLECTION, so lengths
 * and dot products survive but handedness does not. The image of the projected
 * `n0` is therefore `(d.y, -d.x)` of the FLIPPED direction — the negative of the
 * perpendicular you would take naively on this side.
 *
 * That sign only shows in the degenerate tie (an edge whose midpoint sits
 * exactly on the view centre, where compose.py's `>= 0` keeps `n0`); taking the
 * mirrored vector rather than the naive perpendicular keeps the client and the
 * server on the same side even there. Null for a zero-length span.
 */
export function awayNormal(
  a: Point2D,
  b: Point2D,
  viewAnchor: Point2D,
): Point2D | null {
  const d = unit(sub(b, a));
  if (d === null) return null;
  const n0 = { x: d.y, y: -d.x };
  return dot(n0, sub(mid(a, b), viewAnchor)) >= 0 ? n0 : neg(n0);
}

/**
 * The signed `offset_mm` that puts the dimension line under `pointer` — the
 * perpendicular distance from the span's midpoint, positive on the `away` side.
 * 0 for a degenerate span (which the composer reads as "auto-place me").
 */
export function offsetAt(
  a: Point2D,
  b: Point2D,
  viewAnchor: Point2D,
  pointer: Point2D,
): number {
  const away = awayNormal(a, b, viewAnchor);
  if (away === null) return 0;
  return dot(sub(pointer, mid(a, b)), away);
}

/**
 * The foot of the perpendicular from `p` onto the infinite line `a`–`b` — the
 * across-the-wall span an `edge_to_edge` dimension is drawn on (compose.py
 * `_perpendicular_foot`). Null when `a`–`b` is degenerate.
 */
export function perpendicularFoot(
  p: Point2D,
  a: Point2D,
  b: Point2D,
): Point2D | null {
  const d = sub(b, a);
  const len2 = dot(d, d);
  if (len2 < 1e-18) return null;
  return add(a, mul(d, dot(sub(p, a), d) / len2));
}

// --- what a PLACE stage is authoring --------------------------------------

/**
 * What the PLACE stage is authoring.
 *
 * `offset` — a LINEAR dimension, whose `offset_mm` the composer applies to the
 * whole annotation (line, witness lines, arrows and text move together).
 * `text` — every other type, where `offset_mm` is inapplicable in v1 and the
 * authored `text_pos` moves the value stamp (the composer's own division of
 * labour; see `build_dimension_annotation`).
 */
export type PlaceTarget =
  | {
      mode: "offset";
      /** The span the dimension is drawn on, in composed sheet mm. */
      span: { a: Point2D; b: Point2D };
      viewAnchor: Point2D;
      /** The live signed offset (mm) — what `offset_mm` will carry. */
      offsetMm: number;
    }
  | {
      mode: "text";
      /** Where the leader starts (the measured feature), composed sheet mm. */
      leaderFrom: Point2D;
      /** The live text seat (mm, sheet-SVG space) — what `text_pos` will carry. */
      textPos: Point2D;
    };

// --- the ghost the sheet draws while you place ----------------------------

/** One ghost rule. `rule` is the live offset tick — the placing signature. */
export interface GhostLine {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  role: "extension" | "dimension" | "rule" | "leader";
}

/** A ghost arrowhead triangle (sheet mm), drawn as an SVG polygon. */
export interface GhostArrow {
  points: readonly Point2D[];
}

/** Everything the sheet draws for an in-progress placement. */
export interface PlacementGhost {
  lines: readonly GhostLine[];
  arrows: readonly GhostArrow[];
  /** A crosshair marking the text seat (text mode only). */
  target: Point2D | null;
}

/** An arrowhead triangle: tip at `tip`, barb pointing `direction`. */
function arrow(tip: Point2D, direction: Point2D): GhostArrow {
  const base = sub(tip, mul(direction, drawing.arrowLengthMm));
  const wing = mul(
    { x: -direction.y, y: direction.x },
    drawing.arrowHalfWidthMm,
  );
  return { points: [tip, add(base, wing), sub(base, wing)] };
}

const line = (a: Point2D, b: Point2D, role: GhostLine["role"]): GhostLine => ({
  x1: a.x,
  y1: a.y,
  x2: b.x,
  y2: b.y,
  role,
});

/**
 * The drafting annotation a linear dimension WILL have at `offsetMm` — the same
 * construction `_place_linear_between`'s `place()` emits (witness lines gapped
 * off the geometry and overrunning the dimension line, arrowheads turned in),
 * so what you drag is what the composer draws back.
 *
 * The extra `rule` line — a tick from the measured midpoint out to the dimension
 * line — belongs to the GHOST only. It is the draughtsman's rule laid on the
 * paper: the one mark that says you are still setting this distance, so a ghost
 * can never be mistaken for a placed dimension.
 */
export function linearGhost(
  a: Point2D,
  b: Point2D,
  viewAnchor: Point2D,
  offsetMm: number,
): PlacementGhost | null {
  const d = unit(sub(b, a));
  const away = awayNormal(a, b, viewAnchor);
  if (d === null || away === null) return null;
  const n = offsetMm >= 0 ? away : neg(away);
  const o = Math.abs(offsetMm);
  const dimA = add(a, mul(n, o));
  const dimB = add(b, mul(n, o));
  const over = o + drawing.extensionOverrunMm;
  return {
    lines: [
      line(
        add(a, mul(n, drawing.dimensionGapMm)),
        add(a, mul(n, over)),
        "extension",
      ),
      line(
        add(b, mul(n, drawing.dimensionGapMm)),
        add(b, mul(n, over)),
        "extension",
      ),
      line(dimA, dimB, "dimension"),
      line(mid(a, b), mid(dimA, dimB), "rule"),
    ],
    arrows: [arrow(dimA, neg(d)), arrow(dimB, d)],
    target: null,
  };
}

/**
 * The ghost for a text-position placement (diameter / radius / angular, whose
 * `offset_mm` the composer does not apply — only `text_pos`): a leader from the
 * measured feature out to a crosshair at the seat the text will take.
 */
export function textGhost(
  leaderFrom: Point2D,
  textPos: Point2D,
): PlacementGhost {
  return {
    lines: [line(leaderFrom, textPos, "leader")],
    arrows: [],
    target: textPos,
  };
}

/** Half-width (mm) of the ghost text crosshair — sized to the value stamp. */
export const GHOST_TARGET_MM = drawing.dimensionTextMm * 0.7;

/** The ghost for a live {@link PlaceTarget} — what the sheet draws, verbatim. */
export function ghostFor(target: PlaceTarget): PlacementGhost | null {
  return target.mode === "offset"
    ? linearGhost(
        target.span.a,
        target.span.b,
        target.viewAnchor,
        target.offsetMm,
      )
    : textGhost(target.leaderFrom, target.textPos);
}
