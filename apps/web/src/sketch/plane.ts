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
 * TWO FRAMES, AND WHICH FUNCTION HANDS YOU WHICH (FB-7c / FB-9, 2026-08-06).
 * A `PlaneBasis` is just four vectors; it does not say what space they are in,
 * and this module produces BOTH:
 *
 *  · the OCCT / build123d world frame (Z-up, millimetres) — what the kernel
 *    evaluates, and the only frame in which the datum algebra below can mirror
 *    `geometry.kernel.datum` exactly; and
 *  · the SCENE frame (three.js, Y-up) — where the body actually renders,
 *    because the GLB bakes OCCT's Z-up→Y-up rotation ({@link occtToSceneTuple}).
 *
 * The origin/offset/midplane bases were OCCT and `faceBasis` was scene, and
 * nothing in the type said so — so the sketch ink, the origin datum sheets and
 * the live extrude ghost for a sketch on XY all rendered rotated 90° away from
 * the body they belong to. Measured in a real browser: a 10 mm box on XY put
 * the BODY at scene y∈[0,10], z∈[−15.4,16.6] and its own extrude GHOST at
 * y∈[−16.6,15.4], z∈[0,10] — the same solid, un-rotated, hanging through the
 * ground grid and into the bottom view rail.
 *
 * The rule, now enforced by naming rather than by memory: **anything that
 * renders takes a `scene*` entry point** ({@link sceneOriginBasis},
 * {@link resolveSpecBasis}, {@link resolveDatumSceneBasis}, {@link faceBasis});
 * the un-prefixed algebra ({@link originBasis}, {@link offsetBasis},
 * {@link offsetFromBasis}, {@link midplaneBasis}, {@link resolveDatumBasis}) is
 * the KERNEL frame and exists so the client's plane math stays byte-comparable
 * with the server's. One rotation, applied once, at the boundary.
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
/**
 * Any datum feature's params — the full discriminated union. Used by
 * {@link resolveDatumBasis} to resolve a datum plane of ANY kind (offset,
 * offset-from-another-datum, or midplane) to its placed basis client-side, the
 * SAME math the kernel's `geometry.kernel.datum` resolves server-side (one
 * plane-math source, two renderers — CLAUDE.md design mandate 2).
 */
