import { describe, expect, it } from "vitest";

import type { OverlayEdge, Vec3 } from "../api/measure";
import { applyConstraintAction, pointDimensionEditor } from "./constraints";
import { sceneOriginBasis, faceBasis } from "./plane";
import { pointEntryOpening } from "./pointEntry";
import {
  allProjected,
  breakLinks,
  isProjected,
  PROJECTED_SUBJECT_HINT,
  projectedRefusal,
  projectedSignatures,
  sickProjections,
  type SketchProjection,
} from "./project";
import { PROJECT_SPLINE_HINT, projectOverlayEdge } from "./projectEdge";
import type { SketchEntity } from "./tools";

const v = (x: number, y: number, z: number): Vec3 => ({ x, y, z });

/** An overlay edge with an exact signature, as the /overlay route sends it. */
function edge(
  curve: "line" | "circle" | "other",
  a: Vec3,
  b: Vec3,
  mid: Vec3,
  polyline: Vec3[] = [a, mid, b],
): OverlayEdge {
  return {
    kind: curve,
    start: a,
    end: b,
    polyline,
    signature: {
      subshape_type: "edge",
      curve,
      end_a: a,
      end_b: b,
      midpoint: mid,
      length_mm: 1,
    },
  };
}

const XY = sceneOriginBasis("XY");
const ANCHOR = "00000000-0000-0000-0000-00000000a001";

const projection = (e: OverlayEdge): SketchProjection => ({
  edge: {
    kind: "subshape",
    feature_id: ANCHOR,
    subshape_type: "edge",
    selector: { selector_version: 1, signature: e.signature },
  },
});

function entityOf(result: ReturnType<typeof projectOverlayEdge>): SketchEntity {
  if (!("entity" in result)) throw new Error(`refused: ${result.hint}`);
  return result.entity;
}

describe("projectOverlayEdge — a picked body edge to its sketch entity", () => {
  it("projects a line's exact ends onto the plane, linked to its edge", () => {
    const rim = edge("line", v(-55, -38, 35), v(55, -38, 35), v(0, -38, 35));
    const line = entityOf(projectOverlayEdge(rim, XY, ANCHOR, "e7"));
    expect(line).toMatchObject({
      id: "e7",
      kind: "line",
      start: { x: -55, y: -38 },
      end: { x: 55, y: -38 },
      construction: false,
    });
    expect(isProjected(line)).toBe(true);
    expect("projection" in line && line.projection).toEqual(projection(rim));
  });

  it("drops an edge above the plane straight down (offset planes)", () => {
    const high = edge("line", v(0, 0, 50), v(10, 0, 50), v(5, 0, 50));
    const line = entityOf(projectOverlayEdge(high, XY, ANCHOR, "e1"));
    expect(line).toMatchObject({ start: { x: 0, y: 0 }, end: { x: 10, y: 0 } });
  });

  it("projects into an on-face sketch's own frame", () => {
    // The rim of a box whose top is z = 35: the face basis's origin is the
    // centroid, so plane coordinates are relative to it.
    const basis = faceBasis(
      {
        subshape_type: "face",
        surface: "plane",
        normal: v(0, 0, 1),
        centroid: v(10, 0, 35),
        area_mm2: 100,
      },
      0,
    );
    const rim = edge("line", v(0, -5, 35), v(20, -5, 35), v(10, -5, 35));
    const line = entityOf(projectOverlayEdge(rim, basis, ANCHOR, "e1"));
    if (line.kind !== "line") throw new Error("not a line");
    expect(
      Math.hypot(line.end.x - line.start.x, line.end.y - line.start.y),
    ).toBeCloseTo(20, 9);
    const mid = {
      x: (line.start.x + line.end.x) / 2,
      y: (line.start.y + line.end.y) / 2,
    };
    expect(Math.hypot(mid.x, mid.y)).toBeCloseTo(5, 9);
  });

  it("projects a full circle seen face-on as a circle", () => {
    const seam = v(15, 0, 10);
    const hole = edge("circle", seam, seam, v(5, 0, 10), [
      seam,
      v(10, 5, 10),
      v(5, 0, 10),
      v(10, -5, 10),
      seam,
    ]);
    const circle = entityOf(projectOverlayEdge(hole, XY, ANCHOR, "e2"));
    expect(circle.kind).toBe("circle");
    if (circle.kind !== "circle") return;
    expect(circle.center.x).toBeCloseTo(10, 9);
    expect(circle.center.y).toBeCloseTo(0, 9);
    expect(circle.radius).toBeCloseTo(5, 9);
  });

  it("orients an arc counter-clockwise whichever way the signature sorts its ends", () => {
    // A quarter round from (5,0) to (0,5) about the origin: CCW is 5,0 -> 0,5.
    const r = 5;
    const m = v(r * Math.SQRT1_2, r * Math.SQRT1_2, 0);
    for (const [a, b] of [
      [v(0, r, 0), v(r, 0, 0)],
      [v(r, 0, 0), v(0, r, 0)],
    ] as const) {
      const arc = entityOf(
        projectOverlayEdge(edge("circle", a, b, m), XY, ANCHOR, "e3"),
      );
      if (arc.kind !== "arc") throw new Error("not an arc");
      expect(arc.start.x).toBeCloseTo(5, 9);
      expect(arc.start.y).toBeCloseTo(0, 9);
      expect(arc.end.x).toBeCloseTo(0, 9);
      expect(arc.end.y).toBeCloseTo(5, 9);
      expect(arc.center.x).toBeCloseTo(0, 9);
      expect(arc.center.y).toBeCloseTo(0, 9);
    }
  });

  it("refuses a circle tilted to the sketch (it would be an ellipse)", () => {
    // A circle in the XZ plane, seen from XY.
    const tilted = edge("circle", v(5, 0, 0), v(-5, 0, 0), v(0, 0, 5));
    const result = projectOverlayEdge(tilted, XY, ANCHOR, "e1");
    expect(result).toMatchObject({ reason: "ellipse" });
  });

  it("refuses a spline edge (SKETCH-PROJECT-SPLINE)", () => {
    const spline = edge("other", v(0, 0, 0), v(10, 3, 0), v(5, 2, 0));
    expect(projectOverlayEdge(spline, XY, ANCHOR, "e1")).toEqual({
      reason: "spline",
      hint: PROJECT_SPLINE_HINT,
    });
  });

  it("refuses a line that runs straight at the sketch (it projects to a point)", () => {
    const post = edge("line", v(3, 4, 0), v(3, 4, 20), v(3, 4, 10));
    expect(projectOverlayEdge(post, XY, ANCHOR, "e1")).toMatchObject({
      reason: "degenerate",
    });
  });
});

