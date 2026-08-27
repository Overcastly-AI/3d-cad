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

/**
 * The live reading, ON THE PAPER, beside the rule that is setting it.
 *
 * The number used to live only in the pick-hint chip at the foot of the window
 * — measured at 1280x800, the ghost sat at y≈378 and the number at y=750, so
 * you could not watch the paper and read the value at the same time, and the
 * ghost itself carried **no text at all**: four `<line>`s and zero `<text>`.
 * That is the difference between "a form moved earlier" and direct
 * manipulation; every tool this one is benchmarked against (Fusion,
 * SolidWorks, Plasticity) puts the live figure at the cursor for exactly this
 * reason (frontend-QA 2026-08-27, P1-C).
 *
 * It is the SIGNED offset, printed to the same two decimals the field shows and
 * the server stores — one number with one meaning, in the two places the eye
 * uses. Deliberately absent from a TEXT placement: `text_pos` is a point, not a
 * scalar, and a coordinate pair floated beside a crosshair would be decoration
 * rather than a reading (mandate 3a: chrome that only decorates is a defect).
 */
export interface GhostFigure {
  /** Where the figure is seated (sheet mm) — its centre. */
  at: Point2D;
  /** The reading, formatted. */
  text: string;
}

/** Everything the sheet draws for an in-progress placement. */
export interface PlacementGhost {
  lines: readonly GhostLine[];
  arrows: readonly GhostArrow[];
  /** A crosshair marking the text seat (text mode only). */
  target: Point2D | null;
  /** The live reading beside the rule, or null when there is no scalar to read. */
  figure: GhostFigure | null;
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
    // Seated just BEYOND the dimension line, on the outer end of the rule: the
    // eye is already there (it is watching the line move), and it is the one
    // place on the paper that cannot collide with the geometry being measured
    // or with the value stamp the committed dimension will take.
    figure: {
      at: add(mid(dimA, dimB), mul(n, FIGURE_STANDOFF_MM)),
      text: formatOffset(offsetMm),
    },
  };
}

/**
 * Height (sheet mm) of the ghost's reading — deliberately a third LARGER than
 * the value stamp a placed dimension gets.
 *
 * A printed dimension obeys the print's type scale; this is not print, it is an
 * instrument reading you have to be able to take at a glance mid-drag, and at
 * the stamp's own 3.2 mm it lands near 9 px on an A4 sheet at 1280. Being
 * visibly bigger than drafting ink is also the second cue (after the blueprint
 * blue) that what you are looking at is not yet on the drawing.
 */
export const GHOST_FIGURE_MM = drawing.dimensionTextMm * 1.35;

/** How far past the dimension line the ghost's reading sits (sheet mm). */
const FIGURE_STANDOFF_MM = GHOST_FIGURE_MM * 1.1;

/** The reading, to the 0.01 mm the placement is actually stored at. */
export function formatOffset(offsetMm: number): string {
  // `-0.00` is a real output of toFixed and it is nonsense on paper.
  const fixed = offsetMm.toFixed(2);
  return fixed === "-0.00" ? "0.00" : fixed;
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
    // No scalar is being set here — the crosshair IS the reading. See
    // {@link GhostFigure}.
    figure: null,
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

// --- reading a PLACED dimension back into a placement (REACH-3 follow-up) ---

/**
 * Recover the {@link PlaceTarget} of a dimension ALREADY on the paper, so it can
 * be picked up and moved — the half of REACH-3 that shipped unfinished. Its own
 * commit named the defect as "no way to move it — not while drawing, and **not
 * afterwards**" and fixed only the first half: a committed dimension measured
 * `cursor: auto`, no tabindex, no role, no aria-label, and a real press-drag
 * across it moved nothing. The only control the panel offered was Delete, so
 * recovering from a mis-drag meant delete, re-find the edge, re-pick, re-choose
 * the type, re-drag (frontend-QA 2026-08-27, P1-E).
 *
 * The composed annotation is inverted rather than the original pick re-derived,
 * which matters for the common case: MOST dimensions on a sheet were never
 * hand-placed at all, so there is no stored `offset_mm` to read — the composer
 * auto-placed them. Their geometry, however, is on the paper either way.
 *
 * The construction is `_place_linear_between`'s, run backwards. A witness line
 * runs from `p + n*gap` to `p + n*(|offset| + overrun)`, so its own direction is
 * `n` and its start, walked back one gap, is the MEASURED endpoint. With both
 * endpoints in hand the signed offset is just {@link offsetAt} of the dimension
 * line's midpoint — the same function the live drag uses, so a re-placement and
 * a first placement cannot disagree about which side "away" is. Only
 * `dimensionGapMm` is borrowed from the tokens, and `linearGhost` already
 * depends on it for the forward direction.
 *
 * Null when the annotation is not a linear one this can invert (fewer than two
 * witness lines, no dimension line, or a degenerate span) — the caller then
 * leaves the dimension alone rather than moving it somewhere invented.
 */
export function offsetPlacementFromComposed(
  lines: readonly {
    role: string;
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  }[],
  viewAnchor: Point2D,
): Extract<PlaceTarget, { mode: "offset" }> | null {
  const witness = lines.filter((l) => l.role === "extension");
  const dim = lines.find((l) => l.role === "dimension");
  if (witness.length < 2 || dim === undefined) return null;
  const first = witness[0]!;
  const second = witness[1]!;
  const n = unit({ x: first.x2 - first.x1, y: first.y2 - first.y1 });
  if (n === null) return null;
  const back = mul(n, drawing.dimensionGapMm);
  const a = sub({ x: first.x1, y: first.y1 }, back);
  const b = sub({ x: second.x1, y: second.y1 }, back);
  if (hyp(sub(b, a)) < 1e-9) return null;
  const dimMid = mid({ x: dim.x1, y: dim.y1 }, { x: dim.x2, y: dim.y2 });
  return {
    mode: "offset",
    span: { a, b },
    viewAnchor,
    offsetMm: offsetAt(a, b, viewAnchor, dimMid),
  };
}

/**
 * The same for a dimension whose placement is a TEXT SEAT (diameter / radius /
 * angular — the composer applies `offset_mm` to linear dimensions only). Here
 * there is nothing to invert: the seat is where the stamp already is, and the
 * leader starts at the first drawn line, or at the seat itself for an
 * annotation drawn without one.
 */
export function textPlacementFromComposed(
  lines: readonly { x1: number; y1: number; x2: number; y2: number }[],
  text: { x: number; y: number },
): Extract<PlaceTarget, { mode: "text" }> {
  const first = lines[0];
  return {
    mode: "text",
    leaderFrom:
      first === undefined
        ? { x: text.x, y: text.y }
        : { x: first.x1, y: first.y1 },
    textPos: { x: text.x, y: text.y },
  };
}
