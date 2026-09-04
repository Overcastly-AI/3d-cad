import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { Button, NumberField, Stamp, TextField, drawing } from "@loft/design";

import {
  type AnnotationResponse,
  type BendTableRow,
  type ComposedView,
  type DimensionParams,
  type DimensionResponse,
  type DrawingBomLine,
  type DrawingDimensionInput,
  type DrawingViewResult,
  type EvaluateDrawingViewsRequest,
  type MeasuredDimension,
  type RefDocumentKind,
  type SectionViewParams,
  type SheetContent,
  type SheetResponse,
  type SheetSize,
  type ViewProjection,
  composeDrawingSheet,
  createAnnotation,
  createDimension,
  createSheet,
  createView,
  deleteAnnotation,
  deleteDimension,
  evaluateDrawingViews,
  fetchAssemblyExtents,
  fetchDrawing,
  fetchDrawingBom,
  updateView,
} from "../api/drawings";
import { gatewayClient } from "../api/client";
import { envelopeMessage } from "../api/envelope";
import { evaluatePart, fetchFeatureTree, fetchParts } from "../api/parts";
import { fetchAssemblies } from "../api/assemblies";
import { Breadcrumb } from "../components/Breadcrumb";
import { DimensionAuthorMenu } from "../components/DimensionAuthorMenu";
import { DrawingCommandBand } from "../components/DrawingCommandBand";
import {
  DrawingSheet,
  type DimensionGrabEvent,
  type EdgePickEvent,
  type EndpointPickEvent,
  edgeKey,
  vertexKey,
} from "../components/DrawingSheet";
import { FloatingPanel } from "../components/FloatingPanel";
import { SectionAuthorPanel } from "../components/SectionAuthorPanel";
import { SheetIssueStrip } from "../components/SheetIssueStrip";
import { TopBar } from "../components/TopBar";
import { TopToolbar } from "../components/TopToolbar";
import {
  IDLE,
  PLACE_NUDGE_MM,
  type AuthoringState,
  type DimensionAction,
  armPair,
  armedSignatures,
  beginPlacement,
  beginReplacement,
  buildDimension,
  cancelPlacement,
  commitParams,
  menuActions,
  menuAnchor,
  movePlacement,
  nudgePlacement,
  pickEdge,
  pickEndpoint,
  pickHint,
  placementMoved,
  placementOffsetMm,
  placementReplaces,
  placementTarget,
  selectedEndpoints,
  setPlacementOffset,
} from "../drawing/authoring";
import { type DrawingExportFormat, exportDrawing } from "../api/exportDrawing";
import { downloadBlob } from "../api/exportPart";
import { healDimensionParams, reanchoredAnchor } from "../drawing/anchorHeal";
import { formatDimensionLabel } from "../drawing/dimensions";
import { exportSheetSvg } from "../drawing/exportSvg";
import {
  ghostFor,
  offsetPlacementFromComposed,
  textPlacementFromComposed,
} from "../drawing/placement";
import {
  SCALE_OPTIONS,
  STANDARD_VIEWS,
  VIEW_LABEL,
  type ModelExtents,
  type OrientationFit,
  boxExtents,
  fitScale,
  proposeOrientation,
  reframePinnedCentre,
  sheetDimensions,
  sheetHeaderForNewSheet,
  sheetSizeLabel,
  standardLayout,
} from "../drawing/layout";
import {
  drawingSourceKind,
  drawingSourceName,
  drawingSourceOptions,
} from "../drawing/source";
import { isTypingTarget } from "../lib/isTypingTarget";
import { resolveDatumPlaneOptions } from "../sketch/plane";
import { drawingRoute } from "../router";

/** The scale (num/den) for a picker value like "1:2", defaulting to 1:1. */
function scaleFromValue(value: string): {
  numerator: number;
  denominator: number;
} {
  const found = SCALE_OPTIONS.find((s) => s.value === value);
  return found
    ? { numerator: found.numerator, denominator: found.denominator }
    : { numerator: 1, denominator: 1 };
}

/** The sheet's drafting-standard placement convention (ISO 128 / design §1.2). */
type SheetProjection = SheetResponse["projection"];
/** The sheet's paper orientation (landscape | portrait). */
type SheetOrientation = SheetResponse["orientation"];

/** Plain-language name per convention — the words the cell and its accessible
 * name both read from, so the stamp and the screen reader never disagree. */
