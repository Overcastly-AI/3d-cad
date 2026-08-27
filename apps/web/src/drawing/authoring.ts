/**
 * Dimension authoring — the pure pick→type state machine the drawing editor
 * drives, kept out of React so it runs (and is tested) without a DOM.
 *
 * A dimension names model geometry by PICKING it on the sheet (design §3.3).
 * Most types need one pick (a circle → diameter/radius, a straight edge →
 * linear), but three need a pair:
 *
 *   • angular — TWO straight edges;
 *   • edge-to-edge linear — TWO parallel straight edges (the wall thickness of a
 *     shelled part, FB-10); and
 *   • point-to-point linear — TWO edge ENDPOINTS.
 *
 * So the flow is staged. A single edge pick opens the type menu (linear /
 * diameter / radius, plus "Angle" and "Distance to edge", either of which ARMS
 * a second-edge pick). A vertex handle pick starts a point-to-point pair. The
 * SECOND pick of a pair completes it and the gated menu offers BOTH two-edge
 * types — the arming choice orders them, it never locks you in, so a user who
 * meant thickness and clicked "Angle" is one item away rather than restarting.
 * This module is the single source of truth for that progression; the component
 * only renders the state and dispatches picks.
 *
 * The progression ends in a PLACE stage (REACH-3). Choosing a type used to POST
 * immediately and let the auto engine decide which side of the geometry the
 * dimension sat on — the authored `DimensionPlacement` the contract has always
 * carried was never sent, so a user could not put a dimension anywhere. Now the
 * type choice arms {@link AuthoringState} `placing`: the ghost tracks the
 * pointer, the perpendicular distance becomes `offset_mm` (or the pointer itself
 * becomes `text_pos`), and click/Enter commits. Escape returns to the state the
 * placement began from, so backing out of the PLACEMENT never destroys the PICK.
 */
import { drawing } from "@loft/design";

import type {
  DimensionParams,
  EdgeSignature,
  ProjectedViewEdge,
  SheetPoint,
  ViewProjection,
} from "../api/drawings";
import type { Point2D } from "./layout";
import { offsetAt, perpendicularFoot, type PlaceTarget } from "./placement";

export type { PlaceTarget };

/**
 * The composed sheet-mm geometry of a picked edge, carried on the pick so the
 * PLACE stage can measure against the SAME coordinates the composer placed
 * (`ComposedView` is already in final sheet-SVG space — no transform needed).
 */
export interface PickGeometry {
  /** Composed endpoints in start→end order (a straight edge only). */
  line: { a: Point2D; b: Point2D } | null;
  /** Composed centre + radius (a circle / arc only). */
  circle: { center: Point2D; radius: number } | null;
  /** The view's composed centre — the composer's `view_center`, mapped. */
  viewAnchor: Point2D;
}

/** One picked, dimensionable straight/circular edge. */
export interface EdgeTarget {
  projection: ViewProjection;
  viewId: string;
  sourceEdge: EdgeSignature;
  primitive: ProjectedViewEdge["primitive"];
  clientX: number;
  clientY: number;
  /**
   * Where this edge sits on the composed sheet. OPTIONAL on purpose: a pick
   * that cannot supply it (a caller with no composed geometry to hand) simply
   * skips the PLACE stage and authors at auto placement — byte-identical to the
   * pre-REACH-3 flow, so no pick path can regress into a dead end.
   */
  geometry?: PickGeometry;
}

/** One picked edge endpoint (a vertex named through an edge — design §3.3). */
export interface EndpointTarget {
  projection: ViewProjection;
  viewId: string;
  sourceEdge: EdgeSignature;
  endpoint: "end_a" | "end_b";
  clientX: number;
  clientY: number;
  /** This endpoint's composed sheet position (see {@link EdgeTarget.geometry}). */
  at?: Point2D;
  /** The view's composed centre. */
  viewAnchor?: Point2D;
}

/** Which two-edge dimension the user reached for — it ORDERS the ready menu. */
export type PairIntent = "angular" | "edge_to_edge";

/**
 * The authoring progression. `single-edge` / `pair-ready` / `p2p-ready`
 * show the gated type menu (`anchor` positions it); `arming-pair` /
 * `one-endpoint` show a "pick the second …" hint and keep the sheet live;
 * `placing` is the final stage — the measurement is settled and the user is
 * putting it on the paper.
 */
