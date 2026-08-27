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
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type Ref,
} from "react";

import { drawing, font, viewport } from "@loft/design";

import type {
  ComposedBendTable,
  ComposedDimension,
  ComposedEdge,
  ComposedHatch,
  ComposedMeasuredDimension,
  ComposedNote,
  ComposedPoint,
  ComposedSheet,
  ComposedTitleBlock,
  ComposedView,
  DimensionParams,
  DrawingViewResult,
  EdgeSignature,
  FeatureError,
  ProjectedViewEdge,
  ViewProjection,
  ViewResponse,
} from "../api/drawings";
import type { PickGeometry } from "../drawing/authoring";
import { edgeSignatureKey } from "../drawing/dimensions";
import {
  VIEW_LABEL,
  endpointHandlesForEdge,
  type Point2D,
  type SvgEdge,
} from "../drawing/layout";
import { BANNER_TEXT_MM, bannerLines } from "../drawing/layoutIssues";
import {
  GHOST_FIGURE_MM,
  GHOST_TARGET_MM,
  type PlacementGhost,
} from "../drawing/placement";
import { titleBlockFields } from "../drawing/titleBlock";
import { viewRowsByProjection } from "../drawing/views";

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
  /** Where this edge sits on the COMPOSED sheet (mm) — the PLACE stage measures
   * the authored `offset_mm` / `text_pos` against these coordinates. */
  geometry: PickGeometry;
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
  /** This endpoint's composed sheet position (mm). */
  at: Point2D;
  /** The view's composed centre (mm) — the PLACE stage's outward reference. */
  viewAnchor: Point2D;
}

/**
 * The id of the dimension grab under a viewport point, or null.
 *
 * The grab layer is painted ahead of every view so that GEOMETRY always wins a
 * contest with annotation chrome (frontend-QA P2-B). That ordering also puts it
 * behind each view's drag PLATE, and a view's frame is padded out into the
 * gutter — which is exactly where a draughtsman puts dimensions. SVG has no
 * z-index to express the three tiers the sheet actually needs (plate < grab <
 * geometry), so the plate asks the DOM what is really beneath it.
 */
function grabUnderPointer(clientX: number, clientY: number): string | null {
  for (const el of document.elementsFromPoint(clientX, clientY)) {
    const grab = el.closest('[data-testid="dimension-grab"]');
    if (grab !== null) return grab.getAttribute("data-dimension-id");
  }
  return null;
}

/** A placed dimension picked up to be moved — it re-enters the PLACE stage. */
export interface DimensionGrabEvent {
  dimensionId: string;
  viewId: string;
  projection: ViewProjection;
  /** The composed annotation, which is what the placement is recovered FROM. */
  dim: ComposedMeasuredDimension;
  /** The view's composed centre (mm) — the placement's outward reference. */
  viewAnchor: Point2D;
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
  /** Fired when a view is dragged (or nudged) to a new placement — `position` is
   * the view CENTRE in sheet mm, y-up from bottom-left (the SheetViewPlacement
   * convention; the y-flip from SVG space is applied here). Persisted with
   * `auto_place: false` so the composer honours it verbatim. */
  onPlaceView?: (
    viewId: string,
    position: { x_mm: number; y_mm: number },
  ) => void;
  /** Fired to return a view to bounds-aware auto-layout (`auto_place: true`). */
  onResetView?: (viewId: string) => void;
  /** A placement write is in flight — suspend further drag/nudge/reset. */
  placementBusy?: boolean;
  /** The in-progress dimension placement to draw, or null when not placing.
   * While it is non-null the sheet takes ALL pointer input (a placement is a
   * modal gesture — an edge pick underneath would end it by accident). */
  dimensionGhost?: PlacementGhost | null;
  /** Pointer moved during a placement — reports the sheet-mm point under it. */
  onPlacePointer?: (at: Point2D) => void;
  /** The placement was clicked down onto the paper — commit it. */
  onPlaceCommit?: () => void;
  /** The pointer was RELEASED on the paper mid-placement — the end of a
   * press-drag. The caller commits only if the placement actually moved, which
   * is what lets one gesture serve both press-drag-release and click-to-drop. */
  onPlaceRelease?: () => void;
  /** Fired when a PLACED dimension is picked up to be moved (press or Enter). */
  onGrabDimension?: (event: DimensionGrabEvent) => void;
  /** The dimension currently being re-placed — drawn as the ghost instead of as
   * ink, so the sheet never shows the same dimension twice. */
  movingDimensionId?: string | null;
  /** Handle on the root `<svg>` so the editor can serialize it to a file (#5). */
  svgRef?: Ref<SVGSVGElement>;
}

/** Stroke props by outline role (sheet-metal.md §6): a `bend` fold line draws as
 * a distinct dashed-blue stroke — the sheet-metal signature, orthogonal to
 * `visible` — while a `body` edge keeps the solid (visible) / dashed (hidden)
 * object-line styling every drawing view uses. */
function strokeFor(visible: boolean, edgeRole: SvgEdge["edgeRole"]) {
  if (edgeRole === "bend") {
    return {
      stroke: drawing.bend,
      strokeWidth: drawing.bendWeightMm,
      strokeDasharray: `${drawing.bendDashMm} ${drawing.bendGapMm}`,
    };
  }
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
  const edgeRole = composed.edge_role;
  if (composed.kind === "line") {
    return {
      kind: "line",
      x1: composed.x1,
      y1: composed.y1,
      x2: composed.x2,
      y2: composed.y2,
      visible: composed.visible,
      edgeRole,
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
      edgeRole,
      ...info,
    };
  }
  return {
    kind: "polyline",
    points: composed.points.map((p) => ({ x: p.x_mm, y: p.y_mm })),
    visible: composed.visible,
    edgeRole,
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
  bendIndex = -1,
}: {
  edge: SvgEdge;
  hover: boolean;
  focus: boolean;
  selected: boolean;
  /** 0-based index of this fold line among the view's `bend` edges — the
   * POSITIONAL key to its bend-table row (sheet-metal.md §6); -1 for a body edge. */
  bendIndex?: number;
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
    : strokeFor(edge.visible, edge.edgeRole);
  const common = {
    ...stroke,
    fill: "none" as const,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    // DRAWN INK NEVER TAKES A PICK (frontend-QA 2026-08-27, P3-D). An SVG
    // stroke is `visiblePainted` by default, so every outline painted after a
    // neighbour's transparent hit band sat ON TOP of it — and a view's own
    // polyline outline sat on top of its own 40 mm edge target, exactly at the
    // midpoint a user aims for. Measured on the FRONT view before this line:
    // 9 of 18 points along the edge resolved to the pick target, the central
    // run resolved to `polyline` inside `drawing-view`, and a real
    // `page.mouse.click` at the midpoint did nothing at all. The specs did not
    // see it because they picked with `click({ force: true })`.
    pointerEvents: "none" as const,
    "data-edge": edge.kind,
    "data-edge-role": edge.edgeRole,
    ...(bendIndex >= 0 ? { "data-bend-index": String(bendIndex) } : {}),
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
              pointerEvents: "none",
              "data-testid": "drawing-edge-focus-ring",
            },
            "ring",
          )
        : null}
      {edgePrimitive(edge, common, "core")}
    </>
  );
}