const CONVENTION_NAME: Record<SheetProjection, string> = {
  third_angle: "third angle",
  first_angle: "first angle",
};
const ORIENTATION_NAME: Record<SheetOrientation, string> = {
  landscape: "landscape",
  portrait: "portrait",
};
/** The other value of a two-valued sheet header field. */
const OTHER_CONVENTION: Record<SheetProjection, SheetProjection> = {
  third_angle: "first_angle",
  first_angle: "third_angle",
};
const OTHER_ORIENTATION: Record<SheetOrientation, SheetOrientation> = {
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
async function fetchSourceExtents(
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
function sourceExtentsQueryOptions(
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
 * NB this belongs beside `createSheet` in `../api/drawings`; it lives here only
 * because this batch's territory split gives that file to another builder. Same
 * shape as its siblings — generated client, generated body type, server envelope
 * message on failure (no hand-written API shape; CLAUDE.md DRY rule).
 */
async function updateSheetHeader(
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

/**
 * The drawing editor — an engineering sheet on the blued-steel bench. The
 * signature action drops the standard four views (front / top / right + iso,
 * third-angle) onto the sheet: it creates the views (CRUD) and projects the
 * referenced part through `/geometry/drawing/evaluate`, then renders each view
 * as scale-correct SVG — visible edges solid, hidden edges dashed. The sheet is
 * the hero; the chrome recedes.
 */
export function DrawingPage() {
  const { drawingId } = drawingRoute.useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const drawingQuery = useQuery({
    queryKey: ["drawing", drawingId],
    queryFn: () => fetchDrawing(drawingId),
  });
  const tree = drawingQuery.data;
  const docVersion = tree?.doc_version ?? 0;

  // Multi-sheet: the drawing stores an ORDERED list of sheets (the API has always
  // supported many; FINDINGS #18 was the missing UI). `activeSheetIndex` selects
  // which one the page reads + acts on; the switcher below moves it. Clamped when
  // the tree changes (a delete/refetch can shrink the list under a stale index).
  const sheetCount = tree?.sheets.length ?? 0;
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  useEffect(() => {
    if (sheetCount > 0 && activeSheetIndex >= sheetCount) {
      setActiveSheetIndex(sheetCount - 1);
    }
  }, [sheetCount, activeSheetIndex]);
  const activeIndex = activeSheetIndex < sheetCount ? activeSheetIndex : 0;

  const sheet = tree?.sheets[activeIndex]?.sheet ?? null;
  // The active sheet's id threads through compose + export so BOTH render the
  // sheet the switcher selects (not always sheet 0). Omitting it composes the
  // first sheet (back-compat); the gateway now accepts `?sheet=<id>` on both.
  const activeSheetId = sheet?.id ?? null;
  const views = useMemo(
    () => tree?.sheets[activeIndex]?.views ?? [],
    [tree, activeIndex],
  );
  // The projections actually persisted on the sheet — the SET we evaluate (so a
  // flat-pattern sheet evaluates `flat_pattern`, carrying its bend-table +
  // provenance + any typed failure). Falls back to the standard four before layout.
  const requestedViews = useMemo<ViewProjection[]>(() => {
    const seen = new Set<ViewProjection>();
    const ordered: ViewProjection[] = [];
    for (const view of views) {
      if (seen.has(view.projection)) continue;
      seen.add(view.projection);
      ordered.push(view.projection);
    }
    return ordered.length > 0 ? ordered : [...STANDARD_VIEWS];
  }, [views]);
  const isFlatPatternSheet = requestedViews.includes("flat_pattern");
  // The persisted section view (v1: at most one) and its cutting-plane params.
  const sectionView = useMemo(
    () => views.find((view) => view.projection === "section") ?? null,
    [views],
  );
  // The evaluate wire keys `section_params` by the INDEX into `views` of each
  // section view (drawings-section.md §1); we send the persisted view's own
  // params so the PICK provenance for the section resolves (compose reads the
  // persisted params directly and needs no body). Empty for a non-section sheet.
  const sectionParamsByIndex = useMemo(() => {
    const map: Record<string, SectionViewParams> = {};
    requestedViews.forEach((projection, index) => {
      if (projection === "section" && sectionView?.section_params) {
        map[String(index)] = sectionView.section_params;
      }
    });
    return map;
  }, [requestedViews, sectionView]);
  const dimensions = useMemo<readonly DimensionResponse[]>(
    () => tree?.sheets[activeIndex]?.dimensions ?? [],
    [tree, activeIndex],
  );
  const annotations = useMemo<readonly AnnotationResponse[]>(
    () => tree?.sheets[activeIndex]?.annotations ?? [],
    [tree, activeIndex],
  );
  const hasLayout = sheet !== null && views.length > 0;

  // view id → its projection, and dimensions grouped by the view they annotate.
  const projectionByViewId = useMemo(() => {
    const map = new Map<string, ViewProjection>();
    for (const view of views) map.set(view.id, view.projection);
    return map;
  }, [views]);
  // The evaluate-request twin of the stored dimensions (each tagged with its
  // view) — geometry measures these against the SAME body it projects (§3.1).
  const dimensionInputs = useMemo<DrawingDimensionInput[]>(() => {
    const out: DrawingDimensionInput[] = [];
    for (const dim of dimensions) {
      const view = projectionByViewId.get(dim.view_id);
      if (!view) continue;
      out.push({ id: dim.id, view, dimension: dim.dimension });
    }
    return out;
  }, [dimensions, projectionByViewId]);

  // The document the sheet drafts: the reference of its first view once laid
  // out (the one-sheet-one-source invariant, §2.2). It is a PART or an
  // ASSEMBLY — both have always been legal on the wire, and the assembly half
  // is what a numbered parts list hangs off.
  const draftedSourceId = hasLayout
    ? (views[0]?.ref_document_id ?? null)
    : null;
  const draftedSourceKind: RefDocumentKind = hasLayout
    ? (views[0]?.ref_document_kind ?? "part")
    : "part";

  const partsQuery = useQuery({
    queryKey: ["parts"],
    queryFn: () => fetchParts(),
    staleTime: 30_000,
  });
  const parts = useMemo(() => partsQuery.data ?? [], [partsQuery.data]);
  const assembliesQuery = useQuery({
    queryKey: ["assemblies"],
    queryFn: () => fetchAssemblies(),
    staleTime: 30_000,
  });
  const assemblies = useMemo(
    () => assembliesQuery.data ?? [],
    [assembliesQuery.data],
  );
  const sources = useMemo(
    () => drawingSourceOptions(parts, assemblies),
    [parts, assemblies],
  );

  // Pre-layout picker state (what to draft, on what sheet, at what scale).
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [scaleValue, setScaleValue] = useState("1:1");
  const [sizeValue, setSizeValue] = useState<SheetSize>("A4");
  // `?source=<id>` pre-selects the picker — how the assembly workspace's
  // "Drawing" action hands off, so the sheet opens already pointed at the
  // assembly you were looking at instead of making you find it in a list.
  // Honoured once, and only for a source that actually exists (a stale link
  // must not strand the picker on an id nothing can project).
  //
  // Seeding is ONE effect on purpose. As two, the hand-off and the "default to
  // the first source" rule both fired in the commit where the registers land —
  // each reading the same `null` — and the default won, so the hand-off
  // silently did nothing. Resolving both in one place makes the precedence
  // explicit instead of a function of effect order.
  const { source: requestedSourceId } = drawingRoute.useSearch();
  const handedOff = useRef(false);
  useEffect(() => {
    if (sources.length === 0) return;
    if (
      !handedOff.current &&
      requestedSourceId !== undefined &&
      sources.some((source) => source.id === requestedSourceId)
    ) {
      handedOff.current = true;
      setSelectedSourceId(requestedSourceId);
      return;
    }
    setSelectedSourceId((current) => current ?? sources[0]?.id ?? null);
  }, [sources, requestedSourceId]);
  const selectedSourceKind = drawingSourceKind(sources, selectedSourceId);

  // The effective source + scale to project: the drafted one once laid out.
  const effectiveSourceId = draftedSourceId ?? null;
  const effectiveSourceKind: RefDocumentKind = hasLayout
    ? draftedSourceKind
    : selectedSourceKind;
  // The part-shaped pipeline (feature tree → evaluate → pick provenance) runs
  // for a part source ONLY. An assembly sheet is composed entirely server-side
  // (the gateway resolves its instance+mate graph and geometry projects the
  // SOLVED compound), so the browser has no feature tree to send and needs none.
  const effectivePartId =
    effectiveSourceKind === "part" ? effectiveSourceId : null;
  const effectiveScaleValue = hasLayout
    ? `${views[0]?.scale.numerator ?? 1}:${views[0]?.scale.denominator ?? 1}`
    : scaleValue;
  // Post-layout the sheet SIZE is read from the persisted sheet (mirroring how
  // the scale readout derives from the stored view scale); pre-layout it is the
  // user's pick. Changing it after layout is a re-layout, not a re-size in place
  // (the backend has no re-flow-on-resize; matches how scale re-selection works).
  const effectiveSize: SheetSize = hasLayout
    ? (sheet?.size ?? "A4")
    : sizeValue;

  // The drafted part's feature tree (the projection intent).
  const partTreeQuery = useQuery({
    queryKey: ["drawing-part-tree", effectivePartId],
    enabled: effectivePartId !== null,
    queryFn: () => fetchFeatureTree(effectivePartId as string),
    staleTime: 30_000,
  });
  const partTree = partTreeQuery.data;

  // The document the proposal MEASURES: the drafted one once laid out, and the
  // one the picker is pointing at before that. Reading `effectiveSourceId` here
  // was the root of REACH-3-FLOW's P1-1 — it is null until a sheet has views, so
  // the query never ran on the create screen and `orientationFit` was
  // structurally null at every Sheet-1 create path. A proposal that cannot have
  // been computed cannot fire.
  const measuredSourceId = draftedSourceId ?? selectedSourceId;
  const measuredSourceKind: RefDocumentKind = hasLayout
    ? draftedSourceKind
    : selectedSourceKind;

  // The drafted document's extents — the ONLY input the orientation proposal
  // needs, and the SAME reading the layout action fits its scale from
  // (`fetchSourceExtents`), so the header cell can never promise a scale the
  // next "Lay out" does not deliver. An assembly source is measured too
  // (ASMDRAW-FIT-1b): before that, an assembly sheet's orientation cells read
  // state only, silently, which is the same missing branch in a second place.
  // A source that cannot be measured yields no proposal — the cells then read
  // state only, honestly.
  const sourceExtentsQuery = useQuery({
    ...sourceExtentsQueryOptions(
      measuredSourceId ?? "",
      measuredSourceKind,
      partTree?.tree_version,
    ),
    enabled: measuredSourceId !== null,
  });
  // Fitted against the paper the sheet is ACTUALLY on (`effectiveSize`), not the
  // picker's value: a laid-out A3 sheet whose picker still reads A4 would have
  // had its header cell quote A4's fits.
  const orientationFit = useMemo<OrientationFit | null>(() => {
    const extents = sourceExtentsQuery.data;
    if (!extents) return null;
    return proposeOrientation(extents, effectiveSize);
  }, [sourceExtentsQuery.data, effectiveSize]);
  // The user's answer to the proposal, before any sheet exists to hold it. Once
  // a sheet exists the SHEET holds the orientation (and the header cell re-heads
  // it), so this only ever governs the very first create. Cleared whenever the
  // thing being proposed about changes — a "portrait" the user chose for another
  // part, on another paper, is not an answer to this question.
  const [orientationOverride, setOrientationOverride] =
    useState<SheetOrientation | null>(null);
  useEffect(() => {
    setOrientationOverride(null);
  }, [selectedSourceId, sizeValue, activeIndex]);

  // The paper the next layout will make: the persisted sheet's own orientation
  // whenever a sheet exists (laid out or not — `handleLayout` honours it), and
  // the proposal, or the user's override of it, before that.
  const paperOrientation: SheetOrientation =
    sheet?.orientation ??
    orientationOverride ??
    orientationFit?.proposed ??
    "landscape";
  const paperScale = orientationFit
    ? orientationFit.scaleByOrientation[paperOrientation]
    : null;

  // Project the part into the standard views (exact HLR, server-side).
  const evalQuery = useQuery({
    queryKey: [
      "drawing-eval",
      // Sheet-scoped: the request body carries THIS sheet's section params
      // (`sectionParamsByIndex`) and THIS sheet's dimensions
      // (`dimensionInputs` ← `tree.sheets[activeIndex].dimensions`). Without
      // the sheet id, two sheets of the same part at the same scale with the
      // same projection list collide on one cache entry — sheet 2 would be
      // served sheet 1's section cut while the composed paper (keyed
      // correctly below) shows its own, and sheet 2's dimension ids would
      // miss in `measuredById`. Audit H1.
      activeSheetId,
      effectivePartId,
      partTree?.tree_version,
      effectiveScaleValue,
      requestedViews.join(","),
      // Re-measure whenever a dimension is added/removed (any mutation bumps it).
      docVersion,
    ],
    enabled: hasLayout && partTree !== undefined,
    queryFn: () => {
      const t = partTree as NonNullable<typeof partTree>;
      const request: EvaluateDrawingViewsRequest = {
        part_id: t.part_id,
        tree_version: t.tree_version,
        scale: scaleFromValue(effectiveScaleValue),
        views: requestedViews,
        features: t.features
          .filter((feature) => !feature.rolled_back)
          .map((feature) => ({ id: feature.id, feature: feature.feature })),
        dimensions: dimensionInputs,
        section_params: sectionParamsByIndex,
      };
      return evaluateDrawingViews(request);
    },
    staleTime: Infinity,
  });
  const evaluation = evalQuery.data;

  const resultByProjection = useMemo(() => {
    const map = new Map<ViewProjection, DrawingViewResult>();
    for (const result of evaluation?.views ?? []) map.set(result.view, result);
    return map;
  }, [evaluation]);
  // Model-true measured value per dimension id (design §3.1).
  const measuredById = useMemo(() => {
    const map = new Map<string, MeasuredDimension>();
    for (const result of evaluation?.dimensions ?? []) {
      if (result.id) map.set(result.id, result.measured);
    }
    return map;
  }, [evaluation]);

  // The server-composed sheet (DE-1c): the SINGLE placement source the sheet
  // renders from. The gateway `/sheet` route reads the drawing's persisted state
  // and composes it — the browser computes no layout. Keyed identically to the
  // evaluate query so the VISUAL (composed) and the PICK provenance (evaluate)
  // move in lockstep: a reproject / new dimension refetches both together.
  const sheetQuery = useQuery({
    queryKey: [
      "drawing-sheet",
      activeSheetId,
      effectiveSourceId,
      effectiveSourceKind,
      partTree?.tree_version,
      effectiveScaleValue,
      docVersion,
    ],
    // A PART sheet waits for its feature tree (the compose is keyed on that
    // tip, so composing before it lands would cache a stale sheet). An
    // ASSEMBLY sheet has no client-side tree to wait for — the gateway
    // resolves the instance+mate graph itself — so it composes as soon as the
    // sheet exists. Re-project invalidates this key for both.
    enabled:
      hasLayout &&
      activeSheetId !== null &&
      (effectiveSourceKind === "assembly" || partTree !== undefined),
    queryFn: () => composeDrawingSheet(drawingId, activeSheetId),
    staleTime: Infinity,
  });
  const composed = sheetQuery.data;
  // The PLACED views by projection — the reading the Views panel falls back to
  // when there is no client-side evaluation to read (an assembly sheet).
  const composedByProjection = useMemo(() => {
    const map = new Map<ViewProjection, ComposedView>();
    for (const view of composed?.views ?? []) map.set(view.projection, view);
    return map;
  }, [composed]);

  // The sheet's numbered bill of materials (§7 BOM) — the parts list. A READ
  // MODEL over the source assembly's direct instances, so it needs no
  // evaluation and no geometry: quantities and item numbers are a pure
  // function of the assembly graph, which is why the numbers are derived at
  // read time and never stored on the drawing. Only an ASSEMBLY sheet has one;
  // asking for a part sheet's BOM is a typed 422, and the panel says why
  // rather than making the user find out by clicking.
  const bomQuery = useQuery({
    queryKey: ["drawing-bom", drawingId, activeSheetId, docVersion],
    enabled:
      hasLayout && activeSheetId !== null && effectiveSourceKind === "assembly",
    queryFn: () => fetchDrawingBom(drawingId, activeSheetId),
    staleTime: 30_000,
  });

  // ---------------------------------------------------------------------
  // The auto-layout action: create the sheet (if needed) + the four views,
  // threading the optimistic-concurrency version through each write.
  // ---------------------------------------------------------------------
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Section-view authoring: the panel's open state, its own create-time error,
  // and the referenced part's reusable datums (fetched lazily when the panel
  // opens). The datum options come from the SAME resolver the sketch plane
  // picker reads, so a section's plane FeatureRef means the same plane there.
  const [sectionOpen, setSectionOpen] = useState(false);
  const [sectionError, setSectionError] = useState<string | null>(null);
  const sectionPartTreeQuery = useQuery({
    queryKey: ["drawing-section-part-tree", selectedSourceId],
    enabled:
      sectionOpen && selectedSourceId !== null && selectedSourceKind === "part",
    queryFn: () => fetchFeatureTree(selectedSourceId as string),
    staleTime: 30_000,
  });
  const sectionDatumOptions = useMemo(
    () => resolveDatumPlaneOptions(sectionPartTreeQuery.data?.features ?? []),
    [sectionPartTreeQuery.data],
  );

  const handleLayout = useCallback(() => {
    if (hasLayout || selectedSourceId === null || busy) return;
    setBusy(true);
    setActionError(null);
    void (async () => {
      try {
        let version = docVersion;
        let sheetId = sheet?.id ?? null;
        // Measure FIRST, through the same cache the header cell reads, so the
        // paper is chosen from the document rather than after it (REACH-3-FLOW
        // P1-1: Sheet 1 used to be born `orientation: "landscape"` as a
        // literal). `ensureQueryData` shares the one evaluation the proposal
        // already warmed — and closes the race where a user clicks "Lay out"
        // before that query lands, which reading `orientationFit` here would
        // have left as a silent fall back to landscape.
        let extents: ModelExtents | null = null;
        try {
          extents = await queryClient.ensureQueryData(
            sourceExtentsQueryOptions(
              selectedSourceId,
              selectedSourceKind,
              partTree?.tree_version,
            ),
          );
        } catch {
          // unmeasurable — keep the picked scale and the default paper
        }
        const header = sheetHeaderForNewSheet({
          name: "Sheet 1",
          size: sizeValue,
          layout: "standard",
          fit: extents ? proposeOrientation(extents, sizeValue) : null,
          inherit: sheet,
          override: orientationOverride,
        });
        if (sheetId === null) {
          const created = await createSheet(drawingId, {
            name: header.name,
            size: header.size,
            orientation: header.orientation,
            projection: header.projection,
            expected_version: version,
          });
          version = created.doc_version;
          sheetId = created.sheet.id;
        }
        // Lay out against the paper THIS sheet is actually on — a sheet added
        // portrait (REACH-3) must seed its anchors and fit its scale against
        // 210x297, not the landscape default. For a sheet created a moment ago
        // that is the proposed paper; for an existing empty sheet it is the one
        // already persisted, which the user may have flipped by hand.
        const dims = sheetDimensions(
          sheet?.size ?? header.size,
          sheet?.orientation ?? header.orientation,
        );
        const anchors = standardLayout(dims);
        // Fit-scale: never lay out views that overflow their cells — measure
        // the source and reduce the scale until the four standard views fit
        // (the user's picked scale is a ceiling; see fitScale). EITHER kind of
        // source is measurable now (`fetchSourceExtents`): a part by its bbox,
        // an ASSEMBLY by its SOLVED compound's extents. Before that route
        // existed the assembly branch kept the picked scale, and a rig whose
        // instances were seeded apart laid out at 1:1 with its right view
        // straddling the title block (ASMDRAW-FIT-1b, and the founder's
        // parts-list screenshot).
        //
        // A source that cannot be measured keeps the picked scale — the layout
        // still lands, just unfitted, and the composer's own `views_overlap` /
        // `views_crowded` measurements surface in the check strip, so a sheet
        // that could not be fitted says so rather than looking fine.
        //
        // This fit runs ONCE, here, at layout time. A later re-solve that moves
        // the extents does NOT re-scale a sheet already on screen: the scale of
        // a laid-out sheet is the user's (they can re-pick it, and a dragged
        // view is pinned `auto_place:false`), and re-flowing paper under
        // someone editing mates in another tab is the "no surprises" half of
        // the flow rule. The check strip tells them; it never moves them.
        const fittedValue = extents
          ? fitScale(extents, dims, scaleValue).value
          : scaleValue;
        const scale = scaleFromValue(fittedValue);
        for (const projection of STANDARD_VIEWS) {
          const anchor = anchors[projection];
          const created = await createView(drawingId, sheetId, {
            projection,
            ref_document_id: selectedSourceId,
            ref_document_kind: selectedSourceKind,
            scale,
            position: { x_mm: anchor.x, y_mm: anchor.y },
            // Auto-layout lands each standard view (bounds-aware); a later drag
            // flips this view to auto_place:false with a persisted position.
            auto_place: true,
            expected_version: version,
          });
          version = created.doc_version;
        }
        // Only after every view landed: reflect the substitution in the picker
        // state (a FAILED layout must not mutate the user's pick — review
        // 2026-07-22), and post-layout the band's scale readout derives from
        // the stored views either way.
        if (fittedValue !== scaleValue) setScaleValue(fittedValue);
        await queryClient.invalidateQueries({
          queryKey: ["drawing", drawingId],
        });
      } catch (error) {
        setActionError(
          error instanceof Error
            ? error.message
            : "The views could not be laid out.",
        );
      } finally {
        setBusy(false);
      }
    })();
  }, [
    hasLayout,
    selectedSourceId,
    selectedSourceKind,
    busy,
    docVersion,
    sheet,
    drawingId,
    scaleValue,
    sizeValue,
    partTree,
    orientationOverride,
    queryClient,
  ]);

  // The flat-pattern action: create the sheet (if needed) + a single flat_pattern
  // view (the lone unfold blank + its bend table, sheet-metal.md §7). A part with
  // no sheet-metal bends composes an honest `flat_pattern_not_sheet_metal` failed
  // view — surfaced inline, never a crash.
  const handleFlatPattern = useCallback(() => {
    // Part-only, and the guard is not redundant with the band's disabled cell:
    // `F` reaches this handler directly from the keyboard.
    if (hasLayout || selectedSourceId === null || busy) return;
    if (selectedSourceKind !== "part") return;
    setBusy(true);
    setActionError(null);
    void (async () => {
      try {
        let version = docVersion;
        let sheetId = sheet?.id ?? null;
        // A LONE-view sheet: `fit: null` on purpose, not by omission. The
        // proposal is a reading of the FOUR-quadrant fit, and a flat pattern's
        // drawn footprint is the UNFOLDED blank, which the client has not
        // measured (see the scale note below). Proposing paper from the 3D bbox
        // here would be the "promises what it will not deliver" defect
        // REACH-3-FLOW's other half is about, in a new place.
        const header = sheetHeaderForNewSheet({
          name: "Sheet 1",
          size: sizeValue,
          layout: "lone",
          fit: null,
          inherit: sheet,
        });
        if (sheetId === null) {
          const created = await createSheet(drawingId, {
            name: header.name,
            size: header.size,
            orientation: header.orientation,
            projection: header.projection,
            expected_version: version,
          });
          version = created.doc_version;
          sheetId = created.sheet.id;
        }
        // The chosen size flows to the flat-pattern sheet too, so the lone
        // unfold blank is centred on (and composed against) the picked paper.
        // NB: the lone flat view is not yet fit-scaled to the sheet the way the
        // four standard views are — a flat-pattern fit needs the UNFOLDED
        // extents (not the 3D bbox `fitScale` reads), a separate slice (BACKLOG).
        const dims = sheetDimensions(
          sheet?.size ?? header.size,
          sheet?.orientation ?? header.orientation,
        );
        const created = await createView(drawingId, sheetId, {
          projection: "flat_pattern",
          ref_document_id: selectedSourceId,
          ref_document_kind: "part",
          scale: scaleFromValue(scaleValue),
          position: { x_mm: dims.width / 2, y_mm: dims.height / 2 },
          auto_place: true,
          expected_version: version,
        });
        version = created.doc_version;
        await queryClient.invalidateQueries({
          queryKey: ["drawing", drawingId],
        });
      } catch (error) {
        setActionError(
          error instanceof Error
            ? error.message
            : "The flat pattern could not be laid out.",
        );
      } finally {
        setBusy(false);
      }
    })();
  }, [
    hasLayout,
    selectedSourceId,
    selectedSourceKind,
    busy,
    docVersion,
    sheet,
    drawingId,
    scaleValue,
    sizeValue,
    queryClient,
  ]);

  // The section action: create the sheet (if needed) + a single centred section
  // view carrying its cutting plane + flip (drawings-section.md §1). The compose
  // wire (E1a) then resolves the datum, cuts, and hatches automatically — no
  // request body: the compose route reads the persisted `section_params`. A
  // non-principal plane is caught in the panel before this runs; the server also
  // guards it, and the sheet renders `section_plane_not_principal` readably.
  const handleAuthorSection = useCallback(
    (plane: SectionViewParams["plane"], flip: boolean) => {
      // Part-only (`S` reaches this from the keyboard too — see flat pattern).
      if (hasLayout || selectedSourceId === null || busy) return;
      if (selectedSourceKind !== "part") return;
      setBusy(true);
      setSectionError(null);
      void (async () => {
        try {
          let version = docVersion;
          let sheetId = sheet?.id ?? null;
          // A lone centred cut, like the flat pattern above: the four-quadrant
          // fit does not model it, so it takes the shop default rather than a
          // proposal it cannot honour. Convention is still inherited.
          const header = sheetHeaderForNewSheet({
            name: "Sheet 1",
            size: sizeValue,
            layout: "lone",
            fit: null,
            inherit: sheet,
          });
          if (sheetId === null) {
            const created = await createSheet(drawingId, {
              name: header.name,
              size: header.size,
              orientation: header.orientation,
              projection: header.projection,
              expected_version: version,
            });
            version = created.doc_version;
            sheetId = created.sheet.id;
          }
          const dims = sheetDimensions(
            sheet?.size ?? header.size,
            sheet?.orientation ?? header.orientation,
          );
          await createView(drawingId, sheetId, {
            projection: "section",
            ref_document_id: selectedSourceId,
            ref_document_kind: "part",
            scale: scaleFromValue(scaleValue),
            position: { x_mm: dims.width / 2, y_mm: dims.height / 2 },
            section_params: { plane, flip },
            auto_place: true,
            expected_version: version,
          });
          setSectionOpen(false);
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
        } catch (error) {
          setSectionError(
            error instanceof Error
              ? error.message
              : "The section view could not be created.",
          );
        } finally {
          setBusy(false);
        }
      })();
    },
    [
      hasLayout,
      selectedSourceId,
      selectedSourceKind,
      busy,
      docVersion,
      sheet,
      drawingId,
      scaleValue,
      sizeValue,
      queryClient,
    ],
  );

  const handleToggleSection = useCallback(() => {
    setSectionError(null);
    setSectionOpen((open) => !open);
  }, []);

  // "What IS item 2?" — open the document a parts-list line names, in its own
  // workspace. The list is the only place on this sheet where another document
  // is named, so it is the only place that answer can be reached from; without
  // it the numbers are a dead end (design mandate: no chrome that only reads).
  const handleOpenBomLine = useCallback(
    (line: DrawingBomLine) => {
      if (line.missing) return;
      void (line.ref_document_kind === "assembly"
        ? navigate({
            to: "/assemblies/$assemblyId",
            params: { assemblyId: line.ref_document_id },
          })
        : navigate({
            to: "/parts/$partId",
            params: { partId: line.ref_document_id },
          }));
    },
    [navigate],
  );

  // Append a new (empty) sheet and switch to it (FINDINGS #18). The new sheet is
  // laid out through the SAME flow the first sheet uses — selecting it makes the
  // Set-up band + layout actions target its id (createView takes the sheet id, so
  // no per-index guesswork). Appends at the tip → its index is the old count.
  const [addingSheet, setAddingSheet] = useState(false);
  // `Sheet ${count + 1}` collides after a delete: with Sheet 1/2/3, removing
  // Sheet 2 leaves count 2, so the next add is another "Sheet 3" — two tabs
  // with the same label (the tab renders `sheet.name`). Take the lowest free
  // number instead, so names stay unique and stable across deletes.
  const nextSheetName = useMemo(() => {
    const taken = new Set((tree?.sheets ?? []).map((s) => s.sheet.name));
    let n = 1;
    while (taken.has(`Sheet ${n}`)) n += 1;
    return `Sheet ${n}`;
  }, [tree]);
  const handleAddSheet = useCallback(() => {
    if (addingSheet || sheetCount === 0) return;
    setAddingSheet(true);
    setActionError(null);
    void (async () => {
      try {
        // The SAME derivation Sheet 1 is born from (`sheetHeaderForNewSheet`) —
        // this used to be the one smart call site while the four Sheet-1 paths
        // wrote literals, which is exactly the defect REACH-3-FLOW names.
        const header = sheetHeaderForNewSheet({
          name: nextSheetName,
          size: sizeValue,
          layout: "standard",
          fit: orientationFit,
          inherit: sheet,
        });
        await createSheet(drawingId, {
          name: header.name,
          size: header.size,
          orientation: header.orientation,
          projection: header.projection,
          expected_version: docVersion,
        });
        if (header.scaleValue !== null) setScaleValue(header.scaleValue);
        await queryClient.invalidateQueries({
          queryKey: ["drawing", drawingId],
        });
        setActiveSheetIndex(sheetCount);
      } catch (error) {
        setActionError(
          error instanceof Error
            ? error.message
            : "The sheet could not be added.",
        );
      } finally {
        setAddingSheet(false);
      }
    })();
  }, [
    addingSheet,
    sheetCount,
    nextSheetName,
    drawingId,
    sizeValue,
    docVersion,
    queryClient,
    orientationFit,
    sheet,
  ]);

  // ---------------------------------------------------------------------
  // Re-heading the sheet in place (REACH-3): the projection convention and the
  // paper orientation are properties of the SHEET, so both flip through
  // `SheetUpdate` and the server re-composes. Every auto-placed view is
  // re-anchored by the composer from the sheet's own convention, so a flip
  // genuinely re-lays the drawing out — third angle puts the top view above
  // front and the right view to its right; first angle mirrors both.
  //
  // ORIENTATION additionally RE-PLACES every view onto the new paper
  // (REACH-3-FLOW P1-2). A flip used to change the `viewBox` and nothing else,
  // which for a HAND-PLACED view is not cosmetic: `auto_place:false` is honoured
  // verbatim by the composer, and a view pinned 270 mm across a landscape A4 is
  // off the edge of a 210 mm-wide portrait one.
  //
  // It does NOT re-scale, and the cell no longer claims it will. MEASURED
  // 2026-08-28 against the real stack: documents refuses a per-view re-scale on
  // a multi-view sheet with `sheet_view_scale_mismatch` (its H2 "one sheet, one
  // source, one scale" invariant), and the refusal is unavoidable — `siblings[0]`
  // always still holds the OLD scale, so the FIRST view of the four is always
  // rejected whichever order you write them in. There is no sheet-level re-scale
  // verb, so no sequence of frontend writes can re-fit a laid-out sheet.
  //
  // The half of P1-2 that was a genuine defect is therefore fixed at the
  // PROMISE, not the delivery: the fit comparison now lives on the SET-UP
  // screen's paper cell, where the scale is still free and the answer is still
  // free to give, and the post-layout cell states only what it does. That is
  // "capture intent where it forms, not afterwards" — the flow rule this ticket
  // is judged by — rather than a control quoting a scale it cannot produce.
  // The residual (an in-place sheet re-scale) is a documents-service verb;
  // filed as SHEET-RESCALE-1.
  // ---------------------------------------------------------------------
  const [reheading, setReheading] = useState(false);
  const reheadSheet = useCallback(
    (
      change:
        { projection: SheetProjection } | { orientation: SheetOrientation },
    ) => {
      if (reheading || sheet === null) return;
      const from = sheet;
      setReheading(true);
      setActionError(null);
      void (async () => {
        try {
          const rehead = await updateSheetHeader(drawingId, from.id, {
            expected_version: docVersion,
            ...change,
          });
          if ("orientation" in change && views.length > 0) {
            const next = change.orientation;
            const oldDims = sheetDimensions(from.size, from.orientation);
            const newDims = sheetDimensions(from.size, next);
            const anchors = standardLayout(newDims);
            let version = rehead.doc_version;
            for (const view of views) {
              const updated = await updateView(drawingId, view.id, {
                expected_version: version,
                // An auto-placed view re-seeds to the new paper's anchors (the
                // composer re-derives the final placement from them anyway); a
                // HAND-PLACED one keeps its composition, remapped, so the pin
                // lands on paper that exists.
                position: view.auto_place
                  ? {
                      x_mm: anchors[view.projection].x,
                      y_mm: anchors[view.projection].y,
                    }
                  : reframePinnedCentre(view.position, oldDims, newDims),
              });
              version = updated.doc_version;
            }
          }
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
          await queryClient.invalidateQueries({ queryKey: ["drawing-sheet"] });
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The sheet could not be updated.",
          );
        } finally {
          setReheading(false);
        }
      })();
    },
    [reheading, sheet, views, drawingId, docVersion, queryClient],
  );
  const handleFlipConvention = useCallback(() => {
    if (sheet === null) return;
    reheadSheet({ projection: OTHER_CONVENTION[sheet.projection] });
  }, [sheet, reheadSheet]);
  const handleFlipOrientation = useCallback(() => {
    if (sheet === null) return;
    reheadSheet({ orientation: OTHER_ORIENTATION[sheet.orientation] });
  }, [sheet, reheadSheet]);
  /**
   * The paper control on the SET-UP screen — the one place a wrong proposal can
   * be answered before it costs anything (REACH-3-FLOW's P2 flag: the header
   * cells were post-layout only, i.e. absent from the only screen that could
   * have prevented the problem). Same gesture either side of the sheet's
   * existence: re-head the sheet if there is one, otherwise record the answer
   * the very first create will be born with.
   */
  const handleFlipPaper = useCallback(() => {
    if (sheet !== null) {
      handleFlipOrientation();
      return;
    }
    setOrientationOverride(OTHER_ORIENTATION[paperOrientation]);
  }, [sheet, handleFlipOrientation, paperOrientation]);

  const handleReproject = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: ["drawing-part-tree", effectivePartId],
    });
    void queryClient.invalidateQueries({ queryKey: ["drawing-eval"] });
    // Re-compose the placed sheet too (the VISUAL source) so a reproject repaints.
    void queryClient.invalidateQueries({ queryKey: ["drawing-sheet"] });
  }, [queryClient, effectivePartId]);

  // ---------------------------------------------------------------------
  // Drag-to-place: the sheet reports a dragged/nudged view centre (sheet mm,
  // y-up); we persist it with `auto_place: false` so the composer honours it
  // verbatim — the placement survives reload. "Reset" returns the view to
  // bounds-aware auto-layout. One in-flight flag serialises the OCC writes.
  // ---------------------------------------------------------------------
  const [placingView, setPlacingView] = useState(false);
  const handlePlaceView = useCallback(
    (viewId: string, position: { x_mm: number; y_mm: number }) => {
      if (placingView) return;
      setPlacingView(true);
      setActionError(null);
      void (async () => {
        try {
          await updateView(drawingId, viewId, {
            expected_version: docVersion,
            position,
            auto_place: false,
          });
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
          void queryClient.invalidateQueries({ queryKey: ["drawing-sheet"] });
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The view could not be moved.",
          );
        } finally {
          setPlacingView(false);
        }
      })();
    },
    [placingView, drawingId, docVersion, queryClient],
  );
  const handleResetView = useCallback(
    (viewId: string) => {
      if (placingView) return;
      setPlacingView(true);
      setActionError(null);
      void (async () => {
        try {
          await updateView(drawingId, viewId, {
            expected_version: docVersion,
            auto_place: true,
          });
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
          void queryClient.invalidateQueries({ queryKey: ["drawing-sheet"] });
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The view could not be returned to auto-layout.",
          );
        } finally {
          setPlacingView(false);
        }
      })();
    },
    [placingView, drawingId, docVersion, queryClient],
  );

  // The sheet-check strip's fix action (audit N2): return the named views to
  // bounds-aware auto-layout in ONE gesture. A collision only ever involves
  // hand-placed views the composer was told to honour verbatim, so undoing that
  // intent IS the fix — and it is the same `auto_place: true` write the per-view
  // AUTO grip sends, threaded through the bumped version so a pair resets in a
  // single click without a stale-OCC race.
  const handleAutoPlaceViews = useCallback(
    (projections: readonly ViewProjection[]) => {
      if (placingView || projections.length === 0) return;
      setPlacingView(true);
      setActionError(null);
      void (async () => {
        try {
          let version = docVersion;
          for (const projection of projections) {
            const view = views.find((v) => v.projection === projection);
            if (view === undefined) continue;
            const updated = await updateView(drawingId, view.id, {
              expected_version: version,
              auto_place: true,
            });
            version = updated.doc_version;
          }
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
          void queryClient.invalidateQueries({ queryKey: ["drawing-sheet"] });
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The views could not be returned to auto-layout.",
          );
        } finally {
          setPlacingView(false);
        }
      })();
    },
    [placingView, views, drawingId, docVersion, queryClient],
  );

  // ---------------------------------------------------------------------
  // Export SVG (#5): serialize the already-rendered sheet <svg> to a
  // standalone, self-contained .svg and hand it to the browser as a download.
  // The renderer IS the export — no second drafting engine (DRY).
  // ---------------------------------------------------------------------
  const sheetSvgRef = useRef<SVGSVGElement>(null);
  const handleExportSvg = useCallback(() => {
    const svg = sheetSvgRef.current;
    if (svg === null) return;
    setActionError(null);
    try {
      exportSheetSvg(svg, tree?.drawing.name ?? "drawing");
    } catch (error) {
      setActionError(
        error instanceof Error
          ? error.message
          : "The drawing could not be exported.",
      );
    }
  }, [tree]);

  // ---------------------------------------------------------------------
  // Server-composed export (DE-2 PDF, DE-3 DXF): the shop deliverables. Unlike
  // Export SVG (which serializes the on-screen <svg>), the gateway composes the
  // sheet from the SAME persisted placement — byte-deterministic — and streams
  // the artifact bytes back, which we hand to the browser as a named download.
  // ONE in-flight + error path drives every server format (DRY); the SVG path
  // stays separate because it is a synchronous client-side serialize.
  // ---------------------------------------------------------------------
  const [exporting, setExporting] = useState(false);
  const runServerExport = useCallback(
    (format: DrawingExportFormat) => {
      if (!hasLayout || exporting) return;
      setExporting(true);
      setActionError(null);
      void (async () => {
        try {
          const { blob, filename } = await exportDrawing(
            drawingId,
            format,
            activeSheetId,
          );
          downloadBlob(blob, filename);
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : `The drawing could not be exported to ${format.toUpperCase()}.`,
          );
        } finally {
          setExporting(false);
        }
      })();
    },
    [hasLayout, exporting, drawingId, activeSheetId],
  );
  const handleExportPdf = useCallback(
    () => runServerExport("pdf"),
    [runServerExport],
  );
  const handleExportDxf = useCallback(
    () => runServerExport("dxf"),
    [runServerExport],
  );

  // ---------------------------------------------------------------------
  // Dimension authoring: pick sheet geometry → choose a valid type → persist it
  // (CRUD) → the re-evaluate measures + renders it model-true. Most types take
  // one pick; angular and edge-to-edge take two straight edges and point-to-point
  // two endpoints, staged through the pure `authoring` state machine (§3.1/§3.3).
  // ---------------------------------------------------------------------
  const [authoring, setAuthoring] = useState<AuthoringState>(IDLE);
  const [dimBusy, setDimBusy] = useState(false);

  // Highlight sets the sheet reads: the single selected edge, all armed edges,
  // and the selected endpoint handles for the in-progress pick.
  const armed = armedSignatures(authoring);
  const selectedEdgeKey = armed[0]
    ? edgeKey(armed[0].projection, armed[0].sourceEdge)
    : null;
  const armedEdgeKeys = armed.map((a) => edgeKey(a.projection, a.sourceEdge));
  const selectedVertexKeys = selectedEndpoints(authoring).map((e) =>
    vertexKey(e.projection, e.sourceEdge, e.endpoint),
  );
  // A point-to-point pick is in progress — reveal every endpoint handle (and put
  // it in the tab order) so the second vertex is reachable on any edge; at rest
  // handles only appear on their edge's hover/focus (frontend-QA P2).
  const endpointPickActive =
    authoring.kind === "one-endpoint" || authoring.kind === "p2p-ready";
  const menuActionList = menuActions(authoring);
  const anchor = menuAnchor(authoring);
  const hint = pickHint(authoring);
  // The live placement: the ghost the sheet draws and the offset it reads out.
  const placingGhost =
    authoring.kind === "placing" ? ghostFor(authoring.target) : null;
  const placingOffsetMm = placementOffsetMm(authoring);

  const handlePickEdge = useCallback((event: EdgePickEvent) => {
    setAuthoring((state) =>
      pickEdge(state, {
        projection: event.projection,
        viewId: event.viewId,
        sourceEdge: event.sourceEdge,
        primitive: event.primitive,
        clientX: event.clientX,
        clientY: event.clientY,
        geometry: event.geometry,
      }),
    );
  }, []);

  const handlePickEndpoint = useCallback((event: EndpointPickEvent) => {
    setAuthoring((state) =>
      pickEndpoint(state, {
        projection: event.projection,
        viewId: event.viewId,
        sourceEdge: event.sourceEdge,
        endpoint: event.endpoint,
        clientX: event.clientX,
        clientY: event.clientY,
        at: event.at,
        viewAnchor: event.viewAnchor,
      }),
    );
  }, []);

  /** POST the authored dimension (with whatever placement it carries) + refresh. */
  const persistDimension = useCallback(
    (viewId: string, params: DimensionParams) => {
      setDimBusy(true);
      setActionError(null);
      void (async () => {
        try {
          await createDimension(drawingId, viewId, {
            dimension: params,
            expected_version: docVersion,
          });
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
          setAuthoring(IDLE);
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The dimension could not be added.",
          );
        } finally {
          setDimBusy(false);
        }
      })();
    },
    [drawingId, docVersion, queryClient],
  );

  const handleChooseAction = useCallback(
    (action: DimensionAction) => {
      if (dimBusy) return;
      // "Angle" / "Distance to edge" arm a second-edge pick rather than
      // authoring immediately; the intent orders the menu that follows.
      if (action === "start_angular" || action === "start_edge_to_edge") {
        const intent = action === "start_angular" ? "angular" : "edge_to_edge";
        setAuthoring((state) => armPair(state, intent));
        return;
      }
      const built = buildDimension(authoring, action);
      if (built === null) return;
      // The measurement is settled — now say WHERE it goes. The ghost tracks the
      // pointer from the auto-placement default, so the user is adjusting a real
      // proposal (REACH-3). A pick that carried no composed geometry has nothing
      // to place against and authors straight away, exactly as it always did.
      const target = placementTarget(authoring, action);
      if (target !== null) {
        setAuthoring((state) =>
          beginPlacement(state, built.viewId, built.params, target),
        );
        return;
      }
      persistDimension(built.viewId, built.params);
    },
    [authoring, dimBusy, persistDimension],
  );

  /** Track the pointer across the paper while a placement is live. */
  const handlePlacePointer = useCallback((at: { x: number; y: number }) => {
    setAuthoring((state) => movePlacement(state, at));
  }, []);

  /** Set when a grab begins from the sheet — see {@link handlePlaceClick}. */
  const grabClickGuard = useRef(false);

  /**
   * MOVE a dimension already on the paper: re-enter the same PLACE stage it was
   * born in (REACH-3's own commit named "not afterwards" as the defect and
   * fixed only the first half — frontend-QA P1-E).
   *
   * The placement is recovered from the COMPOSED annotation rather than from
   * the stored params, because most dimensions on a sheet have no stored
   * placement at all — the composer auto-placed them, and it is exactly those
   * the user most often wants to nudge out of the way.
   */
  const handleGrabDimension = useCallback(
    (event: DimensionGrabEvent) => {
      if (dimBusy) return;
      const row = dimensions.find((d) => d.id === event.dimensionId);
      if (row === undefined) return;
      const target =
        event.dim.dimension_type === "linear"
          ? offsetPlacementFromComposed(event.dim.lines, event.viewAnchor)
          : textPlacementFromComposed(event.dim.lines, event.dim.text);
      if (target === null) return;
      setAuthoring(
        beginReplacement(row.id, row.view_id, row.dimension, target),
      );
    },
    [dimBusy, dimensions],
  );

  /**
   * Commit the live placement — the click that puts the dimension down.
   *
   * Safe to read `authoring` from the closure ONLY because the sheet reports the
   * pointer on `pointerdown` as well as on `pointermove`: a discrete event
   * flushes before the click that follows it, so this sees the placement the
   * user is looking at. See the `onPointerDown` note on the place surface for
   * what went wrong when it did not.
   */
  const handlePlaceCommit = useCallback(() => {
    if (dimBusy) return;
    const replaces = placementReplaces(authoring);
    const commit = commitParams(authoring);
    if (commit === null) {
      // A re-placement that never moved: nothing to write, and leaving the
      // ghost up would be a dead end. Put the dimension back and stand down.
      if (replaces !== null) setAuthoring(IDLE);
      return;
    }
    if (replaces === null) {
      persistDimension(commit.viewId, commit.params);
      return;
    }
    // No PATCH route for a dimension, so: APPEND the moved copy, then DELETE
    // the original. That order is deliberate and matches `handleHealDimension`
    // — a failure between the two leaves a visible duplicate the user can
    // remove, never a lost dimension.
    setDimBusy(true);
    setActionError(null);
    void (async () => {
      try {
        const created = await createDimension(drawingId, commit.viewId, {
          dimension: commit.params,
          expected_version: docVersion,
        });
        await deleteDimension(drawingId, replaces, created.doc_version);
        await queryClient.invalidateQueries({
          queryKey: ["drawing", drawingId],
        });
        setAuthoring(IDLE);
      } catch (error) {
        setActionError(
          error instanceof Error
            ? error.message
            : "The dimension could not be moved.",
        );
      } finally {
        setDimBusy(false);
      }
    })();
  }, [
    authoring,
    dimBusy,
    persistDimension,
    drawingId,
    docVersion,
    queryClient,
  ]);

  /** The end of a press-drag: commit only if the placement actually moved, so
   * a bare press (click-to-grab) leaves the ghost up for a second click. */
  const handlePlaceRelease = useCallback(() => {
    if (placementMoved(authoring)) handlePlaceCommit();
  }, [authoring, handlePlaceCommit]);

  /**
   * A CLICK on the paper drops the placement — with one exception.
   *
   * THE TAIL OF THE GRAB PRESS IS NOT A DROP. Pressing a placed dimension
   * opens the stage on `pointerdown`, and the release that ends that same
   * press produces a `click` — which Chrome retargets onto the place surface,
   * because the grab the press started on has just been unmounted (the
   * dimension is drawn as the ghost while it moves). Acting on it would make a
   * bare click on a dimension a no-op that opens and shuts the stage in one
   * frame. Exactly one click is swallowed per grab; every click after it drops
   * the dimension normally, and the guard is on the CLICK path only so a
   * press-drag still commits on release.
   */
  const handlePlaceClick = useCallback(() => {
    if (grabClickGuard.current) {
      grabClickGuard.current = false;
      return;
    }
    handlePlaceCommit();
  }, [handlePlaceCommit]);

  /** The sheet's grab route — the only one that arms the click guard, because
   * it is the only one whose gesture ends in a click on the paper. */
  const handleGrabFromSheet = useCallback(
    (event: DimensionGrabEvent) => {
      grabClickGuard.current = true;
      handleGrabDimension(event);
    },
    [handleGrabDimension],
  );

  /** The panel's Move — the same grab, found by id instead of by pointer. */
  const handleMoveFromPanel = useCallback(
    (dimensionId: string) => {
      const row = dimensions.find((d) => d.id === dimensionId);
      if (row === undefined || composed === undefined) return;
      for (const view of composed.views ?? []) {
        for (const dim of view.dimensions ?? []) {
          if (dim.kind !== "measured" || dim.dimension_id !== dimensionId) {
            continue;
          }
          handleGrabDimension({
            dimensionId,
            viewId: row.view_id,
            projection: view.projection,
            dim,
            viewAnchor: { x: view.anchor.x_mm, y: view.anchor.y_mm },
          });
          return;
        }
      }
    },
    [composed, dimensions, handleGrabDimension],
  );

  // --- the typed route to the offset (P1-D) -------------------------------
  // The offset field is CONTROLLED by the placement (the pointer moves it at
  // pointer rate) except while the user has it focused, when the text is
  // theirs: a controlled field rewritten mid-keystroke eats characters. A
  // non-null draft means "the user is typing; leave their text alone".
  const [offsetDraft, setOffsetDraft] = useState<string | null>(null);
  const offsetFieldRef = useRef<HTMLInputElement | null>(null);
  const offsetText =
    offsetDraft ?? (placingOffsetMm !== null ? placingOffsetMm.toFixed(2) : "");
  useEffect(() => {
    if (authoring.kind !== "placing") {
      setOffsetDraft(null);
      // Never leak a swallowed click into a later gesture.
      grabClickGuard.current = false;
    }
  }, [authoring.kind]);

  const handleOffsetTyped = useCallback((text: string) => {
    setOffsetDraft(text);
    const value = Number(text);
    // A half-typed "-" or "1." parses to NaN; hold the placement where it is
    // and let the digits arrive rather than snapping the ghost to nothing.
    if (text.trim() !== "" && Number.isFinite(value)) {
      setAuthoring((state) => setPlacementOffset(state, value));
    }
  }, []);

  // The window key handler below must see the CURRENT placement without being
  // re-registered on every pointer move (a placement changes state at pointer
  // rate), so the two things it needs live in refs.
  const placingRef = useRef(false);
  const commitPlacementRef = useRef(handlePlaceCommit);
  useEffect(() => {
    placingRef.current = authoring.kind === "placing";
    commitPlacementRef.current = handlePlaceCommit;
  }, [authoring, handlePlaceCommit]);

  const handleDeleteDimension = useCallback(
    (dimensionId: string) => {
      if (dimBusy) return;
      setDimBusy(true);
      setActionError(null);
      void (async () => {
        try {
          await deleteDimension(drawingId, dimensionId, docVersion);
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The dimension could not be deleted.",
          );
        } finally {
          setDimBusy(false);
        }
      })();
    },
    [dimBusy, drawingId, docVersion, queryClient],
  );

  // Confirm a re-anchored reference (topological-naming §11 / audit N1): the
  // part changed, the stored stage-1 signature no longer matched verbatim, and
  // geometry re-anchored the dimension on its rebuild invariant — reporting
  // `tier: "durable"` plus the signature of the edge it landed on. One click
  // stores that signature, so the reference stops being a re-derived guess.
  //
  // There is no PATCH route for a dimension, so the write is an APPEND of the
  // healed dimension followed by a DELETE of the stale one. That order matters:
  // a failure between the two leaves a visible duplicate the user can remove,
  // never a lost dimension.
  const handleHealDimension = useCallback(
    (dimensionId: string) => {
      if (dimBusy) return;
      const dim = dimensions.find((d) => d.id === dimensionId);
      const anchor = reanchoredAnchor(measuredById.get(dimensionId));
      if (dim === undefined || anchor === null) return;
      const healed = healDimensionParams(dim.dimension, anchor);
      if (healed === null) return;
      setDimBusy(true);
      setActionError(null);
      void (async () => {
        try {
          const created = await createDimension(drawingId, dim.view_id, {
            dimension: healed,
            expected_version: docVersion,
          });
          await deleteDimension(drawingId, dim.id, created.doc_version);
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The reference could not be confirmed.",
          );
        } finally {
          setDimBusy(false);
        }
      })();
    },
    [dimBusy, dimensions, measuredById, drawingId, docVersion, queryClient],
  );

  // ---------------------------------------------------------------------
  // Note annotations: author a free-text note → persist it (CRUD) → the
  // re-compose places it at its sheet point and the sheet draws it from
  // `ComposedSheet.notes` (design §2.2). A note bumps `doc_version`, so the
  // compose query (keyed on it) refetches with the note — one placement source.
  // ---------------------------------------------------------------------
  const [noteBusy, setNoteBusy] = useState(false);

  const refetchDrawingAndSheet = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["drawing", drawingId] });
    // The composed sheet is keyed on `doc_version` (bumped by the write) so it
    // refetches on its own, but invalidate it too so the note appears at once.
    void queryClient.invalidateQueries({ queryKey: ["drawing-sheet"] });
  }, [queryClient, drawingId]);

  const handleAddNote = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (trimmed.length === 0 || noteBusy || sheet === null) return;
      setNoteBusy(true);
      setActionError(null);
      // A default anchor just inside the top-left border, each new note stacked
      // below the last so they never land on top of one another (v1 has no
      // drag-to-place yet — the note is placed verbatim in final sheet-mm space).
      const margin = composed?.margin_mm ?? 10;
      const x = margin + 6;
      const y = margin + 12 + annotations.length * (drawing.noteTextMm + 3);
      void (async () => {
        try {
          await createAnnotation(drawingId, sheet.id, {
            annotation: {
              type: "note",
              text: trimmed,
              position: { x_mm: x, y_mm: y },
            },
            expected_version: docVersion,
          });
          await refetchDrawingAndSheet();
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The note could not be added.",
          );
        } finally {
          setNoteBusy(false);
        }
      })();
    },
    [
      noteBusy,
      sheet,
      composed,
      annotations.length,
      drawingId,
      docVersion,
      refetchDrawingAndSheet,
    ],
  );

  const handleDeleteNote = useCallback(
    (annotationId: string) => {
      if (noteBusy) return;
      setNoteBusy(true);
      setActionError(null);
      void (async () => {
        try {
          await deleteAnnotation(drawingId, annotationId, docVersion);
          await refetchDrawingAndSheet();
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The note could not be deleted.",
          );
        } finally {
          setNoteBusy(false);
        }
      })();
    },
    [noteBusy, drawingId, docVersion, refetchDrawingAndSheet],
  );

  // Keyboard-first: L lays out (or re-projects once laid out).
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // Escape during a placement backs out ONE stage: the pick that led here
        // survives, so a mis-drag never costs you the geometry you selected
        // (CLAUDE.md flow rule — no ambiguous exits).
        setAuthoring((state) =>
          state.kind === "placing" ? cancelPlacement(state) : IDLE,
        );
        setSectionOpen(false);
        return;
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      // Keyboard parity for the placement drag: arrows nudge, Enter commits.
      // Claimed BEFORE the single-letter commands so an arrow/Enter mid-place
      // can never fire an export instead.
      if (placingRef.current) {
        // TYPE A NUMBER AND YOU ARE SETTING IT. A digit (or a leading minus)
        // hands the keystroke to the offset field and focuses it, so the
        // precision route costs no hunting and no mouse — the same reflex a
        // modeller already has from every other CAD tool. Intent captured
        // where it forms (CLAUDE.md flow rule), not recovered afterwards.
        const field = offsetFieldRef.current;
        if (field && /^[0-9.-]$/.test(event.key)) {
          event.preventDefault();
          // FOCUS FIRST, then seed. `focus()` fires the field's own onFocus
          // synchronously, which opens a draft from the CURRENT value — so
          // seeding before focusing hands the user "11.0025" instead of "-25".
          field.focus();
          setOffsetDraft(event.key);
          const seed = Number(event.key);
          if (Number.isFinite(seed)) {
            setAuthoring((state) => setPlacementOffset(state, seed));
          }
          return;
        }
        const step = event.shiftKey ? PLACE_NUDGE_MM * 5 : PLACE_NUDGE_MM;
        const delta: Record<string, [number, number]> = {
          ArrowUp: [0, -1],
          ArrowDown: [0, 1],
          ArrowLeft: [-1, 0],
          ArrowRight: [1, 0],
        };
        const move = delta[event.key];
        if (move) {
          event.preventDefault();
          setAuthoring((state) =>
            nudgePlacement(state, move[0], move[1], step),
          );
          return;
        }
        if (event.key === "Enter") {
          event.preventDefault();
          commitPlacementRef.current();
          return;
        }
      }
      if (event.key.toLowerCase() === "l") {
        event.preventDefault();
        if (hasLayout) handleReproject();
        else handleLayout();
      }
      // F unfolds the flat pattern (a lone flat blank + bend table). No-op once
      // laid out (mirrors the command band's Flat pattern action).
      if (event.key.toLowerCase() === "f" && !hasLayout) {
        event.preventDefault();
        handleFlatPattern();
      }
      // S opens the section-view author (pick a cutting plane + flip). Pre-layout
      // only, mirroring the command band's Section action.
      if (event.key.toLowerCase() === "s" && !hasLayout) {
        event.preventDefault();
        handleToggleSection();
      }
      // E exports the laid-out sheet to a .svg (keyboard-first, mirrors the
      // command band's Export SVG action). No-op before layout.
      if (event.key.toLowerCase() === "e" && hasLayout) {
        event.preventDefault();
        handleExportSvg();
      }
      // P server-composes the laid-out sheet to a .pdf (the shop deliverable),
      // mirroring the command band's Export PDF action. No-op before layout.
      if (event.key.toLowerCase() === "p" && hasLayout) {
        event.preventDefault();
        handleExportPdf();
      }
      // D server-composes the laid-out sheet to a .dxf (the interchange
      // deliverable), mirroring the command band's Export DXF action.
      if (event.key.toLowerCase() === "d" && hasLayout) {
        event.preventDefault();
        handleExportDxf();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    hasLayout,
    handleLayout,
    handleFlatPattern,
    handleToggleSection,
    handleReproject,
    handleExportSvg,
    handleExportPdf,
    handleExportDxf,
  ]);

  const draftedSourceName = drawingSourceName(sources, draftedSourceId);

  // The composer's own layout measurements (audit N2) — a colliding or crowded
  // pair of views, in millimetres, with the sentence every export stamps. The
  // strip below is the on-screen half of that banner.
  const layoutIssues = composed?.layout_issues ?? [];
  // Which views carry a hand-dragged placement: those are the only ones a
  // "return to auto-layout" fix can act on (the composer honours an
  // `auto_place: false` position verbatim, which is how a collision gets made).
  const handPlacedViews = useMemo(() => {
    const set = new Set<ViewProjection>();
    for (const view of views) {
      if (view.auto_place === false) set.add(view.projection);
    }
    return set;
  }, [views]);

  const projecting =
    evalQuery.isFetching || partTreeQuery.isFetching || sheetQuery.isFetching;

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <Breadcrumb
          register="drawings"
          documentName={tree?.drawing.name ?? "Drawing"}
          documentTestId="drawing-name"
          mode={hasLayout ? null : "Set up"}
        />
      </TopBar>
      <TopToolbar>
        {/* Only once the drawing has loaded — otherwise the band invites "Lay
            out" against a not-yet-known doc_version (a stale-OCC race). */}
        {drawingQuery.isSuccess ? (
          <DrawingCommandBand
            sources={sources}
            selectedSourceId={selectedSourceId}
            onSelectSource={setSelectedSourceId}
            sourceKind={effectiveSourceKind}
            scaleValue={effectiveScaleValue}
            onSelectScale={setScaleValue}
            sizeValue={effectiveSize}
            onSelectSize={setSizeValue}
            paperOrientation={paperOrientation}
            paperScale={paperScale}
            hasLayout={hasLayout}
            isFlatPattern={isFlatPatternSheet}
            draftedSourceName={draftedSourceName}
            onLayout={handleLayout}
            onFlatPattern={handleFlatPattern}
            onToggleSection={handleToggleSection}
            sectionOpen={sectionOpen}
            onReproject={handleReproject}
            onExportSvg={handleExportSvg}
            onExportPdf={handleExportPdf}
            onExportDxf={handleExportDxf}
            exporting={exporting}
            busy={busy || projecting}
          />
        ) : null}

        {/* The section-view author hangs from the band into the viewport (the
            sketch strip's offset-plane idiom), so the Sheet actions stay one
            row above. Pre-layout only — a section is a lone-view sheet in v1. */}
        {sectionOpen && !hasLayout ? (
          <div className="absolute left-3 top-full z-overlay mt-2">
            <SectionAuthorPanel
              datumPlanes={sectionDatumOptions}
              loadingDatums={sectionPartTreeQuery.isFetching}
              onCut={handleAuthorSection}
              onClose={() => setSectionOpen(false)}
              busy={busy}
              error={sectionError}
            />
          </div>
        ) : null}
      </TopToolbar>

      <main className="relative min-h-0 grow overflow-hidden bg-carbide">
        {/* The bench under the sheet — same grid the viewport + registers use. */}
        <div
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_38%,theme(colors.anvil),theme(colors.carbide)_72%)]"
          aria-hidden="true"
        />

        {/* The sheet switcher (FINDINGS #18) — move between the drawing's sheets,
            add a new one. Appears once the drawing has a sheet (post-layout). */}
        {tree && sheetCount > 0 ? (
          <SheetTabs
            sheets={tree.sheets}
            activeIndex={activeIndex}
            onSelect={setActiveSheetIndex}
            onAdd={handleAddSheet}
            adding={addingSheet}
            sheet={sheet}
            fit={orientationFit}
            drawnScale={effectiveScaleValue}
            onFlipConvention={handleFlipConvention}
            onFlipOrientation={handleFlipOrientation}
            reheading={reheading}
          />
        ) : null}

        {drawingQuery.isError ? (
          <CenterNote
            testId="drawing-load-error"
            tone="error"
            title="Drawing could not be loaded"
            body={
              drawingQuery.error instanceof Error
                ? drawingQuery.error.message
                : "Reload and try again."
            }
          />
        ) : !tree ? (
          <CenterNote
            testId="drawing-loading"
            tone="quiet"
            title="Loading drawing…"
            body="Fetching the sheet."
          />
        ) : hasLayout && sheet && composed ? (
          // Reserve the right gutter for the Views panel so the paper never
          // slides under it (the panel would clip the sheet's framed corner).
          // The check strip stacks ABOVE the paper rather than floating over it:
          // a diagnostic that covers the geometry it is about is not a
          // diagnostic. It only occupies rows when there is something to say.
          <div
            className={`absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 sm:p-10 lg:pr-[22rem] ${
              // The check strip needs clearance from the sheet switcher, which
              // floats in this same top-left margin; without it the two touch at
              // narrow widths. Only paid for when the strip is there.
              layoutIssues.length > 0 ? "pt-12 sm:pt-12" : ""
            }`}
          >
            <SheetIssueStrip
              issues={layoutIssues}
              handPlaced={handPlacedViews}
              onAutoPlace={handleAutoPlaceViews}
              busy={placingView}
            />
            <div className="min-h-0 w-full grow">
              <DrawingSheet
                svgRef={sheetSvgRef}
                composed={composed}
                views={views}
                resultByProjection={resultByProjection}
                selectedEdgeKey={selectedEdgeKey}
                armedEdgeKeys={armedEdgeKeys}
                selectedVertexKeys={selectedVertexKeys}
                endpointPickActive={endpointPickActive}
                placementBusy={placingView}
                dimensionGhost={placingGhost}
                movingDimensionId={placementReplaces(authoring)}
                onPickEdge={handlePickEdge}
                onPickEndpoint={handlePickEndpoint}
                onPlaceView={handlePlaceView}
                onPlacePointer={handlePlacePointer}
                onPlaceCommit={handlePlaceClick}
                onPlaceRelease={handlePlaceRelease}
                onGrabDimension={handleGrabFromSheet}
                onResetView={handleResetView}
              />
            </div>
          </div>
        ) : hasLayout && sheet && sheetQuery.isError ? (
          <CenterNote
            testId="drawing-compose-error"
            tone="error"
            title="Sheet could not be composed"
            body={
              sheetQuery.error instanceof Error
                ? sheetQuery.error.message
                : "Reload and try again."
            }
          />
        ) : hasLayout && sheet ? (
          <CenterNote
            testId="drawing-composing"
            tone="quiet"
            title="Composing sheet…"
            body="Placing the standard views."
          />
        ) : (
          <SetupHint
            hasParts={parts.length > 0}
            size={effectiveSize}
            orientation={paperOrientation}
            fit={orientationFit}
            onFlipPaper={handleFlipPaper}
            busy={reheading || busy}
          />
        )}

        {/* Honest projection-failure banner (part produced no body). */}
        {evaluation?.part_error ? (
          <div
            role="alert"
            data-testid="drawing-part-error"
            className="absolute bottom-3 left-3 max-w-sm border border-flag bg-anvil px-3 py-2"
          >
            <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
              Projection failed
            </span>
            <span className="mt-1 block font-body text-xs text-mist">
              {evaluation.part_error.message}
            </span>
          </div>
        ) : null}

        {actionError ? (
          <div
            role="alert"
            data-testid="drawing-action-error"
            className="absolute bottom-3 left-3 max-w-sm border border-flag bg-anvil px-3 py-2"
          >
            <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
              Layout failed
            </span>
            <span className="mt-1 block font-body text-xs text-mist">
              {actionError}
            </span>
            <button
              type="button"
              onClick={() => setActionError(null)}
              className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
            >
              Dismiss
            </button>
          </div>
        ) : null}

        {hasLayout ? (
          // A 2D sheet has no r3f gizmo cube, so reclaim the default right-panel
          // bottom clearance that reserves space for it (frontend-QA P2).
          <FloatingPanel
            side="right"
            title="Views"
            id="drawing-views"
            maxHeightClassName="max-h-[calc(100%-4.5rem)]"
          >
            <div className="flex flex-col gap-3">
              <ViewsPanel
                projecting={projecting}
                projections={requestedViews}
                resultByProjection={resultByProjection}
                composedByProjection={composedByProjection}
              />
              <BendSchedulePanel
                rows={resultByProjection.get("flat_pattern")?.bend_table ?? []}
              />
              <DimensionsPanel
                dimensions={dimensions}
                measuredById={measuredById}
                busy={dimBusy}
                movingId={placementReplaces(authoring)}
                onMove={handleMoveFromPanel}
                onDelete={handleDeleteDimension}
                onHeal={handleHealDimension}
              />
              <NotesPanel
                annotations={annotations}
                busy={noteBusy}
                onAdd={handleAddNote}
                onDelete={handleDeleteNote}
              />
              <PartsListPanel
                sourceKind={effectiveSourceKind}
                lines={bomQuery.data?.lines ?? []}
                totalInstances={bomQuery.data?.total_instances ?? 0}
                loading={bomQuery.isLoading}
                error={bomQuery.error}
                onOpen={handleOpenBomLine}
              />
            </div>
          </FloatingPanel>
        ) : null}

        {/* One chip for the whole authoring gesture: the "pick the second …"
            hint while a two-pick dimension is in progress, then "click to
            place" once the measurement is settled. Same chip, next sentence —
            placing is a continuation of the pick, not a new mode. Non-modal so
            the sheet stays live; Esc steps back one stage. */}
        {hint ? (
          <div
            role="status"
            data-testid="dimension-pick-hint"
            className="pointer-events-none absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-2 border border-brass/60 bg-anvil px-3 py-1.5 shadow-float"
          >
            <span className="font-display text-2xs whitespace-nowrap uppercase tracking-[0.16em] text-brass">
              {hint}
            </span>
            {/* THE PRECISION FALLBACK, not the live reading. The number you are
                watching rides the ghost on the paper (see PlacementGhostLayer);
                this is the field you reach for when the answer is exactly -25.
                Sheet millimetres: a distance on the PAPER, not in the model, so
                it is unit-free by nature — an A3 sheet is 420 mm whatever the
                part is drawn in. The chip stays pointer-transparent so it can
                never swallow a placement click; only the cell takes input. */}
            {placingOffsetMm !== null ? (
              <NumberField
                layout="inline"
                label="Offset"
                unit="mm"
                className="pointer-events-auto w-[13rem] shrink-0"
                ref={offsetFieldRef}
                data-testid="dimension-offset-field"
                data-offset-mm={placingOffsetMm.toFixed(2)}
                aria-label="Dimension offset in sheet millimetres"
                value={offsetText}
                onChange={(event) => handleOffsetTyped(event.target.value)}
                onFocus={() => setOffsetDraft(offsetText)}
                onBlur={() => setOffsetDraft(null)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    commitPlacementRef.current();
                    return;
                  }
                  // Up/Down keep nudging while the caret is in the cell (the
                  // numeric-field convention); Left/Right stay caret motion.
                  const sense =
                    event.key === "ArrowUp"
                      ? 1
                      : event.key === "ArrowDown"
                        ? -1
                        : 0;
                  if (sense !== 0) {
                    event.preventDefault();
                    const step = event.shiftKey
                      ? PLACE_NUDGE_MM * 5
                      : PLACE_NUDGE_MM;
                    setOffsetDraft(null);
                    setAuthoring((state) =>
                      nudgePlacement(state, 0, -sense, step),
                    );
                  }
                }}
              />
            ) : null}
            <span className="font-body text-2xs whitespace-nowrap text-gauge">
              {authoring.kind === "placing"
                ? placingOffsetMm !== null
                  ? "Type a value · arrows nudge · Enter places · Esc back"
                  : "Arrows nudge · Enter places · Esc back"
                : "Esc to cancel"}
            </span>
          </div>
        ) : null}

        {/* The gated dimension author menu — opens by the completing pick. A
            backdrop closes it on an outside click; it renders only for a menu
            state (a single-edge / two-edge / two-endpoint selection), never
            while a second pick is still being made. */}
        {anchor && menuActionList.length > 0 ? (
          <>
            <div
              // Same layer as the menu it dismisses (the menu is the later
              // sibling, so it paints above) — the scrim must cover EVERY
              // page-level surface, including the band.
              className="fixed inset-0 z-menu"
              aria-hidden="true"
              onClick={() => setAuthoring(IDLE)}
            />
            <DimensionAuthorMenu
              actions={menuActionList}
              x={anchor.x}
              y={anchor.y}
              busy={dimBusy}
              onChoose={handleChooseAction}
              onClose={() => setAuthoring(IDLE)}
            />
          </>
        ) : null}
      </main>
    </div>
  );
}