export type AnyDatumParams =
  | components["schemas"]["DatumOffsetParams"]
  | components["schemas"]["DatumOnFaceParams"]
  | components["schemas"]["DatumOffsetFromParams"]
  | components["schemas"]["DatumMidplaneParams"];
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
    }
  | {
      /**
       * A sketch seated on an already-resolved datum feature of ANY kind
       * (offset-from-another-datum or midplane) whose placed basis was resolved
       * by {@link resolveDatumBasis}. The basis is carried so the sketcher +
       * camera place the sheet without re-walking the datum table, and the wire
       * ref is a `FeatureRef` to the datum — the SAME slot offset/on_face use.
       */
      kind: "datum";
      /** The persisted `datum` feature this plane belongs to. */
      datumFeatureId: string;
      /** A short readout label (the datum feature's name). */
      label: string;
      /**
       * The datum's resolved sketch basis, in SCENE coordinates (Y-up) — it is
       * carried so the sketcher and camera can place the sheet without
       * re-walking the datum table, and both of those draw. Minted by
       * {@link resolveDatumSceneBasis}.
       */
      basis: PlaneBasis;
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

/**
 * Slide an already-resolved base plane `offsetMm` along its OWN normal, with an
 * optional flip — the offset-CHAINING rule (`kind: "offset_from"`). The exact
 * port of the kernel's `geometry.kernel.datum.offset_plane`: `Plane.offset`
 * shifts the origin by `normal * offsetMm` preserving u/normal; `flip` reverses
 * the normal (and v), keeping u. Generalizes {@link offsetBasis} from an origin
 * datum to any resolved base, so an offset off a midplane or a chained offset
 * resolves to the byte-identical composite the server evaluates.
 */
export function offsetFromBasis(
  base: PlaneBasis,
  offsetMm: number,
  flip: boolean,
): PlaneBasis {
  const { u, v, normal, origin } = base;
  const placed: Vec3Tuple = [
    origin[0] + normal[0] * offsetMm + 0,
    origin[1] + normal[1] * offsetMm + 0,
    origin[2] + normal[2] * offsetMm + 0,
  ];
  if (!flip) return { u, v, normal, origin: placed };
  return {
    u,
    v: [-v[0], -v[1], -v[2]],
    normal: [-normal[0], -normal[1], -normal[2]],
    origin: placed,
  };
}

/** Documented parallelism bound — the port of `MIDPLANE_PARALLEL_TOLERANCE`. */
const MIDPLANE_PARALLEL_TOLERANCE = 1e-9;

/**
 * The plane midway between two resolved planes — the exact port of the kernel's
 * `geometry.kernel.datum.midplane_between` (datum-planes §7a), so the client
 * preview and the server body agree. PARALLEL sides (incl. anti-parallel): the
 * midway plane, normal = side `a`'s normal, origin = the midpoint of the two
 * origins. NON-PARALLEL sides: the angular-bisector plane through their
 * intersection line, normal = normalize(n_a + n_b), origin = the min-norm point
 * of the two plane equations. `x_dir` is pinned from the normal by
 * {@link deterministicXDir} (the on_face rule; sign-symmetric so `flip` keeps
 * +u and flips +v). TOTAL over any two valid planes.
 */
export function midplaneBasis(
  a: PlaneBasis,
  b: PlaneBasis,
  flip: boolean,
): PlaneBasis {
  const nA = normalize(a.normal);
  const nB = normalize(b.normal);
  const crossLen = Math.hypot(...cross(nA, nB));
  let origin: Vec3Tuple;
  let normal: Vec3Tuple;
  if (crossLen <= MIDPLANE_PARALLEL_TOLERANCE) {
    // PARALLEL (incl. anti-parallel and identical/coplanar sides).
    origin = [
      (a.origin[0] + b.origin[0]) * 0.5 + 0,
      (a.origin[1] + b.origin[1]) * 0.5 + 0,
      (a.origin[2] + b.origin[2]) * 0.5 + 0,
    ];
    normal = nA;
  } else {
    // NON-PARALLEL: bisector through the intersection line (min-norm point).
    const dA = dot(nA, a.origin);
    const dB = dot(nB, b.origin);
    const cosAB = dot(nA, nB);
    const denom = 1 - cosAB * cosAB;
    const s = (dA - cosAB * dB) / denom;
    const t = (dB - cosAB * dA) / denom;
    origin = [
      nA[0] * s + nB[0] * t + 0,
      nA[1] * s + nB[1] * t + 0,
      nA[2] * s + nB[2] * t + 0,
    ];
    normal = normalize([nA[0] + nB[0], nA[1] + nB[1], nA[2] + nB[2]]);
  }
  if (flip) normal = [-normal[0], -normal[1], -normal[2]];
  const u = deterministicXDir(normal);
  const v = cross(normal, u); // build123d y_dir = z_dir × x_dir
  return { u, v, normal, origin };
}

/**
 * Resolve a datum feature of ANY kind to its placed sketch basis (world
 * build123d frame), by walking the datum table exactly as the kernel does:
 * `offset` from an origin datum, `offset_from` off another resolved datum, or a
 * `midplane` between two resolved sides (an origin datum or an earlier datum).
 * Returns null for a reference the client cannot resolve here — an `on_face`
 * datum (its basis is a scene-frame {@link faceBasis} the sketch-on-face flow
 * owns) or a face-picked midplane side — and for a missing/cyclic reference (the
 * `seen` guard; the strict-backward rule means real trees never cycle).
 */
export function resolveDatumBasis(
  datumFeatureId: string,
  byId: ReadonlyMap<string, AnyDatumParams>,
  seen: ReadonlySet<string> = new Set(),
): PlaneBasis | null {
  if (seen.has(datumFeatureId)) return null;
  const params = byId.get(datumFeatureId);
  if (params === undefined) return null;
  const next = new Set(seen).add(datumFeatureId);
  switch (params.kind) {
    case "offset":
      return offsetBasis(params.base, params.offset_mm, params.flip);
    case "offset_from": {
      const parent = resolveDatumBasis(params.base.feature_id, byId, next);
      return parent === null
        ? null
        : offsetFromBasis(parent, params.offset_mm, params.flip);
    }
    case "midplane": {
      const a = resolveMidplaneSide(params.a, byId, next);
      const b = resolveMidplaneSide(params.b, byId, next);
      return a === null || b === null ? null : midplaneBasis(a, b, params.flip);
    }
    case "on_face":
      // The on_face basis is a scene-frame faceBasis owned by the
      // sketch-on-face flow; not resolvable in this world-frame walk.
      return null;
  }
}

/**
 * {@link resolveDatumBasis}, rotated into SCENE coordinates — the renderer's
 * entry point for a datum FeatureRef. The walk itself stays in the kernel frame
 * (it has to: `deterministicXDir` picks a WORLD axis, and the client's choice
 * must equal the server's or a midplane-seated sketch's u/v would mean
 * something different at each end).
 */
export function resolveDatumSceneBasis(
  datumFeatureId: string,
  byId: ReadonlyMap<string, AnyDatumParams>,
): PlaneBasis | null {
  const basis = resolveDatumBasis(datumFeatureId, byId);
  return basis === null ? null : occtToSceneBasis(basis);
}

/** One side of a midplane (an origin datum, an earlier datum, or a face). */
type MidplaneSide = components["schemas"]["DatumMidplaneParams"]["a"];

/** Resolve one midplane side (an origin datum or an earlier datum) to a basis. */
function resolveMidplaneSide(
  side: MidplaneSide,
  byId: ReadonlyMap<string, AnyDatumParams>,
  seen: ReadonlySet<string>,
): PlaneBasis | null {
  switch (side.kind) {
    case "datum_plane":
      return originBasis(side.plane);
    case "feature":
      return resolveDatumBasis(side.feature_id, byId, seen);
    case "subshape":
      // A face-picked side — deferred (needs the scene-frame faceBasis).
      return null;
  }
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
 * The INVERSE of {@link occtToSceneTuple}: three.js scene (Y-up) → OCCT world-mm
 * (Z-up), `(x, y, z) → (x, −z, y)`.
 *
 * It lives here, beside its forward twin, because this file is THE one
 * OCCT↔scene rotation and a second copy of a frame transform is how a hole ends
 * up 0.065 mm out (CLAUDE.md DRY rule). Needed the moment a pick reports a
 * point in the SCENE — hole free placement raycasts the drawn surface, and the
 * hit point has to come back to the kernel's frame before it can be written as
 * a `HoleParamsV1.position`.
 */
export function sceneToOcctTuple(v: Vec3Tuple): Vec3Tuple {
  return [v[0], v[2] === 0 ? 0 : -v[2], v[1]];
}

/**
 * A whole basis, rotated OCCT (Z-up) → scene (Y-up). The rotation is linear and
 * proper (det +1), so it carries u/v/normal as directions and `origin` as a
 * point, and a right-handed basis stays right-handed — which the extrude ghost
 * depends on, since it orients local +Z onto `normal`.
 *
 * THE one place the kernel-frame datum algebra becomes something a renderer may
 * use. Everything a mesh, a line or a camera is built from goes through here
 * (or through {@link faceBasis}, which converts its own result).
 */
export function occtToSceneBasis(basis: PlaneBasis): PlaneBasis {
  return {
    u: occtToSceneTuple(basis.u),
    v: occtToSceneTuple(basis.v),
    normal: occtToSceneTuple(basis.normal),
    origin: occtToSceneTuple(basis.origin),
  };
}

/**
 * The origin datum's basis IN SCENE COORDINATES — what every renderer wants.
 *
 * `originBasis("XY")` is the kernel's XY: normal +Z in a Z-up world. On screen
 * that plane is the GROUND (the adaptive grid's own plane), so its scene normal
 * is +Y. Drawing an XY sheet — or an XY sketch's ink, or its extrude ghost —
 * from the un-rotated basis stands it up vertically, at right angles to the
 * body the same sketch produced.
 */
export function sceneOriginBasis(base: DatumPlaneName): PlaneBasis {
  return occtToSceneBasis(originBasis(base));
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

/**
 * Resolve a viewport plane spec to its placed basis IN SCENE COORDINATES — the
 * renderer's entry point (sketch ink, grid, pointer catcher, camera pose).
 *
 * This function used to mix frames: `on_face` came back in scene coordinates
 * and the other three in the kernel's, so the same call site got a basis 90°
 * apart depending on which plane the user had picked (FB-9). Every branch is
 * the scene frame now; the kernel-frame algebra is one call in.
 */
export function resolveSpecBasis(spec: SketchPlaneSpec): PlaneBasis {
  switch (spec.kind) {
    case "origin":
      return sceneOriginBasis(spec.base);
    case "offset":
      return occtToSceneBasis(offsetBasis(spec.base, spec.offsetMm, spec.flip));
    case "on_face":
      return faceBasis(spec.signature, spec.offsetMm);
    case "datum":
      // Already scene-frame: `resolveDatumSceneBasis` is what mints it.
      return spec.basis;
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
  if (spec.kind === "datum") return spec.label;
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

/** A reusable datum plane already in a part's feature tree — id + name + the
 * resolved plane spec (a `FeatureRef` on the wire). The shape the sketch plane
 * picker (`SketchStrip`) and the section-view author both offer. */
export interface DatumPlaneOption {
  id: string;
  name: string;
  spec: SketchPlaneSpec;
}

/** One feature tree node, narrowed to what datum enumeration reads. */
type DatumFeatureNode = components["schemas"]["FeatureResponse"];

/**
 * The reusable datum planes in a part's feature tree, resolved to their placed
 * bases by the SAME plane-math the kernel evaluates (offset / offset-from-a-
 * datum / midplane over origin + datum sides). An `offset` datum carries a rich
 * readout ("XY +30") via its spec; every other client-resolvable datum is
 * offered by its resolved basis. An `on_face` datum (or a face-picked midplane
 * side) resolves server-side only, so it is absent here and simply not offered.
 *
 * The ONE derivation both the sketch plane picker and the section-view author
 * read — so a datum FeatureRef means exactly the same plane in both flows (DRY:
 * a section's plane reuses the EXACT `GeomRef` union a sketch's plane uses).
 */
export function resolveDatumPlaneOptions(
  features: readonly DatumFeatureNode[],
): DatumPlaneOption[] {
  const byId = new Map<string, AnyDatumParams>();
  for (const feature of features) {
    if (feature.feature.type === "datum") {
      byId.set(feature.id, feature.feature.params);
    }
  }
  const options: DatumPlaneOption[] = [];
  for (const feature of features) {
    if (feature.feature.type !== "datum") continue;
    const params = feature.feature.params;
    if (params.kind === "offset") {
      options.push({
        id: feature.id,
        name: feature.name,
        spec: offsetSpecFromDatum(feature.id, params),
      });
      continue;
    }
    // Scene frame: the spec's `basis` is carried straight to the sketcher and
    // the section author, both of which draw with it.
    const basis = resolveDatumSceneBasis(feature.id, byId);
    if (basis === null) continue;
    options.push({
      id: feature.id,
      name: feature.name,
      spec: {
        kind: "datum",
        datumFeatureId: feature.id,
        label: feature.name,
        basis,
      },
    });
  }
  return options;
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
