/**
 * The gauge's drawn pose — and the chord defect this seam exists to catch.
 *
 * The decisive case is the ARC one. It has no shipped call site today (the
 * first angular gauge is CRAFT-10), which is exactly the condition under which
 * the defect survived: the straight track's two-point spine is a chord OF
 * ITSELF, so every browser run, every screenshot and every extrude case agreed
 * with a shell that threw the middle of the polyline away.
 */
import { angularTrack, linearTrack, NO_STOPS } from "@loft/design";
import type { GaugeSeat, Vec3 } from "@loft/design";
import { describe, expect, it } from "vitest";

import { OrthographicCamera } from "three";

import { gaugePose, projectedSpineLength, spineLength } from "./gaugePose";

const SEAT: GaugeSeat = {
  base: [0, 0, 0],
  dir: [0, 0, 1],
  radius: 40,
  arms: [
    [1, 0, 0],
    [0, 1, 0],
  ],
};

const straight = linearTrack(SEAT, {
  min: 0.1,
  max: 10_000,
  snap: 0.5,
  keyStep: 0.5,
  format: (v) => `${String(v)} mm`,
});

const swept = angularTrack(SEAT, {
  min: 0.1,
  max: 360,
  radius: 20,
  snap: 5,
  keyStep: 5,
  format: (v) => `${String(v)} deg`,
});

describe("gaugePose", () => {
  it("reduces a two-point spine to ONE segment — extrude is unaffected", () => {
    const pose = gaugePose(straight.draw(40, NO_STOPS));
    expect(pose.segments).toHaveLength(1);
    const [only] = pose.segments;
    if (only === undefined) throw new Error("no segment");
    expect(only.length).toBeCloseTo(40, 9);
    // Centred on the middle of the shaft, which is where a single scaled unit
    // cylinder went before the polyline existed.
    expect(only.centre.z).toBeCloseTo(20, 9);
    expect(only.centre.x).toBeCloseTo(0, 9);
  });

  it("puts the arrowhead's BASE on the end of the shaft, not its centre", () => {
    const drawing = straight.draw(40, NO_STOPS);
    const pose = gaugePose(drawing);
    expect(pose.headCentre.z).toBeCloseTo(40 + drawing.head.length / 2, 9);
  });

  it("DRAWS THE ARC, not the chord across it", () => {
    // THE MEASUREMENT THAT FOUND THIS. A 90 degree sweep at radius 20 emits a
    // 25-point spine; the chord between its ends misses the true arc by 5.86
    // world units, 29 % of the radius. Every drawn segment must stay ON the
    // circle, which the chord does not.
    const drawing = swept.draw(90, NO_STOPS);
    expect(drawing.spine.length).toBeGreaterThan(2);
    const pose = gaugePose(drawing);
    expect(pose.segments).toHaveLength(drawing.spine.length - 1);

    const radiusOf = (p: { x: number; y: number; z: number }): number =>
      Math.hypot(p.x, p.y, p.z);
    let worst = 0;
    for (const segment of pose.segments) {
      // The midpoint of a short chord sits just inside the circle; the bound is
      // the sagitta of ONE segment, not of the whole sweep.
      worst = Math.max(worst, Math.abs(radiusOf(segment.centre) - 20));
    }
    expect(worst).toBeLessThan(0.05);

    // …and the negative control, so this case cannot pass for the wrong reason:
    // the chord the old shell drew really is 5.86 units out at its middle.
    const ends = [
      drawing.spine[0] as Vec3,
      drawing.spine[drawing.spine.length - 1] as Vec3,
    ];
    const chordMid = {
      x: ((ends[0] as Vec3)[0] + (ends[1] as Vec3)[0]) / 2,
      y: ((ends[0] as Vec3)[1] + (ends[1] as Vec3)[1]) / 2,
      z: ((ends[0] as Vec3)[2] + (ends[1] as Vec3)[2]) / 2,
    };
    expect(Math.abs(radiusOf(chordMid) - 20)).toBeCloseTo(5.86, 2);
  });

  it("totals the drawn length over every segment, straight or swept", () => {
    expect(spineLength(gaugePose(straight.draw(40, NO_STOPS)).segments)) //
      .toBeCloseTo(40, 9);
    // A polyline's total is its own length, always a little under the true arc
    // (a chain of chords) and nowhere near the single chord's 28.3.
    const arc = spineLength(gaugePose(swept.draw(90, NO_STOPS)).segments);
    expect(arc).toBeGreaterThan(31);
    expect(arc).toBeLessThanOrEqual((Math.PI / 2) * 20 + 1e-9);
  });

  it("emits no NaN for a zero-length spine", () => {
    // A quaternion built from a zero direction is NaN, and a NaN in a matrix
    // takes the whole mesh off screen rather than drawing nothing.
    const pose = gaugePose({
      spine: [
        [0, 0, 0],
        [0, 0, 0],
      ],
      spineRadius: 0.1,
      head: { base: [0, 0, 0], tip: [0, 0, 1], length: 1, radius: 0.4 },
      rungs: [],
      minorRungs: [],
    });
    const [only] = pose.segments;
    if (only === undefined) throw new Error("no segment");
    for (const n of only.quaternion.toArray())
      expect(Number.isNaN(n)).toBe(false);
  });
});

