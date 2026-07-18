/**
 * The drawing sheet — THE signature surface of the Drawings pillar: a leaf of
 * cool drafting paper laid on the blued-steel bench, the one inversion in an
 * otherwise all-dark product (design mandate: spend boldness in one place). It
 * renders in a SINGLE SVG coordinate system (millimetres, so the print is
 * scale-correct) reading stroke colours + weights straight from the `drawing`
 * design tokens — one palette, two renderers (DOM + this SVG).
 *
 * DE-1c cutover: the sheet now renders a server-composed {@link ComposedSheet} —
 * placed edges, dimensions, and the title block whose coordinates are ALREADY in
 * final sheet-mm SVG space (y-flip applied server-side, the single placement
 * source). The browser no longer computes any layout/transform. It stays a
 * DIMENSIONING surface: interaction (hover/focus/select + endpoint handles) is
 * driven from the neutral `ProjectedViewEdge` PICK list fetched from
 * `/geometry/drawing/evaluate`, whose provenance (source edge / dimensionable /
 * endpoint correspondence) is aligned to the composed geometry by CANONICAL EDGE
 * ORDER (compose + evaluate share it per view). Each authored dimension is drawn
 * as a proper drafting annotation from the composed model; it stays honest about
 * a per-view projection failure and a per-dimension measure error.
 */
import { useState, type Ref } from "react";

import { drawing, font, viewport } from "@loft/design";

import type {
  ComposedDimension,
  ComposedEdge,
  ComposedSheet,
  ComposedTitleBlock,
  ComposedView,
  DimensionParams,
  DrawingViewResult,
  EdgeSignature,
  ProjectedViewEdge,
  ViewProjection,
  ViewResponse,
} from "../api/drawings";
import { edgeSignatureKey } from "../drawing/dimensions";
import {
  VIEW_LABEL,
  endpointHandlesForEdge,
  type Point2D,
  type SvgEdge,
} from "../drawing/layout";

/** A pick on a dimensionable projected edge — the seed of an authored dimension. */
export interface EdgePickEvent {
  projection: ViewProjection;
  viewId: string;
  /** The MODEL edge the dimension will name (design §3.3). */
  sourceEdge: EdgeSignature;
  /** The projected primitive — gates the valid dimension types. */
  primitive: ProjectedViewEdge["primitive"];
  /** Pointer position (viewport px) so the author menu opens by the edge. */
  clientX: number;
  clientY: number;
}

/** A pick on a straight edge's endpoint handle — the seed of a point-to-point
 * dimension (design §3.3 names a vertex THROUGH an edge + a canonical end). */
export interface EndpointPickEvent {
  projection: ViewProjection;
  viewId: string;
  /** The MODEL edge whose endpoint this is. */
  sourceEdge: EdgeSignature;
  /** Which canonical end of that edge (end_a / end_b). */
  endpoint: "end_a" | "end_b";
  clientX: number;
  clientY: number;
}

/** A stable key for a projected edge — `projection:signature`. */
export function edgeKey(
  projection: ViewProjection,
  sig: EdgeSignature,
): string {
  return `${projection}:${edgeSignatureKey(sig)}`;
}

/** A stable key for an edge endpoint — `projection:signature:end_a|end_b`. */
export function vertexKey(
  projection: ViewProjection,
  sig: EdgeSignature,
  endpoint: "end_a" | "end_b",
): string {
  return `${edgeKey(projection, sig)}:${endpoint}`;
}

