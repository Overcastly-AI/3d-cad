import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import {
  type ChamferParams,
  chamferFeatureCreate,
  chamferFeatureUpdate,
  createPart,
  type DatumParams,
  datumFeatureCreate,
  datumFeatureUpdate,
  deletePart,
  type ExtrudeParams,
  extrudeFeatureCreate,
  extrudeFeatureUpdate,
  fetchParts,
  type FilletParams,
  filletFeatureCreate,
  filletFeatureUpdate,
  importStep,
  PartNameTakenError,
  type PatternParams,
  patternFeatureCreate,
  patternFeatureUpdate,
  redoPart,
  type RevolveParams,
  revolveFeatureCreate,
  revolveFeatureUpdate,
  sketchFeatureCreate,
  sketchFeatureUpdate,
  type SketchConstraint,
  type SketchEntity,
  StaleTreeVersionError,
  type SweepParams,
  sweepFeatureCreate,
  sweepFeatureUpdate,
  undoPart,
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

describe("undoPart / redoPart", () => {
  /** The restored tree the endpoints echo (docs/design/undo-redo.md). */
  const restoredTree = {
    part_id: samplePart.id,
    tree_version: 5,
    rollback_feature_id: null,
    can_undo: true,
    can_redo: true,
    features: [],
  };

  it("undoPart POSTs the expected_tree_version and returns the restored tree", async () => {
    let captured: Request | undefined;
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: (request: Request) => {
        captured = request;
        return Promise.resolve(json(restoredTree, 200));
      },
    });

    await expect(undoPart(samplePart.id, 4, client)).resolves.toEqual(
      restoredTree,
    );
    expect(captured?.method).toBe("POST");
    expect(new URL(captured?.url ?? "").pathname).toBe(
      `/api/v1/parts/${samplePart.id}/undo`,
    );
    expect(JSON.parse(await captured!.text())).toEqual({
      expected_tree_version: 4,
    });
  });

  it("redoPart POSTs the expected_tree_version to the redo route", async () => {
    let captured: Request | undefined;
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: (request: Request) => {
        captured = request;
        return Promise.resolve(json(restoredTree, 200));
      },
    });

    await expect(redoPart(samplePart.id, 4, client)).resolves.toEqual(
      restoredTree,
    );
    expect(new URL(captured?.url ?? "").pathname).toBe(
      `/api/v1/parts/${samplePart.id}/redo`,
    );
    expect(JSON.parse(await captured!.text())).toEqual({
      expected_tree_version: 4,
    });
  });

  it("throws the typed StaleTreeVersionError on a 422 stale_tree_version", async () => {
    const stale = json(
      { error: { code: "stale_tree_version", message: "tree moved on" } },
      422,
    );
    const undoError = await undoPart(
      samplePart.id,
      1,
      clientReturning(stale),
    ).catch((e: unknown) => e);
    expect(undoError).toBeInstanceOf(StaleTreeVersionError);
    expect((undoError as Error).message).toMatch(/tree moved on/);

    const redoError = await redoPart(
      samplePart.id,
      1,
      clientReturning(
        json(
          { error: { code: "stale_tree_version", message: "tree moved on" } },
          422,
        ),
      ),
    ).catch((e: unknown) => e);
    expect(redoError).toBeInstanceOf(StaleTreeVersionError);
  });

  it("surfaces the envelope message (untyped) on other failures", async () => {
    const client = clientReturning(
      json({ error: { code: "part_not_found", message: "no such part" } }, 404),
    );
    const error = await undoPart(samplePart.id, 1, client).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(Error);
    expect(error).not.toBeInstanceOf(StaleTreeVersionError);
    expect((error as Error).message).toMatch(/no such part/);
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

describe("importStep", () => {
  const featureMutation = {
    feature: { id: "44444444-4444-4444-4444-444444444444" },
    tree_version: 1,
  };

  it("sends the raw bytes as octet-stream with the version + name query", async () => {
    const bytes = new TextEncoder().encode("ISO-10303-21;\n").buffer;
    let captured: Request | undefined;
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: (request: Request) => {
        captured = request;
        return Promise.resolve(json(featureMutation, 201));
      },
    });

    await expect(
      importStep("part-1", bytes, "bracket", 3, client),
    ).resolves.toMatchObject({ feature: { id: expect.any(String) } });

    expect(captured?.method).toBe("POST");
    const url = new URL(captured?.url ?? "");
    expect(url.pathname).toBe("/api/v1/parts/part-1/features/import");
    expect(url.searchParams.get("expected_tree_version")).toBe("3");
    expect(url.searchParams.get("name")).toBe("bracket");
    expect(captured?.headers.get("content-type")).toBe(
      "application/octet-stream",
    );
    // The exact bytes go on the wire — not a JSON-stringified copy.
    expect(new TextDecoder().decode(await captured!.arrayBuffer())).toBe(
      "ISO-10303-21;\n",
    );
  });

  it("surfaces the server envelope message on a 422 rejection", async () => {
    const bytes = new TextEncoder().encode("not step").buffer;
    const client = clientReturning(
      json(
        {
          error: {
            code: "import_not_step",
            message: "The uploaded file is not a STEP part-21 file.",
          },
        },
        422,
      ),
    );
    await expect(importStep("part-1", bytes, "x", 0, client)).rejects.toThrow(
      /not a STEP part-21 file/,
    );
  });
});

