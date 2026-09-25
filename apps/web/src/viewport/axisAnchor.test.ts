/**
 * THE ARC'S ANCHOR — where the axis is, and what the chain line looks like.
 *
 * Every case here is about a decision that was previously invisible: the axis
 * was not drawn at all, so nothing could tell a correct placement from a wrong
 * one. The frame conversion is the case that would have been worst — a
 * kernel-frame axis puts the whole instrument 90 degrees off the body it is
 * measuring, which is the FB-9 defect the sketch-plane module carries a long
 * note about, and it looks entirely plausible in a screenshot taken from the
 * one camera angle where the two frames agree.
 */
import { describe, expect, it } from "vitest";

import type { SketchEntity } from "../api/parts";
import { PLANE_BASES, sceneOriginBasis } from "../sketch/plane";
import {
  arcReference,
  axisRadial,
  axisReach,
  chainLineSegments,
  crossReference,
  draftAxisAnchor,
  profileAboutAxis,
  revolveAxisAnchor,
  type AxisAnchor,
} from "./axisAnchor";

const XY = sceneOriginBasis("XY");

/** A 20x10 rectangle on the sketch plane, offset 5 in u so it clears the axis. */
const RECT = [
  { x: 5, y: -5 },
  { x: 25, y: -5 },
  { x: 25, y: 5 },
  { x: 5, y: 5 },
];

function line(id: string, sx: number, sy: number, ex: number, ey: number) {
  return {
    kind: "line" as const,
    id,
    start: { x: sx, y: sy },
    end: { x: ex, y: ey },
    construction: true,
  } as SketchEntity;
}

describe("revolveAxisAnchor", () => {
  it("rotates a world ORIGIN axis out of the kernel frame into the scene", () => {
    // The kernel is Z-up and the scene is Y-up, so the kernel's Y axis is the
    // scene's -Z. Getting this wrong draws the axis, the arc and the swept
    // preview 90 degrees away from the body, all three consistently — which is
    // the failure that is hardest to see and easiest to ship.
    expect(
      revolveAxisAnchor({ kind: "origin_axis", axis: "Y" }, XY, []),
    ).toEqual({ base: [0, 0, 0], dir: [0, 0, -1] });
    expect(
      revolveAxisAnchor({ kind: "origin_axis", axis: "Z" }, XY, []),
    ).toEqual({ base: [0, 0, 0], dir: [0, 1, 0] });
    expect(
      revolveAxisAnchor({ kind: "origin_axis", axis: "X" }, XY, []),
    ).toEqual({ base: [0, 0, 0], dir: [1, 0, 0] });
  });

  it("lifts a SKETCH LINE onto its plane", () => {
    const anchor = revolveAxisAnchor(
      { kind: "sketch_line", entity: "e1" },
      XY,
      [line("e1", 0, -10, 0, 10)],
    );
    expect(anchor).not.toBeNull();
    // XY's scene basis: u = +X, v = -Z (the kernel rotation), so a line up the
    // sketch's v axis runs along scene -Z.
    expect(anchor?.base).toEqual([0, 0, 10]);
    expect(anchor?.dir).toEqual([0, 0, -1]);
  });

  it("returns null for a line this sketch does not have", () => {
    // A real state, not a defensive branch: the editor can be retargeted at a
    // different profile while the axis id still names the old sketch's entity.
    expect(
      revolveAxisAnchor({ kind: "sketch_line", entity: "gone" }, XY, [
        line("e1", 0, 0, 0, 10),
      ]),
    ).toBeNull();
  });

  it("returns null for a zero-length line rather than a NaN direction", () => {
    expect(
      revolveAxisAnchor({ kind: "sketch_line", entity: "e1" }, XY, [
        line("e1", 3, 3, 3, 3),
      ]),
    ).toBeNull();
  });
});