export interface DrawingSheetProps {
  /** The server-composed sheet — the single placement source (DE-1c). */
  composed: ComposedSheet;
  /** The stored views — projection → view id, for pick-event routing. */
  views: readonly ViewResponse[];
  /**
   * Per-projection projection outcome from `/geometry/drawing/evaluate` — the
   * neutral PICK list (source edge / dimensionable / endpoint correspondence),
   * aligned to the composed geometry by canonical edge order.
   */
  resultByProjection: Map<ViewProjection, DrawingViewResult>;
  /** The currently-selected pickable edge (`edgeKey`), highlighted for authoring. */
  selectedEdgeKey?: string | null;
  /** Keys (`edgeKey`) of edges armed in a multi-pick (angular's first edge). */
  armedEdgeKeys?: readonly string[];
  /** Keys (`vertexKey`) of endpoint handles selected in a point-to-point pick. */
  selectedVertexKeys?: readonly string[];
  /** A point-to-point pick is armed — reveal ALL endpoint handles (and make them
   * tabbable) so the second vertex is reachable even on an un-hovered edge. */
  endpointPickActive?: boolean;
  /** Fired when a dimensionable edge is picked (click or keyboard). */
  onPickEdge?: (event: EdgePickEvent) => void;
  /** Fired when a straight edge's endpoint handle is picked (point-to-point). */
  onPickEndpoint?: (event: EndpointPickEvent) => void;
  /** Handle on the root `<svg>` so the editor can serialize it to a file (#5). */
  svgRef?: Ref<SVGSVGElement>;
}

/** Stroke props for a visible (solid) or hidden (dashed) projected edge. */
function strokeFor(visible: boolean) {
  return visible
    ? { stroke: drawing.edgeVisible, strokeWidth: drawing.visibleWeightMm }
    : {
        stroke: drawing.edgeHidden,
        strokeWidth: drawing.hiddenWeightMm,
        strokeDasharray: `${drawing.hiddenDashMm} ${drawing.hiddenGapMm}`,
      };
}

/**
 * The pick provenance carried alongside a composed primitive so the sheet can
 * make a dimensionable edge interactive: it comes from the ALIGNED evaluate
 * `ProjectedViewEdge` (same canonical order), never re-derived from geometry.
 */
function pickInfo(
  evalEdge: ProjectedViewEdge | undefined,
  kind: ComposedEdge["kind"],
) {
  const fallback: ProjectedViewEdge["primitive"] =
    kind === "circle" ? "circle" : kind === "line" ? "line" : "polyline";
  return {
    dimensionable: evalEdge?.dimensionable ?? false,
    sourceEdge: evalEdge?.source_edge ?? null,
    edgePrimitive: evalEdge?.primitive ?? fallback,
  };
}

/**
 * A composed placed edge (final SVG space) fused with its aligned evaluate
 * provenance → the `SvgEdge` the interactive layer draws + hit-tests. The
 * geometry is drawn VERBATIM; only the pick metadata comes from `evalEdge`.
 */
function toSvgEdge(
  composed: ComposedEdge,
  evalEdge: ProjectedViewEdge | undefined,
): SvgEdge {
  const info = pickInfo(evalEdge, composed.kind);
  if (composed.kind === "line") {
    return {
      kind: "line",
      x1: composed.x1,
      y1: composed.y1,
      x2: composed.x2,
      y2: composed.y2,
      visible: composed.visible,
      ...info,
    };
  }
  if (composed.kind === "circle") {
    return {
      kind: "circle",
      cx: composed.cx,
      cy: composed.cy,
      r: composed.r,
      visible: composed.visible,
      ...info,
    };
  }
  return {
    kind: "polyline",
    points: composed.points.map((p) => ({ x: p.x_mm, y: p.y_mm })),
    visible: composed.visible,
    ...info,
  };
}

/** Render one SVG primitive for `edge` with the given stroke props. */
function edgePrimitive(
  edge: SvgEdge,
  props: Record<string, unknown>,
  key?: string,
) {
  if (edge.kind === "line") {
    return (
      <line
        key={key}
        x1={edge.x1}
        y1={edge.y1}
        x2={edge.x2}
        y2={edge.y2}
        {...props}
      />
    );
  }
  if (edge.kind === "circle") {
    return <circle key={key} cx={edge.cx} cy={edge.cy} r={edge.r} {...props} />;
  }
  return (
    <polyline
      key={key}
      points={edge.points.map((p) => `${p.x},${p.y}`).join(" ")}
      {...props}
    />
  );
}

