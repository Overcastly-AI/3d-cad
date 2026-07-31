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
/** Re-frame / re-scale / re-place a view (design §2.2). The drag-to-place seam
 * sends `position` + `auto_place: false`; the reset-to-auto seam sends
 * `auto_place: true`. Every field optional; `expected_version` guards the OCC. */
export type ViewUpdate = components["schemas"]["ViewUpdate"];
export type ViewScale = components["schemas"]["ViewScale"];
/** A section view's cutting plane + half selection (drawings-section.md §1). The
 * `plane` is the EXACT `GeomRef` union a sketch's plane uses (DatumPlaneRef |
 * FeatureRef) — no parallel plane taxonomy (DRY). */
export type SectionViewParams = components["schemas"]["SectionViewParams"];
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
export type EdgeSignature = components["schemas"]["EdgeSignature"];
export type DimensionResponse = components["schemas"]["DimensionResponse"];
/** The discriminated dimension params union (linear | diameter | radius | angular). */
export type DimensionParams = DimensionResponse["dimension"];
export type DimensionCreate = components["schemas"]["DimensionCreate"];
export type AnnotationResponse = components["schemas"]["AnnotationResponse"];
/** The v1 annotation params (a free-text note: text + sheet point). */
export type NoteAnnotationParams =
  components["schemas"]["NoteAnnotationParams"];
export type AnnotationCreate = components["schemas"]["AnnotationCreate"];
export type DrawingDimensionInput =
  components["schemas"]["DrawingDimensionInput"];
export type MeasuredDimension = components["schemas"]["MeasuredDimension"];
export type MeasuredDimensionResult =
  components["schemas"]["MeasuredDimensionResult"];

// --- Composed sheet (DE-1c: the single server-side placement source) ---------
// The gateway `/sheet` route returns a fully-placed `ComposedSheet` — every
// coordinate already in FINAL sheet-mm SVG space (y-flip applied). The sheet
// renderer draws these primitives verbatim; the client no longer computes any
// layout/transform (the placement engine moved server-side, parity-gated DE-1a).
export type ComposedSheet = components["schemas"]["ComposedSheet"];
export type ComposedView = components["schemas"]["ComposedView"];
export type ComposedPoint = components["schemas"]["ComposedPoint"];
export type ComposedTitleBlock = components["schemas"]["ComposedTitleBlock"];
export type ComposedLineEdge = components["schemas"]["ComposedLineEdge"];
export type ComposedCircleEdge = components["schemas"]["ComposedCircleEdge"];
export type ComposedPolylineEdge =
  components["schemas"]["ComposedPolylineEdge"];
/** The discriminated placed-edge union (line | circle | polyline). */
export type ComposedEdge =
  ComposedLineEdge | ComposedCircleEdge | ComposedPolylineEdge;
/** A flat-pattern sheet's placed bend-table block — anchor rect + per-bend rows
 * (sheet-metal.md §7). Null for every standard (HLR) sheet. */
export type ComposedBendTable = components["schemas"]["ComposedBendTable"];
/** A placed free-text note annotation — text at a sheet point (design §2.2). */
export type ComposedNote = components["schemas"]["ComposedNote"];
/** A section view's placed crosshatch — the ANSI 45° cut-face fill
 * (drawings-section.md §5); null for every non-section view. */
export type ComposedHatch = components["schemas"]["ComposedHatch"];
/** One bend-table fold row (bend id, angle, radius, direction, allowance). */
export type BendTableRow = components["schemas"]["BendTableRow"];
/** The typed per-view/-feature error envelope (code + human message). */
export type FeatureError = components["schemas"]["FeatureError"];
export type ComposedMeasuredDimension =
  components["schemas"]["ComposedMeasuredDimension"];
export type ComposedDimensionError =
  components["schemas"]["ComposedDimensionError"];
/** The discriminated placed-dimension union (measured | error). */
export type ComposedDimension =
  ComposedMeasuredDimension | ComposedDimensionError;

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

/**
 * Rename one of the caller's drawings under the OCC guard (`expected_version`).
 * A drawing is a pure leaf — nothing references it — so a rename cannot orphan
 * anything; the guard is there because a rename is still a real write.
 */
