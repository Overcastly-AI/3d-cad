/**
 * Drawings data layer — drawing / sheet / view CRUD and the standard-view
 * projection, all proxied through the gateway. Every type comes from the
 * generated `@loft/ts-client` (pydantic → OpenAPI → TS; CLAUDE.md DRY rule);
 * this module never hand-writes an API shape, and each function surfaces the
 * server envelope's own message on failure.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeCode, envelopeMessage } from "./envelope";

export type DrawingResponse = components["schemas"]["DrawingResponse"];
export type DrawingTreeResponse = components["schemas"]["DrawingTreeResponse"];
export type SheetContent = components["schemas"]["SheetContent"];
export type SheetResponse = components["schemas"]["SheetResponse"];
export type SheetCreate = components["schemas"]["SheetCreate"];
export type ViewResponse = components["schemas"]["ViewResponse"];
export type ViewCreate = components["schemas"]["ViewCreate"];
export type ViewScale = components["schemas"]["ViewScale"];
export type SheetPoint = components["schemas"]["SheetPoint"];
export type SheetSize = SheetResponse["size"];
export type ViewProjection = ViewResponse["projection"];
export type EvaluateDrawingViewsRequest =
  components["schemas"]["EvaluateDrawingViewsRequest"];
export type EvaluateDrawingViewsResult =
  components["schemas"]["EvaluateDrawingViewsResult"];
export type DrawingViewResult = components["schemas"]["DrawingViewResult"];
export type ProjectedViewEdge = components["schemas"]["ProjectedViewEdge"];
export type ProjectedPoint = components["schemas"]["ProjectedPoint"];

/**
 * The chosen name already belongs to another of the caller's drawings
 * (documents enforces a per-owner unique index → gateway 409). Typed so the
 * register can pin it to the name field, mirroring `PartNameTakenError`.
 */
export class DrawingNameTakenError extends Error {
  constructor(
    readonly drawingName: string,
    message: string,
  ) {
    super(message);
    this.name = "DrawingNameTakenError";
  }
}

/** The caller's drawings, oldest first (register order). */
export async function fetchDrawings(
  client: GatewayClient = gatewayClient,
): Promise<DrawingResponse[]> {
  const { data, error } = await client.GET("/api/v1/drawings");
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "Your drawings could not be loaded."),
    );
  }
  return data.drawings;
}

/** Create a drawing owned by the caller (201). A duplicate name → 409. */
export async function createDrawing(
  name: string,
  client: GatewayClient = gatewayClient,
): Promise<DrawingResponse> {
  const { data, error } = await client.POST("/api/v1/drawings", {
    body: { name },
  });
  if (error !== undefined) {
    if (
      envelopeCode(error) === "drawing_name_taken" ||
      envelopeCode(error) === "name_taken"
    ) {
      throw new DrawingNameTakenError(
        name,
        envelopeMessage(error, `A drawing named "${name}" already exists.`),
      );
    }
    throw new Error(
      envelopeMessage(error, "The drawing could not be created."),
    );
  }
  return data;
}

/** Delete one of the caller's drawings (204; 404 for unknown/foreign ids). */
export async function deleteDrawing(
  drawingId: string,
  client: GatewayClient = gatewayClient,
): Promise<void> {
  const { error } = await client.DELETE("/api/v1/drawings/{drawing_id}", {
    params: { path: { drawing_id: drawingId } },
  });
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The drawing could not be deleted."),
    );
  }
}

/** The drawing's full sheet → view/dimension/annotation tree + OCC token. */
export async function fetchDrawing(
  drawingId: string,
  client: GatewayClient = gatewayClient,
): Promise<DrawingTreeResponse> {
  const { data, error } = await client.GET("/api/v1/drawings/{drawing_id}", {
    params: { path: { drawing_id: drawingId } },
  });
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The drawing could not be loaded."));
  }
  return data;
}

/** Append a sheet to a drawing (201; 422 on a stale version). */
export async function createSheet(
  drawingId: string,
  body: SheetCreate,
  client: GatewayClient = gatewayClient,
): Promise<components["schemas"]["SheetMutationResponse"]> {
  const { data, error } = await client.POST(
    "/api/v1/drawings/{drawing_id}/sheets",
    { params: { path: { drawing_id: drawingId } }, body },
  );
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The sheet could not be added."));
  }
  return data;
}

/** Append a view referencing a part to a sheet (201; 422 on a stale version). */
export async function createView(
  drawingId: string,
  sheetId: string,
  body: ViewCreate,
  client: GatewayClient = gatewayClient,
): Promise<components["schemas"]["ViewMutationResponse"]> {
  const { data, error } = await client.POST(
    "/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/views",
    {
      params: { path: { drawing_id: drawingId, sheet_id: sheetId } },
      body,
    },
  );
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The view could not be added."));
  }
  return data;
}

/**
 * Project a part into its requested standard drawing views: geometry evaluates
 * the part body ONCE then runs exact HLR per view, returning each view's
 * canonically-ordered visible+hidden 2D edges (or a typed per-view error). A
 * bad body / HLR failure is a 200 with a typed error, never a 5xx; the envelope
 * stays reserved for transport/validation failures of this call itself.
 */
export async function evaluateDrawingViews(
  request: EvaluateDrawingViewsRequest,
  client: GatewayClient = gatewayClient,
): Promise<EvaluateDrawingViewsResult> {
  const { data, error } = await client.POST(
    "/api/v1/geometry/drawing/evaluate",
    { body: request },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The drawing views could not be projected."),
    );
  }
  return data;
}