function EdgeShape({
  edge,
  hover,
  focus,
  selected,
}: {
  edge: SvgEdge;
  hover: boolean;
  focus: boolean;
  selected: boolean;
}) {
  // Keyboard focus MUST read differently from mouse hover (WCAG 2.4.7): hover
  // recolors the edge blueprint-blue; focus adds a deep-blue RING under it (a
  // distinct shape, not a colour-only cue) and brightens the core.
  const coreColor = selected
    ? drawing.pickSelected
    : focus || hover
      ? drawing.pickHover
      : null;
  const stroke = coreColor
    ? { stroke: coreColor, strokeWidth: 0.8 }
    : strokeFor(edge.visible);
  const common = {
    ...stroke,
    fill: "none" as const,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "data-edge": edge.kind,
    "data-visible": edge.visible ? "true" : "false",
    "data-dimensionable": edge.dimensionable ? "true" : "false",
    "data-focused": focus ? "true" : "false",
  };
  return (
    <>
      {focus
        ? edgePrimitive(
            edge,
            {
              stroke: drawing.pickSelected,
              strokeWidth: drawing.pickFocusRingMm,
              fill: "none",
              strokeLinecap: "round",
              strokeLinejoin: "round",
              opacity: 0.5,
              "data-testid": "drawing-edge-focus-ring",
            },
            "ring",
          )
        : null}
      {edgePrimitive(edge, common, "core")}
    </>
  );
}

/** A transparent, generously-wide hit region over one shape. */
function HitShape({ edge }: { edge: SvgEdge }) {
  const stroke = {
    stroke: "transparent",
    strokeWidth: drawing.pickHitMm,
    fill: "none" as const,
    pointerEvents: "stroke" as const,
  };
  if (edge.kind === "line") {
    return (
      <line x1={edge.x1} y1={edge.y1} x2={edge.x2} y2={edge.y2} {...stroke} />
    );
  }
  if (edge.kind === "circle") {
    // A hole reads as a target — the whole disc is pickable (`all` captures the
    // transparent interior too), so clicking the hole dimensions it.
    return (
      <circle
        cx={edge.cx}
        cy={edge.cy}
        r={edge.r}
        fill="transparent"
        pointerEvents="all"
      />
    );
  }
  return (
    <polyline
      points={edge.points.map((p) => `${p.x},${p.y}`).join(" ")}
      {...stroke}
    />
  );
}

/** One projected edge — solid/dashed, and interactive when dimensionable.
 * Hover/focus of a dimensionable straight edge REVEALS its endpoint handles
 * (via `onReveal`, keyed on the edge) — the Fusion/Plasticity proximity idiom,
 * so the sheet stays uncluttered until the vertex snap is actually wanted. */
