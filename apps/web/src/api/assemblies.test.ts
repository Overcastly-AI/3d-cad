import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import {
  checkInterference,
  type EvaluateAssemblyRequest,
  exportAssembly,
  redoAssembly,
  StaleAssemblyVersionError,
  undoAssembly,
} from "./assemblies";

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

const assemblyId = "33333333-3333-3333-3333-333333333333";

/** The restored graph the endpoints echo (docs/design/undo-redo.md §UR3). */
const restoredGraph = {
  assembly: {
    id: assemblyId,
    owner_id: "22222222-2222-2222-2222-222222222222",
    name: "Bolted plates",
    length_unit: "mm",
    created_at: "2026-07-17T10:00:00Z",
    updated_at: "2026-07-17T10:00:00Z",
  },
  instances: [],
  mates: [],
  doc_version: 5,
  can_undo: true,
  can_redo: true,
};

describe("undoAssembly / redoAssembly", () => {
  it("undoAssembly POSTs the expected_version and returns the restored graph", async () => {
    let captured: Request | undefined;
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: (request: Request) => {
        captured = request;
        return Promise.resolve(json(restoredGraph, 200));
      },
    });

    await expect(undoAssembly(assemblyId, 4, client)).resolves.toEqual(
      restoredGraph,
    );
    expect(captured?.method).toBe("POST");
    expect(new URL(captured?.url ?? "").pathname).toBe(
      `/api/v1/assemblies/${assemblyId}/undo`,
    );
    expect(JSON.parse(await captured!.text())).toEqual({ expected_version: 4 });
  });

  it("redoAssembly POSTs the expected_version to the redo route", async () => {
    let captured: Request | undefined;
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: (request: Request) => {
        captured = request;
        return Promise.resolve(json(restoredGraph, 200));
      },
    });

    await expect(redoAssembly(assemblyId, 4, client)).resolves.toEqual(
      restoredGraph,
    );
    expect(new URL(captured?.url ?? "").pathname).toBe(
      `/api/v1/assemblies/${assemblyId}/redo`,
    );
    expect(JSON.parse(await captured!.text())).toEqual({ expected_version: 4 });
  });

  it("throws the typed StaleAssemblyVersionError on a 422 stale_assembly_version", async () => {
    const stale = () =>
      json(
        {
          error: { code: "stale_assembly_version", message: "graph moved on" },
        },
        422,
      );
    const undoError = await undoAssembly(
      assemblyId,
      1,
      clientReturning(stale()),
    ).catch((e: unknown) => e);
    expect(undoError).toBeInstanceOf(StaleAssemblyVersionError);
    expect((undoError as Error).message).toMatch(/graph moved on/);

    const redoError = await redoAssembly(
      assemblyId,
      1,
      clientReturning(stale()),
    ).catch((e: unknown) => e);
    expect(redoError).toBeInstanceOf(StaleAssemblyVersionError);
  });

  it("surfaces the envelope message (untyped) on other failures", async () => {
    const client = clientReturning(
      json(
        { error: { code: "assembly_not_found", message: "no such assembly" } },
        404,
      ),
    );
    const error = await undoAssembly(assemblyId, 1, client).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(Error);
    expect(error).not.toBeInstanceOf(StaleAssemblyVersionError);
    expect((error as Error).message).toMatch(/no such assembly/);
  });
});

const evalRequest: EvaluateAssemblyRequest = {
  assembly_id: assemblyId,
  version: 5,
  linear_deflection: 0.1,
  instances: [
    {
      instance_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      part_key: "p1@tip",
      grounded: true,
      placement: {
        position: { x: 0, y: 0, z: 0 },
        orientation: { w: 1, x: 0, y: 0, z: 0 },
      },
      features: [],
    },
  ],
  mates: [],
};

describe("exportAssembly", () => {
  it("POSTs the evaluate request + format and returns the blob + filename", async () => {
    let captured: Request | undefined;
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: (request: Request) => {
        captured = request;
        return Promise.resolve(
          new Response("SOLID assembly", {
            status: 200,
            headers: {
              "Content-Type": "model/stl",
              "Content-Disposition": 'attachment; filename="bolted-plates.stl"',
            },
          }),
        );
      },
    });

    const file = await exportAssembly(
      evalRequest,
      "stl",
      "Bolted Plates",
      client,
    );
    expect(file.filename).toBe("bolted-plates.stl");
    expect(await file.blob.text()).toBe("SOLID assembly");
    expect(captured?.method).toBe("POST");
    expect(new URL(captured?.url ?? "").pathname).toBe(
      "/api/v1/geometry/assembly/export",
    );
    const body = JSON.parse(await captured!.text());
    expect(body.format).toBe("stl");
    expect(body.assembly_id).toBe(assemblyId);
    expect(body.instances).toHaveLength(1);
    // The document name rides the EXPORT request (audit N4): it names the
    // STEP's root PRODUCT and the download, and nothing else.
    expect(body.name).toBe("Bolted Plates");
  });

  it("sends a null name when the caller has none (id fallback, never a guess)", async () => {
    let captured: Request | undefined;
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: (request: Request) => {
        captured = request;
        return Promise.resolve(
          new Response("step-bytes", {
            status: 200,
            headers: { "Content-Type": "model/step" },
          }),
        );
      },
    });
    await exportAssembly(evalRequest, "step", null, client);
    expect(JSON.parse(await captured!.text()).name).toBeNull();
  });

  it("falls back to assembly.<format> when no Content-Disposition is sent", async () => {
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: () =>
        Promise.resolve(
          new Response("step-bytes", {
            status: 200,
            headers: { "Content-Type": "model/step" },
          }),
        ),
    });
    const file = await exportAssembly(evalRequest, "step", null, client);
    expect(file.filename).toBe("assembly.step");
  });

  it("surfaces the envelope message on a 422 no-body export", async () => {
    const client = clientReturning(
      json(
        {
          error: {
            code: "assembly_export_no_body",
            message: "This assembly has no body to export.",
          },
        },
        422,
      ),
    );
    const error = await exportAssembly(evalRequest, "step", null, client).catch(
      (e: unknown) => e,
    );
    expect((error as Error).message).toMatch(/no body to export/);
  });
});

describe("checkInterference", () => {
  it("POSTs the evaluate request and returns the clash list", async () => {
    let captured: Request | undefined;
    const result = {
      assembly_id: assemblyId,
      version: 5,
      status: "well_constrained",
      clashes: [
        {
          instance_a: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
          instance_b: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
          overlap_volume_mm3: 1234.5,
        },
      ],
      mate_errors: [],
    };
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: (request: Request) => {
        captured = request;
        return Promise.resolve(json(result, 200));
      },
    });

    const res = await checkInterference(evalRequest, client);
    expect(res.clashes).toHaveLength(1);
    expect(res.clashes[0]?.overlap_volume_mm3).toBe(1234.5);
    expect(new URL(captured?.url ?? "").pathname).toBe(
      "/api/v1/geometry/assembly/interference",
    );
  });

  it("surfaces the envelope message on a transport failure", async () => {
    const client = clientReturning(
      json(
        { error: { code: "geometry_unavailable", message: "kernel down" } },
        503,
      ),
    );
    const error = await checkInterference(evalRequest, client).catch(
      (e: unknown) => e,
    );
    expect((error as Error).message).toMatch(/kernel down/);
  });
});
