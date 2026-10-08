/**
 * The `.loft` data layer: the export reads the server's filename, the import
 * sends the RAW bytes as an octet-stream and surfaces the server's own refusal.
 */
import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import { exportPartLoft, ExportRefusedError } from "./exportPart";
import { importLoftFile } from "./importLoft";

const PART_ID = "11111111-1111-1111-1111-111111111111";

function recordingClient(response: Response, seen: Request[] = []) {
  return createGatewayClient({
    baseUrl: "http://gateway.test",
    fetch: (input: Request) => {
      seen.push(input);
      return Promise.resolve(response);
    },
  });
}

describe("exportPartLoft", () => {
  it("GETs the part's .loft and keeps the server filename", async () => {
    const seen: Request[] = [];
    const client = recordingClient(
      new Response("PK\u0003\u0004", {
        status: 200,
        headers: {
          "Content-Type": "application/vnd.loft+zip",
          "Content-Disposition": 'attachment; filename="bracket.loft"',
        },
      }),
      seen,
    );
    const file = await exportPartLoft(PART_ID, client);
    expect(file.filename).toBe("bracket.loft");
    expect(seen[0]?.method).toBe("GET");
    expect(seen[0]?.url).toBe(
      `http://gateway.test/api/v1/parts/${PART_ID}/export.loft`,
    );
  });

  it("keeps the refusal code", async () => {
    const client = recordingClient(
      Response.json(
        { error: { code: "not_found", message: "Part not found." } },
        { status: 404 },
      ),
    );
    const refusal = await exportPartLoft(PART_ID, client).catch(
      (error: unknown) => error,
    );
    expect(refusal).toBeInstanceOf(ExportRefusedError);
    expect((refusal as ExportRefusedError).code).toBe("not_found");
  });
});

describe("importLoftFile", () => {
  it("posts the raw bytes and returns the part with its warnings", async () => {
    const seen: Request[] = [];
    const body = {
      part: { id: PART_ID, name: "Bracket copy" },
      warnings: [
        { code: "loft_tree_edited", message: "tree.json was changed" },
      ],
    };
    const client = recordingClient(Response.json(body, { status: 201 }), seen);
    const bytes = new Uint8Array([0x50, 0x4b, 3, 4]).buffer;
    const response = await importLoftFile(bytes, client);
    expect(response.part.id).toBe(PART_ID);
    expect(response.warnings?.[0]?.code).toBe("loft_tree_edited");
    const request = seen[0];
    expect(request?.method).toBe("POST");
    expect(request?.headers.get("Content-Type")).toBe(
      "application/octet-stream",
    );
    expect(new Uint8Array(await request!.arrayBuffer())).toEqual(
      new Uint8Array(bytes),
    );
  });

  it("throws the server's own message on a refusal", async () => {
    const client = recordingClient(
      Response.json(
        {
          error: {
            code: "loft_format_too_new",
            message: "This .loft was written by a newer Loft. Upgrade Loft.",
          },
        },
        { status: 422 },
      ),
    );
    await expect(importLoftFile(new ArrayBuffer(4), client)).rejects.toThrow(
      "Upgrade Loft",
    );
  });
});
