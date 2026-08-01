/**
 * Pre-selection (UI-W3) — the rules that decide whether the cursor's last pick
 * may prefill the next command.
 *
 * The one that carries risk is rule 1: a pick belongs to the body it was taken
 * from. Get it wrong in the permissive direction and a command opens prefilled
 * with a reference the kernel cannot resolve — a feature that fails to build
 * for a reason the user never chose. Get it wrong in the strict direction and
 * the whole feature does nothing. So the anchor rule is tested from both sides.
 */
import { beforeEach, describe, expect, it } from "vitest";

import type { EdgeSignature, PlanarFaceSignature } from "../api/parts";
import {
  preselectedEdges,
  preselectedFace,
  preselectedFaces,
  usePreselectStore,
  type PreselectedFace,
} from "./preselect";

const face = (z: number): PlanarFaceSignature => ({
  normal: { x: 0, y: 0, z: 1 },
  centroid: { x: 5, y: 5, z },
  area_mm2: 100,
  subshape_type: "face",
  surface: "plane",
});

const picked = (z: number, anchorId: string): PreselectedFace => ({
  signature: face(z),
  anchorId,
});

const edge = (x: number): EdgeSignature => ({
  subshape_type: "edge",
  curve: "line",
  midpoint: { x, y: 0, z: 0 },
  length_mm: 20,
  end_a: { x: x - 10, y: 0, z: 0 },
  end_b: { x: x + 10, y: 0, z: 0 },
});

beforeEach(() => usePreselectStore.getState().clear());

describe("preselected faces — the anchor rule", () => {
  it("offers a face picked on the CURRENT body tip", () => {
    const state = { faces: [picked(10, "extrude-1")] };
    expect(preselectedFaces(state, "extrude-1")).toHaveLength(1);
    expect(preselectedFace(state, "extrude-1")?.signature.centroid.z).toBe(10);
  });

  it("withholds a face picked on a SUPERSEDED body", () => {
    // The hole drilled after the pick reshapes the face it was taken from, so
    // prefilling the next feature with it would author a reference that cannot
    // resolve. Silence is the honest answer.
    const state = { faces: [picked(10, "extrude-1")] };
    expect(preselectedFaces(state, "hole-1")).toEqual([]);
    expect(preselectedFace(state, "hole-1")).toBeNull();
  });

  it("withholds everything when there is no body at all", () => {
    expect(preselectedFace({ faces: [picked(10, "extrude-1")] }, null)).toBe(
      null,
    );
  });

  it("takes the MOST RECENT pick as the single reference — a second click corrects the first", () => {
    const state = { faces: [picked(10, "extrude-1"), picked(0, "extrude-1")] };
    expect(preselectedFace(state, "extrude-1")?.signature.centroid.z).toBe(0);
  });

  it("keeps only the live picks when a set spans two anchors", () => {
    const state = {
      faces: [picked(10, "extrude-1"), picked(0, "hole-1")],
    };
    expect(preselectedFaces(state, "hole-1")).toHaveLength(1);
    expect(preselectedFace(state, "hole-1")?.signature.centroid.z).toBe(0);
  });
});

describe("preselected edges", () => {
  const state = {
    edges: [edge(0), edge(20), edge(40)],
    edgeAnchorId: "extrude-1",
  };

  it("offers the whole set to a multi-edge verb on the current body", () => {
    expect(preselectedEdges(state, "extrude-1")).toHaveLength(3);
  });

  it("withholds the set once the body has moved on", () => {
    expect(preselectedEdges(state, "fillet-1")).toEqual([]);
  });

  it("caps a single-edge verb at the most recent pick", () => {
    const seeded = preselectedEdges(state, "extrude-1", 1);
    expect(seeded).toHaveLength(1);
    expect(seeded[0]?.midpoint.x).toBe(40);
  });
});

describe("the store", () => {
  it("remembers a face pick and hands it to the next command", () => {
    usePreselectStore.getState().rememberFaces([picked(10, "extrude-1")]);
    expect(
      preselectedFace(usePreselectStore.getState(), "extrude-1"),
    ).not.toBeNull();
  });

  it("REPLACES rather than accumulates — a pick session owns the selection", () => {
    const store = usePreselectStore.getState();
    store.rememberFaces([picked(10, "extrude-1"), picked(0, "extrude-1")]);
    store.rememberFaces([picked(5, "extrude-1")]);
    expect(preselectedFaces(usePreselectStore.getState(), "extrude-1")).toEqual(
      [picked(5, "extrude-1")],
    );
  });

  it("keeps faces and edges independent — they carry their own anchors", () => {
    const store = usePreselectStore.getState();
    store.rememberFaces([picked(10, "extrude-1")]);
    store.rememberEdges([edge(0)], "extrude-1");
    const state = usePreselectStore.getState();
    expect(preselectedFace(state, "extrude-1")).not.toBeNull();
    expect(preselectedEdges(state, "extrude-1")).toHaveLength(1);
  });

  it("clears both sets", () => {
    const store = usePreselectStore.getState();
    store.rememberFaces([picked(10, "extrude-1")]);
    store.rememberEdges([edge(0)], "extrude-1");
    store.clear();
    const state = usePreselectStore.getState();
    expect(preselectedFaces(state, "extrude-1")).toEqual([]);
    expect(preselectedEdges(state, "extrude-1")).toEqual([]);
  });
});
