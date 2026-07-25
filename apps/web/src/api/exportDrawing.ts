/**
 * Drawing export data layer — the shop deliverable. The gateway composes the
 * laid-out sheet server-side (same placement the DrawingSheet renders) and
 * streams the artifact BYTES with a `Content-Disposition` filename. All types
 * come from the generated `@loft/ts-client` (pydantic → OpenAPI → TS; CLAUDE.md
 * DRY rule); this module never hand-writes an API shape.
 */
import type { GatewayClient, operations } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import {
  type ExportedFile,
  parseContentDispositionFilename,
} from "./exportPart";

/** The artifact formats the drawing export route composes (typed off the route). */
export type DrawingExportFormat = NonNullable<
  NonNullable<
    operations["export_drawing_api_v1_drawings__drawing_id__export_post"]["parameters"]["query"]
  >["format"]
>;

/**
 * Export a laid-out drawing via the gateway
 * (`POST /api/v1/drawings/{id}/export?format=&sheet=`). The server composes the
 * sheet from the SAME persisted placement the on-screen sheet shows —
 * byte-deterministic — and streams the artifact (PDF/SVG/DXF) back. `sheetId`
 * picks WHICH sheet to export (the active sheet of a multi-sheet drawing);
 * omitting it exports the first sheet (back-compat). `client` is injectable for
 * tests.
 */
export async function exportDrawing(
  drawingId: string,
  format: DrawingExportFormat,
  sheetId?: string | null,
  client: GatewayClient = gatewayClient,
): Promise<ExportedFile> {
  const { data, error, response } = await client.POST(
    "/api/v1/drawings/{drawing_id}/export",
    {
      params: {
        path: { drawing_id: drawingId },
        query: sheetId ? { format, sheet: sheetId } : { format },
      },
      parseAs: "blob",
    },
  );
  if (error !== undefined) {
    throw new Error(
      `The drawing service rejected the ${format.toUpperCase()} export`,
    );
  }
  if (data === undefined) {
    throw new Error(`${format.toUpperCase()} export returned no file`);
  }
  // parseAs:"blob" makes the runtime payload a Blob (openapi-fetch pass-through);
  // the OpenAPI schema types binary content as string.
  const blob = data as unknown as Blob;
  const filename = parseContentDispositionFilename(
    response.headers.get("Content-Disposition"),
    `drawing.${format}`,
  );
  return { blob, filename };
}