export async function renameDrawing(
  drawingId: string,
  name: string,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<DrawingResponse> {
  const { data, error } = await client.PATCH("/api/v1/drawings/{drawing_id}", {
    params: { path: { drawing_id: drawingId } },
    body: { name, expected_version: expectedVersion },
  });
  if (error !== undefined) {
    const code = envelopeCode(error);
    if (code === "drawing_name_taken" || code === "name_taken") {
      throw new DrawingNameTakenError(
        name,
        envelopeMessage(error, `A drawing named "${name}" already exists.`),
      );
    }
    if (code === "stale_drawing_version") {
      throw new Error(
        envelopeMessage(
          error,
          "This drawing changed somewhere else. Reopen the register and try again.",
        ),
      );
    }
    throw new Error(
      envelopeMessage(error, "The drawing could not be renamed."),
    );
  }
  return data;
}

/**
 * Copy a drawing's sheets, views, dimensions and annotations (201). The copied
 * views keep pointing at the same part/assembly — a view is a reference — so
 * this duplicates the LAYOUT, never the modelled document. The server names the
 * copy and returns it.
 */
export async function duplicateDrawing(
  drawingId: string,
  client: GatewayClient = gatewayClient,
): Promise<DrawingResponse> {
  const { data, error } = await client.POST(
    "/api/v1/drawings/{drawing_id}/duplicate",
    { params: { path: { drawing_id: drawingId } } },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The drawing could not be duplicated."),
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
 * Re-place / re-scale / re-frame a stored view (200 with the bumped
 * `doc_version`; 422 on a stale version). The drag-to-place authoring path sends
 * `{ position, auto_place: false }` (the composer then honours the dragged
 * centre verbatim); the return-to-auto path sends `{ auto_place: true }`. The
 * caller re-fetches the tree + re-composes so the moved view repaints.
 */
export async function updateView(
  drawingId: string,
  viewId: string,
  body: ViewUpdate,
  client: GatewayClient = gatewayClient,
): Promise<components["schemas"]["ViewMutationResponse"]> {
  const { data, error } = await client.PATCH(
    "/api/v1/drawings/{drawing_id}/views/{view_id}",
    {
      params: { path: { drawing_id: drawingId, view_id: viewId } },
      body,
    },
  );
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The view could not be updated."));
  }
  return data;
}

/**
 * Author a dimension against a view (201; 422 on a stale version, on a wrong
 * edge/type combo the documents write-time check rejects — e.g. a diameter on a
 * line). Returns the new dimension + the bumped `doc_version`; the caller re-
 * fetches the tree so the stored dimension appears, then re-evaluates to measure
 * it. The value is ALWAYS taken from the model server-side (design §3.1).
 */
export async function createDimension(
  drawingId: string,
  viewId: string,
  body: DimensionCreate,
  client: GatewayClient = gatewayClient,
): Promise<components["schemas"]["DimensionMutationResponse"]> {
  const { data, error } = await client.POST(
    "/api/v1/drawings/{drawing_id}/views/{view_id}/dimensions",
    {
      params: { path: { drawing_id: drawingId, view_id: viewId } },
      body,
    },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The dimension could not be added."),
    );
  }
  return data;
}

/**
 * Delete a dimension (200 with the updated tree; the delete bumps `doc_version`).
 * `expectedVersion` guards the optimistic-concurrency counter.
 */
export async function deleteDimension(
  drawingId: string,
  dimensionId: string,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<DrawingTreeResponse> {
  const { data, error } = await client.DELETE(
    "/api/v1/drawings/{drawing_id}/dimensions/{dimension_id}",
    {
      params: {
        path: { drawing_id: drawingId, dimension_id: dimensionId },
        query: { expected_version: expectedVersion },
      },
    },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The dimension could not be deleted."),
    );
  }
  return data;
}

/**
 * Add an annotation (v1: a free-text note) to a sheet (append at the tip; 201
 * with the new note + bumped `doc_version`). `expected_version` guards the
 * optimistic-concurrency counter. The note is placed at its authored sheet
 * point by the composer and drawn on the DOM sheet from `ComposedSheet.notes`.
 */
export async function createAnnotation(
  drawingId: string,
  sheetId: string,
  body: AnnotationCreate,
  client: GatewayClient = gatewayClient,
): Promise<components["schemas"]["AnnotationMutationResponse"]> {
  const { data, error } = await client.POST(
    "/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/annotations",
    {
      params: { path: { drawing_id: drawingId, sheet_id: sheetId } },
      body,
    },
  );
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The note could not be added."));
  }
  return data;
}

/**
 * Delete an annotation (200 with the updated tree; the delete bumps
 * `doc_version`). `expectedVersion` guards the optimistic-concurrency counter.
 */
export async function deleteAnnotation(
  drawingId: string,
  annotationId: string,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<DrawingTreeResponse> {
  const { data, error } = await client.DELETE(
    "/api/v1/drawings/{drawing_id}/annotations/{annotation_id}",
    {
      params: {
        path: { drawing_id: drawingId, annotation_id: annotationId },
        query: { expected_version: expectedVersion },
      },
    },
  );
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The note could not be deleted."));
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

/**
 * Compose the drawing into a fully-placed {@link ComposedSheet} — the JSON-model
 * twin of the byte export (DE-1b). The gateway does the SAME two-hop aggregation
 * (drawing tree + the referenced part's evaluation-ready feature prefix) then
 * calls geometry's composer, returning placed views/edges/dimensions/title-block
 * in sheet-mm SVG space (y-flip applied). This is the SINGLE placement source the
 * sheet renders from (DE-1c) — the browser no longer computes any layout. The
 * route takes no body; it reads the drawing's persisted state server-side.
 *
 * `sheetId` picks WHICH sheet to compose (the active sheet of a multi-sheet
 * drawing); omitting it composes the first sheet (back-compat). An unknown id is
 * a `sheet_not_found` 404, a sheet with no views a `drawing_not_composable` 422 —
 * both surface the server envelope's own message.
 */
export async function composeDrawingSheet(
  drawingId: string,
  sheetId?: string | null,
  client: GatewayClient = gatewayClient,
): Promise<ComposedSheet> {
  const { data, error } = await client.POST(
    "/api/v1/drawings/{drawing_id}/sheet",
    {
      params: {
        path: { drawing_id: drawingId },
        query: sheetId ? { sheet: sheetId } : undefined,
      },
    },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The drawing sheet could not be composed."),
    );
  }
  return data;
}
