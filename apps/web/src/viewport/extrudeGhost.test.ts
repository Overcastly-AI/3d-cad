/**
 * The extrude ghost must never contradict what Save will do.
 *
 * This asserts the seam BELOW the r3f renderer: `ExtrudePreview` itself is a
 * WebGL component that jsdom cannot render (there is no GL context, and mocking
 * the GPU stack would test the mock), so the decision the defect actually got
 * wrong — how an operation is shaded — was lifted into the pure
 * {@link extrudeGhostAppearance}. What is left in the component is
 * `new MeshMatcapMaterial(...)` assignment from these values.
 *
 * The regression being locked out (FINDINGS burn-down 2026-07-25 #5): the
 * preview ignored `operation: "cut"` entirely and painted a solid standing
 * proud of the plate — the visual opposite of the pocket Save produced.
 */
import { BackSide, FrontSide, Vector3 } from "three";
import { describe, expect, it } from "vitest";

import {
  faceBasis,
  originBasis,
  sceneOriginBasis,
  type PlanarFaceSignature,
} from "../sketch/plane";
import { twistGaugeTrack } from "./axisAnchorGauge";
import {
  extrudeGhostAppearance,
  buildGhostRegion,
  extrudeGhostPose,
  GHOST_WALL_VERTEX_BUDGET,
  ringEdgePositions,
  twistArcSeat,
  twistGhostSteps,
  twistPositionsInPlace,
  type ExtrudeGhostPose,
} from "./extrudeGhost";
import type { ProfileRegion } from "./profileLoops";

/** Relative luminance of a `#rrggbb` token — "is this ink dark or bright?". */
function luminance(hex: string): number {
  const n = Number.parseInt(hex.replace("#", ""), 16);
  const r = (n >> 16) & 0xff;
  const g = (n >> 8) & 0xff;
  const b = n & 0xff;
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}

