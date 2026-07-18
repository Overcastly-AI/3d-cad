import { describe, expect, it } from "vitest";

import { SPLINE_SAMPLES_PER_SEGMENT, sampleSpline } from "./spline";

const p = (x: number, y: number) => ({ x, y });

/** Does `poly` contain a vertex within `eps` of `q`? */
function contains(
  poly: { x: number; y: number }[],
  q: { x: number; y: number },
) {
  return poly.some((v) => Math.hypot(v.x - q.x, v.y - q.y) < 1e-9);
}

describe("sampleSpline", () => {
  it("passes exactly through every fit point (interpolating)", () => {
    const fits = [p(0, 0), p(10, 20), p(30, 5), p(45, 25), p(60, 0)];
    const poly = sampleSpline(fits);
    for (const fit of fits) {
      expect(contains(poly, fit)).toBe(true);
    }
    // Endpoints land on the first/last fit point.
    expect(poly[0]).toEqual(fits[0]);
    expect(poly[poly.length - 1]).toEqual(fits[fits.length - 1]);
  });

  it("emits (n-1)·samples + 1 vertices — one shared boundary per span", () => {
    const fits = [p(0, 0), p(10, 10), p(20, 0), p(30, 10)];
    const poly = sampleSpline(fits, 8);
    expect(poly).toHaveLength((fits.length - 1) * 8 + 1);
  });

  it("renders two fit points as a straight segment (collinear samples)", () => {
    const poly = sampleSpline([p(0, 0), p(40, 20)], 10);
    for (const v of poly) {
      // Every vertex is on the line y = x/2 (cross product zero).
      expect(v.x * 20 - v.y * 40).toBeCloseTo(0, 9);
    }
    // Monotonic in x — no doubling back on a straight run.
    const xs = poly.map((v) => v.x);
    expect([...xs].sort((a, b) => a - b)).toEqual(xs);
  });

  it("stays within a sane band of the fit hull (no wild overshoot)", () => {
    const fits = [p(0, 0), p(10, 30), p(20, 0)];
    const poly = sampleSpline(fits);
    // Centripetal Catmull-Rom does not overshoot far past the fit extent
    // (fit hull peaks at y = 30; a wild uniform-CR bulge would blow past it).
    for (const v of poly) {
      expect(v.y).toBeGreaterThanOrEqual(-5);
      expect(v.y).toBeLessThanOrEqual(35);
    }
  });

  it("degrades gracefully: 0 or 1 point returns the points as-is", () => {
    expect(sampleSpline([])).toEqual([]);
    expect(sampleSpline([p(3, 4)])).toEqual([p(3, 4)]);
  });

  it("defaults to the module sample rate", () => {
    const poly = sampleSpline([p(0, 0), p(10, 0)]);
    expect(poly).toHaveLength(SPLINE_SAMPLES_PER_SEGMENT + 1);
  });
});