/**
 * One transparent band of pick width swept along the segment `a`→`b`.
 *
 * A stroked `<line>` would be the obvious way to write this and it is the wrong
 * one: Chrome's `getBoundingClientRect` on an SVG `<line>` reports the GEOMETRY
 * box and ignores the stroke, so a horizontal 40 mm edge measured **118.1 x
 * 0.0 px** — a control of zero area. The pointer still hit it (hit-testing does
 * honour the stroke), so the app "worked", but every consumer that reasons
 * about BOUNDS saw nothing there: assistive technology, any touch-target audit,
 * and Playwright, whose actionability check calls a zero-area element invisible
 * and refuses to click it. That is why the drawing specs had all acquired
 * `click({ force: true })` — the force flag was papering over a real geometric
 * defect in the control (frontend-QA 2026-08-27, P3-D).
 *
 * A rotated `<rect>` carries the SAME band (`pickHitMm` wide, centred on the
 * line, so no pick moves) with real area, so the box a machine measures and the
 * band a finger hits are finally the same thing.
 */
function HitBand({ a, b }: { a: Point2D; b: Point2D }) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy);
  if (len < 1e-9) return null;
  const half = drawing.pickHitMm / 2;
  return (
    <rect
      x={a.x}
      y={a.y - half}
      width={len}
      height={drawing.pickHitMm}
      transform={`rotate(${(Math.atan2(dy, dx) * 180) / Math.PI} ${a.x} ${a.y})`}
      fill="transparent"
    />
  );
}

