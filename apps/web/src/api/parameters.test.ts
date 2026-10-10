import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import {
  fetchPartParameters,
  ParameterTableError,
  putPartParameters,
} from "./parameters";
import { StaleTreeVersionError } from "./parts";

const PART = "5d7c1f0e-1111-4222-8333-944445555666";
const ROW = {
  id: "00000000-0000-4000-8000-000000000001",
  name: "W",
  expression: "40",
  unit: "length" as const,
  comment: "",
};

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, message: string, details?: unknown) {
  return { error: { code, message, details, request_id: "r" } };
}

function clientAnswering(response: Response) {
  const seen: Request[] = [];
  const client = createGatewayClient({
    baseUrl: "http://gateway.test",
    fetch: (request: Request) => {
      seen.push(request);
      return Promise.resolve(response);
    },
  });
  return { client, seen };
}

describe("part parameters api", () => {
  it("reads the table", async () => {
    const body = { tree_version: 3, parameters: [{ ...ROW, value: 40 }] };
    const { client, seen } = clientAnswering(json(body, 200));
    await expect(fetchPartParameters(PART, client)).resolves.toEqual(body);
    expect(new URL(seen[0]!.url).pathname).toBe(
      `/api/v1/parts/${PART}/parameters`,
    );
  });

  it("replaces the whole table under the tree version on screen", async () => {
    const body = { tree_version: 4, parameters: [{ ...ROW, value: 40 }] };
    const { client, seen } = clientAnswering(json(body, 200));
    await putPartParameters(PART, [ROW], 3, client);
    expect(seen[0]!.method).toBe("PUT");
    expect(await seen[0]!.json()).toEqual({
      expected_tree_version: 3,
      parameters: [ROW],
    });
  });

  it("types a refused table with its code, row and chain", async () => {
    const { client } = clientAnswering(
      json(
        envelope("expression_cycle", "parameter cycle: a -> b -> a", {
          parameter: "a",
          chain: ["a", "b", "a"],
        }),
        422,
      ),
    );
    const error = await putPartParameters(PART, [ROW], 3, client).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(ParameterTableError);
    expect(error).toMatchObject({
      code: "expression_cycle",
      parameter: "a",
      chain: ["a", "b", "a"],
    });
  });

  it("makes a version race a StaleTreeVersionError", async () => {
    const { client } = clientAnswering(
      json(envelope("stale_tree_version", "stale"), 422),
    );
    await expect(putPartParameters(PART, [ROW], 3, client)).rejects.toThrow(
      StaleTreeVersionError,
    );
  });

  it("keeps a table error without details on the table", async () => {
    const { client } = clientAnswering(
      json(envelope("expression_too_complex", "201 parameters"), 422),
    );
    await expect(
      putPartParameters(PART, [ROW], 3, client),
    ).rejects.toMatchObject({
      code: "expression_too_complex",
      parameter: null,
      chain: [],
    });
  });
});