describe("axisRadial", () => {
  const anchor: AxisAnchor = { base: [0, 0, 0], dir: [0, 1, 0] };

  it("splits a point into its foot on the axis and its reach from it", () => {
    const { foot, radial, distance } = axisRadial(anchor, [3, 7, 4]);
    expect(foot).toEqual([0, 7, 0]);
    expect(distance).toBeCloseTo(5, 12);
    expect(radial?.[0]).toBeCloseTo(0.6, 12);
    expect(radial?.[2]).toBeCloseTo(0.8, 12);
  });

  it("gives no radial for a point ON the axis", () => {
    // The degenerate revolve. The kernel refuses it; the gauge must not NaN on
    // the way to finding that out.
    expect(axisRadial(anchor, [0, 4, 0]).radial).toBeNull();
  });
});

describe("chainLineSegments", () => {
  const anchor: AxisAnchor = { base: [0, 0, 0], dir: [1, 0, 0] };

  it("is SYMMETRIC about the seat", () => {
    // The whole message of a centreline is "about something". An asymmetric
    // chain reads as a line that happens to be dashed.
    const buf = chainLineSegments(anchor, [0, 0, 0], { reach: 20 });
    const xs = new Set<number>();
    for (let i = 0; i < buf.length; i += 3) xs.add(Math.round(buf[i]! * 1e6));
    for (const x of xs) expect(xs.has(-x)).toBe(true);
  });

  it("opens with ONE long dash straddling the seat, not two halves", () => {
    const buf = chainLineSegments(anchor, [0, 0, 0], {
      reach: 20,
      longMm: 6,
      shortMm: 1,
      gapMm: 1,
    });
    expect(buf[0]).toBeCloseTo(-3, 12);
    expect(buf[3]).toBeCloseTo(3, 12);
  });

  it("never draws ink past the reach", () => {
    const reach = 17.5;
    const buf = chainLineSegments(anchor, [0, 0, 0], { reach });
    for (let i = 0; i < buf.length; i += 3) {
      expect(Math.abs(buf[i]!)).toBeLessThanOrEqual(reach + 1e-9);
    }
  });

  it("draws a chain, not a rod — at least two cycles of gaps", () => {
    const buf = chainLineSegments(anchor, [0, 0, 0], { reach: 20 });
    // 1 centre dash + 2 shorts + 2 longs per cycle, at least 2 cycles.
    expect(buf.length / 6).toBeGreaterThanOrEqual(5);
  });

  it("seats the pattern on the axis's FOOT beneath the centre", () => {
    // The stored axis base is arbitrary (a world origin axis declares [0,0,0]),
    // so the mirror must be about the geometry, not about the declaration.
    const buf = chainLineSegments(anchor, [40, 3, 0], {
      reach: 10,
      longMm: 4,
      shortMm: 1,
      gapMm: 1,
    });
    expect(buf[0]).toBeCloseTo(38, 12);
    expect(buf[3]).toBeCloseTo(42, 12);
    // The foot is ON the axis, so the drawn line carries the axis's own y/z.
    expect(buf[1]).toBeCloseTo(0, 12);
  });

  it("draws nothing when there is no reach", () => {
    expect(chainLineSegments(anchor, [0, 0, 0], { reach: 0 })).toHaveLength(0);
  });
});

describe("axisReach", () => {
  it("overruns the geometry, whichever way the part is proportioned", () => {
    // A disc (wide, short) and a shaft (long, thin) must BOTH get a line that
    // visibly extends past the material — that overrun is what reads as "axis".
    expect(axisReach(4, 30)).toBeGreaterThan(30);
    expect(axisReach(80, 3)).toBeGreaterThan(40);
  });

  it("holds a floor so a tiny part still gets a legible chain", () => {
    expect(axisReach(0.01, 0.01)).toBeGreaterThanOrEqual(1);
  });
});

