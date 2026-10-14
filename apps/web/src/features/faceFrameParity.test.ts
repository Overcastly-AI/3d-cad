import { describe, expect, it } from "vitest";

import type { PlanarFaceSignature } from "../api/parts";
import { readRepoSource } from "../test/wireSource";
import { faceFrame } from "./facePlacement";

/**
 * HOLE-FRAME-PARITY: the web's face frame against the shared frozen vector.
 *
 * A planar face's in-plane frame is computed three times — `faceFrame` here,
 * `loft_wire.hole_placement.face_frame` (which turns a hole's face X/Y into the
 * stored world position) and the kernel's `deterministic_x_dir`. If they
 * drift, a hole typed at X/Y in the editor is stored somewhere else. All three
 * read one JSON file and must match it to its tolerance (1e-12). The vector is
 * FROZEN: if this fails, fix `faceFrame`, never the file.
 */
const FACE_FRAMES = "packages/loft-wire/tests/fixtures/face_frames.json";

interface FrameCase {
  label: string;
  normal: [number, number, number];
  x_dir: [number, number, number];
  y_dir: [number, number, number];
}

interface FrameVector {
  tolerance: number;
  cases: FrameCase[];
}

const loadVector = (): FrameVector =>
  JSON.parse(
    readRepoSource(FACE_FRAMES, {
      declaredIn:
        "FACE_FRAMES in apps/web/src/features/faceFrameParity.test.ts",
      guards:
        "the shared face-frame vector loft-wire and the kernel also read " +
        "(HOLE-FRAME-PARITY)",
    }),
  ) as FrameVector;

describe("faceFrame — HOLE-FRAME-PARITY shared vector", () => {
  it("matches every frozen normal's x and y directions to 1e-12", () => {
    const vector = loadVector();
    // Non-vacuity: an emptied file would pass the loop below.
    expect(vector.tolerance).toBe(1e-12);
    expect(vector.cases.length).toBeGreaterThanOrEqual(40);

    const misses: string[] = [];
    for (const c of vector.cases) {
      const signature: PlanarFaceSignature = {
        normal: { x: c.normal[0], y: c.normal[1], z: c.normal[2] },
        centroid: { x: 0, y: 0, z: 0 },
        area_mm2: 1,
        subshape_type: "face",
        surface: "plane",
      };
      const { u, v } = faceFrame(signature);
      const got = [u.x, u.y, u.z, v.x, v.y, v.z];
      const want = [...c.x_dir, ...c.y_dir];
      if (
        got.some(
          (g, i) => !(Math.abs(g - (want[i] as number)) <= vector.tolerance),
        )
      ) {
        misses.push(`${c.label}: got ${got.join(",")} want ${want.join(",")}`);
      }
    }
    expect(misses).toEqual([]);
  });
});
