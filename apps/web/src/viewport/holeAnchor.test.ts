/**
 * CRAFT-9c — where the hole instruments stand, and what their preview draws.
 *
 * The same posture as `faceAnchor.test.ts`: every decision in `holeAnchor.ts`
 * is the kind that draws beautifully and means nothing when it is wrong. An
 * arrow along the outward normal is a perfectly good arrow measuring the air
 * above the face; a Ø arrow at `unitsPerValue` 1 lands its point a whole radius
 * outside the drawn bore; a depth seat on the drill point is a sleeve that
 * steals its sibling's pixels. None of those can be seen in a green browser
 * run, so they are asserted here in numbers.
 */
import { describe, expect, it } from "vitest";
import { dot, linearTrack, type Vec3 } from "@loft/design";

import type { PlanarFaceSignature, Vec3 as ApiVec3 } from "../api/parts";
import { drawnAdvance } from "./faceAnchor";
import {
  boreCircle,
  boreWalls,
  CIRCLE_SEGMENTS,
  depthPlane,
  depthSeat,
  DEPTH_PLANE_HALF_FRAC,
  DIAMETER_UNITS_PER_VALUE,
  diameterSeat,
  drawnDiameter,
  holeAnchor,
} from "./holeAnchor";

/** A planar face signature — OCCT frame, as the overlay publishes it. */
function face(
  normal: [number, number, number],
  centroid: [number, number, number],
  areaMm2: number,
): PlanarFaceSignature {
  return {
    subshape_type: "face",
    surface: "plane",
    normal: { x: normal[0], y: normal[1], z: normal[2] },
    centroid: { x: centroid[0], y: centroid[1], z: centroid[2] },
    area_mm2: areaMm2,
  };
}

const at = (x: number, y: number, z: number): ApiVec3 => ({ x, y, z });

/** The top of a 40 mm block (OCCT z = 40), drilled at (12, 30). */
const TOP = face([0, 0, 1], [20, 20, 40], 1600);
const DRILL = at(12, 30, 40);

function close(a: Vec3, b: Vec3, digits = 9): void {
  expect(a[0]).toBeCloseTo(b[0], digits);
  expect(a[1]).toBeCloseTo(b[1], digits);
  expect(a[2]).toBeCloseTo(b[2], digits);
}

describe("holeAnchor — the seat, in scene space", () => {
  it("stands on the drill point and drills INTO the material", () => {
    const anchor = holeAnchor(TOP, DRILL);
    // OCCT (12, 30, 40) is scene (12, 40, -30): Y-up, the one rotation.
    close(anchor.centre, [12, 40, -30]);
    // The top face's outward normal is scene +Y, so the drill runs -Y. An
    // arrow along the OUTWARD normal would be a depth gauge measuring air.
    close(anchor.axis, [0, -1, 0]);
    expect(dot(anchor.axis, anchor.u)).toBeCloseTo(0, 12);
    expect(dot(anchor.axis, anchor.v)).toBeCloseTo(0, 12);
  });

  it("projects a drill point that is a hair off the face back onto it", () => {
    const anchor = holeAnchor(TOP, at(12, 30, 40.25));
    close(anchor.centre, [12, 40, -30]);
  });

  it("takes its scale from the FACE, not from the hole", () => {
    // Area 1600 -> equivalent radius sqrt(1600 / pi).
    expect(holeAnchor(TOP, DRILL).radius).toBeCloseTo(
      Math.sqrt(1600 / Math.PI),
    );
  });

  it("drills along the inward normal of a side face too", () => {
    // The +X side of the block: outward normal +X, so the drill runs -X.
    const side = face([1, 0, 0], [40, 20, 20], 1600);
    const anchor = holeAnchor(side, at(40, 20, 20));
    close(anchor.axis, [-1, 0, 0]);
  });
});