describe("profileAboutAxis", () => {
  const anchor: AxisAnchor = { base: [0, 0, 0], dir: [0, 0, -1] };

  it("measures the profile ALONG the axis and AWAY from it", () => {
    const about = profileAboutAxis(anchor, XY, [RECT]);
    expect(about).not.toBeNull();
    // v spans -5..5 and XY's v is scene -Z, so the extent along the axis is 10.
    expect(about?.extentMm).toBeCloseTo(10, 12);
    // The furthest corner sits at u = 25 from the axis.
    expect(about?.radiusMm).toBeCloseTo(25, 12);
    expect(about?.centre).toEqual([0, 0, 0]);
  });

  it("returns null for a profile with no points", () => {
    expect(profileAboutAxis(anchor, XY, [])).toBeNull();
  });
});

describe("arcReference", () => {
  it("starts the arc AT the material's furthest point", () => {
    // Not at a neutral reference: a sweep that began elsewhere would carry the
    // right number and describe a different solid.
    const anchor: AxisAnchor = { base: [0, 0, 0], dir: [0, 0, -1] };
    expect(arcReference(anchor, XY, [RECT])).toEqual([1, 0, 0]);
  });

  it("falls back to a stable cross direction for a profile on its own axis", () => {
    const anchor: AxisAnchor = { base: [0, 0, 0], dir: [0, 0, -1] };
    const ref = arcReference(anchor, XY, [[{ x: 0, y: 0 }]]);
    expect(ref[0] * 0 + ref[1] * 0 + ref[2] * -1).toBeCloseTo(0, 12);
    expect(Math.hypot(...ref)).toBeCloseTo(1, 12);
  });
});

describe("crossReference", () => {
  it("is always unit and always perpendicular", () => {
    for (const dir of [
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, 1],
      [0.577, 0.577, 0.577],
    ] as const) {
      const ref = crossReference(dir);
      expect(Math.hypot(...ref)).toBeCloseTo(1, 6);
      expect(ref[0] * dir[0] + ref[1] * dir[1] + ref[2] * dir[2]).toBeCloseTo(
        0,
        6,
      );
    }
  });
});

describe("draftAxisAnchor", () => {
  it("pivots a side wall about its line on the neutral plane", () => {
    // A box's +X wall at x = 10, drafted about the scene ground plane (XY's
    // scene normal). The pivot is the bottom edge of that wall.
    const neutral = PLANE_BASES.XY;
    const anchor = draftAxisAnchor([1, 0, 0], [10, 4, 0], [0, 0, 1], [0, 0, 0]);
    expect(anchor).not.toBeNull();
    // The pivot lies in BOTH planes: x = 10 and z = 0.
    expect(anchor?.base[0]).toBeCloseTo(10, 12);
    expect(anchor?.base[2]).toBeCloseTo(0, 12);
    // and runs along their common direction.
    expect(Math.abs(anchor?.dir[1] ?? 0)).toBeCloseTo(1, 12);
    expect(neutral.normal).toEqual([0, 0, 1]);
  });

  it("returns null for a face PARALLEL to the neutral plane", () => {
    // The everyday instance: a box's top face against XY. It is a real
    // modelling answer, not an error — no pivot exists, so no gauge is drawn.
    expect(
      draftAxisAnchor([0, 0, 1], [0, 0, 10], [0, 0, 1], [0, 0, 0]),
    ).toBeNull();
    // Anti-parallel too — the other mould half.
    expect(
      draftAxisAnchor([0, 0, -1], [0, 0, 0], [0, 0, 1], [0, 0, 0]),
    ).toBeNull();
  });

  it("puts the pivot on an OFFSET neutral plane, not on the datum", () => {
    const anchor = draftAxisAnchor([1, 0, 0], [10, 4, 0], [0, 0, 1], [0, 0, 3]);
    expect(anchor?.base[2]).toBeCloseTo(3, 12);
  });

  it("returns null rather than NaN for a direction with no length", () => {
    expect(
      draftAxisAnchor([0, 0, 0], [1, 1, 1], [0, 0, 1], [0, 0, 0]),
    ).toBeNull();
  });
});