function PickableEdge({
  edge,
  projection,
  viewId,
  selected,
  onReveal,
  onPickEdge,
}: {
  edge: SvgEdge;
  projection: ViewProjection;
  viewId: string | null;
  selected: boolean;
  /** Report this edge as the reveal target on hover/focus (null clears on leave). */
  onReveal?: (key: string | null) => void;
  onPickEdge?: (event: EdgePickEvent) => void;
}) {
  const [hover, setHover] = useState(false);
  const [focus, setFocus] = useState(false);
  const interactive =
    edge.dimensionable &&
    edge.sourceEdge !== null &&
    viewId !== null &&
    onPickEdge !== undefined;

  if (!interactive)
    return (
      <EdgeShape edge={edge} hover={false} focus={false} selected={selected} />
    );

  const revealKey =
    edge.sourceEdge !== null ? edgeKey(projection, edge.sourceEdge) : null;
  const fire = (clientX: number, clientY: number) => {
    if (edge.sourceEdge === null || viewId === null) return;
    onPickEdge?.({
      projection,
      viewId,
      sourceEdge: edge.sourceEdge,
      primitive: edge.edgePrimitive,
      clientX,
      clientY,
    });
  };

  return (
    <g>
      <EdgeShape edge={edge} hover={hover} focus={focus} selected={selected} />
      <g
        role="button"
        tabIndex={0}
        aria-label={`Dimension this ${edge.edgePrimitive} edge in the ${VIEW_LABEL[projection]} view`}
        data-testid="drawing-pick-edge"
        data-view={projection}
        data-primitive={edge.edgePrimitive}
        data-selected={selected ? "true" : "false"}
        data-focused={focus ? "true" : "false"}
        // A custom SVG focus ring (in `EdgeShape`) is the visible focus
        // affordance, so the default box outline on this hit-group is suppressed.
        style={{ cursor: "pointer", outline: "none" }}
        onMouseEnter={() => {
          setHover(true);
          onReveal?.(revealKey);
        }}
        onMouseLeave={() => {
          setHover(false);
          onReveal?.(null);
        }}
        onFocus={() => {
          setFocus(true);
          // Focus latches the reveal (no clear on blur) so a keyboard user can
          // tab onward and still reach the now-revealed endpoint handles.
          onReveal?.(revealKey);
        }}
        onBlur={() => setFocus(false)}
        onClick={(event) => fire(event.clientX, event.clientY)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            const rect = event.currentTarget.getBoundingClientRect();
            fire(rect.left + rect.width / 2, rect.top + rect.height / 2);
          }
        }}
      >
        <HitShape edge={edge} />
      </g>
    </g>
  );
}

/** One endpoint handle on a straight edge — the vertex pick for point-to-point.
 * It is NOT a persistent stamp: the drawn square + its tab stop only appear once
 * `revealed` (the edge is hovered/focused, the pick is armed, or the handle
 * itself is engaged). The transparent hit target is always present so a mouse
 * (or a forced e2e click) can pick the vertex the moment it is approached. */
function VertexHandle({
  at,
  projection,
  viewId,
  sourceEdge,
  endpoint,
  selected,
  revealed,
  onPickEndpoint,
}: {
  at: Point2D;
  projection: ViewProjection;
  viewId: string;
  sourceEdge: EdgeSignature;
  endpoint: "end_a" | "end_b";
  selected: boolean;
  /** Reveal the drawn handle + admit it to the tab order (edge hover/focus or
   * an armed point-to-point pick) — otherwise it stays out of both. */
  revealed: boolean;
  onPickEndpoint: (event: EndpointPickEvent) => void;
}) {
  const [hover, setHover] = useState(false);
  const [focus, setFocus] = useState(false);
  const half = drawing.vertexHandleMm;
  // Hover recolors the square; focus adds a distinct deep-blue RING (a shape
  // cue, not a colour-only change) so keyboard focus reads differently from
  // mouse hover (WCAG 2.4.7) — the same seam `EdgeShape` uses (`pickFocusRingMm`).
  const emphasized = hover || focus || selected;
  // Drawn (and tabbable) when revealed by context or engaged directly. Its own
  // hover reveals it (mouse proximity) but adds no tab stop; keyboard reach is
  // gated on the contextual reveal / selection only.
  const drawn = revealed || hover || focus || selected;
  const tabbable = revealed || selected;
  const fire = (clientX: number, clientY: number) =>
    onPickEndpoint({
      projection,
      viewId,
      sourceEdge,
      endpoint,
      clientX,
      clientY,
    });
  return (
    <g
      role="button"
      tabIndex={tabbable ? 0 : -1}
      aria-hidden={tabbable ? undefined : true}
      aria-label={`Dimension from this vertex in the ${VIEW_LABEL[projection]} view`}
      data-testid="drawing-pick-vertex"
      data-view={projection}
      data-endpoint={endpoint}
      data-selected={selected ? "true" : "false"}
      data-revealed={drawn ? "true" : "false"}
      style={{ cursor: "pointer", outline: "none" }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocus={() => setFocus(true)}
      onBlur={() => setFocus(false)}
      onClick={(event) => fire(event.clientX, event.clientY)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          const rect = event.currentTarget.getBoundingClientRect();
          fire(rect.left + rect.width / 2, rect.top + rect.height / 2);
        }
      }}
    >
      {/* Generous transparent hit target — always present so the vertex stays
          pickable (and force-clickable in tests) even before it is revealed. */}
      <rect
        x={at.x - drawing.pickHitMm}
        y={at.y - drawing.pickHitMm}
        width={drawing.pickHitMm * 2}
        height={drawing.pickHitMm * 2}
        fill="transparent"
      />
      {drawn ? (
        <>
          {focus ? (
            <rect
              data-testid="drawing-vertex-focus-ring"
              x={at.x - half}
              y={at.y - half}
              width={half * 2}
              height={half * 2}
              fill="none"
              stroke={drawing.pickSelected}
              strokeWidth={drawing.pickFocusRingMm}
              opacity={0.5}
            />
          ) : null}
          <rect
            x={at.x - half}
            y={at.y - half}
            width={half * 2}
            height={half * 2}
            fill={emphasized ? drawing.pickSelected : drawing.paper}
            stroke={
              emphasized ? drawing.pickSelected : drawing.vertexHandleRest
            }
            strokeWidth={emphasized ? 0.6 : 0.4}
          />
        </>
      ) : null}
    </g>
  );
}

