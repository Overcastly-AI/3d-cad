import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import { AssemblyNameTakenError } from "./assemblies";
import {
  IMPORT_NAME_ATTEMPTS,
  importAssemblyStep,
  importStepAsNewDocument,
} from "./assemblyImport";

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const ASSEMBLY_RESULT = {
  kind: "assembly",
  assembly: {
    assembly: {
      id: "11111111-1111-1111-1111-111111111111",
      name: "band",
    },
    instances: [{ id: "a" }, { id: "b" }],
    mates: [],
    doc_version: 1,
  },
  part_ids: ["22222222-2222-2222-2222-222222222222"],
};

describe("importAssemblyStep", () => {
  it("streams the raw bytes as octet-stream under the ?name query", async () => {
    const bytes = new TextEncoder().encode("ISO-10303-21;\nHEADER;\n").buffer;
    let captured: Request | undefined;
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: (request: Request) => {
        captured = request;
        return Promise.resolve(json(ASSEMBLY_RESULT, 201));
      },
    });

    const result = await importAssemblyStep(bytes, "band", client);
    expect(result.kind).toBe("assembly");

    expect(captured?.method).toBe("POST");
    const url = new URL(captured?.url ?? "");
    expect(url.pathname).toBe("/api/v1/assemblies/import");
    expect(url.searchParams.get("name")).toBe("band");
    expect(captured?.headers.get("content-type")).toBe(
      "application/octet-stream",
    );
    // The exact bytes go on the wire — not a JSON-stringified copy.
    expect(new TextDecoder().decode(await captured!.arrayBuffer())).toBe(
      "ISO-10303-21;\nHEADER;\n",
    );
  });

  it("surfaces the server's typed envelope message verbatim", async () => {
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: () =>
        Promise.resolve(
          json(
            {
              error: {
                code: "import_not_step",
                message:
                  "Uploaded file is not a STEP part-21 file (missing the ISO-10303-21 header).",
              },
            },
            422,
          ),
        ),
    });
    await expect(
      importAssemblyStep(new ArrayBuffer(4), "notes", client),
    ).rejects.toThrow(/missing the ISO-10303-21 header/);
  });

  it("types a name collision so the caller can offer a way forward", async () => {
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: () =>
        Promise.resolve(
          json(
            {
              error: {
                code: "assembly_name_taken",
                message: "An assembly named 'band' already exists.",
              },
            },
            409,
          ),
        ),
    });
    await expect(
      importAssemblyStep(new ArrayBuffer(4), "band", client),
    ).rejects.toBeInstanceOf(AssemblyNameTakenError);
  });
});

describe("importStepAsNewDocument", () => {
  it("steps to '(2)' when the file's own name is already filed", async () => {
    const names: string[] = [];
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: (request: Request) => {
        const name = new URL(request.url).searchParams.get("name") ?? "";
        names.push(name);
        return Promise.resolve(
          name === "band"
            ? json(
                {
                  error: {
                    code: "assembly_name_taken",
                    message: "An assembly named 'band' already exists.",
                  },
                },
                409,
              )
            : json(ASSEMBLY_RESULT, 201),
        );
      },
    });

    await expect(
      importStepAsNewDocument(new ArrayBuffer(4), "band", client),
    ).resolves.toMatchObject({ kind: "assembly" });
    expect(names).toEqual(["band", "band (2)"]);
  });

  it("reports the collision verbatim once the attempts run out", async () => {
    let calls = 0;
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: () => {
        calls += 1;
        return Promise.resolve(
          json(
            {
              error: {
                code: "part_name_taken",
                message: "A part named 'band' already exists.",
              },
            },
            409,
          ),
        );
      },
    });

    await expect(
      importStepAsNewDocument(new ArrayBuffer(4), "band", client),
    ).rejects.toThrow(/already exists/);
    expect(calls).toBe(IMPORT_NAME_ATTEMPTS);
  });

  it("does not retry a rejection that renaming cannot fix", async () => {
    let calls = 0;
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: () => {
        calls += 1;
        return Promise.resolve(
          json(
            {
              error: {
                code: "import_too_many_products",
                message: "Imported assembly has 900 products.",
              },
            },
            422,
          ),
        );
      },
    });

    await expect(
      importStepAsNewDocument(new ArrayBuffer(4), "huge", client),
    ).rejects.toThrow(/900 products/);
    expect(calls).toBe(1);
  });
});
