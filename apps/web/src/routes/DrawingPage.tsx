import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  type DimensionResponse,
  type DrawingDimensionInput,
  type DrawingViewResult,
  type EvaluateDrawingViewsRequest,
  type MeasuredDimension,
  type ViewProjection,
  createDimension,
  createSheet,
  createView,
  deleteDimension,
  evaluateDrawingViews,
  fetchDrawing,
} from "../api/drawings";
import { fetchFeatureTree, fetchParts } from "../api/parts";
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
import { formatDimensionLabel } from "../drawing/dimensions";
import { exportSheetSvg } from "../drawing/exportSvg";
import {
  SCALE_OPTIONS,
  STANDARD_VIEWS,
  VIEW_LABEL,
  sheetDimensions,
  standardLayout,
} from "../drawing/layout";
import { isTypingTarget } from "../lib/isTypingTarget";
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
  const sheet = tree?.sheets[0]?.sheet ?? null;
  const views = useMemo(() => tree?.sheets[0]?.views ?? [], [tree]);
  const dimensions = useMemo<readonly DimensionResponse[]>(
    () => tree?.sheets[0]?.dimensions ?? [],
    [tree],
  );
  const hasLayout = sheet !== null && views.length > 0;

  // view id → its projection, and dimensions grouped by the view they annotate.
  const projectionByViewId = useMemo(() => {
    const map = new Map<string, ViewProjection>();
    for (const view of views) map.set(view.id, view.projection);
    return map;
  }, [views]);
  const dimensionsByView = useMemo(() => {
    const map = new Map<ViewProjection, DimensionResponse[]>();
    for (const dim of dimensions) {
      const projection = projectionByViewId.get(dim.view_id);
      if (!projection) continue;
      const list = map.get(projection) ?? [];
      list.push(dim);
      map.set(projection, list);
    }
    return map;
  }, [dimensions, projectionByViewId]);
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

  // Pre-layout picker state (which part to draft, at what scale).
  const [selectedPartId, setSelectedPartId] = useState<string | null>(null);
  const [scaleValue, setScaleValue] = useState("1:1");
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
        views: [...STANDARD_VIEWS],
        features: t.features
          .filter((feature) => !feature.rolled_back)
          .map((feature) => ({ id: feature.id, feature: feature.feature })),
        dimensions: dimensionInputs,
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

  // ---------------------------------------------------------------------
  // The auto-layout action: create the sheet (if needed) + the four views,
  // threading the optimistic-concurrency version through each write.
  // ---------------------------------------------------------------------
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

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
            size: "A4",
            orientation: "landscape",
            projection: "third_angle",
            expected_version: version,
          });
          version = created.doc_version;
          sheetId = created.sheet.id;
        }
        const dims = sheetDimensions("A4", "landscape");
        const anchors = standardLayout(dims);
        const scale = scaleFromValue(scaleValue);
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
    queryClient,
  ]);

  const handleReproject = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: ["drawing-part-tree", effectivePartId],
    });
    void queryClient.invalidateQueries({ queryKey: ["drawing-eval"] });
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

  // Keyboard-first: L lays out (or re-projects once laid out).
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setAuthoring(IDLE);
        return;
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      if (event.key.toLowerCase() === "l") {
        event.preventDefault();
        if (hasLayout) handleReproject();
        else handleLayout();
      }
      // E exports the laid-out sheet to a .svg (keyboard-first, mirrors the
      // command band's Export SVG action). No-op before layout.
      if (event.key.toLowerCase() === "e" && hasLayout) {
        event.preventDefault();
        handleExportSvg();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hasLayout, handleLayout, handleReproject, handleExportSvg]);

  const draftedPartName =
    parts.find((part) => part.id === draftedPartId)?.name ?? null;

  const projecting = evalQuery.isFetching || partTreeQuery.isFetching;

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
            hasLayout={hasLayout}
            draftedPartName={draftedPartName}
            onLayout={handleLayout}
            onReproject={handleReproject}
            onExportSvg={handleExportSvg}
            busy={busy || projecting}
          />
        ) : null}
      </TopToolbar>

      <main className="relative min-h-0 grow overflow-hidden bg-carbide">
        {/* The bench under the sheet — same grid the viewport + registers use. */}
        <div
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_38%,theme(colors.anvil),theme(colors.carbide)_72%)]"
          aria-hidden="true"
        />

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
        ) : hasLayout && sheet ? (
          // Reserve the right gutter for the Views panel so the paper never
          // slides under it (the panel would clip the sheet's framed corner).
          <div className="absolute inset-0 flex items-center justify-center p-6 sm:p-10 lg:pr-[22rem]">
            <DrawingSheet
              svgRef={sheetSvgRef}
              sheet={sheet}
              views={views}
              resultByProjection={resultByProjection}
              title={tree.drawing.name}
              dimensionsByView={dimensionsByView}
              measuredById={measuredById}
              selectedEdgeKey={selectedEdgeKey}
              armedEdgeKeys={armedEdgeKeys}
              selectedVertexKeys={selectedVertexKeys}
              endpointPickActive={endpointPickActive}
              onPickEdge={handlePickEdge}
              onPickEndpoint={handlePickEndpoint}
            />
          </div>
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
                resultByProjection={resultByProjection}
              />
              <DimensionsPanel
                dimensions={dimensions}
                measuredById={measuredById}
                busy={dimBusy}
                onDelete={handleDeleteDimension}
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
              className="fixed inset-0 z-40"
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
            ? "Choose a part and scale above, then lay out the standard views — front, top, right and isometric drop onto the sheet."
            : "A drawing projects a part. Model a part, then return to draft it."}
        </p>
      </div>
    </div>
  );
}

/** The right-hand "Views" panel — a functional legend + per-view line count. */
function ViewsPanel({
  projecting,
  resultByProjection,
}: {
  projecting: boolean;
  resultByProjection: Map<ViewProjection, DrawingViewResult>;
}) {
  return (
    <div className="border border-hairline bg-anvil">
      <header className="flex items-baseline gap-2 border-b border-hairline px-3 py-2">
        <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Standard views
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
        {STANDARD_VIEWS.map((projection) => {
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
          <span className="font-body text-2xs text-gauge">Visible edge</span>
        </div>
        <div className="flex items-center gap-2 py-0.5">
          <svg width="26" height="6" aria-hidden="true">
            <line
              x1="0"
              y1="3"
              x2="26"
              y2="3"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeDasharray="4 3"
              className="text-gauge"
            />
          </svg>
          <span className="font-body text-2xs text-gauge">Hidden edge</span>
        </div>
      </div>
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