describe("the two seats never share a point", () => {
  const anchor = holeAnchor(TOP, DRILL);

  it("puts Ø on the drill point, running out along u", () => {
    const seat = diameterSeat(anchor);
    close(seat.base, anchor.centre);
    close(seat.dir, anchor.u);
  });

  it("puts depth on the bore WALL at -u, running down the axis", () => {
    const seat = depthSeat(anchor, 8);
    // One bore radius from the drill point, opposite the Ø arrow — the whole
    // reason the two hit sleeves cannot claim each other's pixels.
    const offset = [
      seat.base[0] - anchor.centre[0],
      seat.base[1] - anchor.centre[1],
      seat.base[2] - anchor.centre[2],
    ] as Vec3;
    expect(Math.hypot(...offset)).toBeCloseTo(4, 9);
    expect(dot(offset, anchor.u)).toBeCloseTo(-4, 9);
    close(seat.dir, anchor.axis);
  });

  it("the Ø arrow's base lands ON the bore circle at every value", () => {
    // unitsPerValue 0.5: the value is a DIAMETER and the arrow is a radius. At
    // 1 the arrowhead would sit a whole radius outside the ring it sizes.
    const track = linearTrack(diameterSeat(anchor), {
      min: 0.1,
      max: 100,
      snap: 0.5,
      keyStep: 0.5,
      format: String,
      unitsPerValue: DIAMETER_UNITS_PER_VALUE,
    });
    for (const d of [1, 6, 8.5, 40]) {
      const tip = track.pointAt(d);
      const ring = boreCircle(anchor, d);
      const r = Math.hypot(
        tip[0] - anchor.centre[0],
        tip[1] - anchor.centre[1],
        tip[2] - anchor.centre[2],
      );
      expect(r).toBeCloseTo(d / 2, 9);
      expect(drawnDiameter(ring, anchor.centre)).toBeCloseTo(d, 4);
    }
  });
});

describe("the preview — the bore circle and the depth plane", () => {
  const anchor = holeAnchor(TOP, DRILL);

  it("draws the mouth as a closed ring of the live diameter, in the face", () => {
    const ring = boreCircle(anchor, 8);
    expect(ring.length).toBe(CIRCLE_SEGMENTS * 6);
    // Float32 buffers: exact to the fifth place, which is 10 nm.
    expect(drawnDiameter(ring, anchor.centre)).toBeCloseTo(8, 5);
    // In the face: no vertex leaves the plane along the axis.
    expect(drawnAdvance(ring, anchor.centre, anchor.axis)).toBeCloseTo(0, 5);
    // Closed: the last segment ends where the first began.
    const n = ring.length;
    expect(ring[n - 3]).toBeCloseTo(ring[0] as number, 5);
    expect(ring[n - 2]).toBeCloseTo(ring[1] as number, 5);
    expect(ring[n - 1]).toBeCloseTo(ring[2] as number, 5);
  });

  it("stands the depth plane at exactly the live depth", () => {
    for (const depth of [0.5, 12, 37.25]) {
      const plane = depthPlane(anchor, 8, depth);
      expect(drawnAdvance(plane, anchor.centre, anchor.axis)).toBeCloseTo(
        depth,
        5,
      );
    }
  });

  it("frames the bottom ring with a square sized by the bore", () => {
    const plane = depthPlane(anchor, 10, 5);
    // Ring + four square sides.
    expect(plane.length).toBe(CIRCLE_SEGMENTS * 6 + 4 * 6);
    const half = 10 * DEPTH_PLANE_HALF_FRAC;
    const corner = Array.from(
      plane.slice(CIRCLE_SEGMENTS * 6, CIRCLE_SEGMENTS * 6 + 3),
    );
    const bottom = [anchor.centre[0], anchor.centre[1] - 5, anchor.centre[2]];
    expect(Math.abs((corner[0] as number) - (bottom[0] as number))).toBeCloseTo(
      half,
      5,
    );
    expect(Math.abs((corner[2] as number) - (bottom[2] as number))).toBeCloseTo(
      half,
      5,
    );
  });

  it("ties mouth to bottom with four wall generators of the depth's length", () => {
    const walls = boreWalls(anchor, 8, 12);
    expect(walls.length).toBe(4 * 6);
    for (let i = 0; i < walls.length; i += 6) {
      const top: Vec3 = [
        walls[i] as number,
        walls[i + 1] as number,
        walls[i + 2] as number,
      ];
      const bottom: Vec3 = [
        walls[i + 3] as number,
        walls[i + 4] as number,
        walls[i + 5] as number,
      ];
      expect(bottom[1] - top[1]).toBeCloseTo(-12, 5);
      expect(
        Math.hypot(top[0] - anchor.centre[0], top[2] - anchor.centre[2]),
      ).toBeCloseTo(4, 5);
    }
  });

  it("draws nothing for a hole of no size — there is no honest picture of one", () => {
    expect(boreCircle(anchor, 0).length).toBe(0);
    expect(boreCircle(anchor, Number.NaN).length).toBe(0);
    expect(depthPlane(anchor, 8, 0).length).toBe(0);
    expect(boreWalls(anchor, 8, -1).length).toBe(0);
    expect(drawnDiameter(new Float32Array(0), anchor.centre)).toBe(0);
  });
});
