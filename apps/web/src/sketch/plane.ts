/**
 * Datum-plane math — the ONE mapping between sketch-plane (u,v) mm and world
 * xyz mm, shared by the pointer raycast, the entity renderers, and the
 * camera rig. Generalized (BACKLOG #2b) from the three origin datums to
 * "origin datum OR offset datum feature": a resolved `PlaneBasis` now carries
 * an `origin` term, so a sketch can sit on a plane that is NOT through
 * `[0,0,0]`.
 *
 * The orientation triples follow build123d's `Plane.XY` / `.XZ` / `.YZ`
 * exactly (x_dir = u, normal = u × v). An offset datum keeps its base's
 * orientation and slides the origin along the base normal by `offset_mm`
 * (the kernel's `DATUM_PLANES[base].offset(offset_mm)`); `flip` reverses the
 * normal (negating v, keeping u — build123d's `y_dir = z_dir × x_dir`), so
 * the TS viewport and the kernel `resolve_sketch_plane` agree exactly
 * (docs/design/datum-planes.md §3a/§8/§11.3 — one plane-math source, two
 * renderers):
 *
 *   XY: u=+X v=+Y normal=+Z
 *   XZ: u=+X v=+Z normal=−Y
 *   YZ: u=+Y v=+Z normal=+X
 *
 * Pure math, no three.js imports — unit-testable in node.
 */
import type { components } from "@loft/ts-client/gateway";

export type DatumPlaneName = components["schemas"]["DatumPlaneRef"]["plane"];
export type Point2D = components["schemas"]["Point2D"];
/** The sketch `plane` slot on the wire: an origin datum OR a datum FeatureRef. */
export type SketchPlaneRef = components["schemas"]["SketchParamsV1"]["plane"];
/** A datum feature's v1 params (offset-from-origin + optional normal flip). */
export type DatumParams = components["schemas"]["DatumParamsV1"];

export type Vec3Tuple = readonly [number, number, number];

/** Orientation-only axis triple for an origin datum (no placement). */
export interface PlaneAxes {
  /** Sketch +u axis in world space. */
  u: Vec3Tuple;
  /** Sketch +v axis in world space. */
  v: Vec3Tuple;
  /** Plane normal (u × v) — the extrude "normal" direction. */
  normal: Vec3Tuple;
}

/** A fully-placed sketch plane: orientation plus a world-space origin. */
export interface PlaneBasis extends PlaneAxes {
  /** Plane origin in world mm (origin datums: [0,0,0]; offset: normal·offset). */
  origin: Vec3Tuple;
}

export const DATUM_PLANES: readonly DatumPlaneName[] = ["XY", "XZ", "YZ"];

/** The three origin datums' orientation triples (through the world origin). */
export const PLANE_AXES: Record<DatumPlaneName, PlaneAxes> = {
  XY: { u: [1, 0, 0], v: [0, 1, 0], normal: [0, 0, 1] },
  XZ: { u: [1, 0, 0], v: [0, 0, 1], normal: [0, -1, 0] },
  YZ: { u: [0, 1, 0], v: [0, 0, 1], normal: [1, 0, 0] },
};

/**
 * The three origin datum bases, placed at the world origin. Kept as an export
 * (its historical name) for the origin-datum path; offset datums resolve
 * through {@link offsetBasis}.
 */
export const PLANE_BASES: Record<DatumPlaneName, PlaneBasis> = {
  XY: { ...PLANE_AXES.XY, origin: [0, 0, 0] },
  XZ: { ...PLANE_AXES.XZ, origin: [0, 0, 0] },
  YZ: { ...PLANE_AXES.YZ, origin: [0, 0, 0] },
};

/**
 * A sketch's chosen plane, in the viewport's own vocabulary: one of the three
 * origin datums, OR an offset datum feature (base + signed offset + flip) that
 * a `datum` feature persists and the sketch references by id.
 */
export type SketchPlaneSpec =
  | { kind: "origin"; base: DatumPlaneName }
  | {
      kind: "offset";
      base: DatumPlaneName;
      offsetMm: number;
      flip: boolean;
      /** The persisted `datum` feature this plane belongs to. */
      datumFeatureId: string;
    };

/** The origin datum basis (through world zero). */
export function originBasis(base: DatumPlaneName): PlaneBasis {
  return PLANE_BASES[base];
}

/**
 * The resolved basis of an offset datum: the base orientation slid along its
 * normal by `offsetMm`, with `flip` reversing the normal (and v). Mirrors the
 * kernel's `DATUM_PLANES[base].offset(offset_mm)` + z_dir flip exactly.
 */
