/**
 * Plane Along Path, client side (PIPE-ALONG-PATH): the basis of a plane normal
 * to a sketch curve at a point along it, KERNEL frame, exactly as
 * `geometry.kernel.datum_path.plane_along_edge` builds it — origin the point
 * at `ratio` of the curve's length (or `distance_mm` along it) from its start,
 * normal its travel direction there (negated by `flip`), `u` the owning
 * sketch's normal (projected off the tangent), `v = normal x u` (build123d).
 *
 * Lines and arcs are placed here; a spline (OCCT's interpolation) or a model
 * edge that is not straight is server-side only, so it returns null and the
 * datum is not offered as a sketch plane until the server's plane exists.
 */
import type { components } from "@loft/ts-client/gateway";

import type { PlaneBasis, Vec3Tuple } from "./plane";

type AlongPath = components["schemas"]["DatumAlongPathParams"];
type Entity = components["schemas"]["SketchParamsV1"]["entities"][number];

function add(a: Vec3Tuple, b: Vec3Tuple, k = 1): Vec3Tuple {
  return [a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k];
}

function cross(a: Vec3Tuple, b: Vec3Tuple): Vec3Tuple {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function dot(a: Vec3Tuple, b: Vec3Tuple): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function normalize(v: Vec3Tuple): Vec3Tuple {
  const n = Math.hypot(v[0], v[1], v[2]);
  return n === 0 ? [0, 0, 0] : [v[0] / n, v[1] / n, v[2] / n];
}

/** A point and travel direction (sketch 2D) at `along` mm, or null. */
function at2d(
  entity: Entity,
  fraction: (length: number) => number | null,
): { p: [number, number]; t: [number, number] } | null {
  if (entity.kind === "line") {
    const dx = entity.end.x - entity.start.x;
    const dy = entity.end.y - entity.start.y;
    const length = Math.hypot(dx, dy);
    const s = fraction(length);
    if (s === null || length === 0) return null;
    return {
      p: [
        entity.start.x + (dx * s) / length,
        entity.start.y + (dy * s) / length,
      ],
      t: [dx / length, dy / length],
    };
  }
  if (entity.kind === "arc" || entity.kind === "circle") {
    const c = entity.center;
    const r =
      entity.kind === "circle"
        ? entity.radius
        : Math.hypot(entity.start.x - c.x, entity.start.y - c.y);
    const a0 =
      entity.kind === "circle"
        ? 0
        : Math.atan2(entity.start.y - c.y, entity.start.x - c.x);
    let sweep = 2 * Math.PI;
    if (entity.kind === "arc") {
      sweep = Math.atan2(entity.end.y - c.y, entity.end.x - c.x) - a0;
      if (sweep <= 0) sweep += 2 * Math.PI;
    }
    const s = fraction(r * sweep);
    if (s === null || r === 0) return null;
    const a = a0 + s / r;
    return {
      p: [c.x + r * Math.cos(a), c.y + r * Math.sin(a)],
      t: [-Math.sin(a), Math.cos(a)],
    };
  }
  return null;
}

/**
 * The basis of an along-path datum on a sketch curve, given the curve's
 * entity and its sketch's (kernel-frame) basis; null when the curve cannot be
 * placed client-side or the distance is past its end.
 */
export function alongPathBasis(
  params: AlongPath,
  entity: Entity,
  sketch: PlaneBasis,
): PlaneBasis | null {
  const fraction = (length: number): number | null => {
    if (params.measure === "ratio") return (params.ratio ?? 0) * length;
    const d = params.distance_mm ?? 0;
    return d > length + 1e-6 ? null : Math.min(d, length);
  };
  const local = at2d(entity, fraction);
  if (local === null) return null;
  const origin = add(
    add(sketch.origin, sketch.u, local.p[0]),
    sketch.v,
    local.p[1],
  );
  const tangent = normalize(
    add(
      [
        sketch.u[0] * local.t[0],
        sketch.u[1] * local.t[0],
        sketch.u[2] * local.t[0],
      ],
      sketch.v,
      local.t[1],
    ),
  );
  const n = sketch.normal;
  const u = normalize(add(n, tangent, -dot(n, tangent)));
  const normal: Vec3Tuple = params.flip
    ? [-tangent[0], -tangent[1], -tangent[2]]
    : tangent;
  return { u, v: cross(normal, u), normal, origin };
}
