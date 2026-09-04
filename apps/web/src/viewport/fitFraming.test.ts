import { describe, expect, it } from "vitest";

import {
  chargedInsetChanged,
  fitDistance,
  fitZoom,
  insetsFor,
  targetShift,
  unobstructedRect,
  type Rect,
} from "./fitFraming";

/** A 1440×800 canvas, the small-laptop frame the quality floor names. */
const CANVAS: Rect = { x: 0, y: 0, width: 1440, height: 800 };
/** The feature tree, as `FloatingPanel side="left"` lays it out. */
const LEFT_PANEL: Rect = { x: 12, y: 12, width: 320, height: 420 };
/** The inspector. */
const RIGHT_PANEL: Rect = { x: 1108, y: 12, width: 320, height: 600 };
/** The view rail, bottom centre. */
const VIEW_BAR: Rect = { x: 660, y: 748, width: 220, height: 40 };

describe("insetsFor", () => {
  it("charges a docked panel to the ONE edge it is nearest", () => {
    expect(insetsFor(CANVAS, LEFT_PANEL)).toEqual({
      left: 332,
      right: 0,
      top: 0,
      bottom: 0,
    });
    expect(insetsFor(CANVAS, RIGHT_PANEL)).toEqual({
      left: 0,
      right: 332,
      top: 0,
      bottom: 0,
    });
  });

  it("charges the bottom rail to the bottom, not to both sides", () => {
    // A centred strip is 660px from the left and 560px from the right; if it
    // were charged to a horizontal edge the fit would lose half the frame.
    expect(insetsFor(CANVAS, VIEW_BAR)).toEqual({
      left: 0,
      right: 0,
      top: 0,
      bottom: 52,
    });
  });

  it("ignores an overlay that straddles the centre in both axes", () => {
    const modal: Rect = { x: 400, y: 200, width: 640, height: 400 };
    expect(insetsFor(CANVAS, modal)).toEqual({
      left: 0,
      right: 0,
      top: 0,
      bottom: 0,
    });
  });

  it("charges a SHORT side panel to its side, not across the top", () => {
    // The assembly workspace's components panel: 320 wide, 340 tall, in a
    // 1600×900 frame. Charging it to the cheapest edge alone picked TOP (340 <
    // 332 + gap), which wasted a full-width band and pushed the model 24px out
    // of the bottom of the rect the fit had just solved for. Measured, not
    // hypothesised — see `insetsFor`.
    const wide: Rect = { x: 0, y: 0, width: 1600, height: 900 };
    const shortPanel: Rect = { x: 12, y: 12, width: 320, height: 340 };
    expect(insetsFor(wide, shortPanel)).toEqual({
      left: 332,
      right: 0,
      top: 0,
      bottom: 0,
    });
  });

  it("still reads a full-width band as a band", () => {
    const wide: Rect = { x: 0, y: 0, width: 1600, height: 900 };
    const statusStrip: Rect = { x: 0, y: 852, width: 1600, height: 48 };
    expect(insetsFor(wide, statusStrip)).toEqual({
      left: 0,
      right: 0,
      top: 0,
      bottom: 48,
    });
  });

  it("ignores an element entirely outside the canvas", () => {
    const below: Rect = { x: 0, y: 900, width: 1440, height: 48 };
    expect(insetsFor(CANVAS, below)).toEqual({
      left: 0,
      right: 0,
      top: 0,
      bottom: 0,
    });
  });
});

describe("unobstructedRect", () => {
  it("is the canvas minus the deepest bite per edge, minus the margin", () => {
    const free = unobstructedRect(
      CANVAS,
      [LEFT_PANEL, RIGHT_PANEL, VIEW_BAR],
      24,
    );
    expect(free).toEqual({ x: 356, y: 24, width: 728, height: 700 });
    // Strictly inside the canvas on all four sides — the invariant the e2e
    // asserts on the projected body.
    expect(free.x).toBeGreaterThan(LEFT_PANEL.x + LEFT_PANEL.width);
    expect(free.x + free.width).toBeLessThan(RIGHT_PANEL.x);
    expect(free.y + free.height).toBeLessThan(VIEW_BAR.y);
  });

  it("gives the space back when a panel collapses", () => {
    const both = unobstructedRect(CANVAS, [LEFT_PANEL, RIGHT_PANEL]);
    const onlyLeft = unobstructedRect(CANVAS, [LEFT_PANEL]);
    expect(onlyLeft.width).toBeGreaterThan(both.width);
  });

  it("falls back to the whole canvas rather than collapsing to nothing", () => {
    const topBand: Rect = { x: 0, y: 0, width: 1440, height: 340 };
    const bottomBand: Rect = { x: 0, y: 460, width: 1440, height: 340 };
    expect(unobstructedRect(CANVAS, [topBand, bottomBand])).toEqual(CANVAS);
  });

  it("reads a full-width top bar as a TOP inset, not a left one", () => {
    const topBar: Rect = { x: 0, y: 0, width: 1440, height: 56 };
    expect(insetsFor(CANVAS, topBar)).toEqual({
      left: 0,
      right: 0,
      top: 56,
      bottom: 0,
    });
  });
});

