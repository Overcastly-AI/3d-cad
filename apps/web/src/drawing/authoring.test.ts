import { describe, expect, it } from "vitest";

import type { EdgeSignature } from "../api/drawings";
import {
  IDLE,
  type EdgeTarget,
  type EndpointTarget,
  armAngular,
  buildDimension,
  menuActions,
  menuAnchor,
  pickEdge,
  pickEndpoint,
  pickHint,
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

  it("a straight edge offers linear + the angular arm", () => {
    const state = pickEdge(IDLE, edge(lineSig(), "line"));
    expect(menuActions(state)).toEqual(["linear", "start_angular"]);
  });

  it("arming angular then picking a second edge readies an angular dimension", () => {
    const first = pickEdge(IDLE, edge(lineSig(), "line"));
    const armed = armAngular(first);
    expect(armed.kind).toBe("arming-angular");
    expect(pickHint(armed)).toMatch(/second edge/i);
    expect(menuActions(armed)).toEqual([]); // no menu while a pick is pending

    const ready = pickEdge(armed, edge(vertSig(), "line"));
    expect(ready.kind).toBe("angular-ready");
    expect(menuActions(ready)).toEqual(["angular"]);

    const built = buildDimension(ready, "angular");
    expect(built?.viewId).toBe("view-1");
    expect(built?.params.type).toBe("angular");
    if (built?.params.type !== "angular") return;
    expect(built.params.edge_a.length_mm).toBe(40);
    expect(built.params.edge_b.length_mm).toBe(25);
  });

  it("re-picking the SAME edge while arming does not complete an angle", () => {
    const armed = armAngular(pickEdge(IDLE, edge(lineSig(), "line")));
    const again = pickEdge(armed, edge(lineSig(), "line"));
    // Same edge → falls back to a fresh single-edge selection, not angular-ready.
    expect(again.kind).toBe("single-edge");
  });

  it("start_angular only arms — it never authors", () => {
    const state = pickEdge(IDLE, edge(lineSig(), "line"));
    expect(buildDimension(state, "start_angular")).toBeNull();
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