/** A centered status/error note over the bench. */
function CenterNote({
  testId,
  tone,
  title,
  body,
}: {
  testId: string;
  tone: "quiet" | "error";
  title: string;
  body: string;
}) {
  return (
    <div
      data-testid={testId}
      role={tone === "error" ? "alert" : "status"}
      className="absolute inset-0 flex items-center justify-center p-6"
    >
      <div className="max-w-sm border border-hairline bg-anvil px-4 py-3 text-center shadow-float">
        <p
          className={`font-display text-2xs uppercase tracking-[0.2em] ${
            tone === "error" ? "text-flag" : "text-gauge"
          }`}
        >
          {title}
        </p>
        <p className="mt-1 font-body text-sm text-mist">{body}</p>
      </div>
    </div>
  );
}

/**
 * The ISO projection-convention symbol — a truncated cone drawn twice: its
 * elevation (the trapezoid) and its end view (the two concentric circles). This
 * is the drawing's own vernacular rather than a generic UI icon, and it is the
 * one place this surface spends any boldness; everything around it stays quiet.
 *
 * WHICH SIDE THE CIRCLES SIT ON *IS* THE CONVENTION, and it is derived from the
 * SAME rule the server composer applies to the sheet (`bounds_aware_layout`'s
 * `right_sx`: +1 for third angle, -1 for first). The circles are the frustum's
 * RIGHT-side view, so third angle places them to the RIGHT of the elevation and
 * first angle to the LEFT — exactly where the sheet's own right view will land.
 * The glyph therefore teaches the layout the user is about to see. The two
 * symbols are exact mirrors (one path, one `scale(-1,1)`), as the standard's
 * pair are, with the frustum tapering toward its end view.
 *
 * Drawn in `currentColor` so it inherits the cell's brass/gauge state — no hex
 * literal, and one palette between the chrome and the sheet.
 */
