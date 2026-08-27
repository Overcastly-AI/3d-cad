import { describe, expect, it } from "vitest";

import type { DimensionParams, EdgeSignature } from "../api/drawings";
import {
  IDLE,
  PLACE_NUDGE_MM,
  type EdgeTarget,
  type EndpointTarget,
  type PlaceTarget,
  armPair,
  armedSignatures,
  beginPlacement,
  beginReplacement,
  buildDimension,
  cancelPlacement,
  commitParams,
  menuActions,
  menuAnchor,
  movePlacement,
  nudgePlacement,
  pickEdge,
  pickEndpoint,
  pickHint,
  placementMoved,
  placementOffsetMm,
  placementReplaces,
  placementTarget,
  placementTextPos,
  quantise,
  setPlacementOffset,
  withPlacement,
} from "./authoring";

const vec = (x: number, y: number, z: number) => ({ x, y, z });

const lineSig = (): EdgeSignature => ({
  curve: "line",
  end_a: vec(0, 0, 0),
  end_b: vec(40, 0, 0),
  midpoint: vec(20, 0, 0),
  length_mm: 40,
  subshape_type: "edge",
});
const vertSig = (): EdgeSignature => ({
  curve: "line",
  end_a: vec(0, 0, 0),
  end_b: vec(0, 25, 0),
  midpoint: vec(0, 12.5, 0),
  length_mm: 25,
  subshape_type: "edge",
});
const circleSig = (): EdgeSignature => ({
  curve: "circle",
  end_a: vec(15, 12.5, 0),
  end_b: vec(15, 12.5, 0),
  midpoint: vec(25, 12.5, 0),
  length_mm: Math.PI * 10,
  subshape_type: "edge",
});

const edge = (
  sig: EdgeSignature,
  primitive: EdgeTarget["primitive"],
): EdgeTarget => ({
  projection: "top",
  viewId: "view-1",
  sourceEdge: sig,
  primitive,
  clientX: 10,
  clientY: 20,
});
const endpoint = (
  sig: EdgeSignature,
  end: "end_a" | "end_b",
): EndpointTarget => ({
  projection: "top",
  viewId: "view-1",
  sourceEdge: sig,
  endpoint: end,
  clientX: 30,
  clientY: 40,
});

