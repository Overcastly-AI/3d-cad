import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button, TextField, drawing } from "@loft/design";

import {
  type AnnotationResponse,
  type BendTableRow,
  type DimensionResponse,
  type DrawingDimensionInput,
  type DrawingViewResult,
  type EvaluateDrawingViewsRequest,
  type MeasuredDimension,
  type SectionViewParams,
  type SheetContent,
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
  fetchDrawing,
} from "../api/drawings";
import { evaluatePart, fetchFeatureTree, fetchParts } from "../api/parts";
import { Breadcrumb } from "../components/Breadcrumb";
import { DimensionAuthorMenu } from "../components/DimensionAuthorMenu";
import { DrawingCommandBand } from "../components/DrawingCommandBand";
import {
  DrawingSheet,
  type EdgePickEvent,
  type EndpointPickEvent,
  edgeKey,
  vertexKey,
} from "../components/DrawingSheet";
import { FloatingPanel } from "../components/FloatingPanel";
import { SectionAuthorPanel } from "../components/SectionAuthorPanel";
import { TopBar } from "../components/TopBar";
import { TopToolbar } from "../components/TopToolbar";
import {
  IDLE,
  type AuthoringState,
  type DimensionAction,
  armAngular,
  armedSignatures,
  buildDimension,
  menuActions,
  menuAnchor,
  pickEdge,
  pickEndpoint,
  pickHint,
  selectedEndpoints,
} from "../drawing/authoring";
import { type DrawingExportFormat, exportDrawing } from "../api/exportDrawing";
import { downloadBlob } from "../api/exportPart";
import { formatDimensionLabel } from "../drawing/dimensions";
import { exportSheetSvg } from "../drawing/exportSvg";
import {
  SCALE_OPTIONS,
  STANDARD_VIEWS,
  VIEW_LABEL,
  fitScale,
  sheetDimensions,
  standardLayout,
} from "../drawing/layout";
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
  // v1 compose/export are first-sheet only (gateway `_aggregate_compose_request`
  // composes `sheets[0]`); the paper preview + server exports therefore render the
  // FIRST sheet. Every other sheet is fully set-up-able + managed (its own views/
  // dimensions/notes), just not yet composable — tracked as a backend follow-up.
  const isComposableSheet = activeIndex === 0;

  const sheet = tree?.sheets[activeIndex]?.sheet ?? null;
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

  // The part the sheet drafts: the referenced part of its first view once laid
  // out (v1 references a single part across the standard views).
  const draftedPartId = hasLayout ? (views[0]?.ref_document_id ?? null) : null;

  const partsQuery = useQuery({
    queryKey: ["parts"],
    queryFn: () => fetchParts(),
    staleTime: 30_000,
  });
  const parts = useMemo(() => partsQuery.data ?? [], [partsQuery.data]);

  // Pre-layout picker state (which part to draft, on what sheet, at what scale).
  const [selectedPartId, setSelectedPartId] = useState<string | null>(null);
  const [scaleValue, setScaleValue] = useState("1:1");
  const [sizeValue, setSizeValue] = useState<SheetSize>("A4");
  useEffect(() => {
    if (selectedPartId === null && parts.length > 0) {
      setSelectedPartId(parts[0]?.id ?? null);
    }
  }, [parts, selectedPartId]);

  // The effective part + scale to project: the drafted part once laid out.
  const effectivePartId = draftedPartId ?? null;
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

  // Project the part into the standard views (exact HLR, server-side).
  const evalQuery = useQuery({
    queryKey: [
      "drawing-eval",
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
      effectivePartId,
      partTree?.tree_version,
      effectiveScaleValue,
      docVersion,
    ],
    enabled: hasLayout && partTree !== undefined && isComposableSheet,
    queryFn: () => composeDrawingSheet(drawingId),
    staleTime: Infinity,
  });
  const composed = sheetQuery.data;

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
    queryKey: ["drawing-section-part-tree", selectedPartId],
    enabled: sectionOpen && selectedPartId !== null,
    queryFn: () => fetchFeatureTree(selectedPartId as string),
    staleTime: 30_000,
  });
  const sectionDatumOptions = useMemo(
    () => resolveDatumPlaneOptions(sectionPartTreeQuery.data?.features ?? []),
    [sectionPartTreeQuery.data],
  );

  const handleLayout = useCallback(() => {
    if (hasLayout || selectedPartId === null || busy) return;
    setBusy(true);
    setActionError(null);
    void (async () => {
      try {
        let version = docVersion;
        let sheetId = sheet?.id ?? null;
        if (sheetId === null) {
          const created = await createSheet(drawingId, {
            name: "Sheet 1",
            size: sizeValue,
            orientation: "landscape",
            projection: "third_angle",
            expected_version: version,
          });
          version = created.doc_version;
          sheetId = created.sheet.id;
        }
        const dims = sheetDimensions(sizeValue, "landscape");
        const anchors = standardLayout(dims);
        // Fit-scale: never lay out views that overflow their cells — evaluate
        // the part's bbox and reduce the scale until the four standard views
        // fit (the user's picked scale is a ceiling; see fitScale). A part
        // that fails to evaluate keeps the picked scale — the layout still
        // lands, just unfitted, and the sheet surfaces the eval error.
        let fittedValue = scaleValue;
        try {
          const evaluated = await evaluatePart(selectedPartId);
          const box = evaluated.properties?.bounding_box;
          if (box) {
            fittedValue = fitScale(
              {
                x: box.max.x - box.min.x,
                y: box.max.y - box.min.y,
                z: box.max.z - box.min.z,
              },
              dims,
              scaleValue,
            ).value;
          }
        } catch {
          // keep the picked scale
        }
        const scale = scaleFromValue(fittedValue);
        for (const projection of STANDARD_VIEWS) {
          const anchor = anchors[projection];
          const created = await createView(drawingId, sheetId, {
            projection,
            ref_document_id: selectedPartId,
            ref_document_kind: "part",
            scale,
            position: { x_mm: anchor.x, y_mm: anchor.y },
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
    selectedPartId,
    busy,
    docVersion,
    sheet,
    drawingId,
    scaleValue,
    sizeValue,
    queryClient,
  ]);

  // The flat-pattern action: create the sheet (if needed) + a single flat_pattern
  // view (the lone unfold blank + its bend table, sheet-metal.md §7). A part with
  // no sheet-metal bends composes an honest `flat_pattern_not_sheet_metal` failed
  // view — surfaced inline, never a crash.
  const handleFlatPattern = useCallback(() => {
    if (hasLayout || selectedPartId === null || busy) return;
    setBusy(true);
    setActionError(null);
    void (async () => {
      try {
        let version = docVersion;
        let sheetId = sheet?.id ?? null;
        if (sheetId === null) {
          const created = await createSheet(drawingId, {
            name: "Sheet 1",
            size: sizeValue,
            orientation: "landscape",
            projection: "third_angle",
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
        const dims = sheetDimensions(sizeValue, "landscape");
        const created = await createView(drawingId, sheetId, {
          projection: "flat_pattern",
          ref_document_id: selectedPartId,
          ref_document_kind: "part",
          scale: scaleFromValue(scaleValue),
          position: { x_mm: dims.width / 2, y_mm: dims.height / 2 },
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
    selectedPartId,
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
      if (hasLayout || selectedPartId === null || busy) return;
      setBusy(true);
      setSectionError(null);
      void (async () => {
        try {
          let version = docVersion;
          let sheetId = sheet?.id ?? null;
          if (sheetId === null) {
            const created = await createSheet(drawingId, {
              name: "Sheet 1",
              size: sizeValue,
              orientation: "landscape",
              projection: "third_angle",
              expected_version: version,
            });
            version = created.doc_version;
            sheetId = created.sheet.id;
          }
          const dims = sheetDimensions(sizeValue, "landscape");
          await createView(drawingId, sheetId, {
            projection: "section",
            ref_document_id: selectedPartId,
            ref_document_kind: "part",
            scale: scaleFromValue(scaleValue),
            position: { x_mm: dims.width / 2, y_mm: dims.height / 2 },
            section_params: { plane, flip },
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
      selectedPartId,
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

  // Append a new (empty) sheet and switch to it (FINDINGS #18). The new sheet is
  // laid out through the SAME flow the first sheet uses — selecting it makes the
  // Set-up band + layout actions target its id (createView takes the sheet id, so
  // no per-index guesswork). Appends at the tip → its index is the old count.
  const [addingSheet, setAddingSheet] = useState(false);
  const handleAddSheet = useCallback(() => {
    if (addingSheet || sheetCount === 0) return;
    setAddingSheet(true);
    setActionError(null);
    void (async () => {
      try {
        await createSheet(drawingId, {
          name: `Sheet ${sheetCount + 1}`,
          size: sizeValue,
          orientation: "landscape",
          projection: "third_angle",
          expected_version: docVersion,
        });
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
  }, [addingSheet, sheetCount, drawingId, sizeValue, docVersion, queryClient]);

  const handleReproject = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: ["drawing-part-tree", effectivePartId],
    });
    void queryClient.invalidateQueries({ queryKey: ["drawing-eval"] });
    // Re-compose the placed sheet too (the VISUAL source) so a reproject repaints.
    void queryClient.invalidateQueries({ queryKey: ["drawing-sheet"] });
  }, [queryClient, effectivePartId]);

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
          const { blob, filename } = await exportDrawing(drawingId, format);
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
    [hasLayout, exporting, drawingId],
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
  // one pick; angular takes two straight edges and point-to-point two endpoints,
  // staged through the pure `authoring` state machine (design §3.1/§3.3).
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

  const handlePickEdge = useCallback((event: EdgePickEvent) => {
    setAuthoring((state) =>
      pickEdge(state, {
        projection: event.projection,
        viewId: event.viewId,
        sourceEdge: event.sourceEdge,
        primitive: event.primitive,
        clientX: event.clientX,
        clientY: event.clientY,
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
      }),
    );
  }, []);

  const handleChooseAction = useCallback(
    (action: DimensionAction) => {
      if (dimBusy) return;
      // "Angle" arms a second-edge pick rather than authoring immediately.
      if (action === "start_angular") {
        setAuthoring((state) => armAngular(state));
        return;
      }
      const built = buildDimension(authoring, action);
      if (built === null) return;
      setDimBusy(true);
      setActionError(null);
      void (async () => {
        try {
          await createDimension(drawingId, built.viewId, {
            dimension: built.params,
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
    [authoring, dimBusy, drawingId, docVersion, queryClient],
  );

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
        setAuthoring(IDLE);
        setSectionOpen(false);
        return;
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
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

  const draftedPartName =
    parts.find((part) => part.id === draftedPartId)?.name ?? null;

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
            parts={parts}
            selectedPartId={selectedPartId}
            onSelectPart={setSelectedPartId}
            scaleValue={effectiveScaleValue}
            onSelectScale={setScaleValue}
            sizeValue={effectiveSize}
            onSelectSize={setSizeValue}
            hasLayout={hasLayout}
            isFlatPattern={isFlatPatternSheet}
            draftedPartName={draftedPartName}
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
          <div className="absolute inset-0 flex items-center justify-center p-6 sm:p-10 lg:pr-[22rem]">
            <DrawingSheet
              svgRef={sheetSvgRef}
              composed={composed}
              views={views}
              resultByProjection={resultByProjection}
              selectedEdgeKey={selectedEdgeKey}
              armedEdgeKeys={armedEdgeKeys}
              selectedVertexKeys={selectedVertexKeys}
              endpointPickActive={endpointPickActive}
              onPickEdge={handlePickEdge}
              onPickEndpoint={handlePickEndpoint}
            />
          </div>
        ) : hasLayout && sheet && !isComposableSheet ? (
          // A laid-out SECONDARY sheet: its views/dimensions/notes are managed in
          // the right gutter, but v1 compose/export render the first sheet only
          // (gateway limitation), so the paper preview lives on Sheet 1.
          <CenterNote
            testId="drawing-secondary-sheet"
            tone="quiet"
            title={`${sheet.name} · laid out`}
            body="This sheet's views, dimensions and notes are managed in the panel at right. Printable preview and PDF/DXF export compose the first sheet in this version."
          />
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
          <SetupHint hasParts={parts.length > 0} />
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
              />
              <BendSchedulePanel
                rows={resultByProjection.get("flat_pattern")?.bend_table ?? []}
              />
              <DimensionsPanel
                dimensions={dimensions}
                measuredById={measuredById}
                busy={dimBusy}
                onDelete={handleDeleteDimension}
              />
              <NotesPanel
                annotations={annotations}
                busy={noteBusy}
                onAdd={handleAddNote}
                onDelete={handleDeleteNote}
              />
            </div>
          </FloatingPanel>
        ) : null}

        {/* A "pick the second …" hint while a two-pick dimension is in progress
            (angular / point-to-point). Non-modal so the sheet stays live for the
            second pick; Esc cancels. */}
        {hint ? (
          <div
            role="status"
            data-testid="dimension-pick-hint"
            className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 border border-brass/60 bg-anvil px-3 py-1.5 shadow-float"
          >
            <span className="font-display text-2xs uppercase tracking-[0.16em] text-brass">
              {hint}
            </span>
            <span className="ml-2 font-body text-2xs text-gauge">
              Esc to cancel
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
 * The sheet switcher (FINDINGS #18) — a compact tab strip that moves between the
 * drawing's sheets and appends a new one. A quiet precision instrument in the
 * top-left margin so the sheet stays the hero: brass underline on the active tab,
 * keyboard-first (roving tablist), all wired to real state/actions (mandate 3a).
 */
function SheetTabs({
  sheets,
  activeIndex,
  onSelect,
  onAdd,
  adding,
}: {
  sheets: readonly SheetContent[];
  activeIndex: number;
  onSelect: (index: number) => void;
  onAdd: () => void;
  adding: boolean;
}) {
  return (
    <div
      className="absolute left-3 top-3 z-overlay flex items-center gap-1 border border-hairline bg-anvil/95 px-1.5 py-1 shadow-float backdrop-blur-sm"
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
            className={`border-b-2 px-2.5 py-1 font-display text-2xs uppercase tracking-[0.14em] transition-colors duration-fast focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass ${
              active
                ? "border-brass text-mist"
                : "border-transparent text-gauge hover:text-mist"
            }`}
          >
            {content.sheet.name}
          </button>
        );
      })}
      <button
        type="button"
        onClick={onAdd}
        disabled={adding}
        data-testid="sheet-tab-add"
        aria-label="Add sheet"
        className="ml-0.5 shrink-0 rounded-sm px-1.5 py-1 font-display text-xs leading-none text-gauge transition-colors duration-fast hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40"
      >
        {adding ? "…" : "+"}
      </button>
    </div>
  );
}

/** The empty-bench invitation before any views are laid out. */
function SetupHint({ hasParts }: { hasParts: boolean }) {
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
}: {
  projecting: boolean;
  projections: readonly ViewProjection[];
  resultByProjection: Map<ViewProjection, DrawingViewResult>;
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
          const failed = Boolean(result?.error);
          const count = result?.edges?.length ?? 0;
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
 */
function DimensionsPanel({
  dimensions,
  measuredById,
  busy,
  onDelete,
}: {
  dimensions: readonly DimensionResponse[];
  measuredById: Map<string, MeasuredDimension>;
  busy: boolean;
  onDelete: (dimensionId: string) => void;
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
          a diameter or radius, a straight edge a linear.
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
              return (
                <li
                  key={dim.id}
                  className="flex items-center gap-2 px-3 py-1.5"
                  data-testid="dimension-row"
                  data-dimension-type={dim.dimension.type}
                  data-foreshortened={foreshortened ? "true" : "false"}
                >
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
        </>
      )}
    </div>
  );
}
