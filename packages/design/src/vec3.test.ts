/**
 * The consolidated tuple arithmetic (board #63).
 *
 * EVERY CASE BELOW IS A DECISION, NOT A SANITY CHECK. Four copies of these
 * helpers had diverged, and they diverged EXCLUSIVELY on inputs no
 * well-conditioned test would ever supply: a zero vector, a denormal, an
 * enormous one, a cross product that is pure rounding noise. A suite that only
 * exercises `[3,4,0]` cannot observe this defect class at all — it agreed with
 * all four implementations, including the two that were wrong — so the
 * degenerate cases are the POINT of this file and are written first.
 *
 * The invariant each of them serves: **no call can return a vector that claims
 * to be unit and is not.** `null` is the refusal, and it is the only other
 * answer {@link unit} is allowed to give.
 */
import { describe, expect, it } from "vitest";

import {
  add,
  addScaled,
  cross,
  dot,
  length,
  negate,
  reject,
  scale,
  sub,
  unit,
  VEC3_UNIT_FLOOR,
  type Vec3,
} from "./vec3";

const mag = (v: Vec3): number => Math.hypot(v[0], v[1], v[2]);

describe("unit — the function the four copies disagreed about", () => {
  it("normalises a well-conditioned vector (where all four agreed)", () => {
    expect(unit([3, 4, 0])).toEqual([0.6000000000000001, 0.8, 0]);
  });

  it("REFUSES a zero vector instead of returning it as a direction", () => {
    // `gauge.ts` returned `[0,0,0]` here — a "unit" vector of length 0, which
    // seats a gauge on nothing and draws graduation crosses with no arms.
    expect(unit([0, 0, 0])).toBeNull();
  });

  it("REFUSES a denormal instead of handing back the input unchanged", () => {
    // `gauge.ts` returned `[1e-300,0,0]`, a "unit" vector 300 decades short,
    // because `Math.sqrt(dot(a,a))` underflowed and its `l > 0` guard fired on
    // a length it had already destroyed.
    expect(unit([1e-300, 0, 0])).toBeNull();
    expect(unit([1e-170, 0, 0])).toBeNull();
  });

  it("REFUSES a direction distilled from rounding noise", () => {
    // The realistic one, at CAD magnitudes: the cross product of two nearly
    // antiparallel face normals. `axisAnchor` and `gauge` both returned a
    // confident [0,0,1] built from 1e-11 of float error.
    const noise = cross([1, 0, 0], [-1, 1e-11, 0]);
    expect(mag(noise)).toBe(1e-11);
    expect(unit(noise)).toBeNull();
  });

  it("normalises an ENORMOUS vector rather than collapsing it to zero", () => {
    // `Math.sqrt(dot(a,a))` overflows to Infinity above |a| = 1.34e154, and
    // `scale(a, 1/Infinity)` is `[0,0,0]`. `Math.hypot` has no such range.
    expect(unit([1e200, 0, 0])).toEqual([1, 0, 0]);
    expect(unit([0, 1e155, 0])).toEqual([0, 1, 0]);
  });

  it("returns a vector of length 1 or null — never anything else", () => {
    // The invariant stated directly, swept across 18 decades in both
    // directions. This is the assertion that would have caught all four
    // divergences at once; each case above says WHICH copy it catches.
    for (let e = -320; e <= 300; e += 4) {
      const m = Number(`1e${e}`);
      for (const v of [
        [m, 0, 0],
        [0, m, 0],
        [m, m, m],
        [-m, m, -m],
      ] as Vec3[]) {
        const u = unit(v);
        if (u === null) continue;
        expect(mag(u)).toBeCloseTo(1, 12);
      }
    }
  });

  it("refuses NaN and Infinity rather than propagating them into a pose", () => {
    expect(unit([NaN, 0, 0])).toBeNull();
    expect(unit([Infinity, 0, 0])).toBeNull();
    expect(unit([0, -Infinity, 0])).toBeNull();
  });

  it("puts the refusal at VEC3_UNIT_FLOOR, exclusive", () => {
    // The floor is a named picometre, not a `0` — see the module note for why
    // `l > 0` becomes an Inf/NaN generator the moment `length` is correct.
    expect(unit([VEC3_UNIT_FLOOR, 0, 0])).toBeNull();
    expect(mag(unit([VEC3_UNIT_FLOOR * 2, 0, 0]) as Vec3)).toBeCloseTo(1, 12);
    // Five decades below the kernel's own 1e-4 mm linear tolerance, so it
    // cannot swallow a direction the kernel considers real.
    expect(VEC3_UNIT_FLOOR).toBeLessThan(1e-4 / 1e4);
  });
});

