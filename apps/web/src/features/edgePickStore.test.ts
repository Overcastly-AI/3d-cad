import { beforeEach, describe, expect, it } from "vitest";

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
