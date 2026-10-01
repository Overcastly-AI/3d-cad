/**
 * Everything the drawing page READS: the drawing tree and its active sheet,
 * the source picker, the drafted part's tree, the orientation proposal, the
 * evaluate (pick provenance) + compose (placement) queries and the parts
 * list. Split out of `DrawingPage.tsx` (SPLIT-DRAWINGPAGE); behaviour
 * unchanged.
 */
import { type QueryClient, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  type AnnotationResponse,
  type ComposedView,
  type DimensionResponse,
  type DrawingDimensionInput,
  type DrawingViewResult,
  type EvaluateDrawingViewsRequest,
  type MeasuredDimension,
  type RefDocumentKind,
  type SectionViewParams,
  type SheetSize,
  type ViewProjection,
  composeDrawingSheet,
  evaluateDrawingViews,
  fetchDrawing,
  fetchDrawingBom,
} from "../../api/drawings";
import { fetchFeatureTree, fetchParts } from "../../api/parts";
import { fetchAssemblies } from "../../api/assemblies";
import {
  STANDARD_VIEWS,
  type OrientationFit,
  proposeOrientation,
} from "../../drawing/layout";
import { drawingSourceKind, drawingSourceOptions } from "../../drawing/source";
import { drawingRoute } from "../../router";
import {
  type SheetOrientation,
  scaleFromValue,
  sourceExtentsQueryOptions,
} from "./sheetHeader";

/** The drawing page's reads, keyed by the drawing in the route. */
export function useDrawingData(drawingId: string) {
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

  return {
    drawingQuery,
    tree,
    docVersion,
    sheetCount,
    setActiveSheetIndex,
    activeIndex,
    sheet,
    activeSheetId,
    views,
    requestedViews,
    isFlatPatternSheet,
    dimensions,
    annotations,
    hasLayout,
    draftedSourceId,
    parts,
    sources,
    selectedSourceId,
    setSelectedSourceId,
    scaleValue,
    setScaleValue,
    sizeValue,
    setSizeValue,
    selectedSourceKind,
    effectiveSourceKind,
    effectivePartId,
    effectiveScaleValue,
    effectiveSize,
    partTreeQuery,
    partTree,
    orientationFit,
    orientationOverride,
    setOrientationOverride,
    paperOrientation,
    paperScale,
    evalQuery,
    evaluation,
    resultByProjection,
    measuredById,
    sheetQuery,
    composed,
    composedByProjection,
    bomQuery,
  };
}

/** The page's read model, as the action hooks receive it. */
export type DrawingData = ReturnType<typeof useDrawingData>;

/** What every write on the page needs: the drawing, the cache, the one error banner. */
export interface DrawingActionContext {
  drawingId: string;
  queryClient: QueryClient;
  setActionError: (message: string | null) => void;
}