function ProjectionSymbol({ convention }: { convention: SheetProjection }) {
  return (
    <svg
      viewBox="0 0 40 16"
      width="35"
      height="14"
      aria-hidden="true"
      focusable="false"
      className="shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.1}
      strokeLinejoin="round"
    >
      <g
        transform={
          convention === "first_angle"
            ? "translate(40 0) scale(-1 1)"
            : undefined
        }
      >
        {/* Elevation: the frustum, large end out, tapering toward its end view.
            The two circles are that SAME frustum's ends seen down its axis —
            outer radius = the large end's half-height, inner = the small end's —
            so the pair reads as one object rather than two marks. */}
        <path d="M1.6 1 L17 3.75 L17 12.25 L1.6 15 Z" />
        <circle cx="32" cy="8" r="7" />
        <circle cx="32" cy="8" r="4.25" />
      </g>
    </svg>
  );
}

/** The paper glyph — a sheet in its orientation, with the title-block corner
 * scribed in so it reads as THIS product's sheet rather than a generic page. */
function OrientationSymbol({ orientation }: { orientation: SheetOrientation }) {
  const landscape = orientation === "landscape";
  const w = landscape ? 14 : 9.5;
  const h = landscape ? 9.5 : 14;
  const x = (16 - w) / 2;
  const y = (16 - h) / 2;
  const block = 4;
  return (
    <svg
      viewBox="0 0 16 16"
      width="13"
      height="13"
      aria-hidden="true"
      focusable="false"
      className="shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.2}
      strokeLinejoin="round"
    >
      <rect x={x} y={y} width={w} height={h} />
      <path
        d={`M${x + w - block} ${y + h} L${x + w - block} ${y + h - 3} L${x + w} ${y + h - 3}`}
      />
    </svg>
  );
}

