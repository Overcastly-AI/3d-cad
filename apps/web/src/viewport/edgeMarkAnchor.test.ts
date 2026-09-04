/**
 * PICKMARK-OCCLUDE-1 — where a pick diamond sits on its own edge.
 *
 * Four decisions worth pinning here, all of them ones a screenshot cannot
 * check: that a seat is an ARC-LENGTH fraction and never a vertex index (an
 * index-based "middle" is the END VERTEX of a straight edge, i.e. a corner);
 * that the mid-span WINS whenever it is addressable; that a mark which must
 * move lands in the MIDDLE of the visible stretch rather than on its silhouette
 * boundary; and that the search stays inside a fixed per-edge sample budget.
 */
import { describe, expect, it } from "vitest";

import type { Vec3 } from "../api/measure";
import { polylineAt, polylineMidpoint } from "../measure/geometry";
import {
  ANCHOR_END_INSET,
  ANCHOR_FRAME_BUDGET,
  ANCHOR_SAMPLE_BUDGET,
  anchorCandidates,
  chooseAnchor,
} from "./edgeMarkAnchor";

/** Addressable exactly on the listed candidate fractions (within 1e-9). */
const answersAt = (fractions: readonly number[]) => (t: number) =>
  fractions.some((f) => Math.abs(f - t) < 1e-9);

describe("anchorCandidates", () => {
  it("puts the mid-span first, because that is the convention", () => {
    expect(anchorCandidates()[0]).toBe(0.5);
    expect(anchorCandidates(3)[0]).toBe(0.5);
  });

  it("NEVER offers an edge's endpoint — an endpoint is a shared corner", () => {
    for (const c of anchorCandidates()) {
      expect(c).toBeGreaterThanOrEqual(ANCHOR_END_INSET - 1e-9);
      expect(c).toBeLessThanOrEqual(1 - ANCHOR_END_INSET + 1e-9);
    }
  });

  it("stays within the budget", () => {
    for (const budget of [1, 2, 5, 9, 33]) {
      expect(anchorCandidates(budget).length).toBeLessThanOrEqual(budget + 1);
    }
  });

  it("reaches both inset ends — a mark must escape onto a visible tip", () => {
    const c = anchorCandidates();
    expect(Math.min(...c)).toBeCloseTo(ANCHOR_END_INSET, 9);
    expect(Math.max(...c)).toBeCloseTo(1 - ANCHOR_END_INSET, 9);
  });

  it("orders outward from the mid-span, so a mark moves as little as it must", () => {
    const gaps = anchorCandidates().map((t) => Math.abs(t - 0.5));
    expect([...gaps].sort((a, b) => a - b)).toEqual(gaps);
  });
});

describe("chooseAnchor", () => {
  it("keeps the mid-span when the band answers there", () => {
    expect(chooseAnchor(() => true)).toEqual({ at: 0.5, buried: false });
  });

  it("costs ONE test in that common case — the whole frame budget depends on it", () => {
    let tests = 0;
    chooseAnchor(() => {
      tests += 1;
      return true;
    });
    expect(tests).toBe(1);
  });

  it("seats on the MIDDLE of the addressable run, not its first point", () => {
    // The near quarter answers; the rest of the edge is behind material.
    // Taking the first hit would park the diamond on the silhouette, where half
    // its corridor runs off the geometry.
    const ordered = [...anchorCandidates()].sort((a, b) => a - b);
    const run = ordered.slice(0, 3);
    expect(chooseAnchor(answersAt(run))).toEqual({
      at: run[1],
      buried: false,
    });
  });

  it("prefers the LONGEST run when the edge answers in two places", () => {
    const ordered = [...anchorCandidates()].sort((a, b) => a - b);
    const short = ordered.slice(0, 1);
    const long = ordered.slice(5, 9);
    const anchor = chooseAnchor(answersAt([...short, ...long]));
    expect(anchor.buried).toBe(false);
    expect(long).toContain(anchor.at);
    expect(short).not.toContain(anchor.at);
  });

  it("is a pure function of the current answers — no memory to go stale", () => {
    const ordered = [...anchorCandidates()].sort((a, b) => a - b);
    const oracle = answersAt(ordered.slice(0, 3));
    expect(chooseAnchor(oracle)).toEqual(chooseAnchor(oracle));
  });

  it("reports BURIED, at the conventional seat, when nothing answers", () => {
    expect(chooseAnchor(() => false)).toEqual({ at: 0.5, buried: true });
  });

  it("never spends more than the sample budget on one edge", () => {
    let tests = 0;
    chooseAnchor(() => {
      tests += 1;
      return false;
    }, ANCHOR_SAMPLE_BUDGET);
    expect(tests).toBeLessThanOrEqual(ANCHOR_SAMPLE_BUDGET + 1);
  });
});

describe("the seat is an arc-length fraction of the SAME interpolation", () => {
  /**
   * The guard that stops the moving mark and the still one drifting apart: a
   * seat of 0.5 must be exactly the point the accessible name describes.
   */
  it("agrees with polylineMidpoint at t = 0.5", () => {
    const line: Vec3[] = [
      { x: 0, y: 0, z: 0 },
      { x: 10, y: 0, z: 0 },
      { x: 10, y: 40, z: 0 },
    ];
    expect(polylineAt(line, 0.5)).toEqual(polylineMidpoint(line));
  });

  it("puts a STRAIGHT edge's mid-span between its ends, not on one", () => {
    // The defect an index-based parameterisation shipped: a straight edge's
    // polyline is [start, end], so index round((2-1)/2) = 1 is the END VERTEX
    // — a corner shared with two neighbours, where their corridors are as close
    // as this edge's own.
    const line: Vec3[] = [
      { x: -20, y: 0, z: 0 },
      { x: 20, y: 0, z: 0 },
    ];
    expect(polylineAt(line, 0.5)).toEqual({ x: 0, y: 0, z: 0 });
  });

  it("clamps out-of-range fractions to the edge", () => {
    const line: Vec3[] = [
      { x: 0, y: 0, z: 0 },
      { x: 4, y: 0, z: 0 },
    ];
    expect(polylineAt(line, -1)).toEqual({ x: 0, y: 0, z: 0 });
    expect(polylineAt(line, 2)).toEqual({ x: 4, y: 0, z: 0 });
  });
});

describe("the frame budget", () => {
  /**
   * MEASURED at 0.259-0.270 ms per band+surface hit-test on the reference
   * coupling at 1600x1000. The cap exists so the worst recompute is a fraction
   * of a 60 fps frame no matter how many edges a part has; if either number
   * moves, this is the arithmetic that has to be redone.
   */
  it("keeps the worst recompute inside a 60 fps frame", () => {
    const MEASURED_MS_PER_TEST = 0.27;
    expect(ANCHOR_FRAME_BUDGET * MEASURED_MS_PER_TEST).toBeLessThan(1000 / 60);
  });

  it("is big enough to finish an average edge in one frame", () => {
    expect(ANCHOR_FRAME_BUDGET).toBeGreaterThanOrEqual(ANCHOR_SAMPLE_BUDGET);
  });
});