// --- the constraint gate ------------------------------------------------------

const rimEdge = edge("line", v(0, 0, 0), v(20, 0, 0), v(10, 0, 0));
const sideEdge = edge("line", v(20, 0, 0), v(20, 10, 0), v(20, 5, 0));
const roundEdge = edge(
  "circle",
  v(25, 0, 0),
  v(20, 5, 0),
  v(20 + 5 * Math.SQRT1_2, 5 * Math.SQRT1_2, 0),
);
const P1 = entityOf(projectOverlayEdge(rimEdge, XY, ANCHOR, "e1"));
const P2 = entityOf(projectOverlayEdge(sideEdge, XY, ANCHOR, "e2"));
const PA = entityOf(projectOverlayEdge(roundEdge, XY, ANCHOR, "e4"));
const DRAWN: SketchEntity = {
  id: "e3",
  kind: "line",
  start: { x: 0, y: 5 },
  end: { x: 10, y: 8 },
  construction: false,
};
const ENTITIES = [P1, P2, DRAWN, PA];

describe("projected geometry is a target, never a subject", () => {
  it("refuses H, V and Fixed on a projected entity", () => {
    for (const action of ["horizontal", "vertical", "fixed"] as const) {
      const result = applyConstraintAction(
        action,
        [{ kind: "entity", id: "e1" }],
        ENTITIES,
        [],
      );
      expect(result).toEqual({ outcome: "hint", hint: PROJECTED_SUBJECT_HINT });
    }
  });

  it("refuses a coincident between two projected points (both are fixed)", () => {
    const result = applyConstraintAction(
      "coincident",
      [
        { kind: "point", entity: "e1", point: "end" },
        { kind: "point", entity: "e2", point: "start" },
      ],
      ENTITIES,
      [],
    );
    expect(result).toEqual({ outcome: "hint", hint: PROJECTED_SUBJECT_HINT });
  });

  it("refuses equal between two projected lines, allows it onto drawn geometry", () => {
    expect(
      projectedRefusal(
        "equal",
        [
          { kind: "entity", id: "e1" },
          { kind: "entity", id: "e2" },
        ],
        ENTITIES,
      ),
    ).toBe(PROJECTED_SUBJECT_HINT);
    expect(
      projectedRefusal(
        "equal",
        [
          { kind: "entity", id: "e1" },
          { kind: "entity", id: "e3" },
        ],
        ENTITIES,
      ),
    ).toBeNull();
  });

  it("lets drawn geometry be constrained TO a projected point", () => {
    const result = applyConstraintAction(
      "coincident",
      [
        { kind: "point", entity: "e3", point: "start" },
        { kind: "point", entity: "e1", point: "start" },
      ],
      ENTITIES,
      [],
    );
    expect(result.outcome).toBe("added");
  });

  it("creates a dimension on a projected line DRIVEN", () => {
    const result = applyConstraintAction(
      "distance",
      [{ kind: "entity", id: "e1" }],
      ENTITIES,
      [],
    );
    expect(result.outcome).toBe("editor");
    if (result.outcome !== "editor") return;
    expect(result.target.initialDriving).toBe(false);
    expect(result.target.initialValue).toBeCloseTo(20, 9);
  });

  it("creates a radius on a projected arc driven, and a drawn line's length driving", () => {
    const radius = applyConstraintAction(
      "radius",
      [{ kind: "entity", id: "e4" }],
      ENTITIES,
      [],
    );
    expect(radius.outcome === "editor" && radius.target.initialDriving).toBe(
      false,
    );
    const drawn = applyConstraintAction(
      "distance",
      [{ kind: "entity", id: "e3" }],
      ENTITIES,
      [],
    );
    expect(drawn.outcome === "editor" && drawn.target.initialDriving).toBe(
      true,
    );
  });

  it("creates a point dimension between two projected points driven", () => {
    const both = pointDimensionEditor(
      {
        kind: "point_distance",
        a: { entity: "e1", point: "start" },
        b: { entity: "e2", point: "end" },
        direction: "aligned",
      },
      ENTITIES,
      [],
    );
    expect(both.initialDriving).toBe(false);
    const mixed = pointDimensionEditor(
      {
        kind: "point_distance",
        a: { entity: "e1", point: "start" },
        b: { entity: "e3", point: "end" },
        direction: "aligned",
      },
      ENTITIES,
      [],
    );
    expect(mixed.initialDriving).toBe(true);
  });

  it("counts the frame as fixed but never as projected on its own", () => {
    expect(allProjected(["e1", "origin"], ENTITIES)).toBe(true);
    expect(allProjected(["origin"], ENTITIES)).toBe(false);
    expect(allProjected(["e1", "e3"], ENTITIES)).toBe(false);
  });
});

