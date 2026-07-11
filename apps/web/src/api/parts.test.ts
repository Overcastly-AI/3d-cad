import { describe, expect, it } from "vitest";

import {
  sketchFeatureCreate,
  sketchFeatureUpdate,
  type SketchConstraint,
  type SketchEntity,
} from "./parts";

const entities: SketchEntity[] = [
  { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 40, y: 0 } },
  { id: "e2", kind: "circle", center: { x: 20, y: 12 }, radius: 4 },
];

const constraints: SketchConstraint[] = [
  { kind: "horizontal", entity: "e1" },
  { kind: "distance", entity: "e1", value_mm: 40 },
  { kind: "radius", entity: "e2", value_mm: 4 },
  {
    kind: "coincident",
    a: { entity: "e1", point: "end" },
    b: { entity: "e1", point: "start" },
  },
  { kind: "fixed", point: { entity: "e1", point: "start" } },
];

describe("sketchFeatureCreate", () => {
  it("maps the buffer (entities + constraints) to the persisted envelope", () => {
    const body = sketchFeatureCreate("Sketch1", "XZ", entities, constraints, 3);
    expect(body).toEqual({
      name: "Sketch1",
      expected_tree_version: 3,
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XZ" },
          entities,
          constraints,
        },
      },
    });
  });

  it("copies both lists so later buffer edits cannot mutate the payload", () => {
    const body = sketchFeatureCreate("Sketch1", "XY", entities, constraints, 1);
    if (body.feature.type !== "sketch") throw new Error("expected a sketch");
    expect(body.feature.params.entities).not.toBe(entities);
    expect(body.feature.params.entities).toEqual(entities);
    expect(body.feature.params.constraints).not.toBe(constraints);
    expect(body.feature.params.constraints).toEqual(constraints);
  });
});

describe("sketchFeatureUpdate", () => {
  it("wraps the same envelope for the live-loop PATCH (no rename)", () => {
    const body = sketchFeatureUpdate("XY", entities, constraints, 7);
    expect(body).toEqual({
      expected_tree_version: 7,
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XY" },
          entities,
          constraints,
        },
      },
    });
    expect(body).not.toHaveProperty("name", expect.anything());
  });
});
