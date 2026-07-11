import { describe, expect, it } from "vitest";

import { sketchFeatureCreate, type SketchEntity } from "./parts";

const entities: SketchEntity[] = [
  { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 40, y: 0 } },
  { id: "e2", kind: "circle", center: { x: 20, y: 12 }, radius: 4 },
];

describe("sketchFeatureCreate", () => {
  it("maps the buffer to the persisted sketch envelope (unconstrained v1)", () => {
    const body = sketchFeatureCreate("Sketch1", "XZ", entities, 3);
    expect(body).toEqual({
      name: "Sketch1",
      expected_tree_version: 3,
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XZ" },
          entities,
          constraints: [],
        },
      },
    });
  });

  it("copies the entity list so later buffer edits cannot mutate the payload", () => {
    const body = sketchFeatureCreate("Sketch1", "XY", entities, 1);
    if (body.feature.type !== "sketch") throw new Error("expected a sketch");
    expect(body.feature.params.entities).not.toBe(entities);
    expect(body.feature.params.entities).toEqual(entities);
  });
});