export type AuthoringState =
  | { kind: "idle" }
  | { kind: "single-edge"; target: EdgeTarget }
  | { kind: "arming-pair"; edgeA: EdgeTarget; intent: PairIntent }
  | {
      kind: "pair-ready";
      edgeA: EdgeTarget;
      edgeB: EdgeTarget;
      intent: PairIntent;
    }
  | { kind: "one-endpoint"; a: EndpointTarget }
  | { kind: "p2p-ready"; a: EndpointTarget; b: EndpointTarget }
  | {
      kind: "placing";
      viewId: string;
      /** The authored params WITHOUT placement; folded in on commit. */
      base: DimensionParams;
      target: PlaceTarget;
      /**
       * Has the user actually MOVED the placement? Until they have, committing
       * sends no placement at all and the composer auto-places exactly as it
       * always did — so "pick, choose, Enter" is byte-identical to the flow
       * before this stage existed, and the new control costs nobody anything.
       */
      moved: boolean;
      /** The state Escape returns to — the pick survives a cancelled placement. */
      from: AuthoringState;
    };

/** The idle start state. */
export const IDLE: AuthoringState = { kind: "idle" };

/** The menu action a choice fires (a `start_*` arms a second pick, not authors). */
export type DimensionAction =
  | "linear"
  | "diameter"
  | "radius"
  | "start_angular"
  | "start_edge_to_edge"
  | "angular"
  | "edge_to_edge"
  | "point_to_point";

const sameEdge = (a: EdgeSignature, b: EdgeSignature): boolean =>
  a.end_a.x === b.end_a.x &&
  a.end_a.y === b.end_a.y &&
  a.end_a.z === b.end_a.z &&
  a.end_b.x === b.end_b.x &&
  a.end_b.y === b.end_b.y &&
  a.end_b.z === b.end_b.z &&
  a.curve === b.curve;

const sameEndpoint = (a: EndpointTarget, b: EndpointTarget): boolean =>
  a.endpoint === b.endpoint && sameEdge(a.sourceEdge, b.sourceEdge);

/** Fold an edge pick into the authoring state (design §3.1 pick model). */
export function pickEdge(
  state: AuthoringState,
  target: EdgeTarget,
): AuthoringState {
  // A second straight edge completes an armed two-edge pick (same view only —
  // a dimension lives in one view).
  if (
    state.kind === "arming-pair" &&
    target.primitive === "line" &&
    target.projection === state.edgeA.projection &&
    !sameEdge(target.sourceEdge, state.edgeA.sourceEdge)
  ) {
    return {
      kind: "pair-ready",
      edgeA: state.edgeA,
      edgeB: target,
      intent: state.intent,
    };
  }
  // Any other edge pick starts fresh on that single edge.
  return { kind: "single-edge", target };
}

/**
 * Arm a second-edge pick from the single-edge menu. `intent` records which
 * two-edge dimension was reached for so the ready menu leads with it — both are
 * offered either way (a mis-entry is never a dead end, CLAUDE.md flow rule).
 */
export function armPair(
  state: AuthoringState,
  intent: PairIntent,
): AuthoringState {
  if (state.kind === "single-edge" && state.target.primitive === "line") {
    return { kind: "arming-pair", edgeA: state.target, intent };
  }
  return state;
}

/** Fold an endpoint pick into the authoring state (design §3.3 point-to-point). */
export function pickEndpoint(
  state: AuthoringState,
  target: EndpointTarget,
): AuthoringState {
  if (
    state.kind === "one-endpoint" &&
    target.projection === state.a.projection &&
    !sameEndpoint(target, state.a)
  ) {
    return { kind: "p2p-ready", a: state.a, b: target };
  }
  return { kind: "one-endpoint", a: target };
}

/** The menu anchor (viewport px) for a state that shows the type menu, or null. */
export function menuAnchor(
  state: AuthoringState,
): { x: number; y: number } | null {
  switch (state.kind) {
    case "single-edge":
      return { x: state.target.clientX, y: state.target.clientY };
    case "pair-ready":
      return { x: state.edgeB.clientX, y: state.edgeB.clientY };
    case "p2p-ready":
      return { x: state.b.clientX, y: state.b.clientY };
    default:
      return null;
  }
}

/** The type actions the gated menu offers for a state (empty = no menu). */
export function menuActions(state: AuthoringState): DimensionAction[] {
  switch (state.kind) {
    case "single-edge":
      switch (state.target.primitive) {
        case "circle":
          return ["diameter", "radius"];
        case "arc":
          return ["radius"];
        case "line":
          return ["linear", "start_angular", "start_edge_to_edge"];
        default:
          return [];
      }
    case "pair-ready":
      // BOTH two-edge types, the armed intent first. Geometry is the authority on
      // whether the pair is parallel (it is a property of the CURRENT body), so
      // the menu never pre-judges it — an unparallel pair comes back as the typed
      // `dimension_not_parallel` on the sheet rather than a number.
      return state.intent === "edge_to_edge"
        ? ["edge_to_edge", "angular"]
        : ["angular", "edge_to_edge"];
    case "p2p-ready":
      return ["point_to_point"];
    default:
      return [];
  }
}

