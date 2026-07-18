/**
 * Measure-store transitions — the pick machine and, critically, the guard that
 * a body-changing edit (rollback / tree mutation) can never leave stale picks
 * indexing into a superseded overlay (a silent-mismeasurement class of bug).
 */
import { beforeEach, describe, expect, it } from "vitest";

import type { OverlayResult } from "../api/measure";
import { useMeasureStore } from "./store";

/** A minimal overlay — only its object identity matters for these tests. */
function overlay(vertexCount: number): OverlayResult {
  return {
    vertices: Array.from({ length: vertexCount }, () => ({ x: 0, y: 0, z: 0 })),
    edges: [],
    faces: [],
  };
}

beforeEach(() => {
  useMeasureStore.getState().deactivate();
});

describe("useMeasureStore", () => {
  it("accumulates two picks into a measurable pair", () => {
    const s = useMeasureStore.getState();
    s.activate();
    s.setOverlay(overlay(4));
    s.pickVertex(0, { x: 0, y: 0, z: 0 });
    s.pickEdge(1);
    expect(useMeasureStore.getState().picks).toHaveLength(2);
  });

  it("keeps picks when the SAME overlay object is set again", () => {
    const s = useMeasureStore.getState();
    s.activate();
    const o = overlay(4);
    s.setOverlay(o);
    s.pickVertex(2, { x: 1, y: 0, z: 0 });
    s.setOverlay(o); // same identity (a benign re-render)
    expect(useMeasureStore.getState().picks).toHaveLength(1);
  });

  it("clears stale picks the instant the overlay identity changes", () => {
    const s = useMeasureStore.getState();
    s.activate();
    s.setOverlay(overlay(4));
    s.pickEdge(0);
    expect(useMeasureStore.getState().picks).toHaveLength(1);
    // A rollback rebuilds the body → a DIFFERENT overlay object arrives. The
    // edge-0 pick was resolved against the old indexing; it must be dropped.
    s.setOverlay(overlay(6));
    expect(useMeasureStore.getState().picks).toEqual([]);
    expect(useMeasureStore.getState().result).toBeNull();
    expect(useMeasureStore.getState().measureError).toBeNull();
  });

  it("deactivate() drops the overlay and all picks", () => {
    const s = useMeasureStore.getState();
    s.activate();
    s.setOverlay(overlay(4));
    s.pickVertex(0, { x: 0, y: 0, z: 0 });
    s.deactivate();
    const after = useMeasureStore.getState();
    expect(after.active).toBe(false);
    expect(after.overlay).toBeNull();
    expect(after.picks).toEqual([]);
  });
});