/** The three vertices of a composed arrowhead as an SVG `points` string. */
function arrowPoints(arrow: {
  points: readonly { x_mm: number; y_mm: number }[];
}): string {
  return arrow.points.map((p) => `${p.x_mm},${p.y_mm}`).join(" ");
}

/** A placed dimension — extension + dimension lines, arrowheads, value stamp.
 * Drawn VERBATIM from the composed model (coordinates are final SVG space). */
function DimensionGlyph({ dim }: { dim: ComposedDimension }) {
  const dimensionType: DimensionParams["type"] = dim.dimension_type;
  const dimensionId = dim.dimension_id ?? undefined;
  if (dim.kind === "error") {
    const { at, code } = dim;
    return (
      <g
        data-testid="drawing-dimension"
        data-dimension-id={dimensionId}
        data-dimension-type={dimensionType}
        data-dimension-error={code}
      >
        <title>Dimension could not be measured ({code})</title>
        <circle
          cx={at.x_mm}
          cy={at.y_mm}
          r={2.6}
          fill="none"
          stroke={drawing.dimensionFlag}
          strokeWidth={drawing.dimensionWeightMm}
          strokeDasharray="1 1"
        />
        <text
          x={at.x_mm}
          y={at.y_mm}
          textAnchor="middle"
          dominantBaseline="central"
          fill={drawing.dimensionFlag}
          fontFamily={font.data}
          fontSize={3}
        >
          !
        </text>
      </g>
    );
  }

  const { lines, arrows, text, foreshortened } = dim;
  // A paper halo behind the value so lines never cross the digits (keeps the
  // AA contrast the vellum gives — text sits on paper, not on a graphite rule).
  const haloW = text.value.length * drawing.dimensionTextMm * 0.62 + 1.8;
  const haloH = drawing.dimensionTextMm + 1.4;
  return (
    <g
      data-testid="drawing-dimension"
      data-dimension-id={dimensionId}
      data-dimension-type={dimensionType}
      data-dimension-value={text.value}
      data-foreshortened={foreshortened ? "true" : "false"}
    >
      <title>
        {foreshortened
          ? `${text.value} — foreshortened; dimension in a true-size view for the drawn length`
          : text.value}
      </title>
      {lines.map((l, i) => (
        <line
          key={i}
          x1={l.x1}
          y1={l.y1}
          x2={l.x2}
          y2={l.y2}
          stroke={drawing.dimensionInk}
          strokeWidth={
            l.role === "extension"
              ? drawing.extensionWeightMm
              : drawing.dimensionWeightMm
          }
          strokeLinecap="round"
        />
      ))}
      {arrows.map((arrow, i) => (
        <polygon
          key={i}
          points={arrowPoints(arrow)}
          fill={drawing.dimensionInk}
        />
      ))}
      <g transform={`rotate(${text.angle} ${text.x} ${text.y})`}>
        <rect
          x={text.x - haloW / 2}
          y={text.y - haloH / 2}
          width={haloW}
          height={haloH}
          fill={drawing.paper}
          opacity={0.92}
        />
        <text
          data-testid="drawing-dimension-value"
          x={text.x}
          y={text.y}
          textAnchor="middle"
          dominantBaseline="central"
          fill={foreshortened ? drawing.dimensionFlag : drawing.dimensionText}
          fontFamily={font.data}
          fontSize={drawing.dimensionTextMm}
          letterSpacing={0.1}
        >
          {text.value}
        </text>
      </g>
    </g>
  );
}

