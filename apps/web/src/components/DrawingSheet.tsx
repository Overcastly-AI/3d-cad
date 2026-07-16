/**
 * The drawing sheet — THE signature surface of the Drawings pillar: a leaf of
 * cool drafting paper laid on the blued-steel bench, the one inversion in an
 * otherwise all-dark product (design mandate: spend boldness in one place). It
 * renders in a SINGLE SVG coordinate system (millimetres, so the print is
 * scale-correct) reading stroke colours + weights straight from the `drawing`
 * design tokens — one palette, two renderers (DOM + this SVG). Purely
 * presentational: it draws whatever projected edges it is handed and stays
 * honest about a per-view projection failure.
 */
import { drawing, font, viewport } from "@loft/design";

import type {
  DrawingViewResult,
  SheetResponse,
  ViewProjection,
  ViewResponse,
} from "../api/drawings";
import {
  SHEET_MARGIN_MM,
  STANDARD_VIEWS,
  TITLE_BLOCK_MM,
  VIEW_LABEL,
  boundsAwareLayout,
  formatScale,
  sheetDimensions,
  viewBounds,
  viewToSvgEdges,
  type Anchor,
  type SvgEdge,
} from "../drawing/layout";

export interface DrawingSheetProps {
  sheet: SheetResponse;
  views: readonly ViewResponse[];
  /** Per-projection projection outcome from `/geometry/drawing/evaluate`. */
  resultByProjection: Map<ViewProjection, DrawingViewResult>;
  /** Title-block title (the drawing name). */
  title: string;
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

function EdgeShape({ edge, index }: { edge: SvgEdge; index: number }) {
  const stroke = strokeFor(edge.visible);
  const common = {
    ...stroke,
    fill: "none" as const,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "data-edge": edge.kind,
    "data-visible": edge.visible ? "true" : "false",
  };
  if (edge.kind === "line") {
    return (
      <line
        key={index}
        x1={edge.x1}
        y1={edge.y1}
        x2={edge.x2}
        y2={edge.y2}
        {...common}
      />
    );
  }
  if (edge.kind === "circle") {
    return (
      <circle key={index} cx={edge.cx} cy={edge.cy} r={edge.r} {...common} />
    );
  }
  return (
    <polyline
      key={index}
      points={edge.points.map((p) => `${p.x},${p.y}`).join(" ")}
      {...common}
    />
  );
}

/** One placed view: its projected edges + a stamped caption, or a failure note. */
function SheetView({
  projection,
  anchor,
  sheetHeight,
  result,
}: {
  projection: ViewProjection;
  anchor: Anchor;
  sheetHeight: number;
  result: DrawingViewResult | undefined;
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

  return (
    <g
      data-testid="drawing-view"
      data-view={projection}
      data-view-error={failed ? "true" : "false"}
      data-edge-count={svgEdges.length}
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
        svgEdges.map((edge, i) => <EdgeShape key={i} edge={edge} index={i} />)
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
  const scaleLabel = formatScale(
    views[0]?.scale ?? { numerator: 1, denominator: 1 },
  );
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
          sheetHeight={dims.height}
          result={resultByProjection.get(projection)}
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
