/**
 * Cut-list data layer (CUT-LIST): a part's or an assembly's members grouped by
 * member, profile, material and MEASURED length, with stock lengths, and the
 * same list as a CSV download. Types come from the generated `@loft/ts-client`
 * (pydantic → OpenAPI → TS); the grouping is the gateway's, never redone here.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeMessage } from "./envelope";
import {
  type ExportedFile,
  parseContentDispositionFilename,
} from "./exportPart";

export type CutListResponse = components["schemas"]["CutListResponse"];
export type CutListLine = components["schemas"]["CutListLine"];
export type CutListSource = "part" | "assembly";

const LOAD_FAILED = "The cut list could not be loaded.";
const CSV_FAILED = "The cut list CSV could not be written.";

/** The cut list of a part or an assembly (all levels, times quantity). */
export async function fetchCutList(
  kind: CutListSource,
  documentId: string,
  client: GatewayClient = gatewayClient,
): Promise<CutListResponse> {
  if (kind === "part") {
    const { data, error } = await client.GET(
      "/api/v1/parts/{part_id}/cut-list",
      { params: { path: { part_id: documentId } } },
    );
    if (error !== undefined) {
      throw new Error(envelopeMessage(error, LOAD_FAILED));
    }
    return data;
  }
  const { data, error } = await client.GET(
    "/api/v1/assemblies/{assembly_id}/cut-list",
    { params: { path: { assembly_id: documentId } } },
  );
  if (error !== undefined) throw new Error(envelopeMessage(error, LOAD_FAILED));
  return data;
}

/** The cut list as a CSV file (lengths in the document's display unit). */
export async function exportCutListCsv(
  kind: CutListSource,
  documentId: string,
  client: GatewayClient = gatewayClient,
): Promise<ExportedFile> {
  const { data, error, response } =
    kind === "part"
      ? await client.GET("/api/v1/parts/{part_id}/cut-list/csv", {
          params: { path: { part_id: documentId } },
          parseAs: "blob",
        })
      : await client.GET("/api/v1/assemblies/{assembly_id}/cut-list/csv", {
          params: { path: { assembly_id: documentId } },
          parseAs: "blob",
        });
  if (error !== undefined || data === undefined) throw new Error(CSV_FAILED);
  // parseAs:"blob" makes the runtime payload a Blob (openapi-fetch pass-through).
  const blob = data as unknown as Blob;
  const filename = parseContentDispositionFilename(
    response.headers.get("Content-Disposition"),
    "cut list.csv",
  );
  return { blob, filename };
}