/** A pickable vertex handle resolved to final SVG space + its canonical label. */
interface VertexHandleSpec {
  key: string;
  at: Point2D;
  posKey: string;
  sourceEdge: EdgeSignature;
  endpoint: "end_a" | "end_b";
}

/** One placed view: its composed edges + dimensions + caption, or a failure.
 * The VISUAL is the composed model; the interactive layer is the aligned
 * evaluate PICK list (same canonical edge order). */
function SheetView({
  composedView,
  result,
  viewId,
  selectedEdgeKey,
  armedEdgeKeys,
  selectedVertexKeys,
  endpointPickActive,
  onPickEdge,
  onPickEndpoint,
}: {
  composedView: ComposedView;
  /** The aligned evaluate result for this view (pick provenance), or undefined. */
  result: DrawingViewResult | undefined;
  viewId: string | null;
  selectedEdgeKey: string | null | undefined;
  armedEdgeKeys: readonly string[];
  selectedVertexKeys: readonly string[];
  /** A point-to-point pick is armed — reveal all endpoint handles. */
  endpointPickActive: boolean;
  onPickEdge?: (event: EdgePickEvent) => void;
  onPickEndpoint?: (event: EndpointPickEvent) => void;
}) {
  const projection = composedView.projection;
  // Which straight edge (by `edgeKey`) currently reveals its endpoint handles —
  // set on that edge's hover/focus, so handles appear on proximity/intent rather
  // than as a persistent stamp on every corner (frontend-QA P2).
  const [revealKey, setRevealKey] = useState<string | null>(null);
  const failed = composedView.failed;
  const composedEdges = composedView.edges ?? [];
  const composedDims = composedView.dimensions ?? [];
  const evalEdges = result?.edges ?? [];

  // Fuse each composed placed edge (VISUAL) with its aligned evaluate edge
  // (PICK provenance) by canonical index — compose + evaluate share the order.
  const svgEdges = composedEdges.map((composed, i) =>
    toSvgEdge(composed, evalEdges[i]),
  );

  // Endpoint handles for every dimensionable straight edge (deduped by position
  // so a shared corner is one handle, not a stack) — the point-to-point pick.
  // Positions come from the COMPOSED line endpoints; the canonical end_a/end_b
  // correspondence from the aligned evaluate edge's `start_is_end_a`.
  const posKeyOf = (p: Point2D): string =>
    `${p.x.toFixed(2)},${p.y.toFixed(2)}`;
  const vertexHandles: VertexHandleSpec[] = [];
  if (onPickEndpoint && viewId !== null && !failed) {
    const seen = new Set<string>();
    for (let i = 0; i < composedEdges.length; i += 1) {
      const composed = composedEdges[i];
      const evalEdge = evalEdges[i];
      if (composed === undefined || composed.kind !== "line" || !evalEdge) {
        continue;
      }
      const handles = endpointHandlesForEdge(evalEdge);
      if (!handles || !evalEdge.source_edge) continue;
      // `endpointHandlesForEdge` returns [start-handle, end-handle]; the composed
      // line preserves start→(x1,y1), end→(x2,y2), so map by that fixed order.
      const positions: Point2D[] = [
        { x: composed.x1, y: composed.y1 },
        { x: composed.x2, y: composed.y2 },
      ];
      for (let h = 0; h < handles.length; h += 1) {
        const at = positions[h];
        const handle = handles[h];
        if (at === undefined || handle === undefined) continue;
        const posKey = posKeyOf(at);
        if (seen.has(posKey)) continue;
        seen.add(posKey);
        vertexHandles.push({
          key: vertexKey(projection, evalEdge.source_edge, handle.endpoint),
          at,
          posKey,
          sourceEdge: evalEdge.source_edge,
          endpoint: handle.endpoint,
        });
      }
    }
  }

  // The endpoint positions of the currently reveal-keyed edge (its hover/focus
  // reveals its own two corners); an armed pick reveals every handle instead.
  const revealedPosKeys = new Set<string>();
  if (revealKey !== null) {
    for (const handle of vertexHandles) {
      if (edgeKey(projection, handle.sourceEdge) === revealKey) {
        revealedPosKeys.add(handle.posKey);
      }
    }
  }

  return (
    <g
      data-testid="drawing-view"
      data-view={projection}
      data-view-error={failed ? "true" : "false"}
      data-edge-count={composedEdges.length}
      data-dimension-count={composedDims.length}
    >
      {failed ? (
        <g>
          <rect
            x={composedView.anchor.x_mm - 26}
            y={composedView.anchor.y_mm - 14}
            width={52}
            height={28}
            fill="none"
            stroke={drawing.edgeHidden}
            strokeWidth={drawing.hiddenWeightMm}
            strokeDasharray={`${drawing.hiddenDashMm} ${drawing.hiddenGapMm}`}
          />
          <text
            x={composedView.anchor.x_mm}
            y={composedView.anchor.y_mm + 1}
            textAnchor="middle"
            fill={drawing.label}
            fontFamily={font.data}
            fontSize={3}
            letterSpacing={0.4}
          >
            VIEW FAILED
          </text>
        </g>
      ) : (
        <>
          {svgEdges.map((edge, i) => {
            const key =
              edge.sourceEdge !== null
                ? edgeKey(projection, edge.sourceEdge)
                : null;
            return (
              <PickableEdge
                key={i}
                edge={edge}
                projection={projection}
                viewId={viewId}
                selected={
                  key !== null &&
                  (key === selectedEdgeKey || armedEdgeKeys.includes(key))
                }
                onReveal={onPickEndpoint ? setRevealKey : undefined}
                onPickEdge={onPickEdge}
              />
            );
          })}
          {composedDims.map((dim, i) => (
            <DimensionGlyph key={dim.dimension_id ?? i} dim={dim} />
          ))}
          {onPickEndpoint && viewId !== null
            ? vertexHandles.map((h) => (
                <VertexHandle
                  key={h.key}
                  at={h.at}
                  projection={projection}
                  viewId={viewId}
                  sourceEdge={h.sourceEdge}
                  endpoint={h.endpoint}
                  selected={selectedVertexKeys.includes(h.key)}
                  revealed={endpointPickActive || revealedPosKeys.has(h.posKey)}
                  onPickEndpoint={onPickEndpoint}
                />
              ))
            : null}
        </>
      )}
      <text
        data-testid="drawing-view-label"
        x={composedView.label_pos.x_mm}
        y={composedView.label_pos.y_mm}
        textAnchor="middle"
        fill={drawing.label}
        fontFamily={font.data}
        fontSize={3.4}
        letterSpacing={0.6}
      >
        {composedView.label}
      </text>
    </g>
  );
}