describe("fitDistance", () => {
  const FOV = 40;
  const TAN = Math.tan((FOV * Math.PI) / 360);

  /** The 8 corners of a box of the given half-sizes, at depth offset `c`. */
  function corners(hx: number, hy: number, hz: number) {
    const out = [];
    for (const a of [-hx, hx]) {
      for (const b of [-hy, hy]) {
        for (const c of [-hz, hz]) out.push({ a, b, c });
      }
    }
    return out;
  }

  /** Every corner's screen offset, as a fraction of the HALF canvas. */
  function worstNdc(
    box: ReturnType<typeof corners>,
    d: number,
    free: Rect,
  ): { x: number; y: number } {
    let x = 0;
    let y = 0;
    for (const { a, b, c } of box) {
      const depth = d - c;
      x = Math.max(
        x,
        Math.abs(a) / (depth * TAN * (CANVAS.width / CANVAS.height)),
      );
      y = Math.max(y, Math.abs(b) / (depth * TAN));
    }
    return {
      x: x / (free.width / CANVAS.width),
      y: y / (free.height / CANVAS.height),
    };
  }

  it("puts the subject exactly inside the free rect", () => {
    const free: Rect = { x: 356, y: 24, width: 728, height: 700 };
    const box = corners(60, 40, 30);
    const d = fitDistance(box, CANVAS, free, FOV);
    const ndc = worstNdc(box, d, free);
    expect(Math.max(ndc.x, ndc.y)).toBeLessThanOrEqual(1);
    // …and TIGHT: it fills the axis it is constrained by, rather than parking
    // the part in a sea of bench the way the old diagonal rule did.
    expect(Math.max(ndc.x, ndc.y)).toBeGreaterThan(0.9);
  });

  it("accounts for DEPTH — the near end of a long part projects wider", () => {
    const free: Rect = { x: 24, y: 24, width: 1392, height: 752 };
    // Same screen-plane extents; the second box reaches 130 mm toward the
    // camera. Ignoring that is exactly what let a 260 mm rail overhang by 51px.
    const flat = fitDistance(corners(60, 40, 0), CANVAS, free, FOV);
    const deep = fitDistance(corners(60, 40, 130), CANVAS, free, FOV);
    expect(deep).toBeGreaterThan(flat + 100);
  });

  it("backs OFF further when the free rect shrinks", () => {
    const wide: Rect = { x: 24, y: 24, width: 1392, height: 752 };
    const narrow: Rect = { x: 356, y: 24, width: 728, height: 700 };
    const box = corners(60, 40, 30);
    expect(fitDistance(box, CANVAS, narrow, FOV)).toBeGreaterThan(
      fitDistance(box, CANVAS, wide, FOV),
    );
  });

  it("follows the subject's ASPECT, not just its size", () => {
    const free: Rect = { x: 24, y: 24, width: 1392, height: 752 };
    // Same bounding diagonal, very different silhouettes: a long rail seen
    // broadside needs more room than a compact block. The old diagonal rule
    // could not tell them apart.
    const rail = fitDistance(corners(130, 12, 12), CANVAS, free, FOV);
    const block = fitDistance(corners(92, 92, 12), CANVAS, free, FOV);
    expect(rail).not.toBeCloseTo(block, 0);
  });

  it("returns 0 for a degenerate rect so the caller can fall back", () => {
    expect(
      fitDistance(corners(1, 1, 1), CANVAS, { ...CANVAS, width: 0 }, FOV),
    ).toBe(0);
    expect(fitDistance([], CANVAS, CANVAS, FOV)).toBe(0);
  });
});

describe("targetShift", () => {
  it("is zero for a centred free rect", () => {
    expect(targetShift(CANVAS, CANVAS, { width: 200, height: 100 })).toEqual({
      right: 0,
      up: 0,
    });
  });

  it("slides the target so the subject lands in the free rect's middle", () => {
    // Free rect centre is 356 + 728/2 = 720 → dead centre horizontally, but the
    // 24px top / 76px bottom insets push its centre 26px UP the screen.
    const free: Rect = { x: 356, y: 24, width: 728, height: 700 };
    const shift = targetShift(CANVAS, free, { width: 1440, height: 800 });
    expect(shift.right).toBeCloseTo(0, 6);
    // dy = 374 − 400 = −26 px → the target moves 26px-worth DOWN in world,
    // which puts the subject 26px higher on screen.
    expect(shift.up).toBeCloseTo(-26, 6);
  });

  it("pushes the subject right when only the LEFT panel is open", () => {
    const free = unobstructedRect(CANVAS, [LEFT_PANEL]);
    const shift = targetShift(CANVAS, free, { width: 1440, height: 800 });
    // The free rect sits right of centre, so the orbit target moves LEFT in
    // world — which is what carries the part out from under the tree.
    expect(shift.right).toBeLessThan(0);
  });
});

