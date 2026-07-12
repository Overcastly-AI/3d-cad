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
/**
 * A datum feature's OFFSET params (offset-from-origin + optional normal flip).
 * The on-a-face datum variant is `DatumOnFaceParams` (a picked face
 * `SubshapeRef` signature); its plane math lives in {@link faceBasis}.
 */
export type DatumParams = components["schemas"]["DatumOffsetParams"];
/** The stage-1 planar-face fingerprint an on-face datum resolves against. */
export type PlanarFaceSignature = components["schemas"]["PlanarFaceSignature"];

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
    }
  | {
      /**
       * A sketch seated on a picked PLANAR model face, via an `on_face` datum
       * feature. The basis is reconstructed from the face `signature` exactly
       * as the kernel's `resolve_face_plane` derives it (origin = centroid,
       * normal = face normal, x-axis from {@link deterministicXDir}), then
       * expressed in scene coordinates so the ink lands on the rendered body.
       */
      kind: "on_face";
      signature: PlanarFaceSignature;
      /** Signed offset along the face normal (mm); 0 sits on the face. */
      offsetMm: number;
      /** The persisted `on_face` `datum` feature this plane belongs to. */
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

// --- On-face plane math (stage-1 topological naming) -----------------------
//
// A sketch on a picked planar face resolves to the SAME deterministic basis the
// kernel derives (`geometry.kernel.faces._deterministic_x_dir` / `_face_plane`)
// so the drawn 2D→3D mapping matches the server byte-for-byte: origin = face
// area centroid (+ offset along the normal), z_dir = the outward face normal,
// x_dir pinned purely from the normal, y_dir = z_dir × x_dir (build123d). The
// (u,v) parameterisation is frame-independent; only where the ink RENDERS
// differs, so the basis is finally expressed in scene coordinates (below) to
// land exactly on the GLB body face — one enumeration, pick side and resolve
// side (the measurement lesson).

function dot(a: Vec3Tuple, b: Vec3Tuple): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross(a: Vec3Tuple, b: Vec3Tuple): Vec3Tuple {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function normalize(v: Vec3Tuple): Vec3Tuple {
  const len = Math.hypot(v[0], v[1], v[2]);
  return len === 0 ? [0, 0, 0] : [v[0] / len, v[1] / len, v[2] / len];
}

/**
 * A stable in-plane x-axis derived PURELY from a face normal — the exact port
 * of the kernel's `geometry.kernel.faces._deterministic_x_dir` (RESEARCH §9):
 * pick the world axis LEAST aligned with the normal (ties broken by axis order
 * X < Y < Z), project out its normal component, and normalise. A pure function
 * of the normal, so the sketch's 2D→3D basis never varies between rebuilds and
 * always agrees with the server resolver.
 */
export function deterministicXDir(normal: Vec3Tuple): Vec3Tuple {
  const axes: readonly Vec3Tuple[] = [
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
  ];
  let bestIndex = 0;
  let bestAlignment = Infinity;
  for (let i = 0; i < axes.length; i += 1) {
    // Strict `<` keeps the earliest axis on a tie — the kernel's `min` over
    // `(abs(dot), index)`.
    const alignment = Math.abs(dot(axes[i] as Vec3Tuple, normal));
    if (alignment < bestAlignment) {
      bestAlignment = alignment;
      bestIndex = i;
    }
  }
  const axis = axes[bestIndex] as Vec3Tuple;
  const k = dot(axis, normal);
  return normalize([
    axis[0] - normal[0] * k,
    axis[1] - normal[1] * k,
    axis[2] - normal[2] * k,
  ]);
}

/**
 * OCCT world-mm (Z-up) → three.js scene (Y-up): `(x, y, z) → (x, z, −y)`, the
 * SAME rotation build123d bakes into the GLB node. THE one frame transform (the
 * measure overlay's `occtToScene` delegates here — CLAUDE.md DRY rule). Linear,
 * so it applies to direction vectors as well as points; `−0` is normalised so a
 * zero never renders as `-0`.
 */
export function occtToSceneTuple(v: Vec3Tuple): Vec3Tuple {
  return [v[0], v[2], v[1] === 0 ? 0 : -v[1]];
}

/**
 * The scene-frame basis of a sketch seated on a picked planar face. Mirrors the
 * kernel's `resolve_face_plane`: origin = centroid + normal·offset, z = normal,
 * x = {@link deterministicXDir}, y = z × x — computed in OCCT coordinates so the
 * (u,v) mapping equals the server's, then rotated into scene coordinates so the
 * grid, entities, and picks land on the rendered body face.
 */
export function faceBasis(
  signature: PlanarFaceSignature,
  offsetMm: number,
): PlaneBasis {
  const normal: Vec3Tuple = [
    signature.normal.x,
    signature.normal.y,
    signature.normal.z,
  ];
  const centroid: Vec3Tuple = [
    signature.centroid.x,
    signature.centroid.y,
    signature.centroid.z,
  ];
  const xDir = deterministicXDir(normal);
  const yDir = cross(normal, xDir); // build123d y_dir = z_dir × x_dir
  const origin: Vec3Tuple = [
    centroid[0] + normal[0] * offsetMm,
    centroid[1] + normal[1] * offsetMm,
    centroid[2] + normal[2] * offsetMm,
  ];
  return {
    u: occtToSceneTuple(xDir),
    v: occtToSceneTuple(yDir),
    normal: occtToSceneTuple(normal),
    origin: occtToSceneTuple(origin),
  };
}

/** Resolve a viewport plane spec to its placed basis (scene frame for faces). */
export function resolveSpecBasis(spec: SketchPlaneSpec): PlaneBasis {
  switch (spec.kind) {
    case "origin":
      return originBasis(spec.base);
    case "offset":
      return offsetBasis(spec.base, spec.offsetMm, spec.flip);
    case "on_face":
      return faceBasis(spec.signature, spec.offsetMm);
  }
}

/** The persisted plane ref (wire `GeomRef`) for a viewport plane spec. */
export function planeRefFromSpec(spec: SketchPlaneSpec): SketchPlaneRef {
  // Both an offset datum and an on_face datum are referenced by the sketch as a
  // FeatureRef to the persisted `datum` feature — the on_face plane reuses the
  // datum node, not a new sketch-plane mechanism (datum-planes §7).
  return spec.kind === "origin"
    ? { kind: "datum_plane", plane: spec.base }
    : { kind: "feature", feature_id: spec.datumFeatureId };
}

/** A short human label for the chosen plane — the DRO / strip readout. */
export function describePlane(spec: SketchPlaneSpec | null): string {
  if (spec === null) return "—";
  if (spec.kind === "origin") return spec.base;
  if (spec.kind === "on_face") {
    if (spec.offsetMm === 0) return "Face";
    const sign = spec.offsetMm >= 0 ? "+" : "−";
    return `Face ${sign}${Math.abs(spec.offsetMm)}`;
  }
  const sign = spec.offsetMm >= 0 ? "+" : "−";
  const mag = Math.abs(spec.offsetMm);
  return `${spec.base} ${sign}${mag}${spec.flip ? " ⟲" : ""}`;
}

/** An on-face plane spec from a persisted on_face datum's face signature. */
export function faceSpecFromDatum(
  datumFeatureId: string,
  signature: PlanarFaceSignature,
  offsetMm: number,
): SketchPlaneSpec {
  return { kind: "on_face", signature, offsetMm, datumFeatureId };
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