describe("the ladder's scale — one segment at both ends", () => {
  /** An orthographic camera looking down -Z, so the projection is exact. */
  const facing = (): OrthographicCamera => {
    const camera = new OrthographicCamera(-1, 1, 1, -1, 0.1, 1000);
    camera.position.set(0, 0, 100);
    camera.lookAt(0, 0, 0);
    camera.updateMatrixWorld(true);
    camera.updateProjectionMatrix();
    return camera;
  };

  /**
   * THE BIAS, named as a measurement. A camera looking along the track's own
   * axis would project it to a point, so the gauge lies in the camera's screen
   * plane: `x` maps to pixels linearly and a world millimetre is a known number
   * of pixels. The whole test is then "does the shell divide two lengths that
   * describe the same thing".
   */
  const sideways: GaugeSeat = { ...SEAT, dir: [1, 0, 0] };
  const along = linearTrack(sideways, {
    min: 0.1,
    max: 10_000,
    snap: 0.5,
    keyStep: 0.5,
    format: (v) => `${String(v)} mm`,
  });

  it("measures the SPINE, not the spine plus the arrowhead", () => {
    const camera = facing();
    // Frustum half-width 1 world unit over 800 px: 400 px per world unit.
    camera.left = -1;
    camera.right = 1;
    camera.updateProjectionMatrix();
    const drawing = along.draw(40, NO_STOPS);
    const world = spineLength(gaugePose(drawing).segments);
    const px = projectedSpineLength(drawing.spine, camera, 800, 800);
    expect(world).toBeCloseTo(40, 9);
    // 40 world units across a 2-unit frustum is 20 frustum widths; only the
    // RATIO matters, and it is exactly the frame scale with nothing added.
    expect(px / world).toBeCloseTo(400, 6);

    // …and the old reading, kept as the negative control: the same projection
    // taken to the arrowhead's TIP is longer by the head, which `spineLength`
    // does not contain. That surplus IS the bias — 1.18 here, and larger the
    // shorter the feature gets, so the ladder's "14 px" floor was really 11.9
    // and slid with the value. A test that cannot show the wrong answer cannot
    // certify the right one.
    const biased = projectedSpineLength(
      [drawing.spine[0] as Vec3, drawing.head.tip],
      camera,
      800,
      800,
    );
    // The surplus is exactly the head, whatever the seat: `(value + head) /
    // value`. On THIS fixture's 40 mm seat that is 1.25; in the running app,
    // whose profile radius is smaller, the reviewer measured 1.180.
    expect(biased / px).toBeCloseTo((40 + drawing.head.length) / 40, 9);
    expect(biased / px).toBeCloseTo(1.25, 9);

    // And it grows as the feature shortens, which is why the floor SLID rather
    // than simply sitting low: the arrowhead clamp holds the head at 0.45 of a
    // 10 mm shaft, so the same reading is inflated 1.45x there. A ladder whose
    // docstring promises scale-invariance cannot have a floor that depends on
    // the value.
    const short = along.draw(10, NO_STOPS);
    const shortPx = projectedSpineLength(short.spine, camera, 800, 800);
    const shortBiased = projectedSpineLength(
      [short.spine[0] as Vec3, short.head.tip],
      camera,
      800,
      800,
    );
    expect(shortBiased / shortPx).toBeCloseTo(1.45, 9);
    expect(shortBiased / shortPx).toBeGreaterThan(biased / px);
  });

  it("follows the ARC and not its chord, so CRAFT-10 inherits a true scale", () => {
    // The same defect one level up: a straight screen distance between the ends
    // of a 90 degree sweep is a chord, 0.900 of the arc it stands for. An
    // angular gauge reads the identical `unitsPerPixel`, so the polyline sum is
    // what keeps its ladder honest before the first one is built.
    const camera = facing();
    const drawing = swept.draw(90, NO_STOPS);
    const px = projectedSpineLength(drawing.spine, camera, 800, 800);
    const chord = projectedSpineLength(
      [
        drawing.spine[0] as Vec3,
        drawing.spine[drawing.spine.length - 1] as Vec3,
      ],
      camera,
      800,
      800,
    );
    expect(chord / px).toBeCloseTo(0.9, 2);
    // Pixels and world units stay in step: the ratio is the frame scale, the
    // same number the straight track reports on the same camera.
    const world = spineLength(gaugePose(drawing).segments);
    expect(px / world).toBeCloseTo(400, 3);
  });

  it("is allocation-free and returns 0 for a degenerate spine", () => {
    const camera = facing();
    expect(projectedSpineLength([[0, 0, 0]], camera, 800, 800)).toBe(0);
    expect(
      projectedSpineLength(
        [
          [0, 0, 0],
          [0, 0, 0],
        ],
        camera,
        800,
        800,
      ),
    ).toBe(0);
  });
});