/** A transparent, generously-wide hit region over one shape. */
function HitShape({ edge }: { edge: SvgEdge }) {
  if (edge.kind === "line") {
    return (
      <HitBand a={{ x: edge.x1, y: edge.y1 }} b={{ x: edge.x2, y: edge.y2 }} />
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
  // One band per segment: a polyline's own stroke has the same zero-area box.
  return (
    <>
      {edge.points.slice(1).map((p, i) => (
        <HitBand key={i} a={edge.points[i]!} b={p} />
      ))}
    </>
  );
}

/**
 * The composed sheet-mm geometry a pick carries into the PLACE stage. Read
 * straight off the drawn primitive, so the placement is measured against the
 * pixels the user is pointing at rather than a re-derivation of them.
 */
function composedGeometry(edge: SvgEdge, viewAnchor: Point2D): PickGeometry {
  return {
    line:
      edge.kind === "line"
        ? { a: { x: edge.x1, y: edge.y1 }, b: { x: edge.x2, y: edge.y2 } }
        : null,
    circle:
      edge.kind === "circle"
        ? { center: { x: edge.cx, y: edge.cy }, radius: edge.r }
        : null,
    viewAnchor,
  };
}

/** One projected edge — solid/dashed, and interactive when dimensionable.
 * Hover/focus of a dimensionable straight edge REVEALS its endpoint handles
 * (via `onReveal`, keyed on the edge) — the Fusion/Plasticity proximity idiom,
 * so the sheet stays uncluttered until the vertex snap is actually wanted. */
function PickableEdge({
  edge,
  projection,
  viewId,
  viewAnchor,
  selected,
  bendIndex = -1,
  onReveal,
  onPickEdge,
}: {
  edge: SvgEdge;
  projection: ViewProjection;
  viewId: string | null;
  /** This view's composed centre (sheet mm) — carried on the pick for placement. */
  viewAnchor: Point2D;
  selected: boolean;
  /** Positional bend-table key for a fold line (-1 for a body edge). */
  bendIndex?: number;
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
      <EdgeShape
        edge={edge}
        hover={false}
        focus={false}
        selected={selected}
        bendIndex={bendIndex}
      />
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
      geometry: composedGeometry(edge, viewAnchor),
    });
  };

  return (
    <g>
      <EdgeShape
        edge={edge}
        hover={hover}
        focus={focus}
        selected={selected}
        bendIndex={bendIndex}
      />
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
  viewAnchor,
  sourceEdge,
  endpoint,
  selected,
  revealed,
  onPickEndpoint,
}: {
  at: Point2D;
  projection: ViewProjection;
  viewId: string;
  /** This view's composed centre (sheet mm) — carried on the pick for placement. */
  viewAnchor: Point2D;
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
      at,
      viewAnchor,
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

/** Value-stamp halo size (mm) for `value` — the seat the stamp paints on. */
function valueStampBox(value: string): { w: number; h: number } {
  return {
    w: value.length * drawing.dimensionTextMm * 0.62 + 1.8,
    h: drawing.dimensionTextMm + 1.4,
  };
}

/**
 * The ONE part of a placed dimension a pointer can touch: its value stamp,
 * which is what a draughtsman reaches for in every tool that has ever let you
 * move a dimension. Press it (or focus it and press Enter) and the dimension
 * re-enters the PLACE stage it was born in — same ghost, same readout, same
 * arrow keys, same typed field, same Escape.
 *
 * It is a target of real geometry rather than the text's own paint, and it
 * lives in ONE layer painted ahead of every view (see `DrawingSheet`), so an
 * edge pick always wins where the two overlap — in any view, not just its own.
 * That ordering is what lets the rest of the annotation be
 * `pointer-events: none` without a dimension becoming untouchable, and being
 * able to move a dimension out of a view's way is the cure P2-B was missing.
 */
function DimensionGrab({
  dim,
  projection,
  viewId,
  viewAnchor,
  hoveredFromPlate,
  onGrab,
}: {
  dim: ComposedDimension;
  projection: ViewProjection;
  viewId: string;
  viewAnchor: Point2D;
  /** The pointer is over this grab but a view's drag plate is on top of it, so
   * the plate reports the hover on its behalf. Without this the affordance
   * would be invisible exactly where dimensions usually sit — the gutter — and
   * a control nobody can see is a control nobody uses. */
  hoveredFromPlate: boolean;
  onGrab: (event: DimensionGrabEvent) => void;
}) {
  const [selfHover, setSelfHover] = useState(false);
  const hover = selfHover || hoveredFromPlate;
  const [focus, setFocus] = useState(false);
  // An errored dimension has no measured annotation to re-place; its recovery
  // is the panel's Confirm/Delete, not a drag.
  const id = dim.dimension_id;
  // A composed dimension carries no id when the request did not name one; there
  // is then no row to re-place, so it stays ink.
  if (dim.kind === "error" || id === null || id === undefined) return null;
  const { w, h } = valueStampBox(dim.text.value);
  const pad = drawing.pickHitMm / 2;
  const fire = () =>
    onGrab({ dimensionId: id, viewId, projection, dim, viewAnchor });
  return (
    <g
      role="button"
      tabIndex={0}
      aria-label={`Move the ${dim.text.value} ${dim.dimension_type} dimension in the ${VIEW_LABEL[projection]} view`}
      data-testid="dimension-grab"
      data-dimension-id={id}
      data-view={projection}
      style={{ cursor: "grab", outline: "none" }}
      transform={`rotate(${dim.text.angle} ${dim.text.x} ${dim.text.y})`}
      onMouseEnter={() => setSelfHover(true)}
      onMouseLeave={() => setSelfHover(false)}
      onFocus={() => setFocus(true)}
      onBlur={() => setFocus(false)}
      // POINTER DOWN, not click: a press-drag is what a user tries first, and
      // starting the stage on the press means the ghost is already following
      // the pointer by the time they have moved a millimetre. A press with no
      // drag simply leaves the ghost up, and the next click drops it — the
      // same two-step the authoring flow already teaches.
      onPointerDown={(event) => {
        event.preventDefault();
        fire();
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          fire();
        }
      }}
    >
      {/* A visible seat only while engaged — a placed sheet must not sprout a
          box around every number the moment it is drawn. */}
      {hover || focus ? (
        <rect
          data-testid="dimension-grab-seat"
          x={dim.text.x - w / 2 - pad}
          y={dim.text.y - h / 2 - pad}
          width={w + pad * 2}
          height={h + pad * 2}
          fill="none"
          stroke={drawing.pickSelected}
          strokeWidth={focus ? drawing.pickFocusRingMm / 2 : 0.3}
          opacity={focus ? 0.55 : 0.8}
        />
      ) : null}
      <rect
        x={dim.text.x - w / 2 - pad}
        y={dim.text.y - h / 2 - pad}
        width={w + pad * 2}
        height={h + pad * 2}
        fill="transparent"
      />
    </g>
  );
}

/** A placed dimension — extension + dimension lines, arrowheads, value stamp.
 * Drawn VERBATIM from the composed model (coordinates are final SVG space). */
function DimensionGlyph({ dim }: { dim: ComposedDimension }) {
  const dimensionType: DimensionParams["type"] = dim.dimension_type;
  const dimensionId = dim.dimension_id ?? undefined;
  if (dim.kind === "error") {
    const { at, code } = dim;
    // The WORDS the composer already carries (`message`/`text`, `7fde5d2`) —
    // "DIAMETER DIM: REFERENCE LOST - RE-PICK THE EDGE". Every exporter stamps
    // them beside the marker; this sheet drew a bare `!` and nothing else, so
    // the engineer at the screen was told less than the machinist holding the
    // PDF (QA-4b). The phrase is the SERVER's — there is deliberately no second
    // phrase table on this side of the wire.
    const caption = dim.message === "" ? null : dim.message;
    return (
      <g
        data-testid="drawing-dimension"
        data-dimension-id={dimensionId}
        data-dimension-type={dimensionType}
        data-dimension-error={code}
        // DRAFTING INK NEVER TAKES A PICK — see `DimensionGrab` for the one
        // element of a dimension that does.
        pointerEvents="none"
      >
        <title>{caption ?? `Dimension could not be measured (${code})`}</title>
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
        {caption !== null && dim.text ? (
          <text
            data-testid="drawing-dimension-error"
            x={dim.text.x_mm}
            y={dim.text.y_mm}
            fill={drawing.dimensionFlag}
            fontFamily={font.data}
            fontSize={drawing.dimensionErrorTextMm}
            letterSpacing={0.2}
          >
            {caption}
          </text>
        ) : null}
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
      // DRAFTING INK NEVER TAKES A PICK (frontend-QA 2026-08-27, P2-B). A
      // dimension's value stamp is a fat opaque blob of paint that lands
      // wherever the draughtsman put it, and with free placement that is
      // routinely in the gutter over ANOTHER view: measured with the TOP
      // view's 40 mm edge dimensioned 20 mm downward, one of the FRONT view's
      // own 40 mm pick targets became unreachable at its midpoint —
      // `elementFromPoint` returned `text[drawing-dimension-value]`. The only
      // element of a dimension that takes a pointer is now `DimensionGrab`,
      // which is deliberate, labelled, and painted UNDER the view's geometry
      // so an edge pick always wins over it.
      pointerEvents="none"
    >
      <title>
        {foreshortened
          ? `${text.value} — foreshortened; dimension in a true-size view for the drawn length`
          : text.value}
      </title>
      {lines.map((l, i) => (
        <line
          key={i}
          // The composer's own role, exposed so a test (and anyone inspecting
          // the sheet) can tell the dimension line from its witness lines —
          // which is what "the dimension landed HERE" is measured against.
          data-dim-line-role={l.role}
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

/** Wrap `text` into lines of at most `maxChars`, at word boundaries (SVG `<text>`
 * does not wrap). Caps at `maxLines`, ellipsizing the overflow. */
function wrapText(text: string, maxChars: number, maxLines: number): string[] {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let line = "";
  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word;
    if (candidate.length > maxChars && line) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
    if (lines.length === maxLines) break;
  }
  if (line && lines.length < maxLines) lines.push(line);
  if (lines.length === maxLines) {
    const last = lines[maxLines - 1] ?? "";
    if (last.length > maxChars)
      lines[maxLines - 1] = `${last.slice(0, maxChars - 1)}…`;
  }
  return lines;
}

/** A friendly headline per typed view error (sheet-metal.md §7 / drawings §1.5). */
function errorHeadline(
  projection: ViewProjection,
  code: string | undefined,
): string {
  if (code === "flat_pattern_not_sheet_metal") return "NOT A SHEET-METAL PART";
  if (code === "subshape_unresolved") return "BEND UNRESOLVED";
  if (code === "section_plane_not_principal") return "PLANE NOT AXIS-ALIGNED";
  if (code === "section_plane_misses_body") return "PLANE MISSES THE PART";
  if (code === "section_empty") return "NO CUT FACE";
  if (code === "section_params_missing") return "NO CUTTING PLANE SET";
  if (projection === "section") return "SECTION FAILED";
  return projection === "flat_pattern" ? "FLAT PATTERN FAILED" : "VIEW FAILED";
}

/** Forward-looking guidance for a typed section failure (drawings-section.md §7) —
 * an error explains what went wrong and how to fix it (frontend-design). */
function sectionDetail(code: string | undefined): string | null {
  if (code === "section_plane_not_principal")
    return "v1 cuts on an axis-aligned plane. Choose XY, XZ, YZ, or an offset datum parallel to one.";
  if (code === "section_plane_misses_body")
    return "The cutting plane doesn't pass through the part. Choose a plane that intersects it.";
  if (code === "section_empty")
    return "The plane grazes the part without cutting a face. Move it into the solid.";
  if (code === "section_params_missing")
    return "This section view has no cutting plane. Re-create it and pick a plane.";
  return null;
}

/** An honest inline error state for a view that produced no geometry — a dashed
 * placeholder box carrying the typed reason (never a crash or a silent blank).
 * The flat-pattern "not sheet metal" case reads as guidance, not a failure mood
 * (frontend-design: an error explains what went wrong and points forward). */
function FailedView({
  projection,
  anchor,
  error,
}: {
  projection: ViewProjection;
  anchor: ComposedPoint;
  error: FeatureError | null;
}) {
  const headline = errorHeadline(projection, error?.code);
  const detail =
    error?.code === "flat_pattern_not_sheet_metal"
      ? "Add a base flange and an edge flange to unfold a flat blank."
      : (sectionDetail(error?.code) ??
        error?.message ??
        "This view produced no geometry.");
  const lines = wrapText(detail, 34, 3);
  const boxW = 78;
  const boxH = 20 + lines.length * 4.4;
  return (
    <g
      data-testid="drawing-view-error"
      data-error-code={error?.code ?? "unknown"}
    >
      <rect
        x={anchor.x_mm - boxW / 2}
        y={anchor.y_mm - boxH / 2}
        width={boxW}
        height={boxH}
        fill="none"
        stroke={drawing.edgeHidden}
        strokeWidth={drawing.hiddenWeightMm}
        strokeDasharray={`${drawing.hiddenDashMm} ${drawing.hiddenGapMm}`}
      />
      <text
        x={anchor.x_mm}
        y={anchor.y_mm - boxH / 2 + 8}
        textAnchor="middle"
        fill={drawing.dimensionFlag}
        fontFamily={font.display}
        fontSize={3.4}
        letterSpacing={0.6}
      >
        {headline}
      </text>
      {lines.map((line, i) => (
        <text
          key={i}
          x={anchor.x_mm}
          y={anchor.y_mm - boxH / 2 + 14 + i * 4.4}
          textAnchor="middle"
          fill={drawing.label}
          fontFamily={font.data}
          fontSize={2.8}
        >
          {line}
        </text>
      ))}
    </g>
  );
}

/**
 * A section view's crosshatch — the ANSI 45° cut-face fill (drawings-section.md
 * §5), drawn VERBATIM from the composed model (coordinates already in final
 * sheet-mm SVG space). Rendered UNDER the projected edges so the cut outline and
 * any dimensions read on top of the fill. The `drawing.hatch` ink + weight are
 * the same the server serializer emits (`_HATCH_INK` / `_HATCH_W`) and the same
 * `drawing-hatch` test hook, so the on-screen section and the exported SVG/PDF/
 * DXF are one fill — QA drives a single target set (E1b, closing section views
 * to fully end-to-end: kernel + wire + web authoring + on-screen fill). */
function SectionHatch({ hatch }: { hatch: ComposedHatch }) {
  if (hatch.lines.length === 0) return null;
  return (
    <g
      data-testid="drawing-hatch"
      aria-hidden="true"
      stroke={drawing.hatch}
      strokeWidth={drawing.hatchWeightMm}
      // `round` matches the server serializer's hatch stroke (compose.py
      // `_emit_hatch`) so the on-screen fill == the exported SVG/PDF/DXF.
      strokeLinecap="round"
    >
      {hatch.lines.map((line, i) => (
        <line key={i} x1={line.x1} y1={line.y1} x2={line.x2} y2={line.y2} />
      ))}
    </g>
  );
}

/** A view's geometry extents in final SVG space (mm) — the box the placement
 * frame wraps. A failed/empty view (no edges) falls back to a box around its
 * anchor so it stays grabbable. */
interface ViewExtents {
  x: number;
  y: number;
  w: number;
  h: number;
}

function viewGeometryBounds(view: ComposedView): ViewExtents {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const acc = (x: number, y: number) => {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  };
  for (const edge of view.edges ?? []) {
    if (edge.kind === "line") {
      acc(edge.x1, edge.y1);
      acc(edge.x2, edge.y2);
    } else if (edge.kind === "circle") {
      acc(edge.cx - edge.r, edge.cy - edge.r);
      acc(edge.cx + edge.r, edge.cy + edge.r);
    } else {
      for (const p of edge.points) acc(p.x_mm, p.y_mm);
    }
  }
  acc(view.label_pos.x_mm, view.label_pos.y_mm);
  if (!Number.isFinite(minX)) {
    const half = { w: 40, h: 15 };
    return {
      x: view.anchor.x_mm - half.w,
      y: view.anchor.y_mm - half.h,
      w: half.w * 2,
      h: half.h * 2,
    };
  }
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}

/** Map a client (screen px) point into the SVG's own user space (sheet mm),
 * inverting the on-screen fit transform. Uses `createSVGPoint`/`getScreenCTM`
 * (present in every browser that runs the viewport); returns the raw client
 * point in the rare env where the CTM is unavailable so a drag is a no-op, never
 * a throw. */
function clientPointToSvg(
  svg: SVGSVGElement,
  clientX: number,
  clientY: number,
): { x: number; y: number } {
  const ctm = svg.getScreenCTM ? svg.getScreenCTM() : null;
  if (!ctm || typeof svg.createSVGPoint !== "function") {
    return { x: clientX, y: clientY };
  }
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  const mapped = pt.matrixTransform(ctm.inverse());
  return { x: mapped.x, y: mapped.y };
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
  autoPlace,
  sheetHeightMm,
  selectedEdgeKey,
  armedEdgeKeys,
  selectedVertexKeys,
  endpointPickActive,
  placementBusy,
  movingDimensionId,
  onPickEdge,
  onPickEndpoint,
  onPlaceView,
  onResetView,
  onGrabDimensionId,
  onHoverGrabId,
}: {
  composedView: ComposedView;
  /** The aligned evaluate result for this view (pick provenance), or undefined. */
  result: DrawingViewResult | undefined;
  viewId: string | null;
  /** Whether this view is currently auto-placed (false = a persisted drag). */
  autoPlace: boolean;
  /** The sheet height (mm) — the y-flip datum from SVG space to y-up placement. */
  sheetHeightMm: number;
  selectedEdgeKey: string | null | undefined;
  armedEdgeKeys: readonly string[];
  selectedVertexKeys: readonly string[];
  /** A point-to-point pick is armed — reveal all endpoint handles. */
  endpointPickActive: boolean;
  placementBusy: boolean;
  /** The dimension being re-placed — drawn as the ghost, not as ink. */
  movingDimensionId: string | null;
  onPickEdge?: (event: EdgePickEvent) => void;
  onPickEndpoint?: (event: EndpointPickEvent) => void;
  onPlaceView?: (
    viewId: string,
    position: { x_mm: number; y_mm: number },
  ) => void;
  onResetView?: (viewId: string) => void;
  /** Hand a press that landed on a dimension grab to that dimension instead of
   * dragging this view. Returns true when the dimension took it. */
  onGrabDimensionId?: (dimensionId: string) => boolean;
  /** Report the dimension grab under the pointer (null = none) so it can show
   * its affordance through this plate. */
  onHoverGrabId?: (dimensionId: string | null) => void;
}) {
  const projection = composedView.projection;
  // Which straight edge (by `edgeKey`) currently reveals its endpoint handles —
  // set on that edge's hover/focus, so handles appear on proximity/intent rather
  // than as a persistent stamp on every corner (frontend-QA P2).
  const [revealKey, setRevealKey] = useState<string | null>(null);

  // --- Drag-to-place ---------------------------------------------------------
  // The view is grabbable to author its position: a live translate follows the
  // pointer (or an arrow-key nudge), and on drop the new CENTRE persists via
  // `onPlaceView` (y-flipped to the y-up SheetViewPlacement convention). The
  // transform is held until the recompose lands the view at its new anchor —
  // the anchor-change effect clears it, so there is no snap-back flash.
  const placeable = onPlaceView !== undefined && viewId !== null;
  const anchorX = composedView.anchor.x_mm;
  const anchorY = composedView.anchor.y_mm;
  const [placement, setPlacement] = useState<{ dx: number; dy: number } | null>(
    null,
  );
  const [frameHover, setFrameHover] = useState(false);
  const [frameFocus, setFrameFocus] = useState(false);
  const placementRef = useRef<{ dx: number; dy: number } | null>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const pending = useRef(false);
  const setPlace = (next: { dx: number; dy: number } | null) => {
    placementRef.current = next;
    setPlacement(next);
  };
  // Clear the local transform once the recompose settles at the new anchor.
  useEffect(() => {
    setPlace(null);
    pending.current = false;
    dragStart.current = null;
  }, [anchorX, anchorY]);

  const commitPlacement = () => {
    const cur = placementRef.current;
    if (
      !pending.current ||
      !placeable ||
      viewId === null ||
      onPlaceView === undefined ||
      cur === null ||
      (cur.dx === 0 && cur.dy === 0)
    ) {
      pending.current = false;
      if (cur && cur.dx === 0 && cur.dy === 0) setPlace(null);
      return;
    }
    pending.current = false;
    onPlaceView(viewId, {
      x_mm: anchorX + cur.dx,
      y_mm: sheetHeightMm - (anchorY + cur.dy),
    });
    // Keep the transform (do not clear) — the anchor-change effect clears it
    // when the composed view lands at its new home.
  };

  const onFramePointerDown = (event: ReactPointerEvent<SVGElement>) => {
    if (!placeable || placementBusy || event.button !== 0) return;
    // STAND ASIDE FOR A DIMENSION GRAB. The sheet needs three tiers of pick
    // priority — view drag plate < dimension grab < geometry — and SVG has no
    // z-index, so paint order can only express two of them. The grab layer is
    // painted ahead of every view (so geometry always wins, whichever view
    // owns it), which puts it behind this plate; and a view's frame is padded
    // out into the gutter, which is exactly where dimensions live, so without
    // this a press on a dimension's value stamp would drag the VIEW. Asking
    // the DOM what is really under the pointer is the missing tier.
    const grabbed = grabUnderPointer(event.clientX, event.clientY);
    if (grabbed !== null && onGrabDimensionId?.(grabbed) === true) {
      event.stopPropagation();
      return;
    }
    const svg = event.currentTarget.ownerSVGElement;
    if (!svg) return;
    dragStart.current = clientPointToSvg(svg, event.clientX, event.clientY);
    pending.current = true;
    setPlace({ dx: 0, dy: 0 });
    event.currentTarget.setPointerCapture(event.pointerId);
    event.stopPropagation();
  };
  const onFramePointerMove = (event: ReactPointerEvent<SVGElement>) => {
    if (dragStart.current === null) {
      // Not dragging: report whether a dimension grab lies UNDER this plate, so
      // the grab can show its own affordance through it (see `DimensionGrab`).
      // Only the id crosses, and only when it changes, so a stationary pointer
      // costs nothing and a moving one costs one hit test.
      onHoverGrabId?.(grabUnderPointer(event.clientX, event.clientY));
      return;
    }
    const svg = event.currentTarget.ownerSVGElement;
    if (!svg) return;
    const p = clientPointToSvg(svg, event.clientX, event.clientY);
    setPlace({ dx: p.x - dragStart.current.x, dy: p.y - dragStart.current.y });
  };
  const onFramePointerUp = (event: ReactPointerEvent<SVGElement>) => {
    if (dragStart.current === null) return;
    dragStart.current = null;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // capture may already be released
    }
    commitPlacement();
  };
  const onFrameKeyDown = (event: ReactKeyboardEvent) => {
    if (!placeable || placementBusy) return;
    const step = event.shiftKey
      ? drawing.placementNudgeMm * 5
      : drawing.placementNudgeMm;
    const base = placementRef.current ?? { dx: 0, dy: 0 };
    let handled = true;
    switch (event.key) {
      case "ArrowLeft":
        pending.current = true;
        setPlace({ dx: base.dx - step, dy: base.dy });
        break;
      case "ArrowRight":
        pending.current = true;
        setPlace({ dx: base.dx + step, dy: base.dy });
        break;
      case "ArrowUp":
        pending.current = true;
        setPlace({ dx: base.dx, dy: base.dy - step });
        break;
      case "ArrowDown":
        pending.current = true;
        setPlace({ dx: base.dx, dy: base.dy + step });
        break;
      case "Enter":
      case " ":
        commitPlacement();
        break;
      case "Escape":
        pending.current = false;
        setPlace(null);
        break;
      default:
        handled = false;
    }
    if (handled) event.preventDefault();
  };

  const failed = composedView.failed;
  // The composer's `view_center` mapped into sheet space — the reference the
  // authored `offset_mm` sign is measured against (`_place_linear_between`).
  const viewAnchorPoint: Point2D = {
    x: composedView.anchor.x_mm,
    y: composedView.anchor.y_mm,
  };
  const composedEdges = composedView.edges ?? [];
  const composedDims = composedView.dimensions ?? [];
  const evalEdges = result?.edges ?? [];

  // Fuse each composed placed edge (VISUAL) with its aligned evaluate edge
  // (PICK provenance) by canonical index — compose + evaluate share the order.
  const svgEdges = composedEdges.map((composed, i) =>
    toSvgEdge(composed, evalEdges[i]),
  );

  // Positional bend key (sheet-metal.md §6): the i-th `bend` edge (in edge-list
  // order) pairs with the i-th bend-table row — never an id join. Number the fold
  // lines here so each carries its `data-bend-index`, mirroring the table's rows.
  let bendCounter = 0;
  const bendIndexByEdge = svgEdges.map((edge) =>
    edge.edgeRole === "bend" ? bendCounter++ : -1,
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

  const bounds = viewGeometryBounds(composedView);
  const pad = drawing.placementPadMm;
  const frame = {
    x: bounds.x - pad,
    y: bounds.y - pad,
    w: bounds.w + pad * 2,
    h: bounds.h + pad * 2,
  };
  const dragging = placement !== null;
  const frameRevealed = placeable && (frameHover || frameFocus || dragging);

  return (
    <g
      data-testid="drawing-view"
      data-view={projection}
      data-view-error={failed ? "true" : "false"}
      data-edge-count={composedEdges.length}
      data-dimension-count={composedDims.length}
      data-placed={placeable && !autoPlace ? "true" : "false"}
      data-dragging={dragging ? "true" : "false"}
      transform={
        dragging ? `translate(${placement.dx} ${placement.dy})` : undefined
      }
      onMouseEnter={placeable ? () => setFrameHover(true) : undefined}
      onMouseLeave={placeable ? () => setFrameHover(false) : undefined}
    >
      {/* Drag plate — a transparent grab surface UNDER the geometry so empty
          interior moves the view, while edges/handles (painted after) keep their
          own picks. Fills the frame so hover reads across the whole view. */}
      {placeable ? (
        <rect
          data-testid="drawing-view-drag"
          data-placement-chrome="frame"
          x={frame.x}
          y={frame.y}
          width={frame.w}
          height={frame.h}
          fill="transparent"
          style={{ cursor: dragging ? "grabbing" : "grab" }}
          onPointerDown={onFramePointerDown}
          onPointerMove={onFramePointerMove}
          onPointerUp={onFramePointerUp}
          onPointerCancel={onFramePointerUp}
          onPointerLeave={() => onHoverGrabId?.(null)}
        />
      ) : null}
      {failed ? (
        <FailedView
          projection={projection}
          anchor={composedView.anchor}
          error={result?.error ?? null}
        />
      ) : (
        <>
          {/* Section cut-face fill UNDER the edges (a non-section view has no
              `hatch`, so this is a no-op there — the `bend_table` additive rule). */}
          {composedView.hatch ? (
            <SectionHatch hatch={composedView.hatch} />
          ) : null}
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
                viewAnchor={viewAnchorPoint}
                bendIndex={bendIndexByEdge[i] ?? -1}
                selected={
                  key !== null &&
                  (key === selectedEdgeKey || armedEdgeKeys.includes(key))
                }
                onReveal={onPickEndpoint ? setRevealKey : undefined}
                onPickEdge={onPickEdge}
              />
            );
          })}
          {composedDims.map((dim, i) =>
            // The one being moved is drawn as the GHOST instead — a sheet that
            // shows the same dimension in two places while you drag it is
            // telling you something untrue about the drawing.
            dim.dimension_id === movingDimensionId ? null : (
              <DimensionGlyph key={dim.dimension_id ?? i} dim={dim} />
            ),
          )}
          {onPickEndpoint && viewId !== null
            ? vertexHandles.map((h) => (
                <VertexHandle
                  key={h.key}
                  at={h.at}
                  projection={projection}
                  viewId={viewId}
                  viewAnchor={viewAnchorPoint}
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
        // Sits in the gutter BETWEEN views, painted after this view's geometry
        // — so it lands on a neighbour's pick band. Ink, not a control.
        pointerEvents="none"
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
      {/* Placement frame + grip + reset — the drag-to-place affordance. Drawn
          LAST so the chrome sits above the geometry; excluded from the export. */}
      {placeable ? (
        <PlacementFrame
          frame={frame}
          revealed={frameRevealed}
          placed={!autoPlace}
          dragging={dragging}
          busy={placementBusy}
          label={composedView.label}
          onGripPointerDown={onFramePointerDown}
          onGripPointerMove={onFramePointerMove}
          onGripPointerUp={onFramePointerUp}
          onGripKeyDown={onFrameKeyDown}
          onGripFocus={() => setFrameFocus(true)}
          onGripBlur={() => {
            setFrameFocus(false);
            commitPlacement();
          }}
          onReset={
            onResetView && viewId !== null
              ? () => onResetView(viewId)
              : undefined
          }
        />
      ) : null}
    </g>
  );
}

/**
 * The view placement frame — a quiet blueprint-blue border (the CAD view-border
 * idiom) that reveals on hover/focus, with a corner grip you drag or nudge with
 * arrow keys, and a "reset to auto-layout" control shown once the view carries a
 * dragged position. Reuses the pick-blue so placement and dimensioning read as
 * one instrument. All chrome carries `data-placement-chrome` so the SVG export
 * strips it — the print is drafting geometry only.
 */
function PlacementFrame({
  frame,
  revealed,
  placed,
  dragging,
  busy,
  label,
  onGripPointerDown,
  onGripPointerMove,
  onGripPointerUp,
  onGripKeyDown,
  onGripFocus,
  onGripBlur,
  onReset,
}: {
  frame: { x: number; y: number; w: number; h: number };
  revealed: boolean;
  placed: boolean;
  dragging: boolean;
  busy: boolean;
  label: string;
  onGripPointerDown: (event: ReactPointerEvent<SVGElement>) => void;
  onGripPointerMove: (event: ReactPointerEvent<SVGElement>) => void;
  onGripPointerUp: (event: ReactPointerEvent<SVGElement>) => void;
  onGripKeyDown: (event: ReactKeyboardEvent) => void;
  onGripFocus: () => void;
  onGripBlur: () => void;
  onReset?: () => void;
}) {
  const grip = drawing.placementGripMm;
  const ink = dragging ? drawing.pickSelected : drawing.pickHover;
  // A placed view keeps a faint corner tick at rest so the manual placement is
  // discoverable without hovering; hover/drag brings up the full frame.
  const showFrame = revealed;
  const showGrip = revealed || placed;
  return (
    <g data-placement-chrome="frame" aria-hidden={showGrip ? undefined : true}>
      {showFrame ? (
        <rect
          data-testid="drawing-view-frame"
          x={frame.x}
          y={frame.y}
          width={frame.w}
          height={frame.h}
          fill="none"
          stroke={ink}
          strokeWidth={drawing.placementFrameWeightMm}
          strokeDasharray={`${drawing.placementFrameDashMm} ${drawing.placementFrameGapMm}`}
          pointerEvents="none"
        />
      ) : null}
      {showGrip ? (
        <g
          role="button"
          tabIndex={0}
          aria-label={`Move the ${label} view — drag, or use arrow keys to nudge`}
          data-testid="drawing-view-grip"
          style={{
            cursor: dragging ? "grabbing" : "grab",
            outline: "none",
            touchAction: "none",
          }}
          onPointerDown={onGripPointerDown}
          onPointerMove={onGripPointerMove}
          onPointerUp={onGripPointerUp}
          onPointerCancel={onGripPointerUp}
          onKeyDown={onGripKeyDown}
          onFocus={onGripFocus}
          onBlur={onGripBlur}
        >
          <rect
            x={frame.x - grip}
            y={frame.y - grip}
            width={grip * 2}
            height={grip * 2}
            fill={revealed || dragging ? drawing.pickSelected : drawing.paper}
            stroke={ink}
            strokeWidth={0.5}
          />
          {/* Move glyph — a small four-way cross, the drag vernacular. */}
          <g
            stroke={revealed || dragging ? drawing.paper : ink}
            strokeWidth={0.4}
            strokeLinecap="round"
          >
            <line
              x1={frame.x - grip * 0.55}
              y1={frame.y}
              x2={frame.x + grip * 0.55}
              y2={frame.y}
            />
            <line
              x1={frame.x}
              y1={frame.y - grip * 0.55}
              x2={frame.x}
              y2={frame.y + grip * 0.55}
            />
          </g>
        </g>
      ) : null}
      {showFrame && placed && onReset ? (
        <g
          role="button"
          tabIndex={0}
          aria-label={`Return the ${label} view to auto-layout`}
          data-testid="drawing-view-reset"
          style={{ cursor: busy ? "default" : "pointer", outline: "none" }}
          onClick={busy ? undefined : onReset}
          onKeyDown={(event) => {
            if (busy) return;
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onReset();
            }
          }}
        >
          <rect
            x={frame.x + frame.w - 15}
            y={frame.y - grip}
            width={15}
            height={grip * 2}
            fill={drawing.paper}
            stroke={ink}
            strokeWidth={0.4}
            opacity={busy ? 0.5 : 1}
          />
          <text
            x={frame.x + frame.w - 15 / 2}
            y={frame.y + 0.9}
            textAnchor="middle"
            dominantBaseline="middle"
            fill={ink}
            fontFamily={font.display}
            fontSize={2.4}
            letterSpacing={0.3}
            opacity={busy ? 0.5 : 1}
          >
            AUTO
          </text>
        </g>
      ) : null}
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
  // Secondary free-text rows (author/date/notes) — the `titleBlockFields` helper
  // is the shared DOM twin of the server's `_tb_fields`, so both stamp the same
  // rows at the same baselines. x offsets match `_TB_FIELD_CAP_DX` (4) /
  // `_TB_FIELD_VAL_DX` (18); a null field is already skipped by the helper.
  const fields = titleBlockFields(block);
  const fieldCaption = {
    fill: drawing.label,
    fontFamily: font.data,
    fontSize: drawing.titleFieldCaptionMm,
    letterSpacing: 0.4,
  };
  const fieldValue = {
    fill: drawing.ink,
    fontFamily: font.data,
    fontSize: drawing.titleFieldValueMm,
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
      {/* Secondary rows — the same additive DRAWN / DATE / NOTES rows the
          SVG/PDF/DXF serializers now emit; the helper already drops null fields. */}
      {fields.map((field) => (
        <g key={field.key}>
          <text x={x + 4} y={y + field.dy} {...fieldCaption}>
            {field.caption}
          </text>
          <text
            data-testid={`title-block-${field.key}`}
            x={x + 18}
            y={y + field.dy}
            {...fieldValue}
          >
            {field.value}
          </text>
        </g>
      ))}
    </g>
  );
}

/** The flat-pattern bend table — the shop's fold instructions, placed at the
 * server-given anchor rect (top-left, the mirror of the title block). A quiet,
 * dense, columnar precision instrument (design mandate §3): one row per bend,
 * in fold-position order, so the i-th row keys POSITIONALLY to the i-th fold
 * line on the blank (sheet-metal.md §6 — never an id join). Values are the
 * unfold's computed geometry, drawn verbatim. Mirrors the server SVG test hooks
 * (`drawing-bend-table`, `drawing-bend-row`) so QA drives one target set. */
function BendTable({ table }: { table: ComposedBendTable }) {
  const { x, y, width: w, height: h, rows } = table;
  const headerH = drawing.bendTableHeaderMm;
  const rowH = drawing.bendTableRowMm;
  // Column left edges DERIVED from the block width (`x + width * fraction`), not
  // magic absolute mm coupled to the fixed 92 mm block: each fraction is a named
  // design token (the server's `_BEND_COL_DX / _BEND_TABLE_W` ratio, one source).
  const frac = drawing.bendTableColumnFractions;
  const col = {
    bend: x + w * frac[0],
    angle: x + w * frac[1],
    radius: x + w * frac[2],
    dir: x + w * frac[3],
    allow: x + w * frac[4],
  };
  const caption = {
    fill: drawing.label,
    fontFamily: font.display,
    fontSize: drawing.bendTableCaptionMm,
    letterSpacing: 0.4,
  } as const;
  const cell = {
    fill: drawing.dimensionText,
    fontFamily: font.data,
    fontSize: drawing.bendTableTextMm,
  } as const;
  const captionY = y + headerH - 2.4;
  return (
    <g
      data-testid="drawing-bend-table"
      aria-label={`Bend table, ${rows.length} bends`}
    >
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        fill={drawing.paper}
        stroke={drawing.ink}
        strokeWidth={drawing.borderWeightMm}
      />
      {/* Header rule (mirrors the server composer). */}
      <line
        x1={x}
        y1={y + headerH}
        x2={x + w}
        y2={y + headerH}
        stroke={drawing.ink}
        strokeWidth={drawing.hiddenWeightMm}
      />
      <text x={col.bend} y={captionY} {...caption}>
        BEND
      </text>
      <text x={col.angle} y={captionY} {...caption}>
        ANGLE
      </text>
      <text x={col.radius} y={captionY} {...caption}>
        RADIUS
      </text>
      <text x={col.dir} y={captionY} {...caption}>
        DIR
      </text>
      <text x={col.allow} y={captionY} {...caption}>
        ALLOW mm
      </text>
      {rows.map((row, i) => {
        const ry = y + headerH + (i + 1) * rowH - 2;
        return (
          <g key={i} data-testid="drawing-bend-row" data-bend-index={String(i)}>
            <text x={col.bend} y={ry} {...cell}>
              {row.bend_id}
            </text>
            <text x={col.angle} y={ry} {...cell}>
              {`${(row.angle_deg + 0).toFixed(1)}°`}
            </text>
            <text x={col.radius} y={ry} {...cell}>
              {`R${(row.radius_mm + 0).toFixed(2)}`}
            </text>
            <text x={col.dir} y={ry} {...cell}>
              {row.direction === "up" ? "UP" : "DOWN"}
            </text>
            <text x={col.allow} y={ry} {...cell}>
              {(row.bend_allowance_mm + 0).toFixed(2)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

/** A free-text note stamped on the sheet at its authored point (design §2.2) —
 * left-anchored graphite ink, a sibling of the title-block value stamp. Drawn
 * VERBATIM from the composed model: the anchor (`x`/`y`) is already in final
 * sheet-mm SVG space, so no transform. Mirrors the server SVG serializer exactly
 * (`data-testid="drawing-note"`, start-anchored, baseline at `y`, `noteTextMm`
 * height, 0.1 letter-spacing) so the on-screen note and the exported note read
 * identically — one placement, one palette, two renderers. */
function SheetNote({ note }: { note: ComposedNote }) {
  return (
    <text
      data-testid="drawing-note"
      x={note.x}
      y={note.y}
      fill={drawing.dimensionText}
      fontFamily={font.data}
      fontSize={drawing.noteTextMm}
      letterSpacing={0.1}
    >
      {note.text}
    </text>
  );
}

/**
 * The sheet's layout-issue banner (audit N2) — stamped down the top-left margin
 * in the composer's own words, at the composer's own anchors. This is the
 * on-paper twin of the SVG/PDF/DXF banner all three server serializers emit, and
 * it carries the SAME `drawing-layout-issue` hook so QA drives one target set;
 * it also means the client-side "export the SVG you see" (`exportSvg.ts`
 * serializes this live node) carries the warning the server export does. An
 * overlapping print used to reach the shop with nothing on it but the overlap.
 *
 * Additive: a clean sheet has no issues, draws nothing, and exports byte-for-byte
 * as it did before.
 */
function SheetBanner({ composed }: { composed: ComposedSheet }) {
  const lines = bannerLines(composed);
  if (lines.length === 0) return null;
  return (
    <g data-testid="drawing-layout-banner">
      {lines.map((line, i) => (
        <text
          key={i}
          data-testid="drawing-layout-issue"
          x={line.x}
          y={line.y}
          fill={line.error ? drawing.dimensionFlag : drawing.label}
          fontFamily={font.data}
          fontSize={BANNER_TEXT_MM}
          letterSpacing={0.2}
        >
          {line.text}
        </text>
      ))}
    </g>
  );
}

/**
 * The in-progress dimension — where it will land if you click here.
 *
 * Drawn in the pick blue the edge under it is already wearing, never the
 * graphite of a placed dimension: a ghost must be unmistakably not-yet-ink. The
 * `rule` tick from the measured midpoint out to the dimension line is the mark
 * that says "you are setting this distance" — the draughtsman's rule on the
 * paper, and the only thing here a finished dimension does not have.
 */
function PlacementGhostLayer({ ghost }: { ghost: PlacementGhost }) {
  return (
    <g
      data-testid="dimension-ghost"
      // Editor-only, exactly like the drag frame: an export taken mid-gesture
      // must carry drafting geometry, never an un-committed proposal.
      data-placement-chrome="ghost"
      pointerEvents="none"
    >
      {ghost.lines.map((l, i) => (
        <line
          key={i}
          data-ghost-role={l.role}
          x1={l.x1}
          y1={l.y1}
          x2={l.x2}
          y2={l.y2}
          stroke={drawing.pickSelected}
          strokeWidth={
            l.role === "dimension"
              ? drawing.dimensionWeightMm
              : drawing.extensionWeightMm
          }
          strokeDasharray={
            l.role === "rule" || l.role === "leader" ? "1.2 1.2" : undefined
          }
          opacity={l.role === "rule" ? 0.65 : 0.9}
        />
      ))}
      {ghost.arrows.map((a, i) => (
        <polygon
          key={i}
          points={a.points.map((p) => `${p.x},${p.y}`).join(" ")}
          fill={drawing.pickSelected}
          opacity={0.9}
        />
      ))}
      {ghost.target ? (
        <g
          stroke={drawing.pickSelected}
          strokeWidth={drawing.dimensionWeightMm}
        >
          <line
            x1={ghost.target.x - GHOST_TARGET_MM}
            y1={ghost.target.y}
            x2={ghost.target.x + GHOST_TARGET_MM}
            y2={ghost.target.y}
          />
          <line
            x1={ghost.target.x}
            y1={ghost.target.y - GHOST_TARGET_MM}
            x2={ghost.target.x}
            y2={ghost.target.y + GHOST_TARGET_MM}
          />
        </g>
      ) : null}
      {/* THE READING, ON THE PAPER. Set upright rather than along the dimension
          line: a placed value stamp rotates with its rule, and a ghost figure
          that does the same would read as ink already laid down. This one is
          the draughtsman's own pencilled note beside the rule — blueprint blue,
          never graphite, on a paper halo so the ghost's own lines cannot cross
          the digits. */}
      {ghost.figure
        ? (() => {
            const w = ghost.figure.text.length * GHOST_FIGURE_MM * 0.62 + 2;
            const h = GHOST_FIGURE_MM + 1.6;
            return (
              <g data-testid="dimension-ghost-offset">
                <rect
                  x={ghost.figure.at.x - w / 2}
                  y={ghost.figure.at.y - h / 2}
                  width={w}
                  height={h}
                  fill={drawing.paper}
                  opacity={0.92}
                />
                <text
                  x={ghost.figure.at.x}
                  y={ghost.figure.at.y}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill={drawing.pickSelected}
                  fontFamily={font.data}
                  fontSize={GHOST_FIGURE_MM}
                  letterSpacing={0.1}
                >
                  {ghost.figure.text}
                </text>
              </g>
            );
          })()
        : null}
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
  placementBusy,
  dimensionGhost,
  movingDimensionId,
  onPickEdge,
  onPickEndpoint,
  onPlaceView,
  onPlacePointer,
  onPlaceCommit,
  onPlaceRelease,
  onGrabDimension,
  onResetView,
  svgRef,
}: DrawingSheetProps) {
  const width = composed.width_mm;
  const height = composed.height_mm;
  const margin = composed.margin_mm;
  const composedViews = composed.views ?? [];
  // Composed views carry no ids, so each is correlated to its persisted ROW by
  // projection (see drawing/views.ts — engineering audit H3): exact because
  // `(sheet_id, projection)` is unique server-side, first-write-wins for any
  // legacy row, and the source of the stable per-VIEW-ID React key below.
  const viewByProjection = viewRowsByProjection(views);
  // Which dimension grab a view's drag plate is currently covering, if any —
  // the plate reports it so the grab can show its affordance through the plate.
  const [hoveredGrabId, setHoveredGrabId] = useState<string | null>(null);

  /**
   * Grab a placed dimension BY ID — the route a view's drag plate uses when a
   * press lands on a dimension it is covering (see `onFramePointerDown`). The
   * lookup lives here because the plate belongs to one view and the dimension
   * under it may belong to another.
   */
  const grabDimensionById = (dimensionId: string): boolean => {
    if (!onGrabDimension || dimensionId === movingDimensionId) return false;
    for (const composedView of composedViews) {
      const row = viewByProjection.get(composedView.projection) ?? null;
      if (row === null) continue;
      for (const dim of composedView.dimensions ?? []) {
        if (dim.kind !== "measured" || dim.dimension_id !== dimensionId) {
          continue;
        }
        onGrabDimension({
          dimensionId,
          viewId: row.id,
          projection: composedView.projection,
          dim,
          viewAnchor: {
            x: composedView.anchor.x_mm,
            y: composedView.anchor.y_mm,
          },
        });
        return true;
      }
    }
    return false;
  };

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
      {/* DIMENSION GRAB TARGETS, in ONE layer under EVERY view.
          A dimension can be dragged anywhere on the sheet, so its grab will
          sooner or later lie across a DIFFERENT view's edge — and SVG has no
          z-index, so the only thing deciding that contest is document order.
          Keeping each grab inside its own view group was not enough and the
          e2e caught it: with the TOP view's dimension dragged onto the FRONT
          view's 40 mm edge, 10 of 18 points along that edge resolved to
          `dimension-grab`. One layer ahead of all the views makes the rule
          sheet-wide instead of per-view: geometry always beats annotation
          chrome, whoever owns it. (The dimension's INK still paints inside its
          view, after the edges, where drafting ink belongs — it is
          `pointer-events: none`, so its order costs no picks.) */}
      {onGrabDimension ? (
        <g data-dimension-grabs="true">
          {composedViews.map((composedView) => {
            const row = viewByProjection.get(composedView.projection) ?? null;
            if (row === null) return null;
            const anchor = {
              x: composedView.anchor.x_mm,
              y: composedView.anchor.y_mm,
            };
            return (composedView.dimensions ?? []).map((dim, i) =>
              dim.dimension_id === movingDimensionId ? null : (
                <DimensionGrab
                  key={`${composedView.projection}:${dim.dimension_id ?? i}`}
                  dim={dim}
                  projection={composedView.projection}
                  viewId={row.id}
                  viewAnchor={anchor}
                  hoveredFromPlate={dim.dimension_id === hoveredGrabId}
                  onGrab={onGrabDimension}
                />
              ),
            );
          })}
        </g>
      ) : null}
      {composedViews.map((composedView) => {
        const row = viewByProjection.get(composedView.projection) ?? null;
        return (
          <SheetView
            key={row?.id ?? composedView.projection}
            composedView={composedView}
            result={resultByProjection.get(composedView.projection)}
            viewId={row?.id ?? null}
            autoPlace={row?.auto_place ?? true}
            sheetHeightMm={height}
            selectedEdgeKey={selectedEdgeKey}
            armedEdgeKeys={armedEdgeKeys ?? []}
            selectedVertexKeys={selectedVertexKeys ?? []}
            endpointPickActive={endpointPickActive ?? false}
            placementBusy={placementBusy ?? false}
            movingDimensionId={movingDimensionId ?? null}
            onPickEdge={onPickEdge}
            onPickEndpoint={onPickEndpoint}
            onPlaceView={onPlaceView}
            onResetView={onResetView}
            onGrabDimensionId={grabDimensionById}
            onHoverGrabId={setHoveredGrabId}
          />
        );
      })}
      {/* Sheet-level ink — the title block, the bend schedule, the notes and the
          layout banner. All of it is painted AFTER every view, so all of it used
          to sit on top of the views' pick targets; none of it is interactive, so
          none of it should ever take a pointer (frontend-QA P2-B/P3-D — drawn
          ink never takes a pick). The banner is stamped LAST, exactly as the
          server serializers order it, so it reads over anything it lands on. */}
      <g data-sheet-ink="true" pointerEvents="none">
        <TitleBlock block={composed.title_block} />
        {composed.bend_table ? <BendTable table={composed.bend_table} /> : null}
        {(composed.notes ?? []).map((note, i) => (
          <SheetNote key={i} note={note} />
        ))}
        <SheetBanner composed={composed} />
      </g>
      {/* The placement gesture: a full-sheet capture plate that owns the pointer
          for as long as the ghost is up, with the ghost painted over it. Nothing
          underneath can take the click — the next click means "here", full
          stop, which is the whole point of the stage. */}
      {dimensionGhost ? (
        <>
          <rect
            data-testid="dimension-place-surface"
            data-placement-chrome="place-surface"
            x={0}
            y={0}
            width={width}
            height={height}
            fill="transparent"
            style={{ cursor: "crosshair" }}
            onPointerMove={(event) => {
              const svg = event.currentTarget.ownerSVGElement;
              if (!svg || !onPlacePointer) return;
              onPlacePointer(
                clientPointToSvg(svg, event.clientX, event.clientY),
              );
            }}
            // The SAME report on pointer DOWN, and it is load-bearing rather
            // than redundant: React treats `pointermove` as a continuous event,
            // so the placement it schedules need not have flushed by the time
            // the discrete `click` after it is handled — and when the move in
            // question was the first one, the commit then read `moved: false`
            // and sent no placement at all, so the composer auto-placed a
            // dimension the user had just dragged somewhere. Measured under
            // load on 2026-08-27: a diameter's value stamp landed 11.76 mm from
            // where it was dropped. `pointerdown` IS discrete, so it flushes
            // before the click, and it carries the same fractional coordinate
            // the ghost was last drawn at — so what commits is what was on the
            // paper, to the sub-pixel.
            onPointerDown={(event) => {
              const svg = event.currentTarget.ownerSVGElement;
              if (!svg || !onPlacePointer) return;
              onPlacePointer(
                clientPointToSvg(svg, event.clientX, event.clientY),
              );
            }}
            // A press-drag ENDS on release, which is the gesture a user tries
            // first on something they can see is draggable. The caller commits
            // only if the placement actually moved, so a bare press (the
            // click-to-grab half of the same gesture) leaves the ghost up and
            // the next click drops it.
            onPointerUp={() => onPlaceRelease?.()}
            onClick={() => onPlaceCommit?.()}
          />
          <PlacementGhostLayer ghost={dimensionGhost} />
        </>
      ) : null}
    </svg>
  );
}