describe("sketchFeatureCreate", () => {
  it("maps the buffer (entities + constraints) to the persisted envelope", () => {
    const body = sketchFeatureCreate(
      "Sketch1",
      { kind: "datum_plane", plane: "XZ" },
      entities,
      constraints,
      3,
    );
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

  it("carries a datum FeatureRef plane through (sketch on an offset plane)", () => {
    const body = sketchFeatureCreate(
      "Sketch1",
      { kind: "feature", feature_id: "f-p001" },
      entities,
      constraints,
      3,
    );
    if (body.feature.type !== "sketch") throw new Error("expected a sketch");
    expect(body.feature.params.plane).toEqual({
      kind: "feature",
      feature_id: "f-p001",
    });
  });

  it("copies both lists so later buffer edits cannot mutate the payload", () => {
    const body = sketchFeatureCreate(
      "Sketch1",
      { kind: "datum_plane", plane: "XY" },
      entities,
      constraints,
      1,
    );
    if (body.feature.type !== "sketch") throw new Error("expected a sketch");
    expect(body.feature.params.entities).not.toBe(entities);
    expect(body.feature.params.entities).toEqual(entities);
    expect(body.feature.params.constraints).not.toBe(constraints);
    expect(body.feature.params.constraints).toEqual(constraints);
  });

  it("carries each entity's construction flag through to the payload", () => {
    const body = sketchFeatureCreate(
      "Sketch1",
      { kind: "datum_plane", plane: "XY" },
      entities,
      constraints,
      1,
    );
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
    const body = sketchFeatureUpdate(
      { kind: "datum_plane", plane: "XY" },
      entities,
      constraints,
      7,
    );
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

const datumParams: DatumParams = {
  kind: "offset",
  base: "XY",
  offset_mm: 30,
  flip: false,
};

describe("datumFeatureCreate", () => {
  it("wraps the params in the {type, version, params} create envelope", () => {
    const body = datumFeatureCreate("Plane1", datumParams, 2);
    expect(body).toEqual({
      name: "Plane1",
      expected_tree_version: 2,
      feature: { type: "datum", version: 1, params: datumParams },
    });
  });
});

describe("datumFeatureUpdate", () => {
  it("wraps the re-parametrized envelope for the PATCH (no rename)", () => {
    const flipped: DatumParams = {
      kind: "offset",
      base: "XZ",
      offset_mm: -10,
      flip: true,
    };
    const body = datumFeatureUpdate(flipped, 9);
    expect(body).toEqual({
      expected_tree_version: 9,
      feature: { type: "datum", version: 1, params: flipped },
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

const sweepParams: SweepParams = {
  profile: {
    kind: "feature",
    feature_id: "11111111-1111-1111-1111-111111111111",
  },
  path: {
    kind: "feature",
    feature_id: "33333333-3333-3333-3333-333333333333",
  },
  operation: "add",
};

describe("sweepFeatureCreate", () => {
  it("wraps the two FeatureRefs in the {type, version, params} create envelope", () => {
    const body = sweepFeatureCreate("Sweep1", sweepParams, 5);
    expect(body).toEqual({
      name: "Sweep1",
      expected_tree_version: 5,
      feature: { type: "sweep", version: 1, params: sweepParams },
    });
  });
});

describe("sweepFeatureUpdate", () => {
  it("wraps the re-parametrized envelope for the PATCH (no rename)", () => {
    const cut: SweepParams = { ...sweepParams, operation: "cut" };
    const body = sweepFeatureUpdate(cut, 11);
    expect(body).toEqual({
      expected_tree_version: 11,
      feature: { type: "sweep", version: 1, params: cut },
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
