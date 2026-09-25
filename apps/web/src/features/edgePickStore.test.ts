import { beforeEach, describe, expect, it } from "vitest";

import type { OverlayResult } from "../api/measure";
import type { EdgeSignature } from "../api/parts";
import { useEdgePickStore } from "./edgePickStore";

const A: EdgeSignature = {
  curve: "line",
  end_a: { x: 0, y: 0, z: 2 },
  end_b: { x: 50, y: 0, z: 2 },
  midpoint: { x: 25, y: 0, z: 2 },
  length_mm: 50,
  subshape_type: "edge",
};
const B: EdgeSignature = {
  curve: "line",
  end_a: { x: 50, y: 0, z: 2 },
  end_b: { x: 50, y: 20, z: 2 },
  midpoint: { x: 50, y: 10, z: 2 },
  length_mm: 20,
  subshape_type: "edge",
};

describe("edge-pick store selection modes", () => {
  beforeEach(() => useEdgePickStore.getState().close());

  it("multi-select (fillet/chamfer) accumulates picks", () => {
    const store = useEdgePickStore.getState();
    store.open([], true);
    store.toggle(A);
    store.toggle(B);
    expect(useEdgePickStore.getState().picked).toEqual([A, B]);
    // A repeat click removes just that edge.
    store.toggle(A);
    expect(useEdgePickStore.getState().picked).toEqual([B]);
  });

  it("single-select (edge flange) replaces the pick on each click", () => {
    const store = useEdgePickStore.getState();
    store.open([], true, true);
    store.toggle(A);
    expect(useEdgePickStore.getState().picked).toEqual([A]);
    // A different edge replaces, never accumulates.
    store.toggle(B);
    expect(useEdgePickStore.getState().picked).toEqual([B]);
    // Clicking the current edge clears it.
    store.toggle(B);
    expect(useEdgePickStore.getState().picked).toEqual([]);
  });
});

/**
 * RE-PICK THE MOVED EDGES (EDGE-RESOLVE-WARN-1).
 *
 * A pick whose signature is no longer an edge of the body it is picked on has
 * moved: the kernel re-found it by adjacency, and the user is asked to check
 * it. Re-picking drops exactly those and keeps every pick that still names a
 * real edge, so a four-edge fillet with one moved corner loses one pick, not
 * four. The body's edges arrive with the overlay, so a re-pick asked for
 * before then waits for it.
 */
describe("repickMoved", () => {
  beforeEach(() => useEdgePickStore.getState().close());

  const overlayOf = (...edges: EdgeSignature[]) =>
    ({
      vertices: [],
      edges: edges.map((signature) => ({
        kind: "line",
        start: signature.end_a,
        end: signature.end_b,
        polyline: [],
        signature,
      })),
    }) as unknown as OverlayResult;
  const MOVED: EdgeSignature = { ...B, end_a: { x: 60, y: 0, z: 2 } };

  it("drops only the picks the body no longer has, once its edges arrive", () => {
    const store = useEdgePickStore.getState();
    store.open([A, MOVED], false);
    store.repickMoved();
    // Picking is armed at once; nothing is dropped before the body is known.
    expect(useEdgePickStore.getState().picking).toBe(true);
    expect(useEdgePickStore.getState().picked).toEqual([A, MOVED]);
    store.setOverlay(overlayOf(A, B));
    expect(useEdgePickStore.getState().picked).toEqual([A]);
    // Once only: a later overlay (a refetch) does not prune a fresh pick.
    store.toggle(MOVED);
    store.setOverlay(overlayOf(A, B));
    expect(useEdgePickStore.getState().picked).toEqual([A, MOVED]);
  });

  it("drops them at once when the body's edges are already loaded", () => {
    const store = useEdgePickStore.getState();
    store.open([MOVED, A], true);
    store.setOverlay(overlayOf(A, B));
    store.repickMoved();
    expect(useEdgePickStore.getState().picked).toEqual([A]);
  });
});
