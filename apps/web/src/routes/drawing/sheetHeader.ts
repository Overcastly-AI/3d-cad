/**
 * The drawing page's sheet-header vocabulary and the reads/writes behind it:
 * the projection convention + paper orientation names, the source-extents
 * query every fit reads, and the sheet re-head PATCH. Split out of
 * `DrawingPage.tsx` (SPLIT-DRAWINGPAGE); behaviour unchanged.
 */
import {
  type RefDocumentKind,
  type SheetResponse,
  fetchAssemblyExtents,
} from "../../api/drawings";
import { gatewayClient } from "../../api/client";
import { envelopeMessage } from "../../api/envelope";
import { evaluatePart } from "../../api/parts";
import {
  SCALE_OPTIONS,
  type ModelExtents,
  boxExtents,
} from "../../drawing/layout";

/** The scale (num/den) for a picker value like "1:2", defaulting to 1:1. */
export function scaleFromValue(value: string): {
  numerator: number;
  denominator: number;
} {
  const found = SCALE_OPTIONS.find((s) => s.value === value);
  return found
    ? { numerator: found.numerator, denominator: found.denominator }
    : { numerator: 1, denominator: 1 };
}

/** The sheet's drafting-standard placement convention (ISO 128 / design §1.2). */
export type SheetProjection = SheetResponse["projection"];
/** The sheet's paper orientation (landscape | portrait). */
export type SheetOrientation = SheetResponse["orientation"];

/** Plain-language name per convention — the words the cell and its accessible
 * name both read from, so the stamp and the screen reader never disagree. */
export const CONVENTION_NAME: Record<SheetProjection, string> = {
  third_angle: "third angle",
  first_angle: "first angle",
};
export const ORIENTATION_NAME: Record<SheetOrientation, string> = {
  landscape: "landscape",
  portrait: "portrait",
};
/** The other value of a two-valued sheet header field. */
export const OTHER_CONVENTION: Record<SheetProjection, SheetProjection> = {
  third_angle: "first_angle",
  first_angle: "third_angle",
};
export const OTHER_ORIENTATION: Record<SheetOrientation, SheetOrientation> = {
  landscape: "portrait",
  portrait: "landscape",
};

/**
 * How big is the drafted document — the ONE reading every fit on this page
 * takes, for EITHER kind of source (ASMDRAW-FIT-1b).
 *
 * A part reads the bbox off its evaluation's mass properties; an assembly reads
 * the SOLVED compound's extents off `GET /assemblies/{id}/extents`. The second
 * is the whole point of this seam: an assembly's instances carry authored seed
 * placements, and folding those client-side would size the sheet for a pose the
 * mates have already moved. On the reference rig (two 40x25x10 plates seeded
 * 80 mm apart, then bolted flush) the seeds span 120 mm in x and the solved
 * compound 40 — different paper, different scale, and only the second one is
 * the drawing the user asked for.
 *
 * `null` means there is nothing to fit — an assembly whose instances produced
 * no body, or a part whose evaluation reported no box. Callers keep the user's
 * picked scale in that case rather than substituting one: a fit with no
 * measurement behind it is a guess, and a silently-guessed scale is worse than
 * an honest one the sheet's own layout checks can then complain about.
 *
 * NB the assembly branch does NOT gate on the solve `status`. Geometry's
 * `test_status_alone_cannot_distinguish_the_two` shows a seating solve and a
 * constraint-free one both report `under_constrained`, so a status gate here
 * would behave identically in a world where the route answered with seeds.
 */
export async function fetchSourceExtents(
  sourceId: string,
  kind: RefDocumentKind,
): Promise<ModelExtents | null> {
  if (kind === "assembly") {
    const { bounding_box: box } = await fetchAssemblyExtents(sourceId);
    return box ? boxExtents(box) : null;
  }
  const evaluated = await evaluatePart(sourceId);
  const box = evaluated.properties?.bounding_box;
  return box ? boxExtents(box) : null;
}

/**
 * The query the orientation proposal and the layout action BOTH read their
 * measurement from — one definition, so the cell can never promise a scale from
 * a different reading than the one the layout fits against, and selecting a
 * source costs exactly one evaluation whether the user reads the proposal or
 * goes straight to "Lay out".
 */
export function sourceExtentsQueryOptions(
  sourceId: string,
  kind: RefDocumentKind,
  treeVersion: number | undefined,
) {
  return {
    queryKey: ["drawing-source-extents", sourceId, kind, treeVersion] as const,
    queryFn: () => fetchSourceExtents(sourceId, kind),
    staleTime: Infinity,
  };
}

/**
 * Re-head an existing sheet (`SheetUpdate`) — the wire behind the header cells:
 * flipping the projection convention or the paper orientation re-lays the sheet
 * out server-side (the composer re-derives every auto-placed anchor from the
 * sheet's own convention), so the client computes nothing.
 *
 * NB this belongs beside `createSheet` in `../api/drawings`; it lives with the
 * drawing page only because this batch's territory split gives that file to
 * another builder. Same shape as its siblings — generated client, generated body type, server envelope
 * message on failure (no hand-written API shape; CLAUDE.md DRY rule).
 */
export async function updateSheetHeader(
  drawingId: string,
  sheetId: string,
  body: { expected_version: number } & (
    { projection: SheetProjection } | { orientation: SheetOrientation }
  ),
): Promise<{ doc_version: number }> {
  const { data, error } = await gatewayClient.PATCH(
    "/api/v1/drawings/{drawing_id}/sheets/{sheet_id}",
    {
      params: { path: { drawing_id: drawingId, sheet_id: sheetId } },
      body,
    },
  );
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The sheet could not be updated."));
  }
  return data;
}
