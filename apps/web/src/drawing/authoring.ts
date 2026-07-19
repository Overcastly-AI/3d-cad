/**
 * Dimension authoring — the pure pick→type state machine the drawing editor
 * drives, kept out of React so it runs (and is tested) without a DOM.
 *
 * A dimension names model geometry by PICKING it on the sheet (design §3.3).
 * Most types need one pick (a circle → diameter/radius, a straight edge →
 * linear), but two need a pair:
 *
 *   • angular — TWO straight edges; and
 *   • point-to-point linear — TWO edge ENDPOINTS.
 *
 * So the flow is staged. A single edge pick opens the type menu (linear /
 * diameter / radius, plus an "Angle" action that ARMS a second-edge pick). A
 * vertex handle pick starts a point-to-point pair. The SECOND pick of a pair
 * completes it and the gated menu offers the multi-pick type. This module is
 * the single source of truth for that progression; the component only renders
 * the state and dispatches picks.
 */
import type {
  DimensionParams,
  EdgeSignature,
  ProjectedViewEdge,
  ViewProjection,
} from "../api/drawings";

/** One picked, dimensionable straight/circular edge. */
export interface EdgeTarget {
  projection: ViewProjection;
  viewId: string;
  sourceEdge: EdgeSignature;
  primitive: ProjectedViewEdge["primitive"];
  clientX: number;
  clientY: number;
}

/** One picked edge endpoint (a vertex named through an edge — design §3.3). */
export interface EndpointTarget {
  projection: ViewProjection;
  viewId: string;
  sourceEdge: EdgeSignature;
  endpoint: "end_a" | "end_b";
  clientX: number;
  clientY: number;
}

/**
 * The authoring progression. `single-edge` / `angular-ready` / `p2p-ready`
 * show the gated type menu (`anchor` positions it); `arming-angular` /
 * `one-endpoint` show a "pick the second …" hint and keep the sheet live.
 */
export type AuthoringState =
  | { kind: "idle" }
  | { kind: "single-edge"; target: EdgeTarget }
  | { kind: "arming-angular"; edgeA: EdgeTarget }
  | { kind: "angular-ready"; edgeA: EdgeTarget; edgeB: EdgeTarget }
  | { kind: "one-endpoint"; a: EndpointTarget }
  | { kind: "p2p-ready"; a: EndpointTarget; b: EndpointTarget };

/** The idle start state. */
export const IDLE: AuthoringState = { kind: "idle" };

/** The menu action a choice fires (a `start_*` arms a second pick, not authors). */
export type DimensionAction =
  | "linear"
  | "diameter"
  | "radius"
  | "start_angular"
  | "angular"
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
  // A second straight edge completes an armed angular pick (same view only —
  // a dimension lives in one view).
  if (
    state.kind === "arming-angular" &&
    target.primitive === "line" &&
    target.projection === state.edgeA.projection &&
    !sameEdge(target.sourceEdge, state.edgeA.sourceEdge)
  ) {
    return { kind: "angular-ready", edgeA: state.edgeA, edgeB: target };
  }
  // Any other edge pick starts fresh on that single edge.
  return { kind: "single-edge", target };
}

/** Arm a second-edge pick for an angular dimension (from the single-edge menu). */
export function armAngular(state: AuthoringState): AuthoringState {
  if (state.kind === "single-edge" && state.target.primitive === "line") {
    return { kind: "arming-angular", edgeA: state.target };
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
    case "angular-ready":
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
          return ["linear", "start_angular"];
        default:
          return [];
      }
    case "angular-ready":
      return ["angular"];
    case "p2p-ready":
      return ["point_to_point"];
    default:
      return [];
  }
}

/** The "pick the second …" hint for an in-progress pair, or null. */
export function pickHint(state: AuthoringState): string | null {
  switch (state.kind) {
    case "arming-angular":
      return "Pick the second edge for the angle";
    case "one-endpoint":
      return "Pick the second point";
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
    case "arming-angular":
      return [
        {
          projection: state.edgeA.projection,
          sourceEdge: state.edgeA.sourceEdge,
        },
      ];
    case "angular-ready":
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
    return null; // start_angular arms; it does not author
  }
  if (state.kind === "angular-ready" && action === "angular") {
    return {
      viewId: state.edgeA.viewId,
      params: {
        type: "angular",
        edge_a: state.edgeA.sourceEdge,
        edge_b: state.edgeB.sourceEdge,
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