/** The bottom-right title block — stamped in mono, the drafting vernacular.
 * Geometry + stamped values come from the composed model (server-placed). */
function TitleBlock({ block }: { block: ComposedTitleBlock }) {
  const { x, y, width: w, height: h, split_x: splitX, mid_y: midY } = block;
  const rule = { stroke: drawing.ink, strokeWidth: drawing.hiddenWeightMm };
  const caption = {
    fill: drawing.label,
    fontFamily: font.data,
    fontSize: 2.3,
    letterSpacing: 0.5,
  };
  const value = {
    fill: drawing.ink,
    fontFamily: font.data,
    fontSize: 3.4,
  };
  return (
    <g data-testid="drawing-title-block">
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        fill="none"
        stroke={drawing.ink}
        strokeWidth={drawing.borderWeightMm}
      />
      <line x1={splitX} y1={y} x2={splitX} y2={y + h} {...rule} />
      <line x1={splitX} y1={midY} x2={x + w} y2={midY} {...rule} />
      {/* Left: the drawing title */}
      <text x={x + 4} y={y + 8} {...caption}>
        TITLE
      </text>
      <text data-testid="title-block-name" x={x + 4} y={y + 18} {...value}>
        {block.title}
      </text>
      <text x={x + 4} y={y + h - 4} {...caption}>
        LOFT · PART DRAWING
      </text>
      {/* Right: scale over size */}
      <text x={splitX + 4} y={y + 8} {...caption}>
        SCALE
      </text>
      <text
        data-testid="title-block-scale"
        x={splitX + 4}
        y={midY - 3}
        {...value}
      >
        {block.scale}
      </text>
      <text x={splitX + 4} y={midY + 8} {...caption}>
        SIZE
      </text>
      <text x={splitX + 4} y={y + h - 4} {...value}>
        {block.size}
      </text>
    </g>
  );
}