/** The "pick the second …" hint for an in-progress pair, or null. */
export function pickHint(state: AuthoringState): string | null {
  switch (state.kind) {
    case "arming-pair":
      return state.intent === "edge_to_edge"
        ? "Pick the second edge to measure across"
        : "Pick the second edge for the angle";
    case "one-endpoint":
      return "Pick the second point";
    case "placing":
      // The pick is done; the sentence changes to the next thing to DO, in the
      // same chip, so the flow reads as one continued gesture rather than a new
      // mode the user has to notice they are in.
      return state.target.mode === "offset"
        ? "Click to place the dimension"
        : "Click to place the value";
    default:
      return null;
  }
}

/** The edge keys (`projection:signature`) highlighted for the current state. */
export function armedSignatures(
  state: AuthoringState,
): { projection: ViewProjection; sourceEdge: EdgeSignature }[] {
  switch (state.kind) {
    case "single-edge":
      return [
        {
          projection: state.target.projection,
          sourceEdge: state.target.sourceEdge,
        },
      ];
    case "arming-pair":
      return [
        {
          projection: state.edgeA.projection,
          sourceEdge: state.edgeA.sourceEdge,
        },
      ];
    case "pair-ready":
      return [
        {
          projection: state.edgeA.projection,
          sourceEdge: state.edgeA.sourceEdge,
        },
        {
          projection: state.edgeB.projection,
          sourceEdge: state.edgeB.sourceEdge,
        },
      ];
    // The picked geometry stays lit while you place against it — losing the
    // highlight the moment you start placing would read as a lost pick.
    case "placing":
      return armedSignatures(state.from);
    default:
      return [];
  }
}

/** The endpoint refs (edge + end) highlighted for the current point-to-point pick. */
export function selectedEndpoints(state: AuthoringState): EndpointTarget[] {
  switch (state.kind) {
    case "one-endpoint":
      return [state.a];
    case "p2p-ready":
      return [state.a, state.b];
    case "placing":
      return selectedEndpoints(state.from);
    default:
      return [];
  }
}

/**
 * Build the create-payload for the chosen `action` against the current state —
 * the view it authors on plus the discriminated `DimensionParams` (design §3).
 * Returns null for a state/action that does not author (e.g. `start_angular`,
 * which only arms the next pick).
 */
export function buildDimension(
  state: AuthoringState,
  action: DimensionAction,
): { viewId: string; params: DimensionParams } | null {
  if (state.kind === "single-edge") {
    const { viewId, sourceEdge } = state.target;
    if (action === "linear") {
      return {
        viewId,
        params: {
          type: "linear",
          measurement: { mode: "edge_length", edge: sourceEdge },
        },
      };
    }
    if (action === "diameter") {
      return { viewId, params: { type: "diameter", edge: sourceEdge } };
    }
    if (action === "radius") {
      return { viewId, params: { type: "radius", edge: sourceEdge } };
    }
    return null; // a start_* action arms the next pick; it does not author
  }
  if (state.kind === "pair-ready" && action === "angular") {
    return {
      viewId: state.edgeA.viewId,
      params: {
        type: "angular",
        edge_a: state.edgeA.sourceEdge,
        edge_b: state.edgeB.sourceEdge,
      },
    };
  }
  if (state.kind === "pair-ready" && action === "edge_to_edge") {
    return {
      viewId: state.edgeA.viewId,
      params: {
        type: "linear",
        measurement: {
          mode: "edge_to_edge",
          edge_a: state.edgeA.sourceEdge,
          edge_b: state.edgeB.sourceEdge,
        },
      },
    };
  }
  if (state.kind === "p2p-ready" && action === "point_to_point") {
    return {
      viewId: state.a.viewId,
      params: {
        type: "linear",
        measurement: {
          mode: "point_to_point",
          a: { signature: state.a.sourceEdge, endpoint: state.a.endpoint },
          b: { signature: state.b.sourceEdge, endpoint: state.b.endpoint },
        },
      },
    };
  }
  return null;
}

// ---------------------------------------------------------------------------
// The PLACE stage (REACH-3)
// ---------------------------------------------------------------------------

/** Sheet-mm step an arrow key moves a placement — the sheet's nudge token. */
export const PLACE_NUDGE_MM = drawing.placementNudgeMm;

/** Seat a text ghost this far off the feature before the pointer first moves. */
const TEXT_SEAT_MM = drawing.dimensionOffsetMm;

