import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import {
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
