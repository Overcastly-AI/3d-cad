import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import { fetchAssemblyBom } from "./bom";

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const assemblyId = "44444444-4444-4444-4444-444444444444";

const bom = {
  assembly_id: assemblyId,
  lines: [
    {
      ref_document_id: "11111111-1111-1111-1111-111111111111",
      ref_document_kind: "part",
      name: "Hole plate",
      missing: false,
      quantity: 3,
    },
    {
      ref_document_id: "22222222-2222-2222-2222-222222222222",
      ref_document_kind: "assembly",
      name: null,
      missing: true,
      quantity: 1,
    },
  ],
  total_instances: 4,
};

describe("fetchAssemblyBom", () => {
  it("GETs the assembly bom route and returns the read model verbatim", async () => {
    let captured: Request | undefined;
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: (request: Request) => {
        captured = request;
        return Promise.resolve(json(bom, 200));
      },
    });

    await expect(fetchAssemblyBom(assemblyId, client)).resolves.toEqual(bom);
    expect(captured?.method).toBe("GET");
    expect(new URL(captured?.url ?? "").pathname).toBe(
      `/api/v1/assemblies/${assemblyId}/bom`,
    );
  });

  it("surfaces the server envelope message on failure", async () => {
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: () =>
        Promise.resolve(
          json(
            { error: { code: "not_found", message: "No such assembly." } },
            404,
          ),
        ),
    });

    await expect(fetchAssemblyBom(assemblyId, client)).rejects.toThrow(
      "No such assembly.",
    );
  });
});