/**
 * Where the chosen `action` would be PLACED against the current pick, or null
 * when this state/action pair cannot be placed by hand — either it does not
 * author at all (a `start_*` arming choice) or the pick carried no composed
 * geometry, in which case the caller authors at auto placement as before.
 *
 * The initial offset/seat is the composer's own default (`dimensionOffsetMm`),
 * so the ghost appears exactly where the dimension would have landed without
 * this stage: the user is adjusting a real proposal, not starting from nothing.
 */
export function placementTarget(
  state: AuthoringState,
  action: DimensionAction,
): PlaceTarget | null {
  if (state.kind === "single-edge") {
    const geom = state.target.geometry;
    if (geom === undefined) return null;
    if (action === "linear" && geom.line) {
      return {
        mode: "offset",
        span: geom.line,
        viewAnchor: geom.viewAnchor,
        offsetMm: TEXT_SEAT_MM,
      };
    }
    if ((action === "diameter" || action === "radius") && geom.circle) {
      const { center, radius } = geom.circle;
      return {
        mode: "text",
        leaderFrom: center,
        // Seated ABOVE the hole (sheet space is y-down) and clear of its rim.
        textPos: { x: center.x, y: center.y - radius - TEXT_SEAT_MM },
      };
    }
    return null;
  }
  if (state.kind === "pair-ready") {
    const a = state.edgeA.geometry;
    const b = state.edgeB.geometry;
    if (a === undefined || b === undefined) return null;
    if (action === "edge_to_edge" && a.line && b.line) {
      // Across the wall: from the first edge's midpoint, square onto the
      // second edge's supporting line — the composer's own span.
      const p = {
        x: (a.line.a.x + a.line.b.x) / 2,
        y: (a.line.a.y + a.line.b.y) / 2,
      };
      const q = perpendicularFoot(p, b.line.a, b.line.b);
      if (q === null) return null;
      return {
        mode: "offset",
        span: { a: p, b: q },
        viewAnchor: a.viewAnchor,
        offsetMm: TEXT_SEAT_MM,
      };
    }
    if (action === "angular" && a.line && b.line) {
      const seat = {
        x: (a.line.a.x + a.line.b.x + b.line.a.x + b.line.b.x) / 4,
        y: (a.line.a.y + a.line.b.y + b.line.a.y + b.line.b.y) / 4,
      };
      return {
        mode: "text",
        leaderFrom: seat,
        textPos: { x: seat.x, y: seat.y - TEXT_SEAT_MM },
      };
    }
    return null;
  }
  if (state.kind === "p2p-ready" && action === "point_to_point") {
    const { at: a, viewAnchor } = state.a;
    const { at: b } = state.b;
    if (a === undefined || b === undefined || viewAnchor === undefined) {
      return null;
    }
    return {
      mode: "offset",
      span: { a, b },
      viewAnchor,
      offsetMm: TEXT_SEAT_MM,
    };
  }
  return null;
}

/** Enter the PLACE stage for an authored dimension (see {@link placementTarget}). */
export function beginPlacement(
  state: AuthoringState,
  viewId: string,
  base: DimensionParams,
  target: PlaceTarget,
): AuthoringState {
  return { kind: "placing", viewId, base, target, moved: false, from: state };
}

/** Track the pointer (composed sheet mm) into the live placement. */
export function movePlacement(
  state: AuthoringState,
  pointer: Point2D,
): AuthoringState {
  if (state.kind !== "placing") return state;
  const t = state.target;
  const target: PlaceTarget =
    t.mode === "offset"
      ? {
          ...t,
          offsetMm: offsetAt(t.span.a, t.span.b, t.viewAnchor, pointer),
        }
      : { ...t, textPos: pointer };
  return { ...state, target, moved: true };
}

/** Kill floating-point dust so a quantised value is the value it prints. */
const clean = (n: number): number => Math.round(n * 1e6) / 1e6;

/**
 * The nearest multiple of `step` to `value` — the drafting grid a nudge lands
 * on.
 *
 * The nudge used to ADD the step to whatever fraction the drag had left behind,
 * which is a different and much weaker promise: from a real drag it measured
 * `-23.71 -> -22.71 -> -17.71`, so **-25.00 was not reachable at all**. The
 * damage is not the ugly number, it is that two dimensions placed by hand could
 * never be given the SAME offset, so a chain of them could not be lined up —
 * which is most of what drafting is (frontend-QA 2026-08-27, P1-D). Quantising
 * first means the first press lands on the grid and every press after it stays
 * there, at whatever step the modifier chose.
 */
