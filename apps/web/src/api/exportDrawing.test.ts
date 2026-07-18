import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import { exportDrawing } from "./exportDrawing";

const DRAWING_ID = "22222222-2222-2222-2222-222222222222";

/** Typed client whose transport is a canned response — no network. */
function clientReturning(response: Response) {
  return createGatewayClient({
    baseUrl: "http://gateway.test",
    fetch: () => Promise.resolve(response),
  });
}

/** A minimal but valid PDF byte prefix for the streamed-bytes assertion. */
const PDF_BYTES = new TextEncoder().encode("%PDF-1.7\n%\xff\xff\n");

describe("exportDrawing", () => {
  it("streams the composed PDF bytes and reads the server filename", async () => {
    const client = clientReturning(
      new Response(PDF_BYTES, {
        status: 200,
        headers: {
          "Content-Type": "application/pdf",
          "Content-Disposition": 'attachment; filename="Plate - sheet 1.pdf"',
        },
      }),
    );
    const file = await exportDrawing(DRAWING_ID, "pdf", client);
    expect(file.filename).toBe("Plate - sheet 1.pdf");
    const text = await file.blob.text();
    expect(text.startsWith("%PDF-")).toBe(true);
  });

  it("falls back to drawing.<format> when the header is absent", async () => {
    const client = clientReturning(
      new Response(PDF_BYTES, {
        status: 200,
        headers: { "Content-Type": "application/pdf" },
      }),
    );
    const file = await exportDrawing(DRAWING_ID, "pdf", client);
    expect(file.filename).toBe("drawing.pdf");
    expect(file.blob.size).toBe(PDF_BYTES.byteLength);
  });

  it("throws a labelled error when the gateway rejects the export", async () => {
    const client = clientReturning(
      new Response(JSON.stringify({ error: { code: "compose_failed" } }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(exportDrawing(DRAWING_ID, "pdf", client)).rejects.toThrow(
      /rejected the PDF export/,
    );
  });
});