describe("chargedInsetChanged — what a rail may wake the camera for", () => {
  /** The left rail at rest: the tree's column, 320 wide at x=12. */
  const RAIL: Rect = { x: 12, y: 12, width: 320, height: 420 };

  it("ignores height — a card that grows a row must not re-frame", () => {
    // THE reason this predicate exists. An editor docked in the rail gains a
    // row every time a field is revealed or a list gets an entry, and a naive
    // ResizeObserver would refit on each one: the lurching FB-1 removed, back
    // by a different door. Measured at HEAD: opening the extrude editor left
    // the free rect at 356,24,888,758 — identical — because only the column's
    // HEIGHT changed.
    expect(
      chargedInsetChanged(RAIL, { ...RAIL, height: RAIL.height + 260 }),
    ).toBe(false);
  });

  it("answers to a collapse — the column gives its width back", () => {
    // `panel-collapse-tree` shrinks the rail to a ~120px tab; a third of the
    // frame comes back and a fit that was correct is now off-centre.
    expect(chargedInsetChanged(RAIL, { ...RAIL, width: 118 })).toBe(true);
  });

  it("answers to the edge moving (a resized window, a docked drawer)", () => {
    expect(chargedInsetChanged(RAIL, { ...RAIL, x: 340 })).toBe(true);
  });

  it("treats the first measurement as no change", () => {
    // The rail mounts into a frame the fit has already solved for; announcing
    // there would fire a refit on every navigation into the workspace.
    expect(chargedInsetChanged(null, RAIL)).toBe(false);
  });

  it("ignores sub-pixel jitter", () => {
    // Layout rounding, a scrollbar appearing inside a child, DPR arithmetic.
    expect(chargedInsetChanged(RAIL, { ...RAIL, width: 320.3 })).toBe(false);
  });
});

describe("fitZoom — the parallel fit (ORTHO-1)", () => {
  /** The 8 corners of a box of the given half-sizes, at depth offset `c`. */
  function corners(hx: number, hy: number, hz: number) {
    const out = [];
    for (const a of [-hx, hx]) {
      for (const b of [-hy, hy]) {
        for (const c of [-hz, hz]) out.push({ a, b, c });
      }
    }
    return out;
  }

  const FREE: Rect = { x: 356, y: 24, width: 728, height: 700 };
  /** `FIT_PADDING` — the hair of slack the edge overlay's line width needs. */
  const PADDING = 1.01;

  it("puts the subject exactly inside the free rect", () => {
    // One world unit measures `zoom` pixels, so the widest corner must land
    // inside half the free rect — and touch it, or the fit is leaving frame on
    // the table.
    const zoom = fitZoom(corners(60, 40, 30), FREE);
    expect(60 * zoom).toBeLessThanOrEqual(FREE.width / 2);
    expect(40 * zoom).toBeLessThanOrEqual(FREE.height / 2);
    const filled = Math.max(
      (60 * zoom) / (FREE.width / 2),
      (40 * zoom) / (FREE.height / 2),
    );
    expect(filled).toBeGreaterThan(0.98);
  });

  it("IGNORES depth — the property the whole feature exists for", () => {
    // `fitDistance` carries `c` because a near corner projects wider. A
    // parallel projection has no such term, so a subject ten times deeper
    // frames identically. If this ever fails, the camera is not parallel.
    const shallow = fitZoom(corners(60, 40, 3), FREE);
    const deep = fitZoom(corners(60, 40, 300), FREE);
    expect(deep).toBeCloseTo(shallow, 10);
  });

  it("binds on whichever axis runs out first", () => {
    // A long broadside rail is width-bound, a tall one height-bound — the same
    // aspect-ratio awareness `fitDistance` has, in zoom units.
    const wide = fitZoom(corners(400, 10, 10), FREE);
    expect(400 * wide).toBeCloseTo(FREE.width / 2 / PADDING, 6);
    const tall = fitZoom(corners(10, 400, 10), FREE);
    expect(400 * tall).toBeCloseTo(FREE.height / 2 / PADDING, 6);
  });

  it("survives a flat subject (a plane seen face-on)", () => {
    // Zero extent on an axis must not divide by zero; the other axis frames.
    const zoom = fitZoom(corners(60, 0, 0), FREE);
    expect(zoom).toBeGreaterThan(0);
    expect(60 * zoom).toBeCloseTo(FREE.width / 2 / PADDING, 6);
  });

  it("returns 0 for a degenerate rect or an empty scene, never Infinity", () => {
    // The caller keeps its current zoom on a 0; an Infinity would fly the
    // camera to a scale nothing recovers from.
    expect(fitZoom(corners(60, 40, 30), { ...FREE, width: 0 })).toBe(0);
    expect(fitZoom([], FREE)).toBe(0);
    expect(fitZoom(corners(0, 0, 0), FREE)).toBe(0);
  });
});