describe("a projected point cannot be moved", () => {
  it("opens no typed X / Y cells on a projected point", () => {
    const state = {
      tool: "select" as const,
      pending: [],
      cursor: null,
      selection: [
        { kind: "point" as const, entity: "e1", point: "end" as const },
      ],
      entities: ENTITIES,
      drawDimension: null,
      dimensionEdit: null,
    };
    expect(pointEntryOpening(state)).toBeNull();
    expect(
      pointEntryOpening({
        ...state,
        selection: [{ kind: "point", entity: "e3", point: "end" }],
      }),
    ).not.toBeNull();
  });
});

describe("breakLinks — Fusion's Break Link", () => {
  it("keeps the geometry and drops the link", () => {
    const result = breakLinks([{ kind: "entity", id: "e1" }], ENTITIES);
    expect(result?.broken).toBe(1);
    const freed = result?.entities.find((e) => e.id === "e1");
    expect(isProjected(freed)).toBe(false);
    expect(freed).toMatchObject({
      start: { x: 0, y: 0 },
      end: { x: 20, y: 0 },
    });
    expect(isProjected(result?.entities.find((e) => e.id === "e2"))).toBe(true);
  });

  it("breaks a point's owner, and answers null when nothing selected is linked", () => {
    expect(
      breakLinks([{ kind: "point", entity: "e2", point: "start" }], ENTITIES)
        ?.broken,
    ).toBe(1);
    expect(breakLinks([{ kind: "entity", id: "e3" }], ENTITIES)).toBeNull();
  });
});

describe("projection bookkeeping", () => {
  it("lists the projected signatures (what the edge overlay shows as taken)", () => {
    expect(projectedSignatures(ENTITIES)).toEqual([
      rimEdge.signature,
      sideEdge.signature,
      roundEdge.signature,
    ]);
  });

  it("maps sick statuses by entity, ok ones dropped", () => {
    const sick = sickProjections([
      { entity: "e1", state: "ok", tier: "exact" },
      { entity: "e2", state: "sick", reason: "unresolved" },
    ]);
    expect([...sick]).toEqual([["e2", "unresolved"]]);
  });
});
