/**
 * The drawing sheet — THE signature surface of the Drawings pillar: a leaf of
 * cool drafting paper laid on the blued-steel bench, the one inversion in an
 * otherwise all-dark product (design mandate: spend boldness in one place). It
 * renders in a SINGLE SVG coordinate system (millimetres, so the print is
 * scale-correct) reading stroke colours + weights straight from the `drawing`
 * design tokens — one palette, two renderers (DOM + this SVG).
 *
 * Beyond drawing the projected edges it is now a DIMENSIONING surface (Drawings
 * v1 #6b): a `dimensionable` projected edge is interactive (hover/focus/select
 * in the blueprint-blue pick ink), and each authored dimension is stamped as a
 * proper drafting annotation — extension lines, a dimension line with filled
 * arrowheads, and the MODEL-true value with its prefix (Ø / R / bare). It stays
 * honest about a per-view projection failure and a per-dimension measure error.
 */
import { useState } from "react";

import { drawing, font, viewport } from "@loft/design";

import type {
  DimensionParams,
  DimensionResponse,
  DrawingViewResult,
  EdgeSignature,
  MeasuredDimension,
  ProjectedViewEdge,
  SheetResponse,
  ViewProjection,
  ViewResponse,
} from "../api/drawings";
import {
  buildDimensionAnnotation,
  dimensionEdgeSignature,
  edgeSignatureKey,
  findMatchingEdge,
  type DimensionAnnotation,
} from "../drawing/dimensions";
import {
  SHEET_MARGIN_MM,
  STANDARD_VIEWS,
  TITLE_BLOCK_MM,
  VIEW_LABEL,
  boundsAwareLayout,
  formatScale,
  sheetDimensions,
  viewBounds,
  viewContentSvgRect,
  viewToSvgEdges,
  viewTransform,
  type Anchor,
  type SvgEdge,
  type SvgRect,
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

/** A stable key for a projected edge — `projection:signature`. */
export function edgeKey(
  projection: ViewProjection,
  sig: EdgeSignature,
): string {
  return `${projection}:${edgeSignatureKey(sig)}`;
}

export interface DrawingSheetProps {
  sheet: SheetResponse;
  views: readonly ViewResponse[];
  /** Per-projection projection outcome from `/geometry/drawing/evaluate`. */
  resultByProjection: Map<ViewProjection, DrawingViewResult>;
  /** Title-block title (the drawing name). */
  title: string;
  /** Authored dimensions grouped by the view they annotate. */
  dimensionsByView?: Map<ViewProjection, readonly DimensionResponse[]>;
  /** Model-true measured result per dimension id (from the evaluate response). */
  measuredById?: Map<string, MeasuredDimension>;
  /** The currently-selected pickable edge (`edgeKey`), highlighted for authoring. */
  selectedEdgeKey?: string | null;
  /** Fired when a dimensionable edge is picked (click or keyboard). */
  onPickEdge?: (event: EdgePickEvent) => void;
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

/** One projected edge — solid/dashed, and interactive when dimensionable. */
function PickableEdge({
  edge,
  projection,
  viewId,
  selected,
  onPickEdge,
}: {
  edge: SvgEdge;
  projection: ViewProjection;
  viewId: string | null;
  selected: boolean;
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
        <HitShape edge={edge} />
      </g>
    </g>
  );
}

/** A placed dimension — extension + dimension lines, arrowheads, value stamp. */
function DimensionGlyph({
  annotation,
  dimensionType,
  dimensionId,
}: {
  annotation: DimensionAnnotation;
  dimensionType: DimensionParams["type"];
  dimensionId: string;
}) {
  if (annotation.kind === "error") {
    const { at, code } = annotation;
    return (
      <g
        data-testid="drawing-dimension"
        data-dimension-id={dimensionId}
        data-dimension-type={dimensionType}
        data-dimension-error={code}
      >
        <title>Dimension could not be measured ({code})</title>
        <circle
          cx={at.x}
          cy={at.y}
          r={2.6}
          fill="none"
          stroke={drawing.dimensionFlag}
          strokeWidth={drawing.dimensionWeightMm}
          strokeDasharray="1 1"
        />
        <text
          x={at.x}
          y={at.y}
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

  const { lines, arrows, text, foreshortened } = annotation;
  // A paper halo behind the value so lines never cross the digits (keeps the
  // AA contrast the vellum gives — text sits on paper, not on a graphite rule).
  const haloW = text.label.length * drawing.dimensionTextMm * 0.62 + 1.8;
  const haloH = drawing.dimensionTextMm + 1.4;
  return (
    <g
      data-testid="drawing-dimension"
      data-dimension-id={dimensionId}
      data-dimension-type={dimensionType}
      data-dimension-value={text.label}
      data-foreshortened={foreshortened ? "true" : "false"}
    >
      <title>
        {foreshortened
          ? `${text.label} — foreshortened; dimension in a true-size view for the drawn length`
          : text.label}
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
      {arrows.map((points, i) => (
        <polygon key={i} points={points} fill={drawing.dimensionInk} />
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
          {text.label}
        </text>
      </g>
    </g>
  );
}

/** One placed view: its projected edges + dimensions + caption, or a failure. */
function SheetView({
  projection,
  anchor,
  sheetWidth,
  sheetHeight,
  result,
  viewId,
  dimensions,
  measuredById,
  selectedEdgeKey,
  obstacles,
  onPickEdge,
}: {
  projection: ViewProjection;
  anchor: Anchor;
  sheetWidth: number;
  sheetHeight: number;
  result: DrawingViewResult | undefined;
  viewId: string | null;
  dimensions: readonly DimensionResponse[];
  measuredById: Map<string, MeasuredDimension> | undefined;
  selectedEdgeKey: string | null | undefined;
  /** Sibling views' SVG bounds a dimension on THIS view must not overlap. */
  obstacles: readonly SvgRect[];
  onPickEdge?: (event: EdgePickEvent) => void;
}) {
  const anchorSvgX = anchor.x;
  const anchorSvgY = sheetHeight - anchor.y;
  const edges = result?.edges ?? [];
  const failed = Boolean(result?.error) || result === undefined;
  const bounds = viewBounds(edges);
  const svgEdges = viewToSvgEdges(edges, anchor, sheetHeight);
  // Caption sits below the view's drawn extent (or a fixed drop when empty).
  const belowMm = bounds ? bounds.center.y - bounds.min.y : 0;
  const labelY = anchorSvgY + belowMm + 8;

  // Resolve each authored dimension to a drafting annotation on this view.
  const toSvg = viewTransform(edges, anchor, sheetHeight);
  const viewCenter = bounds?.center ?? { x: 0, y: 0 };
  const annotations: {
    id: string;
    type: DimensionParams["type"];
    annotation: DimensionAnnotation;
  }[] = [];
  for (const dim of dimensions) {
    const sig = dimensionEdgeSignature(dim.dimension);
    if (sig === null) continue;
    const matched = findMatchingEdge(edges, sig);
    if (matched === null) continue;
    const measured = measuredById?.get(dim.id);
    if (measured === undefined) continue;
    const annotation = buildDimensionAnnotation({
      type: dim.dimension.type,
      measured,
      edge: matched,
      viewCenter,
      toSvg,
      obstacles,
      sheet: { width: sheetWidth, height: sheetHeight },
    });
    if (annotation === null) continue;
    annotations.push({ id: dim.id, type: dim.dimension.type, annotation });
  }

  return (
    <g
      data-testid="drawing-view"
      data-view={projection}
      data-view-error={failed ? "true" : "false"}
      data-edge-count={svgEdges.length}
      data-dimension-count={annotations.length}
    >
      {failed ? (
        <g>
          <rect
            x={anchorSvgX - 26}
            y={anchorSvgY - 14}
            width={52}
            height={28}
            fill="none"
            stroke={drawing.edgeHidden}
            strokeWidth={drawing.hiddenWeightMm}
            strokeDasharray={`${drawing.hiddenDashMm} ${drawing.hiddenGapMm}`}
          />
          <text
            x={anchorSvgX}
            y={anchorSvgY + 1}
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
          {svgEdges.map((edge, i) => (
            <PickableEdge
              key={i}
              edge={edge}
              projection={projection}
              viewId={viewId}
              selected={
                selectedEdgeKey !== null &&
                selectedEdgeKey !== undefined &&
                edge.sourceEdge !== null &&
                edgeKey(projection, edge.sourceEdge) === selectedEdgeKey
              }
              onPickEdge={onPickEdge}
            />
          ))}
          {annotations.map((a) => (
            <DimensionGlyph
              key={a.id}
              annotation={a.annotation}
              dimensionType={a.type}
              dimensionId={a.id}
            />
          ))}
        </>
      )}
      <text
        data-testid="drawing-view-label"
        x={anchorSvgX}
        y={labelY}
        textAnchor="middle"
        fill={drawing.label}
        fontFamily={font.data}
        fontSize={3.4}
        letterSpacing={0.6}
      >
        {VIEW_LABEL[projection].toUpperCase()}
      </text>
    </g>
  );
}

/** The bottom-right title block — stamped in mono, the drafting vernacular. */
function TitleBlock({
  dims,
  title,
  scale,
  size,
}: {
  dims: { width: number; height: number };
  title: string;
  scale: string;
  size: string;
}) {
  const w = TITLE_BLOCK_MM.width;
  const h = TITLE_BLOCK_MM.height;
  const x = dims.width - SHEET_MARGIN_MM - w;
  const y = dims.height - SHEET_MARGIN_MM - h;
  const splitX = x + w * 0.6; // left: title | right: scale/size stamp
  const midY = y + h * 0.5;
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
        {title.length > 22 ? `${title.slice(0, 21)}…` : title}
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
        {scale}
      </text>
      <text x={splitX + 4} y={midY + 8} {...caption}>
        SIZE
      </text>
      <text x={splitX + 4} y={y + h - 4} {...value}>
        {size.replace("_", " ")}
      </text>
    </g>
  );
}

export function DrawingSheet({
  sheet,
  views,
  resultByProjection,
  title,
  dimensionsByView,
  measuredById,
  selectedEdgeKey,
  onPickEdge,
}: DrawingSheetProps) {
  const dims = sheetDimensions(sheet.size, sheet.orientation);
  // Space the views by their own projected extents so they never overlap for a
  // part larger than the demo plate (fixed sheet fractions did — code review).
  const boundsByProjection: Partial<
    Record<ViewProjection, ReturnType<typeof viewBounds>>
  > = {};
  for (const projection of STANDARD_VIEWS) {
    const result = resultByProjection.get(projection);
    boundsByProjection[projection] =
      result && !result.error ? viewBounds(result.edges ?? []) : null;
  }
  const layout = boundsAwareLayout(boundsByProjection, dims);
  // Each placed view's drawn extent in SVG space — a dimension on any view must
  // clear its SIBLINGS' boxes (no callout landing on a neighbour — P1 fix).
  const svgRectByProjection = new Map<ViewProjection, SvgRect>();
  for (const projection of STANDARD_VIEWS) {
    const result = resultByProjection.get(projection);
    if (!result || result.error) continue;
    const rect = viewContentSvgRect(
      result.edges ?? [],
      layout[projection],
      dims.height,
    );
    if (rect) svgRectByProjection.set(projection, rect);
  }
  const scaleLabel = formatScale(
    views[0]?.scale ?? { numerator: 1, denominator: 1 },
  );
  const viewIdByProjection = new Map<ViewProjection, string>();
  for (const view of views) viewIdByProjection.set(view.projection, view.id);
  // Draw in the standard order, but only views that were actually created.
  const placed = STANDARD_VIEWS.filter((projection) =>
    views.some((view) => view.projection === projection),
  );

  return (
    <svg
      data-testid="drawing-sheet"
      role="img"
      aria-label={`Drawing sheet — ${title}, ${placed.length} views at ${scaleLabel}`}
      viewBox={`0 0 ${dims.width} ${dims.height}`}
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
        width={dims.width}
        height={dims.height}
        fill={drawing.paper}
        stroke={drawing.paperEdge}
        strokeWidth={0.6}
      />
      {/* Drawn border frame. */}
      <rect
        data-testid="drawing-border"
        x={SHEET_MARGIN_MM}
        y={SHEET_MARGIN_MM}
        width={dims.width - 2 * SHEET_MARGIN_MM}
        height={dims.height - 2 * SHEET_MARGIN_MM}
        fill="none"
        stroke={drawing.ink}
        strokeWidth={drawing.borderWeightMm}
      />
      {placed.map((projection) => (
        <SheetView
          key={projection}
          projection={projection}
          anchor={layout[projection]}
          sheetWidth={dims.width}
          sheetHeight={dims.height}
          result={resultByProjection.get(projection)}
          viewId={viewIdByProjection.get(projection) ?? null}
          dimensions={dimensionsByView?.get(projection) ?? []}
          measuredById={measuredById}
          selectedEdgeKey={selectedEdgeKey}
          obstacles={[...svgRectByProjection]
            .filter(([p]) => p !== projection)
            .map(([, rect]) => rect)}
          onPickEdge={onPickEdge}
        />
      ))}
      <TitleBlock
        dims={dims}
        title={title}
        scale={scaleLabel}
        size={sheet.size}
      />
    </svg>
  );
}