describe("length — Math.hypot, and why that is not a detail", () => {
  it("agrees with the naive form at every magnitude a part uses", () => {
    for (const v of [
      [3, 4, 0],
      [1, 1, 1],
      [1e-4, 2e-4, 3e-4],
      [1200, -340, 56],
    ] as Vec3[]) {
      expect(length(v)).toBeCloseTo(Math.sqrt(dot(v, v)), 12);
    }
  });

  it("survives the range where the naive form overflows and underflows", () => {
    expect(Math.sqrt(dot([1e200, 0, 0], [1e200, 0, 0]))).toBe(Infinity); // control
    expect(length([1e200, 0, 0])).toBe(1e200);
    expect(Math.sqrt(dot([1e-170, 0, 0], [1e-170, 0, 0]))).toBe(0); // control
    expect(length([1e-170, 0, 0])).toBe(1e-170);
  });
});

describe("negate — the -0 normalisation, promoted from faceAnchor", () => {
  it("turns -0 components into +0 so two identical directions compare equal", () => {
    // `-0` compares unequal in a deep comparison and prints as `-0` in a
    // readout: a difference between two identical directions that nothing can
    // act on. The naive `-a` is the control.
    const naive = ([0, 1, -0] as Vec3).map((x) => -x);
    expect(Object.is(naive[0], -0)).toBe(true);
    expect(Object.is(negate([0, 1, -0])[0], -0)).toBe(false);
    expect(negate([0, 1, -0])).toEqual([0, -1, 0]);
  });

  it("is its own inverse on ordinary directions", () => {
    expect(negate(negate([0.6, -0.8, 0]))).toEqual([0.6, -0.8, 0]);
  });
});

describe("reject — the component across a unit axis", () => {
  it("removes everything along the axis and nothing across it", () => {
    const axis: Vec3 = [0, 0, 1];
    const r = reject([3, 4, 9], axis);
    expect(r).toEqual([3, 4, 0]);
    expect(dot(r, axis)).toBeCloseTo(0, 12);
  });

  it("leaves nothing to normalise when the input IS the axis", () => {
    // The case `edgeAnchor` relies on refusing: a face centroid that lands on
    // the edge line has no outward direction.
    expect(unit(reject([0, 0, 5], [0, 0, 1]))).toBeNull();
  });
});

describe("the arithmetic the four copies agreed on, pinned once", () => {
  it("adds, subtracts, scales and fuses", () => {
    expect(add([1, 2, 3], [10, 20, 30])).toEqual([11, 22, 33]);
    expect(sub([1, 2, 3], [10, 20, 30])).toEqual([-9, -18, -27]);
    expect(scale([1, 2, 3], -2)).toEqual([-2, -4, -6]);
    expect(addScaled([1, 2, 3], [0, 0, 1], 5)).toEqual([1, 2, 8]);
  });

  it("crosses right-handed, and gives zero for parallel inputs", () => {
    expect(cross([1, 0, 0], [0, 1, 0])).toEqual([0, 0, 1]);
    expect(cross([0, 1, 0], [1, 0, 0])).toEqual([0, 0, -1]);
    // `toEqual` distinguishes `-0`, and a cross product produces them freely
    // (`0*0 - 1*0` is `-0`). Assert the MAGNITUDE: the signed-zero spelling is
    // not a property any caller can act on, which is the whole argument behind
    // `negate`'s `+ 0` above. Nothing here normalises it, and nothing did
    // before — `unit` refuses a zero-length input by length, not by spelling.
    expect(mag(cross([1, 0, 0], [1, 0, 0]))).toBe(0);
    expect(mag(cross([1, 0, 0], [-1, 0, 0]))).toBe(0);
  });

  it("dots", () => {
    expect(dot([1, 2, 3], [4, 5, 6])).toBe(32);
    expect(dot([1, 0, 0], [0, 1, 0])).toBe(0);
  });
});
