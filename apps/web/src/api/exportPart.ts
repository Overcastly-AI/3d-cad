/**
 * STEP/STL export data layer — all types come from the generated
 * `@loft/ts-client` (pydantic → OpenAPI → TS; CLAUDE.md DRY rule).
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import {
  gatewayClient,
  MESH_ANGULAR_DEFLECTION_RAD,
  MESH_LINEAR_DEFLECTION_MM,
} from "./client";
import type { BoxParams } from "./tessellate";

export type ExportRequest = components["schemas"]["ExportRequest"];
export type ExportFormat = ExportRequest["format"];

export interface ExportedFile {
  /** The exported CAD file bytes, ready for an anchor download. */
  blob: Blob;
  /** Download filename from Content-Disposition (server is authoritative). */
  filename: string;
}

/**
 * Extract the download filename from a `Content-Disposition` header
 * (`attachment; filename="box.step"` — quoted or bare). Returns `fallback`
 * when the header is absent or carries no usable name; any path segments a
 * hostile header might smuggle in are stripped to the basename.
 */
export function parseContentDispositionFilename(
  header: string | null,
  fallback: string,
): string {
  if (header === null) return fallback;
  const match = /filename\s*=\s*(?:"([^"]*)"|([^;\s]+))/i.exec(header);
  const raw = match?.[1] ?? match?.[2];
  if (raw === undefined) return fallback;
  const basename = raw.split(/[/\\]/).pop()?.trim();
  return basename ? basename : fallback;
}

/**
 * Export the current parametric box via the gateway. STEP is the exact
 * B-rep; STL is faceted with the SAME deflections as the viewport mesh, so
 * the file matches what the screen shows. `client` is injectable for tests.
 */
export async function exportBox(
  format: ExportFormat,
  params: BoxParams,
  client: GatewayClient = gatewayClient,
): Promise<ExportedFile> {
  const { data, error, response } = await client.POST(
    "/api/v1/geometry/export",
    {
      body: {
        shape: "box",
        format,
        params,
        linear_deflection: MESH_LINEAR_DEFLECTION_MM,
        angular_deflection: MESH_ANGULAR_DEFLECTION_RAD,
      },
      parseAs: "blob",
    },
  );
  if (error !== undefined) {
    throw new Error(
      `The geometry service rejected the ${format.toUpperCase()} export`,
    );
  }
  if (data === undefined) {
    throw new Error(`${format.toUpperCase()} export returned no file`);
  }
  // The OpenAPI schema types binary content as string; parseAs:"blob" makes
  // the runtime payload a Blob (openapi-fetch pass-through).
  const blob = data as unknown as Blob;
  const filename = parseContentDispositionFilename(
    response.headers.get("Content-Disposition"),
    `box.${format}`,
  );
  return { blob, filename };
}

/**
 * Mark a download as a PREFIX of the tree: `part-1234.step` → `part-1234-partial.step`.
 *
 * The server names the file after the part it exported, which is the right
 * default and the wrong claim when the tree is rolled back: the bytes are the
 * body up to the travel stop, and the file outlives the screen that said so
 * (AUDIT-ENGINEERING J2 — the export cell must not hand over an artifact the
 * user believes is their whole model). The suffix goes before the extension so
 * the file still opens as STEP/STL by association.
 */
export function markFilenamePartial(filename: string): string {
  const dot = filename.lastIndexOf(".");
  if (dot <= 0) return `${filename}-partial`;
  return `${filename.slice(0, dot)}-partial${filename.slice(dot)}`;
}

/**
 * Export the CURRENT part's evaluated feature tree via the gateway
 * (`POST /api/v1/parts/{id}/export?format=`). Unlike {@link exportBox}, which
 * exports a bare parametric primitive, this exports the body the engineer
 * actually modeled — the tree is evaluated (rollback bar applied) and the
 * last-good solid is streamed as STEP or STL. `client` is injectable for tests.
 */
export async function exportPartTree(
  partId: string,
  format: ExportFormat,
  client: GatewayClient = gatewayClient,
): Promise<ExportedFile> {
  const { data, error, response } = await client.POST(
    "/api/v1/parts/{part_id}/export",
    {
      params: { path: { part_id: partId }, query: { format } },
      parseAs: "blob",
    },
  );
  if (error !== undefined) {
    throw new Error(
      `The geometry service rejected the ${format.toUpperCase()} export`,
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
    `part.${format}`,
  );
  return { blob, filename };
}

/**
 * Export the current part's FLAT PATTERN as a profile-only DXF cut path
 * (`POST /api/v1/parts/{id}/flat-pattern.dxf`).
 *
 * Not a format of {@link exportPartTree}, and deliberately so: those write the
 * 3-D body, this writes the 2-D blank a laser or turret punch cuts — the outline
 * and the fold lines at 1:1 in millimetres, with no drawing sheet around them.
 * It is the artifact a sheet-metal vendor asks for by name, and until now the
 * only way to get one was to author a drawing, export it as DXF, and delete the
 * A4 border, title block and bend table by hand for every revision.
 *
 * A part that is not sheet metal is the gateway's typed 422, surfaced as the
 * message rather than a mystery failure — an empty DXF would be worse than an
 * error, because a shop cannot tell one from a broken export.
 */
export async function exportPartFlatPatternDxf(
  partId: string,
  client: GatewayClient = gatewayClient,
): Promise<ExportedFile> {
  const { data, error, response } = await client.POST(
    "/api/v1/parts/{part_id}/flat-pattern.dxf",
    { params: { path: { part_id: partId } }, parseAs: "blob" },
  );
  if (error !== undefined) {
    throw new Error(
      "This part has no flat pattern to cut — add a sheet-metal base flange first",
    );
  }
  if (data === undefined) {
    throw new Error("Flat-pattern DXF export returned no file");
  }
  // parseAs:"blob" makes the runtime payload a Blob (openapi-fetch pass-through);
  // the OpenAPI schema types binary content as string.
  const blob = data as unknown as Blob;
  const filename = parseContentDispositionFilename(
    response.headers.get("Content-Disposition"),
    "flat-pattern.dxf",
  );
  return { blob, filename };
}

/** Hand a blob to the browser as a named file download (blob URL + anchor). */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