/** One header cell in the sheet strip — a stamped reading that is also the
 * control that changes it. Same idiom as a tab (hairline seat, brass on focus),
 * one notch quieter so the tabs stay the primary rail. */
function SheetHeaderCell({
  testid,
  label,
  onActivate,
  busy,
  attrs,
  tone = "quiet",
  children,
}: {
  testid: string;
  label: string;
  onActivate: () => void;
  busy: boolean;
  attrs: Record<string, string>;
  /** `stamp` is the drafting standard the sheet DECLARES — it has to be
   * readable at a glance, so it carries the same ink as the active tab.
   * `quiet` is for a secondary control whose state the paper itself shows. */
  tone?: "stamp" | "quiet";
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      data-testid={testid}
      aria-label={label}
      title={label}
      disabled={busy}
      onClick={onActivate}
      {...attrs}
      className={`flex shrink-0 items-center gap-1.5 border border-transparent px-1.5 py-1 font-display text-2xs uppercase tracking-[0.14em] transition-colors duration-fast hover:border-hairline hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40 ${
        tone === "stamp" ? "text-mist" : "text-gauge"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * The sheet header (FINDINGS #18 switcher + REACH-3 sheet convention) — a
 * compact strip in the top-left margin that says WHICH sheet and HOW it is set
 * up, and lets both be changed from where they are read. A quiet precision
 * instrument so the sheet stays the hero: brass underline on the active tab,
 * keyboard-first (every cell is a real button), all wired to real state/actions
 * (mandate 3a — nothing here is decoration).
 *
 * The convention cell stamps the ISO symbol for the sheet's projection standard
 * and flips it on activation; the orientation cell does the same for the paper,
 * and marks itself `data-proposed` when it already matches the orientation the
 * part's own extents argue for.
 *
 * The orientation cell states ONLY what it delivers (REACH-3-FLOW P1-2). It used
 * to read "switch to portrait (1:2)" and then return a sheet still drawn at 1:5
 * — documents refuses a per-view re-scale on a laid-out sheet, so no amount of
 * client work can honour that. The fit comparison lives on the set-up screen's
 * paper cell instead, where the scale is still free; here the cell says what a
 * flip actually does, which is re-draft the SAME scale on the other paper.
 */
function SheetTabs({
  sheets,
  activeIndex,
  onSelect,
  onAdd,
  adding,
  sheet,
  fit,
  drawnScale,
  onFlipConvention,
  onFlipOrientation,
  reheading,
}: {
  sheets: readonly SheetContent[];
  activeIndex: number;
  onSelect: (index: number) => void;
  onAdd: () => void;
  adding: boolean;
  sheet: SheetResponse | null;
  fit: OrientationFit | null;
  /** The scale the sheet is ACTUALLY drawn at, off the stored views. */
  drawnScale: string;
  onFlipConvention: () => void;
  onFlipOrientation: () => void;
  reheading: boolean;
}) {
  const convention = sheet?.projection ?? "third_angle";
  const orientation = sheet?.orientation ?? "landscape";
  const nextConvention = OTHER_CONVENTION[convention];
  const nextOrientation = OTHER_ORIENTATION[orientation];
  // A scrolling rail must still show you where you ARE. Adding an eleventh
  // sheet selects it, and without this the tab that just became active sits off
  // the end of the rail — the switcher would say "SHEET 10" while the page
  // showed sheet 11. Instant, not smooth: this is a state correction, not an
  // animation, so there is no motion for `prefers-reduced-motion` to suppress.
  const railRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const rail = railRef.current;
    const tab = rail?.querySelector<HTMLElement>('[role="tab"][data-active]');
    tab?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [activeIndex, sheets.length]);
  // The strip is capped and the TAB RAIL scrolls inside it, so the two header
  // cells stay put however many sheets exist. Before: eleven sheets pushed the
  // convention and orientation cells off the right of a 1024 viewport — the
  // controls that DECLARE the sheet's standard were the first thing a
  // many-sheet drawing lost, with nothing to say where they had gone.
  return (
    <div className="absolute left-3 top-3 z-overlay flex max-w-[calc(100%-1.5rem)] items-center gap-1 border border-hairline bg-anvil/95 px-1.5 py-1 shadow-float backdrop-blur-sm">
      <div
        ref={railRef}
        className="flex min-w-0 items-center gap-1 overflow-x-auto"
        role="tablist"
        aria-label="Drawing sheets"
        data-testid="sheet-tabs"
      >
        {sheets.map((content, index) => {
          const active = index === activeIndex;
          return (
            <button
              key={content.sheet.id}
              type="button"
              role="tab"
              aria-selected={active}
              data-testid={`sheet-tab-${index}`}
              data-active={active || undefined}
              onClick={() => onSelect(index)}
              className={`shrink-0 whitespace-nowrap border-b-2 px-2.5 py-1 font-display text-2xs uppercase tracking-[0.14em] transition-colors duration-fast focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass ${
                active
                  ? "border-brass text-mist"
                  : "border-transparent text-gauge hover:text-mist"
              }`}
            >
              {content.sheet.name}
            </button>
          );
        })}
      </div>
      {/* ADD sits OUTSIDE the scrolling rail, beside the header cells. It is an
          action, not a tab (it never carried `role="tab"`, so it did not belong
          inside the tablist either), and inside the rail an eleven-sheet drawing
          would scroll the only way to make a twelfth off the end of it. */}
      <button
        type="button"
        onClick={onAdd}
        disabled={adding}
        data-testid="sheet-tab-add"
        aria-label={
          fit
            ? `Add sheet — ${ORIENTATION_NAME[fit.proposed]} at ${fit.scaleByOrientation[fit.proposed]}`
            : "Add sheet"
        }
        data-proposed-orientation={fit?.proposed}
        className="ml-0.5 shrink-0 rounded-sm px-1.5 py-1 font-display text-xs leading-none text-gauge transition-colors duration-fast hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40"
      >
        {adding ? "…" : "+"}
      </button>
      {sheet ? (
        <>
          <span aria-hidden="true" className="mx-1 h-4 w-px bg-hairline" />
          <SheetHeaderCell
            testid="sheet-projection"
            label={`Projection convention: ${CONVENTION_NAME[convention]} — switch to ${CONVENTION_NAME[nextConvention]}`}
            onActivate={onFlipConvention}
            busy={reheading}
            tone="stamp"
            attrs={{ "data-projection": convention }}
          >
            <ProjectionSymbol convention={convention} />
            <span>{convention === "third_angle" ? "3rd" : "1st"}</span>
          </SheetHeaderCell>
          <SheetHeaderCell
            testid="sheet-orientation"
            label={`Sheet orientation: ${ORIENTATION_NAME[orientation]}, drawn at ${drawnScale} — switch to ${ORIENTATION_NAME[nextOrientation]} paper, keeping ${drawnScale}${
              fit
                ? `. A fresh ${ORIENTATION_NAME[nextOrientation]} sheet would fit this at ${fit.scaleByOrientation[nextOrientation]}.`
                : "."
            }`}
            onActivate={onFlipOrientation}
            busy={reheading}
            attrs={{
              "data-orientation": orientation,
              ...(fit
                ? {
                    "data-fit-landscape": fit.scaleByOrientation.landscape,
                    "data-fit-portrait": fit.scaleByOrientation.portrait,
                    "data-proposed": String(orientation === fit.proposed),
                  }
                : {}),
            }}
          >
            <OrientationSymbol orientation={orientation} />
          </SheetHeaderCell>
        </>
      ) : null}
    </div>
  );
}

/**
 * The empty-bench invitation before any views are laid out — and the one place
 * the orientation PROPOSAL is answerable before it costs anything.
 *
 * The paper cell is the same instrument the sheet header wears after layout
 * (`SheetHeaderCell` + `OrientationSymbol`), deliberately: one vocabulary for
 * one decision, so what the user learns here still reads after the sheet
 * exists. It only appears once there is a measured proposal to state — an
 * unmeasurable source gets no cell rather than a cell asserting the default,
 * which would be chrome that only decorates (mandate 3a).
 */
function SetupHint({
  hasParts,
  size,
  orientation,
  fit,
  onFlipPaper,
  busy,
}: {
  hasParts: boolean;
  size: SheetSize;
  orientation: SheetOrientation;
  fit: OrientationFit | null;
  onFlipPaper: () => void;
  busy: boolean;
}) {
  const next = OTHER_ORIENTATION[orientation];
  const paper = `${sheetSizeLabel(size)} ${ORIENTATION_NAME[orientation]}`;
  return (
    <div
      data-testid="drawing-setup-hint"
      style={{ pointerEvents: "none" }}
      className="absolute inset-0 flex items-center justify-center p-6"
    >
      <div className="max-w-md text-center">
        <p className="font-display text-2xs uppercase tracking-[0.2em] text-gauge">
          Empty sheet
        </p>
        <h2 className="mt-2 font-body text-lg text-mist">
          {hasParts ? "Lay out the standard views." : "Create a part first."}
        </h2>
        <p className="mt-1 font-body text-sm text-gauge">
          {hasParts
            ? "Choose a part, sheet size and scale above, then lay out the standard views — front, top, right and isometric — or unfold a sheet-metal part's flat pattern with its bend table."
            : "A drawing projects a part. Model a part, then return to draft it."}
        </p>
        {hasParts && fit ? (
          <div className="mt-4 flex items-center justify-center [pointer-events:auto]">
            <SheetHeaderCell
              testid="setup-paper"
              label={`Sheet paper: ${paper}, fits ${fit.scaleByOrientation[orientation]} — switch to ${ORIENTATION_NAME[next]} (${fit.scaleByOrientation[next]})`}
              onActivate={onFlipPaper}
              busy={busy}
              tone="stamp"
              attrs={{
                "data-orientation": orientation,
                "data-fit-landscape": fit.scaleByOrientation.landscape,
                "data-fit-portrait": fit.scaleByOrientation.portrait,
                "data-proposed": String(orientation === fit.proposed),
              }}
            >
              <OrientationSymbol orientation={orientation} />
              <span>
                {paper} · {fit.scaleByOrientation[orientation]}
              </span>
            </SheetHeaderCell>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** The right-hand "Views" panel — a functional legend + per-view line count. It
 * lists exactly the projections placed on the sheet (the standard four, or a lone
 * flat pattern), and its legend gains the FOLD-LINE swatch when a flat pattern is
 * present (the sheet-metal signature stroke), reading from the same `drawing`
 * token both renderers share. */
function ViewsPanel({
  projecting,
  projections,
  resultByProjection,
  composedByProjection,
}: {
  projecting: boolean;
  projections: readonly ViewProjection[];
  resultByProjection: Map<ViewProjection, DrawingViewResult>;
  /**
   * The PLACED views, which for an assembly sheet are the only reading there
   * is: the part-shaped `evaluate` hop does not run for one (the gateway
   * resolves the instance graph and geometry projects the solved compound), so
   * `resultByProjection` is empty and this panel used to report "0 edges" over
   * a sheet full of geometry. A readout that is confidently wrong is worse
   * than one that is absent — same count, taken from what was drawn.
   */
  composedByProjection: Map<ViewProjection, ComposedView>;
}) {
  const flatPattern = projections.includes("flat_pattern");
  const bendCount =
    resultByProjection.get("flat_pattern")?.bend_table?.length ?? 0;
  return (
    <div className="border border-hairline bg-anvil">
      <header className="flex items-baseline gap-2 border-b border-hairline px-3 py-2">
        <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          {flatPattern ? "Flat pattern" : "Standard views"}
        </h2>
        <span className="grow" />
        {projecting ? (
          <span
            data-testid="drawing-projecting"
            className="font-data text-2xs text-brass"
          >
            Projecting…
          </span>
        ) : null}
      </header>
      <ul className="divide-y divide-hairline">
        {projections.map((projection) => {
          const result = resultByProjection.get(projection);
          const placed = composedByProjection.get(projection);
          const failed = Boolean(result?.error ?? placed?.error);
          // Prefer the evaluated reading (it exists the moment the projection
          // lands, before the compose returns); fall back to what was placed.
          const count = result?.edges?.length ?? placed?.edges?.length ?? 0;
          return (
            <li
              key={projection}
              className="flex items-center justify-between px-3 py-1.5"
              data-testid="drawing-view-row"
              data-view={projection}
            >
              <span className="font-body text-xs text-mist">
                {VIEW_LABEL[projection]}
              </span>
              <span
                className={`font-data text-2xs tabular-nums ${
                  failed ? "text-flag" : "text-gauge"
                }`}
              >
                {failed ? "failed" : `${count} edges`}
              </span>
            </li>
          );
        })}
      </ul>
      {flatPattern && bendCount > 0 ? (
        <div
          className="flex items-center justify-between border-t border-hairline px-3 py-1.5"
          data-testid="drawing-bend-count"
        >
          <span className="font-body text-xs text-mist">Bends</span>
          <span className="font-data text-2xs tabular-nums text-gauge">
            {bendCount}
          </span>
        </div>
      ) : null}
      <div className="border-t border-hairline px-3 py-2">
        <div className="flex items-center gap-2 py-0.5">
          <svg width="26" height="6" aria-hidden="true">
            <line
              x1="0"
              y1="3"
              x2="26"
              y2="3"
              stroke="currentColor"
              strokeWidth="1.5"
              className="text-mist"
            />
          </svg>
          <span className="font-body text-2xs text-gauge">
            {flatPattern ? "Cut edge" : "Visible edge"}
          </span>
        </div>
        {flatPattern ? (
          // The fold-line swatch — the sheet-metal signature stroke, drawn in the
          // exact `drawing.bend` ink AND `bendDash/Gap` pattern the real fold
          // stroke uses, so the legend can never drift from the stroke.
          <div className="flex items-center gap-2 py-0.5">
            <svg width="26" height="6" aria-hidden="true">
              <line
                x1="0"
                y1="3"
                x2="26"
                y2="3"
                stroke={drawing.bend}
                strokeWidth="1.5"
                strokeDasharray={`${drawing.bendDashMm} ${drawing.bendGapMm}`}
              />
            </svg>
            <span className="font-body text-2xs text-gauge">Fold line</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 py-0.5">
            <svg width="26" height="6" aria-hidden="true">
              <line
                x1="0"
                y1="3"
                x2="26"
                y2="3"
                stroke="currentColor"
                strokeWidth="1.5"
                // Same token pattern the hidden-edge stroke draws (was "4 3").
                strokeDasharray={`${drawing.hiddenDashMm} ${drawing.hiddenGapMm}`}
                className="text-gauge"
              />
            </svg>
            <span className="font-body text-2xs text-gauge">Hidden edge</span>
          </div>
        )}
      </div>
    </div>
  );
}

/** The formatted display cells for one bend-schedule row — the same values the
 * SVG bend table stamps (angle°, R-radius, UP/DOWN, allowance), so the DOM text
 * a screen reader reads matches the printed sheet. */
function bendScheduleCells(row: BendTableRow): {
  angle: string;
  radius: string;
  dir: string;
  allow: string;
} {
  return {
    angle: `${row.angle_deg.toFixed(1)}°`,
    radius: `R${row.radius_mm.toFixed(2)}`,
    dir: row.direction === "up" ? "UP" : "DOWN",
    allow: row.bend_allowance_mm.toFixed(2),
  };
}

/**
 * The Bend schedule — a TEXT-accessible twin of the flat-pattern sheet's SVG
 * bend table (which renders inside a `role="img"` sheet, so assistive tech never
 * reads the per-bend values). A real `<table>` with column headers so AT reads
 * each cell's meaning (angle / radius / direction / allowance); each row keys
 * POSITIONALLY to the flat view's `edge_role="bend"` fold lines — the i-th row ↔
 * the i-th bend edge (`data-bend-index`), the SAME contract the visual table
 * uses, never a `bend_id` join. Rendered only for a flat pattern with bends.
 */
function BendSchedulePanel({ rows }: { rows: readonly BendTableRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div
      className="border border-hairline bg-anvil"
      data-testid="bend-schedule-panel"
    >
      <header className="flex items-baseline gap-2 border-b border-hairline px-3 py-2">
        <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Bend schedule
        </h2>
        <span className="grow" />
        <span className="font-data text-2xs tabular-nums text-gauge">
          {rows.length}
        </span>
      </header>
      <table
        className="w-full border-collapse"
        aria-label={`Bend schedule, ${rows.length} bends`}
      >
        <caption className="sr-only">
          Fold instructions per bend, in fold-position order: fold angle, inner
          radius in millimetres, direction, and bend allowance in millimetres.
        </caption>
        <thead>
          <tr className="border-b border-hairline">
            <th
              scope="col"
              className="px-3 py-1.5 text-left font-display text-2xs uppercase tracking-[0.14em] text-gauge"
            >
              Bend
            </th>
            <th
              scope="col"
              className="px-2 py-1.5 text-right font-display text-2xs uppercase tracking-[0.14em] text-gauge"
            >
              Angle
            </th>
            <th
              scope="col"
              className="px-2 py-1.5 text-right font-display text-2xs uppercase tracking-[0.14em] text-gauge"
            >
              Radius
            </th>
            <th
              scope="col"
              className="px-2 py-1.5 text-right font-display text-2xs uppercase tracking-[0.14em] text-gauge"
            >
              Dir
            </th>
            <th
              scope="col"
              className="px-3 py-1.5 text-right font-display text-2xs uppercase tracking-[0.14em] text-gauge"
            >
              Allow mm
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {rows.map((row, i) => {
            const cells = bendScheduleCells(row);
            return (
              <tr
                key={i}
                data-testid="bend-schedule-row"
                data-bend-index={String(i)}
              >
                <td className="px-3 py-1.5 text-left font-data text-2xs text-mist">
                  {row.bend_id}
                </td>
                <td className="px-2 py-1.5 text-right font-data text-2xs tabular-nums text-mist">
                  {cells.angle}
                </td>
                <td className="px-2 py-1.5 text-right font-data text-2xs tabular-nums text-mist">
                  {cells.radius}
                </td>
                <td className="px-2 py-1.5 text-right font-data text-2xs text-gauge">
                  {cells.dir}
                </td>
                <td className="px-3 py-1.5 text-right font-data text-2xs tabular-nums text-mist">
                  {cells.allow}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The Parts list — the sheet's numbered item table (design §7 BOM), the block a
 * shop reads to know WHAT to make and HOW MANY. Sibling of the Notes panel, and
 * the only surface in the workspace that names other documents, so each row is
 * the way to open the one it names.
 *
 * The item NUMBER is the signature: a drafting balloon, the circled numeral
 * that ties a row to the geometry on the paper. It is not decoration — the
 * number is content here, DERIVED server-side from the assembly's stable
 * instance order, which is why two reads of an unchanged assembly number
 * identically and a rename never renumbers anything.
 *
 * A PART-sourced sheet has no bill of materials, and that is a fact worth
 * stating rather than hiding: the block still renders, disabled, carrying the
 * reason. The reason is focusable (`tabIndex={0}`) because a caption a mouse
 * can read and a keyboard cannot is only half-shipped — this is the on-screen
 * form of the server's own `drawing_bom_source_not_assembly`, made legible
 * before anyone can hit it.
 */
function PartsListPanel({
  sourceKind,
  lines,
  totalInstances,
  loading,
  error,
  onOpen,
}: {
  sourceKind: RefDocumentKind;
  lines: readonly DrawingBomLine[];
  totalInstances: number;
  loading: boolean;
  error: unknown;
  onOpen: (line: DrawingBomLine) => void;
}) {
  const unavailable = sourceKind !== "assembly";
  return (
    <div
      className="border border-hairline bg-anvil"
      data-testid="parts-list-panel"
      data-source-kind={sourceKind}
      data-disabled={unavailable ? "true" : "false"}
    >
      <header className="flex items-baseline gap-2 border-b border-hairline px-3 py-2">
        <h2
          className={`font-display text-2xs uppercase tracking-[0.18em] ${
            unavailable ? "text-gauge/60" : "text-gauge"
          }`}
        >
          Parts list
        </h2>
        <span className="grow" />
        {unavailable ? null : (
          <span
            data-testid="parts-list-total"
            className="font-data text-2xs tabular-nums text-gauge"
          >
            {totalInstances}
          </span>
        )}
      </header>
      {unavailable ? (
        <p
          tabIndex={0}
          role="note"
          data-testid="parts-list-unavailable"
          className="px-3 py-2.5 font-body text-2xs text-gauge focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass"
        >
          A parts list needs an assembly source. This sheet drafts a part —
          draft an assembly to number its items.
        </p>
      ) : error ? (
        <p
          role="alert"
          data-testid="parts-list-error"
          className="px-3 py-2.5 font-body text-2xs text-flag"
        >
          {error instanceof Error
            ? error.message
            : "The parts list could not be loaded."}
        </p>
      ) : loading ? (
        <p
          data-testid="parts-list-loading"
          className="px-3 py-2.5 font-body text-2xs text-gauge"
        >
          Numbering the items…
        </p>
      ) : lines.length === 0 ? (
        <p
          data-testid="parts-list-empty"
          className="px-3 py-2.5 font-body text-2xs text-gauge"
        >
          This assembly has no instances yet. Add parts to it and the items
          number themselves.
        </p>
      ) : (
        <table
          className="w-full border-collapse"
          aria-label={`Parts list, ${lines.length} items, ${totalInstances} instances`}
        >
          <caption className="sr-only">
            One row per referenced document in item-number order: item number,
            name, and the quantity of instances.
          </caption>
          <thead>
            <tr className="border-b border-hairline">
              <th
                scope="col"
                className="px-3 py-1.5 text-left font-display text-2xs uppercase tracking-[0.14em] text-gauge"
              >
                No.
              </th>
              <th
                scope="col"
                className="px-2 py-1.5 text-left font-display text-2xs uppercase tracking-[0.14em] text-gauge"
              >
                Item
              </th>
              <th
                scope="col"
                className="px-3 py-1.5 text-right font-display text-2xs uppercase tracking-[0.14em] text-gauge"
              >
                Qty
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {lines.map((line) => (
              <tr
                key={`${line.item_number}:${line.ref_document_id}`}
                data-testid="parts-list-row"
                data-item-number={String(line.item_number)}
                data-ref-document-id={line.ref_document_id}
                data-ref-kind={line.ref_document_kind}
              >
                <td className="px-3 py-1.5">
                  {/* The balloon — the drafting artifact, not an ornament: a
                      circled numeral is how an item list points at the paper. */}
                  <span
                    data-testid="parts-list-item-number"
                    className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-etch font-data text-2xs tabular-nums text-mist"
                  >
                    {line.item_number}
                  </span>
                </td>
                <td className="px-2 py-1.5">
                  {line.missing ? (
                    <span
                      data-testid="parts-list-name"
                      className="font-body text-2xs text-flag"
                    >
                      Deleted document
                    </span>
                  ) : (
                    <button
                      type="button"
                      data-testid="parts-list-name"
                      title={line.name ?? undefined}
                      aria-label={`Open ${line.name ?? "item"}`}
                      onClick={() => onOpen(line)}
                      className="block w-full truncate text-left font-body text-2xs text-mist transition-colors duration-fast hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass"
                    >
                      {line.name}
                    </button>
                  )}
                </td>
                <td
                  data-testid="parts-list-qty"
                  className="px-3 py-1.5 text-right font-data text-2xs tabular-nums text-mist"
                >
                  {line.quantity}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/**
 * The Notes panel — author a free-text note and manage the sheet's notes (design
 * §2.2). Adding a note persists it (CRUD) and re-composes the sheet, which draws
 * it at its authored point from `ComposedSheet.notes`; the list is the keyboard/
 * touch path to removing one. A quiet precision instrument, sibling of the
 * Dimensions panel — the sheet stays the hero.
 */
function NotesPanel({
  annotations,
  busy,
  onAdd,
  onDelete,
}: {
  annotations: readonly AnnotationResponse[];
  busy: boolean;
  onAdd: (text: string) => void;
  onDelete: (annotationId: string) => void;
}) {
  const [text, setText] = useState("");
  const canAdd = text.trim().length > 0 && !busy;
  const submit = () => {
    if (!canAdd) return;
    onAdd(text);
    setText("");
  };
  return (
    <div className="border border-hairline bg-anvil" data-testid="notes-panel">
      <header className="flex items-baseline gap-2 border-b border-hairline px-3 py-2">
        <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Notes
        </h2>
        <span className="grow" />
        <span className="font-data text-2xs tabular-nums text-gauge">
          {annotations.length}
        </span>
      </header>
      <form
        className="flex items-end gap-2 border-b border-hairline px-3 py-2.5"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <TextField
          label="Add a note"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="e.g. Break all sharp edges"
          className="grow"
          data-testid="note-input"
        />
        <Button
          type="submit"
          variant="ghost"
          disabled={!canAdd}
          data-testid="note-add"
          aria-label="Add note"
        >
          Add
        </Button>
      </form>
      {annotations.length === 0 ? (
        <p className="px-3 py-2.5 font-body text-2xs text-gauge">
          Notes print on the sheet at the top-left — material callouts, finish,
          or shop instructions.
        </p>
      ) : (
        <ul className="divide-y divide-hairline">
          {annotations.map((entry) => (
            <li
              key={entry.id}
              className="flex items-center gap-2 px-3 py-1.5"
              data-testid="note-row"
            >
              <span
                data-testid="note-row-text"
                className="grow truncate font-body text-2xs text-mist"
                title={entry.annotation.text}
              >
                {entry.annotation.text}
              </span>
              <button
                type="button"
                disabled={busy}
                data-testid="note-delete"
                aria-label={`Delete note "${entry.annotation.text}"`}
                onClick={() => onDelete(entry.id)}
                className="shrink-0 rounded-sm px-1.5 py-0.5 font-display text-2xs uppercase tracking-[0.14em] text-gauge transition-colors duration-fast hover:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * The Dimensions panel — the authored dimensions with their model-true value and
 * a delete affordance (design §3 "Manage"). It is the keyboard/touch path to
 * removing a dimension and the honest place a measurement error surfaces.
 *
 * Two things the server has always shipped and this panel used to drop (audit
 * N1 frontend half):
 *
 *  - a dimension that could not be measured said only "unresolved", while
 *    `measured.error.message` carried the typed sentence the SHEET already
 *    stamps beside the marker. The words belong on both.
 *  - `measured.anchor.tier === "durable"` means the stored reference did not
 *    match after an edit and geometry re-anchored it on the rebuild invariant.
 *    The value is model-true either way, so this is not an alarm — it is the
 *    dashed "not established" {@link Stamp}, plus the one click that stores the
 *    signature geometry landed on and makes the reference exact again.
 */
function DimensionsPanel({
  dimensions,
  measuredById,
  busy,
  movingId,
  onMove,
  onDelete,
  onHeal,
}: {
  dimensions: readonly DimensionResponse[];
  measuredById: Map<string, MeasuredDimension>;
  busy: boolean;
  /** The dimension currently being re-placed, if any — its row says so. */
  movingId: string | null;
  /** Pick this dimension up and re-enter the PLACE stage (P1-E). */
  onMove: (dimensionId: string) => void;
  onDelete: (dimensionId: string) => void;
  /** Store the re-anchored signature for this dimension (the "confirm" write). */
  onHeal: (dimensionId: string) => void;
}) {
  return (
    <div
      className="border border-hairline bg-anvil"
      data-testid="dimensions-panel"
    >
      <header className="flex items-baseline gap-2 border-b border-hairline px-3 py-2">
        <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Dimensions
        </h2>
        <span className="grow" />
        <span className="font-data text-2xs tabular-nums text-gauge">
          {dimensions.length}
        </span>
      </header>
      {dimensions.length === 0 ? (
        <p className="px-3 py-2.5 font-body text-2xs text-gauge">
          Click a highlighted edge on a view to add a dimension — a circle takes
          a diameter or radius, a straight edge a linear; pick a second edge for
          an angle or the distance across (a wall thickness).
        </p>
      ) : (
        <>
          <ul className="divide-y divide-hairline">
            {dimensions.map((dim) => {
              const measured = measuredById.get(dim.id);
              const errored = Boolean(measured?.error);
              const foreshortened = Boolean(measured?.foreshortened);
              const value =
                measured && typeof measured.value === "number"
                  ? (foreshortened ? "~" : "") +
                    formatDimensionLabel(
                      dim.dimension.type,
                      measured.value,
                      measured.unit,
                    )
                  : errored
                    ? "unresolved"
                    : "…";
              // The typed sentence the server already stamps on the sheet
              // ("REFERENCE LOST - RE-PICK THE EDGE"); the panel said only
              // "unresolved" beside it. The phrase is the SERVER's.
              const reason = measured?.error?.message ?? null;
              const anchor = reanchoredAnchor(measured);
              const healable =
                anchor !== null &&
                healDimensionParams(dim.dimension, anchor) !== null;
              return (
                <li
                  key={dim.id}
                  className="px-3 py-1.5"
                  data-testid="dimension-row"
                  data-dimension-type={dim.dimension.type}
                  // A linear dimension has three quite different meanings; the
                  // row (and any test) can tell them apart without re-parsing.
                  data-dimension-mode={
                    dim.dimension.type === "linear"
                      ? dim.dimension.measurement.mode
                      : undefined
                  }
                  data-foreshortened={foreshortened ? "true" : "false"}
                  data-anchor-tier={measured?.anchor?.tier ?? "none"}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-display text-2xs uppercase tracking-[0.14em] text-gauge">
                      {dim.dimension.type}
                    </span>
                    <span
                      data-testid="dimension-row-value"
                      // Foreshortened matches the sheet: the ~value reads in the
                      // same flag ink on BOTH renderers (was un-flagged here).
                      className={`grow text-right font-data text-2xs tabular-nums ${
                        errored || foreshortened ? "text-flag" : "text-mist"
                      }`}
                    >
                      {value}
                    </span>
                    {/* MOVE, beside Delete. The sheet's own value stamp is the
                        primary route (press it and drag), but the panel is
                        where a user looks for "what can I do to this one", and
                        before this the honest answer was "delete it and author
                        it again" (frontend-QA 2026-08-27, P1-E). */}
                    {!errored ? (
                      <button
                        type="button"
                        disabled={busy}
                        data-testid="dimension-move"
                        aria-label={`Move the ${dim.dimension.type} dimension`}
                        onClick={() => onMove(dim.id)}
                        className="shrink-0 rounded-sm px-1.5 py-0.5 font-display text-2xs uppercase tracking-[0.14em] text-gauge transition-colors duration-fast hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40"
                      >
                        {dim.id === movingId ? "Placing…" : "Move"}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      disabled={busy}
                      data-testid="dimension-delete"
                      aria-label={`Delete ${dim.dimension.type} dimension`}
                      onClick={() => onDelete(dim.id)}
                      className="shrink-0 rounded-sm px-1.5 py-0.5 font-display text-2xs uppercase tracking-[0.14em] text-gauge transition-colors duration-fast hover:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40"
                    >
                      Delete
                    </button>
                  </div>
                  {/* WHY it is unresolved, in the server's words — the print has
                      said this beside the marker since audit N1; the screen
                      said "unresolved" and stopped. */}
                  {errored && reason ? (
                    <p
                      data-testid="dimension-row-reason"
                      className="mt-1 font-body text-2xs text-flag"
                    >
                      {reason}
                    </p>
                  ) : null}
                  {anchor !== null ? (
                    <div className="mt-1 flex items-center gap-2">
                      <Stamp indeterminate data-testid="dimension-reanchored">
                        Re-anchored
                      </Stamp>
                      <span className="grow" />
                      {healable ? (
                        <button
                          type="button"
                          disabled={busy}
                          data-testid="dimension-heal"
                          aria-label={`Confirm the re-anchored reference for the ${dim.dimension.type} dimension`}
                          onClick={() => onHeal(dim.id)}
                          className="shrink-0 rounded-sm px-1.5 py-0.5 font-display text-2xs uppercase tracking-[0.14em] text-brass transition-colors duration-fast hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40"
                        >
                          Confirm
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
          {/* An ALWAYS-VISIBLE legend for the `~` flag — the sheet only explains
              it via a mouse-hover SVG <title>; this reaches keyboard + touch. */}
          {dimensions.some((dim) => measuredById.get(dim.id)?.foreshortened) ? (
            <p
              data-testid="dimension-foreshortened-note"
              className="border-t border-hairline px-3 py-2 font-body text-2xs text-flag"
            >
              <span className="font-data">~</span> shown from a true-size view
              for the drawn length (foreshortened).
            </p>
          ) : null}
          {/* The dashed stamp on its own is jargon; this is the sentence that
              makes it actionable, always visible (the `~` legend's twin). */}
          {dimensions.some(
            (dim) => reanchoredAnchor(measuredById.get(dim.id)) !== null,
          ) ? (
            <p
              data-testid="dimension-reanchored-note"
              className="border-t border-hairline px-3 py-2 font-body text-2xs text-gauge"
            >
              Re-anchored: the part changed, so this was re-measured from the
              edge that is there now. Confirm to store the new reference.
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
