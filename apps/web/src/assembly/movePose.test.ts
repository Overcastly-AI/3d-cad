import { describe, expect, it } from "vitest";

import {
  degreesToOrientation,
  fieldsFromPlacement,
  invalidFields,
  orientationToDegrees,
  parseDegrees,
  placementFromFields,
  samePlacement,
} from "./movePose";
import type { Placement } from "./placement";

const IDENTITY = { w: 1, x: 0, y: 0, z: 0 };
const SEED: Placement = {
  position: { x: 80, y: 0, z: 0 },
  orientation: IDENTITY,
};

describe("degrees ↔ orientation", () => {
  it("Rz = 90 is a quarter turn about kernel +Z", () => {
    const q = degreesToOrientation(0, 0, 90);
    expect(q.w).toBeCloseTo(Math.SQRT1_2, 12);
    expect(q.z).toBeCloseTo(Math.SQRT1_2, 12);
    expect(q.x).toBe(0);
    expect(q.y).toBe(0);
  });

  it("round-trips fixed-axis X→Y→Z angles away from gimbal lock", () => {
    const cases: [number, number, number][] = [
      [0, 0, 0],
      [10, 20, 30],
      [-45, 60, 170],
      [90, -30, -120],
    ];
    for (const [rx, ry, rz] of cases) {
      const [bx, by, bz] = orientationToDegrees(
        degreesToOrientation(rx, ry, rz),
      );
      expect(bx).toBeCloseTo(rx, 9);
      expect(by).toBeCloseTo(ry, 9);
      expect(bz).toBeCloseTo(rz, 9);
    }
  });

  it("applies X first, then Y, then Z about the fixed axes", () => {
    // Rx 90 then Rz 90: local +Y → (Rx) +Z → (Rz) stays +Z.
    const q = degreesToOrientation(90, 0, 90);
    // Rotate (0,1,0) by q by hand: v' = v + 2w(u×v) + 2u×(u×v).
    const u = [q.x, q.y, q.z];
    const v = [0, 1, 0];
    const cross = (a: number[], b: number[]) => [
      (a[1] as number) * (b[2] as number) - (a[2] as number) * (b[1] as number),
      (a[2] as number) * (b[0] as number) - (a[0] as number) * (b[2] as number),
      (a[0] as number) * (b[1] as number) - (a[1] as number) * (b[0] as number),
    ];
    const uv = cross(u, v);
    const uuv = cross(u, uv);
    const out = v.map(
      (n, i) => n + 2 * q.w * (uv[i] as number) + 2 * (uuv[i] as number),
    );
    expect(out[0]).toBeCloseTo(0, 12);
    expect(out[1]).toBeCloseTo(0, 12);
    expect(out[2]).toBeCloseTo(1, 12);
  });
});

describe("fields ↔ placement", () => {
  it("seeds the cells in the document unit and clean degrees", () => {
    const fields = fieldsFromPlacement(
      {
        position: { x: 25.4, y: 0, z: -50.8 },
        orientation: degreesToOrientation(0, 0, 90),
      },
      "in",
    );
    expect(fields).toEqual({
      x: "1",
      y: "0",
      z: "-2",
      rx: "0",
      ry: "0",
      rz: "90",
    });
  });

  it("parses the cells back to kernel mm", () => {
    const fields = { ...fieldsFromPlacement(SEED, "mm"), y: "30", rz: "90" };
    const placement = placementFromFields(fields, "mm", SEED, true);
    expect(placement?.position).toEqual({ x: 80, y: 30, z: 0 });
    expect(placement?.orientation.z).toBeCloseTo(Math.SQRT1_2, 12);
  });

  it("keeps the exact base orientation when no angle cell was edited", () => {
    const odd: Placement = {
      position: { x: 0, y: 0, z: 0 },
      orientation: degreesToOrientation(12.345678, 0, 0),
    };
    const fields = { ...fieldsFromPlacement(odd, "mm"), y: "5" };
    const placement = placementFromFields(fields, "mm", odd, false);
    expect(placement?.orientation).toEqual(odd.orientation);
  });

  it("flags the unparseable cells and builds nothing", () => {
    const fields = { ...fieldsFromPlacement(SEED, "mm"), y: "", rz: "abc" };
    expect([...invalidFields(fields, "mm")].sort()).toEqual(["rz", "y"]);
    expect(placementFromFields(fields, "mm", SEED, true)).toBeNull();
  });

  it("accepts a trailing degree sign", () => {
    expect(parseDegrees("90°")).toBe(90);
    expect(parseDegrees(" ")).toBeNull();
  });
});

describe("samePlacement", () => {
  it("treats q and −q as one pose, and any real move as a change", () => {
    const flipped: Placement = {
      position: SEED.position,
      orientation: { w: -1, x: 0, y: 0, z: 0 },
    };
    expect(samePlacement(SEED, flipped)).toBe(true);
    expect(
      samePlacement(SEED, { ...SEED, position: { x: 80, y: 0.01, z: 0 } }),
    ).toBe(false);
    expect(
      samePlacement(SEED, {
        ...SEED,
        orientation: degreesToOrientation(0, 0, 0.5),
      }),
    ).toBe(false);
  });
});
