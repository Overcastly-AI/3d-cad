/**
 * A view's centre marks — drawn from the composed sheet and PICKABLE as a
 * dimension anchor (QA-DRAWING-CENTRE-MARKS).
 *
 * The composer marks every circle the view sees end-on with an ISO 128 / ASME
 * Y14.2 centre mark; this layer draws those segments verbatim and puts a grab on
 * each centre, so a hole's POSITION can be dimensioned — from a straight edge,
 * or from another hole — the way Fusion's drawing dimension tool picks a centre
 * mark. A mark names its hole through the circle it stands for (`edge_index`,
 * aligned to the evaluate pick list by canonical edge order exactly as the
 * edges are), so the stored reference is the hole rim's signature and follows
 * the hole through a part edit.
 *
 * The grab is capped to a fraction of the circle's own radius, so the circle
 * keeps a pickable rim for its diameter and the centre owns only its middle.
 */
import { useState } from "react";

import { drawing } from "@loft/design";

import type {
  ComposedCentreMark,
  ComposedEdge,
  EdgeSignature,
  ProjectedViewEdge,
  ViewProjection,
} from "../api/drawings";
import type { SheetBox } from "../drawing/centres";
import { edgeSignatureKey } from "../drawing/dimensions";
import { VIEW_LABEL, type Point2D } from "../drawing/layout";

/** A pick on a hole's centre mark — the seed of a hole-position dimension. */
export interface CentrePickEvent {
  projection: ViewProjection;
  viewId: string;
  /** The CIRCLE whose centre was picked (the stored reference). */
  sourceEdge: EdgeSignature;
  clientX: number;
  clientY: number;
  /** The centre's composed sheet position (mm). */
  at: Point2D;
  /** The view's composed centre (mm) — the PLACE stage's outward reference. */
  viewAnchor: Point2D;
  /** The view's drawn extents (mm), which the auto placement clears. */
  bounds: SheetBox;
}

/** A stable key for a centre mark — `projection:centre:<circle key>`. */
export function centreKey(projection: ViewProjection, sig: EdgeSignature) {
  return `${projection}:centre:${edgeSignatureKey(sig)}`;
}

/** The grab radius (sheet mm) of a mark on a circle of radius `r`. */
export function centreGrabMm(r: number): number {
  return Math.min(drawing.centreHitMm, r * 0.6);
}

/** The drawn extents of a view's composed edges (sheet mm). */
function edgeBox(edges: readonly ComposedEdge[]): SheetBox {
  const xs: number[] = [];
  const ys: number[] = [];
  for (const e of edges) {
    if (e.kind === "line") {
      xs.push(e.x1, e.x2);
      ys.push(e.y1, e.y2);
    } else if (e.kind === "circle") {
      xs.push(e.cx - e.r, e.cx + e.r);
      ys.push(e.cy - e.r, e.cy + e.r);
    } else {
      for (const p of e.points) {
        xs.push(p.x_mm);
        ys.push(p.y_mm);
      }
    }
  }
  return {
    min: { x: Math.min(...xs), y: Math.min(...ys) },
    max: { x: Math.max(...xs), y: Math.max(...ys) },
  };
}

export function CentreMarks({
  marks,
  edges,
  evalEdges,
  projection,
  viewId,
  viewAnchor,
  selectedKeys,
  onPickCentre,
}: {
  marks: readonly ComposedCentreMark[];
  /** The view's composed edges — their extents seat a hole dimension. */
  edges: readonly ComposedEdge[];
  /** The view's evaluate pick list, aligned to the composed edges. */
  evalEdges: readonly ProjectedViewEdge[];
  projection: ViewProjection;
  viewId: string | null;
  viewAnchor: Point2D;
  selectedKeys: readonly string[];
  onPickCentre?: (event: CentrePickEvent) => void;
}) {
  if (marks.length === 0) return null;
  const bounds = edgeBox(edges);
  return (
    <g data-testid="drawing-centre-marks" data-view={projection}>
      {marks.map((mark, i) => {
        const edge = evalEdges[mark.edge_index];
        const sig =
          edge?.dimensionable && edge.primitive === "circle"
            ? (edge.source_edge ?? null)
            : null;
        return (
          <CentreMark
            key={i}
            mark={mark}
            sourceEdge={sig}
            projection={projection}
            viewId={viewId}
            viewAnchor={viewAnchor}
            bounds={bounds}
            selected={
              sig !== null && selectedKeys.includes(centreKey(projection, sig))
            }
            onPickCentre={onPickCentre}
          />
        );
      })}
    </g>
  );
}

function CentreMark({
  mark,
  sourceEdge,
  projection,
  viewId,
  viewAnchor,
  bounds,
  selected,
  onPickCentre,
}: {
  mark: ComposedCentreMark;
  sourceEdge: EdgeSignature | null;
  projection: ViewProjection;
  viewId: string | null;
  viewAnchor: Point2D;
  bounds: SheetBox;
  selected: boolean;
  onPickCentre?: (event: CentrePickEvent) => void;
}) {
  const [hover, setHover] = useState(false);
  const [focus, setFocus] = useState(false);
  const at = { x: mark.cx, y: mark.cy };
  // A hole-centre dimension is measured on a standard view's frame; a section
  // or flat-pattern view has none yet (geometry refuses it), so its marks are
  // drawn but offer no pick that could only end in an error.
  const pickable =
    sourceEdge !== null &&
    viewId !== null &&
    onPickCentre !== undefined &&
    projection !== "section" &&
    projection !== "flat_pattern";
  const lit = selected || hover || focus;
  const ink = lit
    ? selected
      ? drawing.pickSelected
      : drawing.pickHover
    : drawing.centreMark;
  const grab = centreGrabMm(mark.r);
  const fire = (clientX: number, clientY: number) => {
    if (!pickable || sourceEdge === null || viewId === null) return;
    onPickCentre?.({
      projection,
      viewId,
      sourceEdge,
      clientX,
      clientY,
      at,
      viewAnchor,
      bounds,
    });
  };
  return (
    <g
      data-testid="drawing-centre-mark"
      data-view={projection}
      data-pickable={pickable ? "true" : "false"}
      data-selected={selected ? "true" : "false"}
      data-cx={mark.cx.toFixed(4)}
      data-cy={mark.cy.toFixed(4)}
    >
      {mark.lines.map((line, j) => (
        <line
          key={j}
          x1={line.x1}
          y1={line.y1}
          x2={line.x2}
          y2={line.y2}
          stroke={ink}
          strokeWidth={
            lit ? drawing.centreMarkWeightMm * 2 : drawing.centreMarkWeightMm
          }
          strokeLinecap="butt"
          pointerEvents="none"
        />
      ))}
      {pickable ? (
        <g
          role="button"
          tabIndex={0}
          aria-label={`Dimension to this hole centre in the ${VIEW_LABEL[projection]} view`}
          data-testid="drawing-pick-centre"
          data-view={projection}
          data-selected={selected ? "true" : "false"}
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
          <circle cx={at.x} cy={at.y} r={grab} fill="transparent" />
          {lit ? (
            <circle
              cx={at.x}
              cy={at.y}
              r={grab * 0.55}
              fill="none"
              stroke={ink}
              strokeWidth={focus ? drawing.pickFocusRingMm * 0.25 : 0.3}
              pointerEvents="none"
            />
          ) : null}
        </g>
      ) : null}
    </g>
  );
}