export function quantise(value: number, step: number): number {
  if (!Number.isFinite(step) || step <= 0) return value;
  return clean(Math.round(value / step) * step);
}

/**
 * Nudge the live placement by one keyboard step — the keyboard parity for the
 * drag. `dx`/`dy` are the arrow-key direction (-1/0/+1) in SCREEN sense (up is
 * -y, as on the sheet); an offset placement reads the vertical axis as
 * "further out / further in" because that is the only degree of freedom it has.
 *
 * The value is QUANTISED to `step` before the step is applied, so the grid is
 * the same one whatever the pointer left behind (see {@link quantise}).
 */
export function nudgePlacement(
  state: AuthoringState,
  dx: number,
  dy: number,
  step: number = PLACE_NUDGE_MM,
): AuthoringState {
  if (state.kind !== "placing") return state;
  const t = state.target;
  if (t.mode === "offset") {
    // Up / Right push the dimension line further onto the `away` side.
    const sense = dy !== 0 ? -dy : dx;
    if (sense === 0) return state;
    return {
      ...state,
      target: {
        ...t,
        offsetMm: clean(quantise(t.offsetMm, step) + sense * step),
      },
      moved: true,
    };
  }
  if (dx === 0 && dy === 0) return state;
  // BOTH axes quantise, not only the one being moved: a text seat nudged only
  // sideways would otherwise keep a fractional y for ever, and two value stamps
  // that cannot share a y cannot be lined up.
  return {
    ...state,
    target: {
      ...t,
      textPos: {
        x: clean(quantise(t.textPos.x, step) + dx * step),
        y: clean(quantise(t.textPos.y, step) + dy * step),
      },
    },
    moved: true,
  };
}

/**
 * Set the live offset to an exact typed value — the precision fallback the
 * mandate asks for beside the direct manipulation ("Fusion's extrude is a
 * draggable arrow; the numeric field is the precision fallback").
 *
 * Not applicable to a text placement: `text_pos` is a POINT, and its precision
 * route is the quantised nudge above rather than one scalar field.
 */
export function setPlacementOffset(
  state: AuthoringState,
  offsetMm: number,
): AuthoringState {
  if (state.kind !== "placing" || state.target.mode !== "offset") return state;
  if (!Number.isFinite(offsetMm)) return state;
  return {
    ...state,
    target: { ...state.target, offsetMm: clean(offsetMm) },
    moved: true,
  };
}

/** Back out of the PLACE stage, keeping the pick that led to it. */
export function cancelPlacement(state: AuthoringState): AuthoringState {
  return state.kind === "placing" ? state.from : state;
}

/** The live offset (mm) of an offset placement — the sheet's readout. */
export function placementOffsetMm(state: AuthoringState): number | null {
  if (state.kind !== "placing" || state.target.mode !== "offset") return null;
  return state.target.offsetMm;
}

/** The live text seat of a text placement — the sheet's readout. */
export function placementTextPos(state: AuthoringState): SheetPoint | null {
  if (state.kind !== "placing" || state.target.mode !== "text") return null;
  return {
    x_mm: state.target.textPos.x,
    y_mm: state.target.textPos.y,
  };
}

/** Round a placement coordinate to 0.01 mm — finer than the paper can show. */
const mm = (n: number): number => Math.round(n * 100) / 100;

/**
 * What a commit sends: the view and the params, placement folded in — or the
 * bare params when the user never moved the placement, so an untouched
 * "pick, choose, Enter" is the pre-REACH-3 auto-placed dimension exactly.
 */
export function commitParams(
  state: AuthoringState,
): { viewId: string; params: DimensionParams } | null {
  if (state.kind !== "placing") return null;
  return {
    viewId: state.viewId,
    params: state.moved ? withPlacement(state.base, state.target) : state.base,
  };
}

/**
 * Fold the live placement into the params the create call sends.
 *
 * An offset that rounds to exactly 0 is sent WITHOUT a placement: `offset_mm ==
 * 0` is the composer's own "auto-place me" sentinel (`_build_dimension_
 * annotation_auto`), so pinning a dimension to zero offset is not expressible —
 * omitting the field says the same thing honestly instead of encoding a value
 * the server will ignore.
 */
export function withPlacement(
  base: DimensionParams,
  target: PlaceTarget,
): DimensionParams {
  if (target.mode === "offset") {
    const offset_mm = mm(target.offsetMm);
    return offset_mm === 0 ? base : { ...base, placement: { offset_mm } };
  }
  return {
    ...base,
    placement: {
      offset_mm: 0,
      text_pos: { x_mm: mm(target.textPos.x), y_mm: mm(target.textPos.y) },
    },
  };
}