describe("extrudeGhostAppearance", () => {
  it("is operation-sensitive at all — a cut is never shaded like an add", () => {
    // The dead-field bug in one assertion: if `operation` stops reaching the
    // shading, these two collapse into the same object and this fails.
    expect(extrudeGhostAppearance("cut")).not.toEqual(
      extrudeGhostAppearance("add"),
    );
  });

  it("draws a cut as a cavity — back walls only, never a proud solid", () => {
    const cut = extrudeGhostAppearance("cut");
    expect(cut.surfaceSide).toBe(BackSide);
    // An added solid shows its NEAR faces; a void must not.
    expect(cut.surfaceSide).not.toBe(extrudeGhostAppearance("add").surfaceSide);
  });

  it("draws an add as a solid — front faces of metal about to exist", () => {
    expect(extrudeGhostAppearance("add").surfaceSide).toBe(FrontSide);
  });

  it("shades a cut cold and dark and an add warm and bright", () => {
    // A hole in aluminium is a shadow, not a highlight: the cut wall tint must
    // read materially darker than the add tint, or the two states look alike.
    const cut = luminance(extrudeGhostAppearance("cut").surfaceTint);
    const add = luminance(extrudeGhostAppearance("add").surfaceTint);
    expect(cut).toBeLessThan(add - 0.25);
  });

  it("keeps both ghosts translucent — a preview is never committed metal", () => {
    for (const operation of ["add", "cut"] as const) {
      const a = extrudeGhostAppearance(operation);
      expect(a.surfaceOpacity).toBeGreaterThan(0);
      expect(a.surfaceOpacity).toBeLessThan(1);
      expect(a.edgeOpacity).toBeGreaterThan(0);
      expect(a.edgeOpacity).toBeLessThanOrEqual(1);
    }
  });

  it("inks the void silhouette differently from the add silhouette", () => {
    expect(extrudeGhostAppearance("cut").edgeColor).not.toBe(
      extrudeGhostAppearance("add").edgeColor,
    );
  });

  it("sources every colour from a design token, never a literal", () => {
    for (const operation of ["add", "cut"] as const) {
      const a = extrudeGhostAppearance(operation);
      expect(a.surfaceTint).toMatch(/^#[0-9a-fA-F]{6}$/);
      expect(a.edgeColor).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
  });
});

/** Where a point of the ghost's own space (profile x/y, sweep z) lands. */
function place(
  pose: ExtrudeGhostPose,
  local: [number, number, number],
): [number, number, number] {
  const p = new Vector3(...local)
    .applyQuaternion(pose.quaternion)
    .add(pose.position);
  const round = (v: number): number => Math.round(v * 1e6) / 1e6 + 0;
  return [round(p.x), round(p.y), round(p.z)];
}

describe("extrudeGhostPose — the ghost sits ON the plane it was drawn on", () => {
  /**
   * FB-7c / FB-9. `ExtrudeGeometry` builds the profile in local XY and sweeps
   * toward local +Z, so the pose has one job: put local +Z on the plane NORMAL,
   * in the frame the body renders in. It was fed a basis stated in the kernel's
   * Z-up frame while the scene is Y-up, so re-opening an unmodified 10 mm
   * extrude on XY drew the ghost lying through the ground grid — 152 px below
   * the body it was meant to coincide with, and into the bottom view rail.
   */
  it("sweeps an XY extrude UP the scene, the way the body grows", () => {
    const pose = extrudeGhostPose(sceneOriginBasis("XY"));
    // 10 mm of sweep = 10 mm of scene height. This is the assertion that fails
    // on the old behaviour: the kernel-frame basis sent it to [0, 0, 10].
    expect(place(pose, [0, 0, 10])).toEqual([0, 10, 0]);
    // …and the profile still lies IN the ground plane (scene y = 0).
    expect(place(pose, [7, -3, 0])).toEqual([7, 0, 3]);
  });

  it("rejects a kernel-frame basis by disagreeing with it", () => {
    // The negative control: same plane, un-rotated basis, 90° of error.
    expect(place(extrudeGhostPose(originBasis("XY")), [0, 0, 10])).toEqual([
      0, 0, 10,
    ]);
  });

  it("agrees with a sketch on the same face, resolved the other way", () => {
    // A sketch on a box's top face at z=10 and a sketch on XY+10 are the same
    // plane. `faceBasis` was already scene-frame, so this pair is what the
    // origin-datum path now has to match.
    const face: PlanarFaceSignature = {
      normal: { x: 0, y: 0, z: 1 },
      centroid: { x: 0, y: 0, z: 10 },
      area_mm2: 100,
      subshape_type: "face",
      surface: "plane",
    };
    const onFace = extrudeGhostPose(faceBasis(face, 0));
    expect(place(onFace, [0, 0, 5])).toEqual([0, 15, 0]);
  });

  it("places the ghost at the plane's own origin", () => {
    const pose = extrudeGhostPose(sceneOriginBasis("YZ"));
    expect(place(pose, [0, 0, 0])).toEqual([0, 0, 0]);
  });
});

/**
 * THE GHOST TWISTS (helical-gear gap G1). A 90 degree twist used to preview as
 * a straight prism standing over the twisted body Save made. The kernel's
 * rule, which the mesh must restate: every slice is the profile turned rigidly
 * about the twist axis by the fraction of the distance travelled, RIGHT-HANDED
 * ABOUT THE TRAVEL (so a reverse extrude turns the other way about +normal).
 */
describe("twistPositionsInPlace", () => {
  function twisted(
    points: number[][],
    twist: number,
    centre: { x: number; y: number } | null,
    reverse: boolean,
  ): number[][] {
    const buffer = new Float32Array(points.flat());
    twistPositionsInPlace(buffer, 20, twist, centre, reverse);
    const out: number[][] = [];
    for (let i = 0; i < buffer.length; i += 3) {
      out.push([buffer[i], buffer[i + 1], buffer[i + 2]] as number[]);
    }
    return out;
  }

  it("leaves the sketch end alone and turns the far end by the whole twist", () => {
    const [base, mid, top] = twisted(
      [
        [10, 0, 0],
        [10, 0, 10],
        [10, 0, 20],
      ],
      90,
      null,
      false,
    ) as number[][];
    expect(base).toEqual([10, 0, 0]);
    // Anticlockwise seen from +normal: the kernel's "positive on XY, normal".
    expect(top?.[0]).toBeCloseTo(0, 5);
    expect(top?.[1]).toBeCloseTo(10, 5);
    // Uniform: half the travel, half the turn.
    expect(mid?.[0]).toBeCloseTo(10 * Math.SQRT1_2, 5);
    expect(mid?.[1]).toBeCloseTo(10 * Math.SQRT1_2, 5);
  });

  it("is right-handed about the TRAVEL: a reverse extrude turns the other way", () => {
    const [top] = twisted([[10, 0, -20]], 90, null, true) as number[][];
    expect(top?.[0]).toBeCloseTo(0, 5);
    expect(top?.[1]).toBeCloseTo(-10, 5);
  });

  it("turns about the chosen centre, not the origin", () => {
    const [top, onAxis] = twisted(
      [
        [20, 10, 20],
        [10, 10, 20],
      ],
      90,
      { x: 10, y: 10 },
      false,
    ) as number[][];
    expect(top?.[0]).toBeCloseTo(10, 5);
    expect(top?.[1]).toBeCloseTo(20, 5);
    expect(onAxis).toEqual([10, 10, 20]);
  });

  for (const reverse of [false, true]) {
    it(`twists a wall normal to the twisted SURFACE's normal (reverse: ${reverse})`, () => {
      // The wall x = 10 of a prism, normal +x, twisted 120 degrees over 20 mm
      // about (2, 1). Recomputing normals from the folded triangles striped the
      // ghost; the analytic one must be perpendicular to the surface itself,
      // which finite differences of the SAME transform measure independently.
      const centre = { x: 2, y: 1 };
      const sign = reverse ? -1 : 1;
      const surface = (y: number, z: number): Vector3 => {
        const b = new Float32Array([10, y, z]);
        twistPositionsInPlace(b, 20, 120, centre, reverse);
        return new Vector3(b[0], b[1], b[2]);
      };
      const y = 5;
      const z = 8 * sign;
      const h = 1e-2;
      const alongWall = surface(y + h, z).sub(surface(y - h, z));
      const alongTravel = surface(y, z + h).sub(surface(y, z - h));
      const normals = new Float32Array([1, 0, 0]);
      twistPositionsInPlace(
        new Float32Array([10, y, z]),
        20,
        120,
        centre,
        reverse,
        normals,
      );
      const n = new Vector3(normals[0], normals[1], normals[2]);
      expect(n.length()).toBeCloseTo(1, 6);
      expect(Math.abs(n.dot(alongWall.normalize()))).toBeLessThan(1e-3);
      expect(Math.abs(n.dot(alongTravel.normalize()))).toBeLessThan(1e-3);
      // Not trivially satisfied: the twist TILTS the wall normal.
      expect(Math.abs(n.z)).toBeGreaterThan(0.1);
    });
  }

  it("keeps a cap flat and a cylinder about its own axis radial", () => {
    const normals = new Float32Array([0, 0, 1, 0.6, 0.8, 0]);
    twistPositionsInPlace(
      new Float32Array([3, 4, 20, 6, 8, 10]),
      20,
      90,
      null,
      false,
      normals,
    );
    expect([normals[0], normals[1], normals[2]]).toEqual([0, 0, 1]);
    // (6, 8) turned 45 degrees is still radial: its normal follows, untilted.
    expect(normals[5]).toBeCloseTo(0, 6);
    expect(normals[3]).toBeCloseTo(0.6 * Math.SQRT1_2 - 0.8 * Math.SQRT1_2, 6);
  });

  it("does nothing at all for no twist", () => {
    expect(twisted([[3, 4, 20]], 0, null, false)).toEqual([[3, 4, 20]]);
  });

  it("cuts the walls into enough rings to read as a helix", () => {
    // A rectangle: the budget never binds, 5 degrees a ring.
    expect(twistGhostSteps(0, 4)).toBe(1);
    expect(twistGhostSteps(1, 4)).toBe(8);
    expect(twistGhostSteps(-90, 4)).toBe(18);
    expect(twistGhostSteps(3600, 4)).toBe(360);
  });
});

/**
 * Review S1: the ghost rebuilds every 70 ms while the twist arc is dragged, and
 * a 664-point gear outline at 360 rings was 1.44M vertices with 3.4 s of edge
 * finding per rebuild. The mesh is now bounded by a vertex BUDGET, and the ink
 * is found on a one-step prism, whatever the twist.
 */
describe("buildGhostRegion — bounded, whatever the outline and the twist", () => {
  /** A gear-like outline: `n` points on a wavy circle (sharp enough corners). */
  function gear(n: number): ProfileRegion {
    const outer = Array.from({ length: n }, (_, i) => {
      const a = (i / n) * 2 * Math.PI;
      const r = i % 2 === 0 ? 30 : 27;
      return { x: r * Math.cos(a), y: r * Math.sin(a) };
    });
    return { outer, holes: [] };
  }

  for (const n of [664, 4000]) {
    it(`keeps a ${n}-point outline at 3600 degrees inside the budget`, () => {
      const { mesh, edges } = buildGhostRegion(
        gear(n),
        20,
        "normal",
        3600,
        null,
      );
      // Walls within the budget; the caps are the outline's own triangulation
      // (two caps, n - 2 triangles each).
      const caps = 2 * 3 * (n - 2);
      const vertices = mesh.getAttribute("position").count;
      expect(vertices).toBeLessThanOrEqual(GHOST_WALL_VERTEX_BUDGET + caps);
      // The ink: two cap outlines, and each side edge split into the rings.
      const steps = twistGhostSteps(3600, n);
      const inkVertices = edges.getAttribute("position").count;
      expect(inkVertices).toBeLessThanOrEqual(2 * (2 * n) + 2 * n * steps);
      mesh.dispose();
      edges.dispose();
    });
  }

  it("still twists the ink with the walls: a side edge becomes a helix", () => {
    const square: ProfileRegion = {
      outer: [
        { x: 0, y: 0 },
        { x: 20, y: 0 },
        { x: 20, y: 20 },
        { x: 0, y: 20 },
      ],
      holes: [],
    };
    const { edges } = buildGhostRegion(square, 20, "normal", 90, null);
    const p = edges.getAttribute("position").array as Float32Array;
    // Every ink vertex at height z is the straight-prism vertex turned by
    // 90 * z / 20 degrees, so its distance from the axis is one of the
    // square's (20 or 20 * sqrt 2 or 0), and the far cap is turned a quarter.
    let sawTop = false;
    for (let i = 0; i < p.length; i += 3) {
      const r = Math.hypot(p[i] as number, p[i + 1] as number);
      expect([0, 20, 20 * Math.SQRT2].some((d) => Math.abs(r - d) < 1e-3)).toBe(
        true,
      );
      if (Math.abs((p[i + 2] as number) - 20) < 1e-6 && r > 1) {
        sawTop = true;
        // (20, 0) -> (0, 20), (20, 20) -> (-20, 20): x <= 0 at the top.
        expect(p[i] as number).toBeLessThan(1e-3);
      }
    }
    expect(sawTop).toBe(true);
    // Split into rings: far more than the 12 edges x 2 vertices of a box.
    expect(p.length / 3).toBeGreaterThan(24);
  });
});

describe("ringEdgePositions", () => {
  it("splits a segment that spans the travel and passes a cap segment through", () => {
    const out = ringEdgePositions(
      new Float32Array([1, 2, 0, 1, 2, 10, 0, 0, 10, 5, 0, 10]),
      4,
    );
    // 4 pieces of the side edge + the cap segment = 5 segments.
    expect(out.length).toBe(5 * 6);
    expect(Array.from(out.slice(0, 6))).toEqual([1, 2, 0, 1, 2, 2.5]);
    expect(Array.from(out.slice(24))).toEqual([0, 0, 10, 5, 0, 10]);
  });
});

describe("twistArcSeat — the arc and the ghost agree about which way it turns", () => {
  const SQUARE: ProfileRegion[] = [
    {
      outer: [
        { x: 0, y: 0 },
        { x: 20, y: 0 },
        { x: 20, y: 20 },
        { x: 0, y: 20 },
      ],
      holes: [],
    },
  ];
  const basis = sceneOriginBasis("XY");

  it("stands on the FAR cap, about the travel, clear of the profile", () => {
    const seat = twistArcSeat(basis, SQUARE, null, 30, "normal");
    expect(seat?.centre).toEqual([0, 30, 0]);
    expect(seat?.axis).toEqual([0, 1, 0]);
    expect(seat?.arcRadiusMm).toBeCloseTo(Math.hypot(20, 20) * 1.2, 9);
    const reverse = twistArcSeat(basis, SQUARE, null, 30, "reverse");
    expect(reverse?.centre).toEqual([0, -30, 0]);
    // (+ 0 folds the -0 a negated zero component carries.)
    expect(reverse?.axis.map((v) => v + 0)).toEqual([0, -1, 0]);
  });

  it("is null when there is nothing to twist", () => {
    expect(twistArcSeat(basis, [], null, 30, "normal")).toBeNull();
  });

  for (const direction of ["normal", "reverse"] as const) {
    for (const twist of [90, -45, 400]) {
      it(`puts the grip beside the far corner the ghost turned (${direction}, ${twist}°)`, () => {
        // The one property that decides whether the arc is an instrument or a
        // decoration: drag it, and the grip travels WITH the corner of the top
        // it dimensions. Ghost and gauge derive the turn separately, so this
        // catches either one getting the sense wrong.
        const depth = 30;
        const seat = twistArcSeat(basis, SQUARE, null, depth, direction);
        if (seat === null) throw new Error("no seat");
        const grip = twistGaugeTrack(seat).pointAt(twist);
        const z = direction === "reverse" ? -depth : depth;
        const corner = new Float32Array([20, 20, z]);
        twistPositionsInPlace(
          corner,
          depth,
          twist,
          null,
          direction === "reverse",
        );
        const pose = extrudeGhostPose(basis);
        const onScene = place(pose, [
          corner[0] as number,
          corner[1] as number,
          corner[2] as number,
        ]);
        const toGrip = new Vector3(...grip).sub(new Vector3(...seat.centre));
        const toCorner = new Vector3(...onScene).sub(
          new Vector3(...seat.centre),
        );
        expect(toGrip.angleTo(toCorner)).toBeLessThan(1e-4);
        expect(toGrip.length()).toBeGreaterThan(toCorner.length());
      });
    }
  }
});