describe("authoring pick model", () => {
  it("a circle pick offers diameter + radius", () => {
    const state = pickEdge(IDLE, edge(circleSig(), "circle"));
    expect(state.kind).toBe("single-edge");
    expect(menuActions(state)).toEqual(["diameter", "radius"]);
    expect(menuAnchor(state)).toEqual({ x: 10, y: 20 });
  });

  it("an arc pick offers radius only", () => {
    const state = pickEdge(IDLE, edge(circleSig(), "arc"));
    expect(menuActions(state)).toEqual(["radius"]);
  });

  it("a straight edge offers linear + both two-edge arms", () => {
    const state = pickEdge(IDLE, edge(lineSig(), "line"));
    expect(menuActions(state)).toEqual([
      "linear",
      "start_angular",
      "start_edge_to_edge",
    ]);
  });

  it("arming angular then picking a second edge readies an angular dimension", () => {
    const first = pickEdge(IDLE, edge(lineSig(), "line"));
    const armed = armPair(first, "angular");
    expect(armed.kind).toBe("arming-pair");
    expect(pickHint(armed)).toMatch(/second edge/i);
    expect(menuActions(armed)).toEqual([]); // no menu while a pick is pending

    const ready = pickEdge(armed, edge(vertSig(), "line"));
    expect(ready.kind).toBe("pair-ready");
    // Both two-edge types, the armed intent first — a mis-entry is one click
    // away from the other, never a dead end.
    expect(menuActions(ready)).toEqual(["angular", "edge_to_edge"]);

    const built = buildDimension(ready, "angular");
    expect(built?.viewId).toBe("view-1");
    expect(built?.params.type).toBe("angular");
    if (built?.params.type !== "angular") return;
    expect(built.params.edge_a.length_mm).toBe(40);
    expect(built.params.edge_b.length_mm).toBe(25);
  });

  it("arming edge-to-edge readies the across-the-wall linear, that type first", () => {
    const armed = armPair(
      pickEdge(IDLE, edge(lineSig(), "line")),
      "edge_to_edge",
    );
    expect(pickHint(armed)).toMatch(/measure across/i);

    const ready = pickEdge(armed, edge(vertSig(), "line"));
    expect(ready.kind).toBe("pair-ready");
    expect(menuActions(ready)).toEqual(["edge_to_edge", "angular"]);

    const built = buildDimension(ready, "edge_to_edge");
    expect(built?.viewId).toBe("view-1");
    expect(built?.params.type).toBe("linear");
    if (built?.params.type !== "linear") return;
    expect(built.params.measurement.mode).toBe("edge_to_edge");
    if (built.params.measurement.mode !== "edge_to_edge") return;
    // Names the two EDGES — not two endpoints, which is the whole point (FB-10).
    expect(built.params.measurement.edge_a.length_mm).toBe(40);
    expect(built.params.measurement.edge_b.length_mm).toBe(25);
  });

  it("re-picking the SAME edge while arming does not complete a pair", () => {
    const armed = armPair(pickEdge(IDLE, edge(lineSig(), "line")), "angular");
    const again = pickEdge(armed, edge(lineSig(), "line"));
    // Same edge → falls back to a fresh single-edge selection, not pair-ready.
    expect(again.kind).toBe("single-edge");
  });

  it("a start_* action only arms — it never authors", () => {
    const state = pickEdge(IDLE, edge(lineSig(), "line"));
    expect(buildDimension(state, "start_angular")).toBeNull();
    expect(buildDimension(state, "start_edge_to_edge")).toBeNull();
    expect(buildDimension(state, "linear")?.params.type).toBe("linear");
  });

  it("two endpoints ready a point-to-point linear naming both vertices", () => {
    const one = pickEndpoint(IDLE, endpoint(lineSig(), "end_b"));
    expect(one.kind).toBe("one-endpoint");
    expect(pickHint(one)).toMatch(/second point/i);
    expect(menuActions(one)).toEqual([]);

    const ready = pickEndpoint(one, endpoint(vertSig(), "end_b"));
    expect(ready.kind).toBe("p2p-ready");
    expect(menuActions(ready)).toEqual(["point_to_point"]);

    const built = buildDimension(ready, "point_to_point");
    expect(built?.params.type).toBe("linear");
    if (built?.params.type !== "linear") return;
    expect(built.params.measurement.mode).toBe("point_to_point");
    if (built.params.measurement.mode !== "point_to_point") return;
    expect(built.params.measurement.a.endpoint).toBe("end_b");
    expect(built.params.measurement.b.signature.length_mm).toBe(25);
  });

  it("re-picking the SAME endpoint does not complete a pair", () => {
    const one = pickEndpoint(IDLE, endpoint(lineSig(), "end_b"));
    const again = pickEndpoint(one, endpoint(lineSig(), "end_b"));
    expect(again.kind).toBe("one-endpoint");
  });

  it("picking an edge after an endpoint resets to the edge (no mixed pair)", () => {
    const one = pickEndpoint(IDLE, endpoint(lineSig(), "end_b"));
    const switched = pickEdge(one, edge(circleSig(), "circle"));
    expect(switched.kind).toBe("single-edge");
  });
});

// --- the PLACE stage (REACH-3) --------------------------------------------
// `DimensionPlacement` shipped in the contract and was honoured by the composer
// from day one, and the app never sent it — so a user could not put a dimension
// anywhere. These cover the seam that changed that: the type choice now arms a
// placement, the pointer (or the arrow keys) sets it, and the committed params
// carry it.

/** A pick that knows where it landed on the composed sheet. */
const placedEdge = (
  sig: EdgeSignature,
  primitive: EdgeTarget["primitive"],
  geometry: NonNullable<EdgeTarget["geometry"]>,
): EdgeTarget => ({ ...edge(sig, primitive), geometry });

/** A 40 mm horizontal edge 10 mm BELOW its view centre (sheet space is y-down). */
const LINE_GEOM = {
  line: { a: { x: 0, y: 110 }, b: { x: 40, y: 110 } },
  circle: null,
  viewAnchor: { x: 20, y: 100 },
};
const CIRCLE_GEOM = {
  line: null,
  circle: { center: { x: 20, y: 100 }, radius: 5 },
  viewAnchor: { x: 20, y: 100 },
};

