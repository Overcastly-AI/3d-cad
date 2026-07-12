import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import {
  type ChamferParams,
  chamferFeatureCreate,
  chamferFeatureUpdate,
  createPart,
  deletePart,
  type ExtrudeParams,
  extrudeFeatureCreate,
  extrudeFeatureUpdate,
  fetchParts,
  type FilletParams,
  filletFeatureCreate,
  filletFeatureUpdate,
  PartNameTakenError,
  type PatternParams,
  patternFeatureCreate,
  patternFeatureUpdate,
  type RevolveParams,
  revolveFeatureCreate,
  revolveFeatureUpdate,
  sketchFeatureCreate,
  sketchFeatureUpdate,
  type SketchConstraint,
  type SketchEntity,
} from "./parts";

const entities: SketchEntity[] = [
  {
    id: "e1",
    kind: "line",
    start: { x: 0, y: 0 },
    end: { x: 40, y: 0 },
    construction: false,
  },
  // A construction circle — reference-only geometry excluded from the profile.
  {
    id: "e2",
    kind: "circle",
    center: { x: 20, y: 12 },
    radius: 4,
    construction: true,
  },
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

/** A typed client whose transport is a canned response — no network. */
function clientReturning(response: Response) {
  return createGatewayClient({
    baseUrl: "http://gateway.test",
    fetch: () => Promise.resolve(response),
  });
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const samplePart = {
  id: "11111111-1111-1111-1111-111111111111",
  owner_id: "22222222-2222-2222-2222-222222222222",
  name: "Bracket plate",
  created_at: "2026-07-11T10:00:00Z",
  updated_at: "2026-07-11T10:00:00Z",
};

describe("fetchParts", () => {
  it("unwraps the register list (oldest first)", async () => {
    const client = clientReturning(json({ parts: [samplePart] }, 200));
    await expect(fetchParts(client)).resolves.toEqual([samplePart]);
  });

  it("surfaces the envelope message on failure", async () => {
    const client = clientReturning(
      json({ error: { code: "upstream_unavailable", message: "down" } }, 502),
    );
    await expect(fetchParts(client)).rejects.toThrow(/down/);
  });
});

describe("createPart", () => {
  it("returns the created part on 201", async () => {
    const client = clientReturning(json(samplePart, 201));
    await expect(createPart("Bracket plate", client)).resolves.toEqual(
      samplePart,
    );
  });

  it("throws a typed PartNameTakenError on a 409 duplicate name", async () => {
    const client = clientReturning(
      json(
        {
          error: {
            code: "part_name_taken",
            message: 'A part named "Bracket plate" already exists.',
          },
        },
        409,
      ),
    );
    const error = await createPart("Bracket plate", client).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(PartNameTakenError);
    expect(error).toMatchObject({
      partName: "Bracket plate",
      message: 'A part named "Bracket plate" already exists.',
    });
  });

  it("surfaces a generic error for other failures", async () => {
    const client = clientReturning(
      json({ error: { code: "boom", message: "server exploded" } }, 500),
    );
    const error = await createPart("X", client).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(Error);
    expect(error).not.toBeInstanceOf(PartNameTakenError);
    expect((error as Error).message).toMatch(/server exploded/);
  });
});

describe("deletePart", () => {
  it("resolves on a 204 (no body)", async () => {
    const client = clientReturning(new Response(null, { status: 204 }));
    await expect(deletePart(samplePart.id, client)).resolves.toBeUndefined();
  });

  it("surfaces the envelope message on a 404", async () => {
    const client = clientReturning(
      json({ error: { code: "part_not_found", message: "no such part" } }, 404),
    );
    await expect(deletePart(samplePart.id, client)).rejects.toThrow(
      /no such part/,
    );
  });
});

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

  it("carries each entity's construction flag through to the payload", () => {
    const body = sketchFeatureCreate("Sketch1", "XY", entities, constraints, 1);
    if (body.feature.type !== "sketch") throw new Error("expected a sketch");
    const byId = new Map(
      body.feature.params.entities.map((e) => [e.id, e.construction]),
    );
    expect(byId.get("e1")).toBe(false); // profile line
    expect(byId.get("e2")).toBe(true); // construction circle
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

const extrudeParams: ExtrudeParams = {
  profile: {
    kind: "feature",
    feature_id: "11111111-1111-1111-1111-111111111111",
  },
  distance_mm: 10,
  operation: "add",
  direction: "normal",
};

describe("extrudeFeatureCreate", () => {
  it("wraps the params in the {type, version, params} create envelope", () => {
    const body = extrudeFeatureCreate("Extrude1", extrudeParams, 2);
    expect(body).toEqual({
      name: "Extrude1",
      expected_tree_version: 2,
      feature: { type: "extrude", version: 1, params: extrudeParams },
    });
  });
});

describe("extrudeFeatureUpdate", () => {
  it("wraps the re-parametrized envelope for the PATCH (no rename)", () => {
    const cut: ExtrudeParams = {
      ...extrudeParams,
      distance_mm: 6,
      operation: "cut",
      direction: "reverse",
    };
    const body = extrudeFeatureUpdate(cut, 9);
    expect(body).toEqual({
      expected_tree_version: 9,
      feature: { type: "extrude", version: 1, params: cut },
    });
    expect(body).not.toHaveProperty("name", expect.anything());
  });
});

const revolveParams: RevolveParams = {
  profile: {
    kind: "feature",
    feature_id: "11111111-1111-1111-1111-111111111111",
  },
  axis: { kind: "sketch_line", entity: "axis" },
  angle_deg: 360,
  operation: "add",
  direction: "normal",
};

describe("revolveFeatureCreate", () => {
  it("wraps the params in the {type, version, params} create envelope", () => {
    const body = revolveFeatureCreate("Revolve1", revolveParams, 2);
    expect(body).toEqual({
      name: "Revolve1",
      expected_tree_version: 2,
      feature: { type: "revolve", version: 1, params: revolveParams },
    });
  });
});

describe("revolveFeatureUpdate", () => {
  it("wraps the re-parametrized envelope for the PATCH (no rename)", () => {
    const half: RevolveParams = {
      ...revolveParams,
      angle_deg: 180,
      operation: "cut",
      direction: "reverse",
    };
    const body = revolveFeatureUpdate(half, 9);
    expect(body).toEqual({
      expected_tree_version: 9,
      feature: { type: "revolve", version: 1, params: half },
    });
    expect(body).not.toHaveProperty("name", expect.anything());
  });
});

const linearPattern: PatternParams = {
  pattern: {
    kind: "linear",
    direction: { x: 1, y: 0, z: 0 },
    spacing_mm: 6,
    count: 3,
  },
};

describe("patternFeatureCreate", () => {
  it("wraps the params in the {type, version, params} create envelope", () => {
    const body = patternFeatureCreate("Pattern1", linearPattern, 4);
    expect(body).toEqual({
      name: "Pattern1",
      expected_tree_version: 4,
      feature: { type: "pattern", version: 1, params: linearPattern },
    });
  });
});

describe("patternFeatureUpdate", () => {
  it("wraps the re-parametrized envelope for the PATCH (no rename)", () => {
    const circular: PatternParams = {
      pattern: {
        kind: "circular",
        axis_point: { x: 0, y: 0, z: 0 },
        axis_direction: { x: 0, y: 0, z: 1 },
        angle_deg: 360,
        count: 6,
      },
    };
    const body = patternFeatureUpdate(circular, 12);
    expect(body).toEqual({
      expected_tree_version: 12,
      feature: { type: "pattern", version: 1, params: circular },
    });
    expect(body).not.toHaveProperty("name", expect.anything());
  });
});

const filletParams: FilletParams = {
  radius_mm: 5,
  edges: { kind: "all_edges" },
};

describe("filletFeatureCreate", () => {
  it("wraps the params in the {type, version, params} create envelope", () => {
    const body = filletFeatureCreate("Fillet1", filletParams, 3);
    expect(body).toEqual({
      name: "Fillet1",
      expected_tree_version: 3,
      feature: { type: "fillet", version: 1, params: filletParams },
    });
  });
});

describe("filletFeatureUpdate", () => {
  it("wraps the re-parametrized envelope for the PATCH (no rename)", () => {
    const body = filletFeatureUpdate(filletParams, 7);
    expect(body).toEqual({
      expected_tree_version: 7,
      feature: { type: "fillet", version: 1, params: filletParams },
    });
    expect(body).not.toHaveProperty("name", expect.anything());
  });
});

const chamferParams: ChamferParams = {
  distance_mm: 2,
  edges: { kind: "axis_parallel", axis: "Z" },
};

describe("chamferFeatureCreate", () => {
  it("wraps the params in the {type, version, params} create envelope", () => {
    const body = chamferFeatureCreate("Chamfer1", chamferParams, 4);
    expect(body).toEqual({
      name: "Chamfer1",
      expected_tree_version: 4,
      feature: { type: "chamfer", version: 1, params: chamferParams },
    });
  });
});

describe("chamferFeatureUpdate", () => {
  it("wraps the re-parametrized envelope for the PATCH (no rename)", () => {
    const body = chamferFeatureUpdate(chamferParams, 9);
    expect(body).toEqual({
      expected_tree_version: 9,
      feature: { type: "chamfer", version: 1, params: chamferParams },
    });
    expect(body).not.toHaveProperty("name", expect.anything());
  });
});