export function offsetBasis(
  base: DatumPlaneName,
  offsetMm: number,
  flip: boolean,
): PlaneBasis {
  const { u, v, normal } = PLANE_AXES[base];
  // `+ 0` normalizes any `-0` (e.g. 0 * -12) to `+0` so readouts never show
  // "-0" and the origin compares cleanly.
  const origin: Vec3Tuple = [
    normal[0] * offsetMm + 0,
    normal[1] * offsetMm + 0,
    normal[2] * offsetMm + 0,
  ];
  if (!flip) return { u, v, normal, origin };
  return {
    u,
    v: [-v[0], -v[1], -v[2]],
    normal: [-normal[0], -normal[1], -normal[2]],
    origin,
  };
}

/** Resolve a viewport plane spec to its placed world basis. */
export function resolveSpecBasis(spec: SketchPlaneSpec): PlaneBasis {
  return spec.kind === "origin"
    ? originBasis(spec.base)
    : offsetBasis(spec.base, spec.offsetMm, spec.flip);
}

/** The persisted plane ref (wire `GeomRef`) for a viewport plane spec. */
export function planeRefFromSpec(spec: SketchPlaneSpec): SketchPlaneRef {
  return spec.kind === "origin"
    ? { kind: "datum_plane", plane: spec.base }
    : { kind: "feature", feature_id: spec.datumFeatureId };
}

/** A short human label for the chosen plane — the DRO / strip readout. */
export function describePlane(spec: SketchPlaneSpec | null): string {
  if (spec === null) return "—";
  if (spec.kind === "origin") return spec.base;
  const sign = spec.offsetMm >= 0 ? "+" : "−";
  const mag = Math.abs(spec.offsetMm);
  return `${spec.base} ${sign}${mag}${spec.flip ? " ⟲" : ""}`;
}

/** An offset plane spec from a persisted datum feature's params. */
export function offsetSpecFromDatum(
  datumFeatureId: string,
  params: DatumParams,
): SketchPlaneSpec {
  return {
    kind: "offset",
    base: params.base,
    offsetMm: params.offset_mm,
    flip: params.flip,
    datumFeatureId,
  };
}

/** Sketch-plane (u,v) mm → world xyz mm (`origin + u·x + v·y`). */
export function planeToWorld(
  basis: PlaneBasis,
  point: Point2D,
): [number, number, number] {
  const { u, v, origin } = basis;
  return [
    origin[0] + u[0] * point.x + v[0] * point.y,
    origin[1] + u[1] * point.x + v[1] * point.y,
    origin[2] + u[2] * point.x + v[2] * point.y,
  ];
}

/** World xyz mm → sketch-plane (u,v) mm (projection onto the plane axes). */
export function worldToPlane(basis: PlaneBasis, world: Vec3Tuple): Point2D {
  const { u, v, origin } = basis;
  const dx = world[0] - origin[0];
  const dy = world[1] - origin[1];
  const dz = world[2] - origin[2];
  return {
    x: u[0] * dx + u[1] * dy + u[2] * dz,
    y: v[0] * dx + v[1] * dy + v[2] * dz,
  };
}

export interface CameraPose {
  position: [number, number, number];
  /** Camera up = the sketch +v axis, so +u reads left→right on screen. */
  up: [number, number, number];
  target: [number, number, number];
}

/** Normal-on camera pose for 2D authoring at `distance` mm from the plane. */
export function planeCameraPose(
  basis: PlaneBasis,
  distance: number,
): CameraPose {
  const { v, normal, origin } = basis;
  return {
    position: [
      origin[0] + normal[0] * distance,
      origin[1] + normal[1] * distance,
      origin[2] + normal[2] * distance,
    ],
    up: [v[0], v[1], v[2]],
    target: [origin[0], origin[1], origin[2]],
  };
}

/** Snap a value to the grid step; step <= 0 disables snapping. */
export function snapValue(value: number, stepMm: number): number {
  if (stepMm <= 0) return value;
  const snapped = Math.round(value / stepMm) * stepMm;
  // Normalize -0 so readouts and payloads never show "-0".
  return snapped === 0 ? 0 : snapped;
}

/** Snap a plane point to the grid step. */
export function snapPoint(point: Point2D, stepMm: number): Point2D {
  return { x: snapValue(point.x, stepMm), y: snapValue(point.y, stepMm) };
}