describe("re-placing a dimension already on the paper", () => {
  const TARGET: PlaceTarget = {
    mode: "offset",
    span: { a: { x: 0, y: 110 }, b: { x: 40, y: 110 } },
    viewAnchor: { x: 20, y: 100 },
    offsetMm: 11,
  };
  const BASE: DimensionParams = {
    type: "linear",
    measurement: { mode: "edge_length", edge: lineSig() },
    placement: { offset_mm: -30.48 },
  };

  it("re-enters the PLACE stage, naming the row it replaces", () => {
    const state = beginReplacement("dim-1", "view-1", BASE, TARGET);
    expect(state.kind).toBe("placing");
    expect(placementReplaces(state)).toBe("dim-1");
    expect(placementOffsetMm(state)).toBe(11);
    // Escape goes to idle — there is no earlier pick to preserve, and the
    // dimension it came from is still on the paper.
    expect(cancelPlacement(state)).toEqual(IDLE);
  });

  it("strips the OLD placement, so the commit writes a fresh one", () => {
    let state = beginReplacement("dim-1", "view-1", BASE, TARGET);
    state = setPlacementOffset(state, -25);
    const commit = commitParams(state);
    // Not merged into the stale -30.48 it was carrying.
    expect(commit?.params.placement).toEqual({ offset_mm: -25 });
  });

  it("commits NOTHING when it was never moved", () => {
    // Grab-and-drop-in-place must not cost a delete, an append and a new id
    // for no change on the paper.
    const state = beginReplacement("dim-1", "view-1", BASE, TARGET);
    expect(placementMoved(state)).toBe(false);
    expect(commitParams(state)).toBeNull();
    // …whereas a fresh authoring commit with `moved: false` still POSTs, at
    // auto placement — that is the untouched fast path and it must survive.
    const picked = pickEdge(IDLE, placedEdge(lineSig(), "line", LINE_GEOM));
    const built = buildDimension(picked, "linear");
    const fresh = beginPlacement(
      picked,
      built!.viewId,
      built!.params,
      placementTarget(picked, "linear")!,
    );
    expect(commitParams(fresh)?.params.placement).toBeUndefined();
  });

  it("reports nothing to replace for a fresh authoring placement", () => {
    const picked = pickEdge(IDLE, placedEdge(lineSig(), "line", LINE_GEOM));
    const built = buildDimension(picked, "linear");
    const fresh = beginPlacement(
      picked,
      built!.viewId,
      built!.params,
      placementTarget(picked, "linear")!,
    );
    expect(placementReplaces(fresh)).toBeNull();
    expect(placementReplaces(IDLE)).toBeNull();
  });
});

describe("quantise", () => {
  it("snaps to the nearest multiple of the step, in both signs", () => {
    expect(quantise(-23.71, 1)).toBe(-24);
    expect(quantise(23.71, 1)).toBe(24);
    expect(quantise(-23.71, 5)).toBe(-25);
    expect(quantise(0.4, 1)).toBe(0);
    // Already on the grid stays put — a nudge must never cost a dead press.
    expect(quantise(-25, 1)).toBe(-25);
    // And the result is CLEAN: 3 * 0.1 must not read 0.30000000000000004 in a
    // field a user is about to trust.
    expect(quantise(0.31, 0.1)).toBe(0.3);
  });

  it("is the identity for a step that is not a step", () => {
    expect(quantise(-23.71, 0)).toBe(-23.71);
    expect(quantise(-23.71, Number.NaN)).toBe(-23.71);
  });
});