export function DrawingSheet({
  composed,
  views,
  resultByProjection,
  selectedEdgeKey,
  armedEdgeKeys,
  selectedVertexKeys,
  endpointPickActive,
  onPickEdge,
  onPickEndpoint,
  svgRef,
}: DrawingSheetProps) {
  const width = composed.width_mm;
  const height = composed.height_mm;
  const margin = composed.margin_mm;
  const composedViews = composed.views ?? [];
  const viewIdByProjection = new Map<ViewProjection, string>();
  for (const view of views) viewIdByProjection.set(view.projection, view.id);

  return (
    <svg
      ref={svgRef}
      data-testid="drawing-sheet"
      role="img"
      aria-label={`Drawing sheet — ${composed.title}, ${composedViews.length} views at ${composed.scale_label}`}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      className="h-full w-full"
      // Seat the sheet on the bench — a drop-shadow follows the paper's alpha
      // (the letterbox stays transparent). Colour from the scene abyss token.
      style={{
        filter: `drop-shadow(0 14px 34px ${viewport.atmosphere.abyss}bf)`,
      }}
    >
      {/* Paper — the sheet on the bench. */}
      <rect
        x={0}
        y={0}
        width={width}
        height={height}
        fill={drawing.paper}
        stroke={drawing.paperEdge}
        strokeWidth={0.6}
      />
      {/* Drawn border frame. */}
      <rect
        data-testid="drawing-border"
        x={margin}
        y={margin}
        width={width - 2 * margin}
        height={height - 2 * margin}
        fill="none"
        stroke={drawing.ink}
        strokeWidth={drawing.borderWeightMm}
      />
      {composedViews.map((composedView) => (
        <SheetView
          key={composedView.projection}
          composedView={composedView}
          result={resultByProjection.get(composedView.projection)}
          viewId={viewIdByProjection.get(composedView.projection) ?? null}
          selectedEdgeKey={selectedEdgeKey}
          armedEdgeKeys={armedEdgeKeys ?? []}
          selectedVertexKeys={selectedVertexKeys ?? []}
          endpointPickActive={endpointPickActive ?? false}
          onPickEdge={onPickEdge}
          onPickEndpoint={onPickEndpoint}
        />
      ))}
      <TitleBlock block={composed.title_block} />
    </svg>
  );
}