describe("dimension placement", () => {
  it("arms an offset placement from a straight-edge linear pick", () => {
    const picked = pickEdge(IDLE, placedEdge(lineSig(), "line", LINE_GEOM));
    const target = placementTarget(picked, "linear");
    expect(target?.mode).toBe("offset");
    // Seeded at the composer's own auto offset, so the ghost opens exactly
    // where the dimension would have landed without this stage.
    expect(target && "offsetMm" in target && target.offsetMm).toBe(11);
  });

  it("arms a TEXT placement from a circle pick (offset_mm is linear-only)", () => {
    const picked = pickEdge(
      IDLE,
      placedEdge(circleSig(), "circle", CIRCLE_GEOM),
    );
    const target = placementTarget(picked, "diameter");
    expect(target?.mode).toBe("text");
    // Seated clear of the rim, above the hole (sheet space is y-down).
    expect(target && "textPos" in target && target.textPos).toEqual({
      x: 20,
      y: 84,
    });
  });

  it("declines to place a pick that carried no composed geometry", () => {
    // The pre-REACH-3 path: no geometry to measure against, so the caller
    // authors at auto placement rather than opening a stage it cannot draw.
    const picked = pickEdge(IDLE, edge(lineSig(), "line"));
    expect(placementTarget(picked, "linear")).toBeNull();
  });

  it("tracks the pointer into offset_mm and says so in the hint", () => {
    const picked = pickEdge(IDLE, placedEdge(lineSig(), "line", LINE_GEOM));
    const target = placementTarget(picked, "linear");
    const built = buildDimension(picked, "linear");
    let state = beginPlacement(picked, built!.viewId, built!.params, target!);
    expect(pickHint(state)).toBe("Click to place the dimension");
    // 24 mm below the edge, on the side away from the view centre.
    state = movePlacement(state, { x: 20, y: 134 });
    expect(placementOffsetMm(state)).toBeCloseTo(24, 9);
    const params = withPlacement(
      (state as { base: DimensionParams }).base,
      (state as { target: PlaceTarget }).target,
    );
    expect(params.placement).toEqual({ offset_mm: 24 });
  });

  it("nudges the offset by the keyboard step, coarse on Shift", () => {
    const picked = pickEdge(IDLE, placedEdge(lineSig(), "line", LINE_GEOM));
    const built = buildDimension(picked, "linear");
    const target = placementTarget(picked, "linear");
    let state = beginPlacement(picked, built!.viewId, built!.params, target!);
    state = nudgePlacement(state, 0, -1); // ArrowUp — further out
    expect(placementOffsetMm(state)).toBeCloseTo(11 + PLACE_NUDGE_MM, 9);
    // Shift coarsens to a 5 mm step, and the value quantises to THAT grid
    // first: 12 is not on it, so Shift+ArrowDown lands on 10 - 5 = 5, not on
    // 12 - 5 = 7. A coarse step that preserves a fine remainder is not a
    // coarse step at all.
    state = nudgePlacement(state, 0, 1, PLACE_NUDGE_MM * 5);
    expect(placementOffsetMm(state)).toBeCloseTo(5, 9);
  });

  it("a nudge QUANTISES, so a round offset is always one press away", () => {
    // The exact sequence frontend-QA measured on 2026-08-27 (P1-D): a drag
    // left -23.71 behind and the nudge ADDED to it —
    //     -23.71 -> -22.71 -> -17.71
    // so -25.00 was not reachable at all, and two hand-placed dimensions could
    // never be given the same offset. This is the negative control for that.
    const picked = pickEdge(IDLE, placedEdge(lineSig(), "line", LINE_GEOM));
    const built = buildDimension(picked, "linear");
    const target = placementTarget(picked, "linear");
    let state = beginPlacement(picked, built!.viewId, built!.params, target!);
    state = setPlacementOffset(state, -23.71);
    expect(placementOffsetMm(state)).toBeCloseTo(-23.71, 9);

    // One press DOWN and the answer is exactly -25.00, not -24.71.
    state = nudgePlacement(state, 0, 1);
    expect(placementOffsetMm(state)).toBe(-25);
    // And it STAYS on the grid from there, in both directions.
    state = nudgePlacement(state, 0, 1);
    expect(placementOffsetMm(state)).toBe(-26);
    state = nudgePlacement(state, 0, -1);
    expect(placementOffsetMm(state)).toBe(-25);
    // …so a second dimension dragged to a different fraction reaches the SAME
    // offset — which is what lining a chain up actually requires.
    let other = beginPlacement(picked, built!.viewId, built!.params, target!);
    other = setPlacementOffset(other, -24.38);
    other = nudgePlacement(other, 0, 1);
    expect(placementOffsetMm(other)).toBe(placementOffsetMm(state));
  });

  it("takes an exact typed offset, and sends it verbatim", () => {
    const picked = pickEdge(IDLE, placedEdge(lineSig(), "line", LINE_GEOM));
    const built = buildDimension(picked, "linear");
    const target = placementTarget(picked, "linear");
    let state = beginPlacement(picked, built!.viewId, built!.params, target!);
    state = setPlacementOffset(state, -25);
    expect(placementOffsetMm(state)).toBe(-25);
    const params = withPlacement(
      (state as { base: DimensionParams }).base,
      (state as { target: PlaceTarget }).target,
    );
    // -30.48 is what the review found persisted from a hand placement; -25.00
    // is what a precision tool has to be able to store.
    expect(params.placement).toEqual({ offset_mm: -25 });

    // A half-typed value never moves the ghost to nowhere.
    expect(placementOffsetMm(setPlacementOffset(state, Number.NaN))).toBe(-25);
    // And a TEXT placement has no scalar to set — it is left untouched.
    const circle = pickEdge(
      IDLE,
      placedEdge(circleSig(), "circle", CIRCLE_GEOM),
    );
    const textBuilt = buildDimension(circle, "diameter");
    const textTarget = placementTarget(circle, "diameter");
    const textState = beginPlacement(
      circle,
      textBuilt!.viewId,
      textBuilt!.params,
      textTarget!,
    );
    expect(setPlacementOffset(textState, -25)).toBe(textState);
  });

  it("quantises BOTH axes of a text seat, so two stamps can line up", () => {
    const picked = pickEdge(
      IDLE,
      placedEdge(circleSig(), "circle", CIRCLE_GEOM),
    );
    const built = buildDimension(picked, "diameter");
    const target = placementTarget(picked, "diameter");
    let state = beginPlacement(picked, built!.viewId, built!.params, target!);
    state = movePlacement(state, { x: 62.345, y: 41.111 });
    // Nudging sideways used to leave y fractional for ever.
    state = nudgePlacement(state, 1, 0);
    expect(placementTextPos(state)).toEqual({ x_mm: 63, y_mm: 41 });
  });

  it("commits a text placement as text_pos, verbatim in sheet mm", () => {
    const picked = pickEdge(
      IDLE,
      placedEdge(circleSig(), "circle", CIRCLE_GEOM),
    );
    const built = buildDimension(picked, "diameter");
    const target = placementTarget(picked, "diameter");
    let state = beginPlacement(picked, built!.viewId, built!.params, target!);
    state = movePlacement(state, { x: 62.345, y: 41.111 });
    expect(placementTextPos(state)).toEqual({ x_mm: 62.345, y_mm: 41.111 });
    const params = withPlacement(
      (state as { base: DimensionParams }).base,
      (state as { target: PlaceTarget }).target,
    );
    expect(params.placement).toEqual({
      offset_mm: 0,
      text_pos: { x_mm: 62.35, y_mm: 41.11 },
    });
  });

  it("sends NO placement at a zero offset — 0 is the composer's auto sentinel", () => {
    const picked = pickEdge(IDLE, placedEdge(lineSig(), "line", LINE_GEOM));
    const built = buildDimension(picked, "linear");
    const target = placementTarget(picked, "linear");
    let state = beginPlacement(picked, built!.viewId, built!.params, target!);
    state = movePlacement(state, { x: 20, y: 110 }); // right on the edge
    const params = withPlacement(
      (state as { base: DimensionParams }).base,
      (state as { target: PlaceTarget }).target,
    );
    expect(params.placement).toBeUndefined();
  });

  it("commits with NO placement until the user actually moves it", () => {
    // The compatibility promise: pick, choose, Enter is the pre-REACH-3
    // auto-placed dimension, byte for byte. The new control costs nobody
    // anything who does not reach for it.
    const picked = pickEdge(IDLE, placedEdge(lineSig(), "line", LINE_GEOM));
    const built = buildDimension(picked, "linear");
    const target = placementTarget(picked, "linear");
    const untouched = beginPlacement(
      picked,
      built!.viewId,
      built!.params,
      target!,
    );
    expect(commitParams(untouched)?.params.placement).toBeUndefined();
    // …and the moment it IS moved, the placement goes with it.
    const nudged = nudgePlacement(untouched, 0, -1);
    expect(commitParams(nudged)?.params.placement).toEqual({ offset_mm: 12 });
  });

  it("Escape from a placement keeps the pick that led to it", () => {
    const picked = pickEdge(IDLE, placedEdge(lineSig(), "line", LINE_GEOM));
    const built = buildDimension(picked, "linear");
    const target = placementTarget(picked, "linear");
    const state = beginPlacement(picked, built!.viewId, built!.params, target!);
    expect(cancelPlacement(state)).toEqual(picked);
    // …and the edge stays lit while placing, so the pick never looks lost.
    expect(armedSignatures(state)).toEqual(armedSignatures(picked));
  });

  it("places an edge-to-edge wall thickness across the two picked walls", () => {
    const wallA = placedEdge(lineSig(), "line", LINE_GEOM);
    const wallB = placedEdge(vertSig(), "line", {
      line: { a: { x: 0, y: 96 }, b: { x: 40, y: 96 } },
      circle: null,
      viewAnchor: { x: 20, y: 100 },
    });
    const armed = armPair(pickEdge(IDLE, wallA), "edge_to_edge");
    const ready = pickEdge(armed, wallB);
    const target = placementTarget(ready, "edge_to_edge");
    expect(target?.mode).toBe("offset");
    // Squared from wall A's midpoint onto wall B's supporting line.
    expect(target && "span" in target && target.span).toEqual({
      a: { x: 20, y: 110 },
      b: { x: 20, y: 96 },
    });
  });
});
