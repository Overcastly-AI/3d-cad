/**
 * THE PICK RAYCAST, AT THE SIZE OF A REAL PART (PERF-REAL-1).
 *
 * ## The defect
 *
 * Every pick in this viewport — the body hover, the armed `PickSurface`, the
 * face-mark burial walk (`useSurfaceMarkBurial`) and the edge band's occluder
 * — asks one question of one fused mesh: "which triangle does this ray strike
 * first?" Three's `Mesh.raycast` answers it by testing EVERY triangle, and on
 * the gauntlet's `gearbox-11752` that is 399 478 triangles per ray. The burial
 * walk casts one ray per offered face mark before a pick can settle, and up to
 * seventeen for a mark whose centroid is hidden. Measured on that part with
 * the face pick armed, at the tip before this module: ~22 ms of JavaScript per
 * ray, ~10 s of it in every two minutes of the armed pick, and the seat pass
 * had still not settled after eleven minutes.
 *
 * ## The shape of the fix
 *
 * A bounding-volume hierarchy over the mesh's triangles, built ONCE per
 * geometry and cached against it, so a ray visits the handful of leaves it
 * passes through instead of the whole part. A nearest-hit query walks near to
 * far and stops as soon as no unvisited box can hold a nearer hit, which is
 * what every caller but the mate column wants.
 *
 * ## What it must NOT change: the answer
 *
 * The burial oracle's docblock records why a second, cheaper hit-test that
 * disagrees with the pointer's is itself the defect. So this is not a stand-in
 * for the raycast; it is the same raycast with the triangles it could never
 * strike skipped. Each surviving triangle goes through exactly the public
 * steps `Mesh.raycast` takes — the world bounding-sphere gate, the local
 * bounding-box gate, `getVertexPosition`, `Ray.intersectTriangle` with the
 * material's `side`, the near/far clamp and the same intersection record
 * (point, distance, face, faceIndex, barycoord, uv, uv1, normal). Where
 * several triangles tie on distance, the one earliest in the index buffer wins,
 * which is the order three would have reported them in. `pickBvh.test.ts`
 * holds that equivalence against the brute-force raycast on thousands of rays.
 * Checked once on the real gearbox mesh as well (1 200 rays, both sides, from
 * the plane-pick vantage): nearest hit and full hit list identical on every
 * ray, at ~22 ms a ray brute force against ~0.2 ms here, and ~0.25 s to build.
 *
 * A mesh whose vertices move after the fact — morph targets, skinning — is
 * handed back to `Mesh.raycast` untouched: a hierarchy over the rest pose would
 * answer for geometry that is no longer drawn there.
 */
import {
  BackSide,
  FrontSide,
  Matrix4,
  Mesh,
  Ray,
  Sphere,
  Triangle,
  Vector2,
  Vector3,
} from "three";
import type {
  BufferAttribute,
  BufferGeometry,
  Face,
  Intersection,
  InterleavedBufferAttribute,
  Material,
  Raycaster,
} from "three";

/** Triangles per leaf. Small enough to prune well, large enough to stay shallow. */
const LEAF_SIZE = 8;

/**
 * A flattened hierarchy. Node `n` owns `bounds[6n .. 6n+5]` (min xyz, max xyz,
 * padded outward — see `makeNode`). An interior node's children are `left[n]` and
 * `right[n]`; a leaf has `left[n] === -1` and owns `order[start[n] ..
 * start[n] + count[n])`, which are TRIANGLE NUMBERS in index-buffer order
 * (`faceIndex` semantics, so no remapping is ever needed).
 */
export interface TriangleBvh {
  readonly bounds: Float64Array;
  readonly left: Int32Array;
  readonly right: Int32Array;
  readonly start: Uint32Array;
  readonly count: Uint32Array;
  readonly order: Uint32Array;
  readonly nodes: number;
  readonly triangles: number;
}

type PositionAttribute = BufferAttribute | InterleavedBufferAttribute;

interface CachedBvh {
  bvh: TriangleBvh;
  position: PositionAttribute;
  positionVersion: number;
  index: BufferAttribute | null;
  indexVersion: number;
}

const cache = new WeakMap<BufferGeometry, CachedBvh>();

/** How many triangles the geometry defines (ignoring draw range and groups). */
function triangleCount(geometry: BufferGeometry): number {
  const index = geometry.index;
  if (index !== null) return Math.floor(index.count / 3);
  const position = geometry.getAttribute("position") as
    PositionAttribute | undefined;
  return position === undefined ? 0 : Math.floor(position.count / 3);
}

/** Build a hierarchy over every triangle of `geometry`. Exported for tests. */
export function buildTriangleBvh(geometry: BufferGeometry): TriangleBvh {
  const position = geometry.getAttribute("position") as PositionAttribute;
  const index = geometry.index;
  const triangles = triangleCount(geometry);

  // Per-triangle bounds and centroid, read once.
  const triMin = new Float64Array(triangles * 3);
  const triMax = new Float64Array(triangles * 3);
  const centroid = new Float64Array(triangles * 3);
  for (let t = 0; t < triangles; t += 1) {
    for (let axis = 0; axis < 3; axis += 1) {
      triMin[t * 3 + axis] = Infinity;
      triMax[t * 3 + axis] = -Infinity;
    }
    for (let corner = 0; corner < 3; corner += 1) {
      const slot = t * 3 + corner;
      const vertex = index !== null ? index.getX(slot) : slot;
      const x = position.getX(vertex);
      const y = position.getY(vertex);
      const z = position.getZ(vertex);
      const o = t * 3;
      if (x < (triMin[o] as number)) triMin[o] = x;
      if (x > (triMax[o] as number)) triMax[o] = x;
      if (y < (triMin[o + 1] as number)) triMin[o + 1] = y;
      if (y > (triMax[o + 1] as number)) triMax[o + 1] = y;
      if (z < (triMin[o + 2] as number)) triMin[o + 2] = z;
      if (z > (triMax[o + 2] as number)) triMax[o + 2] = z;
    }
    for (let axis = 0; axis < 3; axis += 1) {
      const o = t * 3 + axis;
      centroid[o] = ((triMin[o] as number) + (triMax[o] as number)) / 2;
    }
  }

  const order = new Uint32Array(triangles);
  for (let t = 0; t < triangles; t += 1) order[t] = t;

  // Upper bound on node count for a binary tree with >= 1 triangle per leaf.
  const capacity = Math.max(1, 2 * triangles);
  const bounds = new Float64Array(capacity * 6);
  const left = new Int32Array(capacity).fill(-1);
  const right = new Int32Array(capacity).fill(-1);
  const start = new Uint32Array(capacity);
  const count = new Uint32Array(capacity);
  let nodes = 0;

  const makeNode = (from: number, to: number): number => {
    const n = nodes;
    nodes += 1;
    start[n] = from;
    count[n] = to - from;
    let x0 = Infinity;
    let y0 = Infinity;
    let z0 = Infinity;
    let x1 = -Infinity;
    let y1 = -Infinity;
    let z1 = -Infinity;
    for (let i = from; i < to; i += 1) {
      const o = (order[i] as number) * 3;
      if ((triMin[o] as number) < x0) x0 = triMin[o] as number;
      if ((triMin[o + 1] as number) < y0) y0 = triMin[o + 1] as number;
      if ((triMin[o + 2] as number) < z0) z0 = triMin[o + 2] as number;
      if ((triMax[o] as number) > x1) x1 = triMax[o] as number;
      if ((triMax[o + 1] as number) > y1) y1 = triMax[o + 1] as number;
      if ((triMax[o + 2] as number) > z1) z1 = triMax[o + 2] as number;
    }
    // PAD OUTWARD. The box test must never refuse a ray the triangle test
    // would accept — a hit that grazes an edge lands exactly on the box face,
    // and float rounding in the slab arithmetic can put it a hair outside. A
    // relative pad plus an absolute floor makes the box strictly conservative;
    // a box that is slightly too big costs one extra leaf test, never a miss.
    const pad = Math.max(x1 - x0, y1 - y0, z1 - z0, 1) * 1e-6;
    const b = n * 6;
    bounds[b] = x0 - pad;
    bounds[b + 1] = y0 - pad;
    bounds[b + 2] = z0 - pad;
    bounds[b + 3] = x1 + pad;
    bounds[b + 4] = y1 + pad;
    bounds[b + 5] = z1 + pad;
    return n;
  };

  if (triangles === 0) {
    return {
      bounds: new Float64Array(0),
      left: new Int32Array(0),
      right: new Int32Array(0),
      start: new Uint32Array(0),
      count: new Uint32Array(0),
      order,
      nodes: 0,
      triangles: 0,
    };
  }

  // Iterative top-down build: split each node at the midpoint of its
  // centroids' longest axis, falling back to an even split when every centroid
  // lands on one side (coincident centroids — a fan of slivers).
  const stack: number[] = [makeNode(0, triangles)];
  while (stack.length > 0) {
    const n = stack.pop() as number;
    const from = start[n] as number;
    const to = from + (count[n] as number);
    if (to - from <= LEAF_SIZE) continue;

    let c0x = Infinity;
    let c0y = Infinity;
    let c0z = Infinity;
    let c1x = -Infinity;
    let c1y = -Infinity;
    let c1z = -Infinity;
    for (let i = from; i < to; i += 1) {
      const o = (order[i] as number) * 3;
      const x = centroid[o] as number;
      const y = centroid[o + 1] as number;
      const z = centroid[o + 2] as number;
      if (x < c0x) c0x = x;
      if (x > c1x) c1x = x;
      if (y < c0y) c0y = y;
      if (y > c1y) c1y = y;
      if (z < c0z) c0z = z;
      if (z > c1z) c1z = z;
    }
    const ex = c1x - c0x;
    const ey = c1y - c0y;
    const ez = c1z - c0z;
    const axis = ex >= ey && ex >= ez ? 0 : ey >= ez ? 1 : 2;
    const extent = axis === 0 ? ex : axis === 1 ? ey : ez;
    let mid = from;
    if (extent > 0) {
      const split = (axis === 0 ? c0x : axis === 1 ? c0y : c0z) + extent / 2;
      // Hoare-style partition of `order[from..to)` about `split`.
      let i = from;
      let j = to - 1;
      while (i <= j) {
        if ((centroid[(order[i] as number) * 3 + axis] as number) < split) {
          i += 1;
        } else {
          const swap = order[i] as number;
          order[i] = order[j] as number;
          order[j] = swap;
          j -= 1;
        }
      }
      mid = i;
    }
    if (mid === from || mid === to) mid = (from + to) >> 1;

    left[n] = makeNode(from, mid);
    right[n] = makeNode(mid, to);
    stack.push(left[n] as number, right[n] as number);
  }

  return {
    bounds: bounds.slice(0, nodes * 6),
    left: left.slice(0, nodes),
    right: right.slice(0, nodes),
    start: start.slice(0, nodes),
    count: count.slice(0, nodes),
    order,
    nodes,
    triangles,
  };
}

/**
 * The hierarchy for `geometry`, built on first use and reused until its
 * position or index buffer is replaced or marked dirty. Draw groups and the
 * draw range are read at query time, so re-cutting materials
 * (`setFaceMaterials`) costs no rebuild.
 */
export function triangleBvhOf(geometry: BufferGeometry): TriangleBvh {
  const position = geometry.getAttribute("position") as PositionAttribute;
  const index = geometry.index;
  const held = cache.get(geometry);
  if (
    held !== undefined &&
    held.position === position &&
    held.positionVersion === versionOf(position) &&
    held.index === index &&
    held.indexVersion === (index?.version ?? -1)
  ) {
    return held.bvh;
  }
  const bvh = buildTriangleBvh(geometry);
  cache.set(geometry, {
    bvh,
    position,
    positionVersion: versionOf(position),
    index,
    indexVersion: index?.version ?? -1,
  });
  return bvh;
}

function versionOf(attribute: PositionAttribute): number {
  // An interleaved attribute's version lives on its shared buffer.
  return "isInterleavedBufferAttribute" in attribute &&
    attribute.isInterleavedBufferAttribute === true
    ? attribute.data.version
    : (attribute as BufferAttribute).version;
}

/** Test seam: has a hierarchy been built for this geometry yet? */
export function hasTriangleBvh(geometry: BufferGeometry): boolean {
  return cache.has(geometry);
}

// ---------------------------------------------------------------------------
// The query. Scratch is module-level and reused: a raycast runs per pointer
// move and per burial probe, so it must not allocate beyond its hit records.

const _sphere = new Sphere();
const _sphereHitAt = new Vector3();
const _inverse = new Matrix4();
const _ray = new Ray();
const _vA = new Vector3();
const _vB = new Vector3();
const _vC = new Vector3();
const _point = new Vector3();
const _pointWorld = new Vector3();
let _stack = new Int32Array(128);
let _stackT = new Float64Array(128);

/**
 * Can this mesh use the hierarchy? A mesh whose drawn vertices differ from its
 * position buffer (morph targets, skinning) cannot — see the module docblock.
 */
function accelerable(mesh: Mesh): boolean {
  const geometry = mesh.geometry as BufferGeometry | undefined;
  if (geometry === undefined) return false;
  if (geometry.getAttribute("position") === undefined) return false;
  if ((mesh as { isSkinnedMesh?: boolean }).isSkinnedMesh === true) {
    return false;
  }
  const morph = geometry.morphAttributes.position;
  if (morph !== undefined && morph.length > 0) return false;
  // Three walks a range in steps of 3 FROM ITS START, so a range that begins
  // off a triangle boundary reads vertex triples that are not triangles of the
  // index at all. The hierarchy is built over real triangles and cannot answer
  // for those, so such a mesh keeps three's own walk. Nothing this app builds
  // does it — every draw group is cut at a face boundary.
  if (geometry.drawRange.start % 3 !== 0) return false;
  if (Array.isArray(mesh.material)) {
    for (const group of geometry.groups) {
      if (group.start % 3 !== 0) return false;
    }
  }
  return true;
}

/**
 * The slab test: where the ray enters the box, or +Infinity if it misses (or
 * the box lies entirely behind the origin).
 */
function boxEntry(
  bounds: Float64Array,
  node: number,
  ox: number,
  oy: number,
  oz: number,
  ix: number,
  iy: number,
  iz: number,
): number {
  const b = node * 6;
  let tmin: number;
  let tmax: number;
  if (ix >= 0) {
    tmin = ((bounds[b] as number) - ox) * ix;
    tmax = ((bounds[b + 3] as number) - ox) * ix;
  } else {
    tmin = ((bounds[b + 3] as number) - ox) * ix;
    tmax = ((bounds[b] as number) - ox) * ix;
  }
  let ymin: number;
  let ymax: number;
  if (iy >= 0) {
    ymin = ((bounds[b + 1] as number) - oy) * iy;
    ymax = ((bounds[b + 4] as number) - oy) * iy;
  } else {
    ymin = ((bounds[b + 4] as number) - oy) * iy;
    ymax = ((bounds[b + 1] as number) - oy) * iy;
  }
  // NaN (0 * Infinity: origin on a slab plane of a parallel axis) must not
  // cull — treat it as "inside that slab".
  if (Number.isNaN(tmin)) tmin = -Infinity;
  if (Number.isNaN(tmax)) tmax = Infinity;
  if (Number.isNaN(ymin)) ymin = -Infinity;
  if (Number.isNaN(ymax)) ymax = Infinity;
  if (tmin > ymax || ymin > tmax) return Infinity;
  if (ymin > tmin) tmin = ymin;
  if (ymax < tmax) tmax = ymax;
  let zmin: number;
  let zmax: number;
  if (iz >= 0) {
    zmin = ((bounds[b + 2] as number) - oz) * iz;
    zmax = ((bounds[b + 5] as number) - oz) * iz;
  } else {
    zmin = ((bounds[b + 5] as number) - oz) * iz;
    zmax = ((bounds[b + 2] as number) - oz) * iz;
  }
  if (Number.isNaN(zmin)) zmin = -Infinity;
  if (Number.isNaN(zmax)) zmax = Infinity;
  if (tmin > zmax || zmin > tmax) return Infinity;
  if (zmin > tmin) tmin = zmin;
  if (zmax < tmax) tmax = zmax;
  if (tmax < 0) return Infinity;
  return tmin < 0 ? 0 : tmin;
}

/**
 * `Mesh.raycast`'s gates, verbatim in effect: the world bounding sphere
 * (with `near` recast and the `far` reach), then the ray into local space and
 * the local bounding box. Returns false when the mesh cannot be struck.
 */
function prepareLocalRay(mesh: Mesh, raycaster: Raycaster): boolean {
  const geometry = mesh.geometry;
  if (geometry.boundingSphere === null) geometry.computeBoundingSphere();
  _sphere.copy(geometry.boundingSphere as Sphere);
  _sphere.applyMatrix4(mesh.matrixWorld);
  _ray.copy(raycaster.ray).recast(raycaster.near);
  if (!_sphere.containsPoint(_ray.origin)) {
    if (_ray.intersectSphere(_sphere, _sphereHitAt) === null) return false;
    if (
      _ray.origin.distanceToSquared(_sphereHitAt) >
      (raycaster.far - raycaster.near) ** 2
    ) {
      return false;
    }
  }
  _inverse.copy(mesh.matrixWorld).invert();
  _ray.copy(raycaster.ray).applyMatrix4(_inverse);
  if (
    geometry.boundingBox !== null &&
    !_ray.intersectsBox(geometry.boundingBox)
  ) {
    return false;
  }
  return true;
}

/**
 * One triangle through `Mesh.raycast`'s own per-triangle steps, or null.
 * `faceIndex` and `materialIndex` are set by the caller, as three does.
 */
function strike(
  mesh: Mesh,
  material: Material,
  raycaster: Raycaster,
  a: number,
  b: number,
  c: number,
): Intersection | null {
  mesh.getVertexPosition(a, _vA);
  mesh.getVertexPosition(b, _vB);
  mesh.getVertexPosition(c, _vC);
  const hit =
    material.side === BackSide
      ? _ray.intersectTriangle(_vC, _vB, _vA, true, _point)
      : _ray.intersectTriangle(
          _vA,
          _vB,
          _vC,
          material.side === FrontSide,
          _point,
        );
  if (hit === null) return null;
  _pointWorld.copy(_point).applyMatrix4(mesh.matrixWorld);
  const distance = raycaster.ray.origin.distanceTo(_pointWorld);
  if (distance < raycaster.near || distance > raycaster.far) return null;

  const geometry = mesh.geometry;
  const uv = geometry.attributes["uv"];
  const uv1 = geometry.attributes["uv1"];
  const normal = geometry.attributes["normal"];
  const barycoord = new Vector3();
  Triangle.getBarycoord(_point, _vA, _vB, _vC, barycoord);
  const intersection: Intersection = {
    distance,
    point: _pointWorld.clone(),
    object: mesh,
  };
  if (uv !== undefined) {
    intersection.uv = Triangle.getInterpolatedAttribute(
      uv,
      a,
      b,
      c,
      barycoord,
      new Vector2(),
    ) as Vector2;
  }
  if (uv1 !== undefined) {
    intersection.uv1 = Triangle.getInterpolatedAttribute(
      uv1,
      a,
      b,
      c,
      barycoord,
      new Vector2(),
    ) as Vector2;
  }
  if (normal !== undefined) {
    const n = Triangle.getInterpolatedAttribute(
      normal,
      a,
      b,
      c,
      barycoord,
      new Vector3(),
    ) as Vector3;
    if (n.dot(_ray.direction) > 0) n.multiplyScalar(-1);
    intersection.normal = n;
  }
  const face: Face = { a, b, c, normal: new Vector3(), materialIndex: 0 };
  Triangle.getNormal(_vA, _vB, _vC, face.normal);
  intersection.face = face;
  intersection.barycoord = barycoord;
  return intersection;
}

/**
 * Test one triangle number against every draw group / the draw range that
 * covers it, exactly as `Mesh._computeIntersections` would visit it, pushing
 * each hit to `out`. Returns the local-space ray distance of the nearest hit it
 * pushed, or +Infinity.
 */
function testTriangle(
  mesh: Mesh,
  raycaster: Raycaster,
  triangle: number,
  out: Intersection[],
  accept: ((faceIndex: number) => boolean) | null,
): number {
  const geometry = mesh.geometry;
  const index = geometry.index;
  const drawRange = geometry.drawRange;
  const slot = triangle * 3;
  const limit =
    index !== null
      ? index.count
      : (geometry.getAttribute("position") as PositionAttribute).count;
  const a = index !== null ? index.getX(slot) : slot;
  const b = index !== null ? index.getX(slot + 1) : slot + 1;
  const c = index !== null ? index.getX(slot + 2) : slot + 2;
  if (accept !== null && !accept(triangle)) return Infinity;

  const material = mesh.material;
  if (!Array.isArray(material)) {
    const from = Math.max(0, drawRange.start);
    const to = Math.min(limit, drawRange.start + drawRange.count);
    if (slot < from || slot >= to) return Infinity;
    return visit(mesh, material, null, raycaster, triangle, a, b, c, out);
  }
  let nearest = Infinity;
  for (const group of geometry.groups) {
    const from = Math.max(group.start, drawRange.start);
    const to = Math.min(
      limit,
      Math.min(group.start + group.count, drawRange.start + drawRange.count),
    );
    // `accelerable` guarantees `from` is on a triangle boundary, so the
    // triangle is visited iff its first slot lies in the range — the same
    // `j < to` test three's own loop makes.
    if (slot < from || slot >= to) continue;
    const materialIndex = group.materialIndex ?? 0;
    const groupMaterial = material[materialIndex];
    if (groupMaterial === undefined) continue;
    const local = visit(
      mesh,
      groupMaterial,
      materialIndex,
      raycaster,
      triangle,
      a,
      b,
      c,
      out,
    );
    if (local < nearest) nearest = local;
  }
  return nearest;
}

/**
 * Strike one triangle with one material and record the hit as three would.
 * Returns the hit's LOCAL ray distance (what the walk prunes on), or +Infinity.
 */
function visit(
  mesh: Mesh,
  material: Material,
  materialIndex: number | null,
  raycaster: Raycaster,
  triangle: number,
  a: number,
  b: number,
  c: number,
  out: Intersection[],
): number {
  const hit = strike(mesh, material, raycaster, a, b, c);
  if (hit === null) return Infinity;
  hit.faceIndex = triangle;
  if (materialIndex !== null && hit.face) {
    hit.face.materialIndex = materialIndex;
  }
  out.push(hit);
  return _point.distanceTo(_ray.origin);
}

/**
 * Every hit `Mesh.raycast` would report, pushed in the order it would report
 * them (index-buffer order). Morphing or skinned meshes take three's own path.
 */
export function bvhRaycastAll(
  mesh: Mesh,
  raycaster: Raycaster,
  intersects: Intersection[],
): void {
  if (!accelerable(mesh)) {
    Mesh.prototype.raycast.call(mesh, raycaster, intersects);
    return;
  }
  if (mesh.material === undefined) return;
  if (!prepareLocalRay(mesh, raycaster)) return;
  const bvh = triangleBvhOf(mesh.geometry);
  if (bvh.nodes === 0) return;
  const found: Intersection[] = [];
  walk(bvh, mesh, raycaster, found, null, false);
  found.sort((p, q) => (p.faceIndex ?? 0) - (q.faceIndex ?? 0));
  for (const hit of found) intersects.push(hit);
}

/**
 * The NEAREST hit that `accept` admits, or null — what `Mesh.raycast` followed
 * by a strict-minimum scan over its hits returns, earliest triangle winning a
 * tie. Walks near to far and stops once no box can hold a nearer hit.
 */
export function bvhRaycastFirst(
  mesh: Mesh,
  raycaster: Raycaster,
  accept: (faceIndex: number) => boolean,
): Intersection | null {
  if (!accelerable(mesh)) {
    const all: Intersection[] = [];
    Mesh.prototype.raycast.call(mesh, raycaster, all);
    let best: Intersection | null = null;
    for (const hit of all) {
      if (!accept(hit.faceIndex ?? -1)) continue;
      if (best === null || hit.distance < best.distance) best = hit;
    }
    return best;
  }
  if (mesh.material === undefined) return null;
  if (!prepareLocalRay(mesh, raycaster)) return null;
  const bvh = triangleBvhOf(mesh.geometry);
  if (bvh.nodes === 0) return null;
  const found: Intersection[] = [];
  walk(bvh, mesh, raycaster, found, accept, true);
  let best: Intersection | null = null;
  for (const hit of found) {
    if (
      best === null ||
      hit.distance < best.distance ||
      (hit.distance === best.distance &&
        (hit.faceIndex ?? 0) < (best.faceIndex ?? 0))
    ) {
      best = hit;
    }
  }
  return best;
}

/**
 * The traversal. With `nearestOnly`, children are visited near-first and a
 * box whose entry lies beyond the best local hit so far is skipped — a box
 * whose entry EQUALS it is still visited, so a tie is never lost.
 */
function walk(
  bvh: TriangleBvh,
  mesh: Mesh,
  raycaster: Raycaster,
  out: Intersection[],
  accept: ((faceIndex: number) => boolean) | null,
  nearestOnly: boolean,
): void {
  const ox = _ray.origin.x;
  const oy = _ray.origin.y;
  const oz = _ray.origin.z;
  const ix = 1 / _ray.direction.x;
  const iy = 1 / _ray.direction.y;
  const iz = 1 / _ray.direction.z;
  const { bounds, left, right, start, count, order } = bvh;
  let best = Infinity;

  const rootEntry = boxEntry(bounds, 0, ox, oy, oz, ix, iy, iz);
  if (rootEntry === Infinity) return;
  let top = 0;
  _stack[top] = 0;
  _stackT[top] = rootEntry;
  top += 1;

  while (top > 0) {
    top -= 1;
    const node = _stack[top] as number;
    const entry = _stackT[top] as number;
    if (nearestOnly && entry > best) continue;
    const l = left[node] as number;
    if (l === -1) {
      const from = start[node] as number;
      const to = from + (count[node] as number);
      for (let i = from; i < to; i += 1) {
        const local = testTriangle(
          mesh,
          raycaster,
          order[i] as number,
          out,
          accept,
        );
        if (local < best) best = local;
      }
      continue;
    }
    const r = right[node] as number;
    const tl = boxEntry(bounds, l, ox, oy, oz, ix, iy, iz);
    const tr = boxEntry(bounds, r, ox, oy, oz, ix, iy, iz);
    if (top + 2 > _stack.length) {
      const grownNodes = new Int32Array(_stack.length * 2);
      grownNodes.set(_stack);
      _stack = grownNodes;
      const grownT = new Float64Array(_stackT.length * 2);
      grownT.set(_stackT);
      _stackT = grownT;
    }
    // Push the FAR child first so the near one is popped next.
    const nearIsLeft = tl <= tr;
    const nearNode = nearIsLeft ? l : r;
    const farNode = nearIsLeft ? r : l;
    const nearT = nearIsLeft ? tl : tr;
    const farT = nearIsLeft ? tr : tl;
    if (farT !== Infinity) {
      _stack[top] = farNode;
      _stackT[top] = farT;
      top += 1;
    }
    if (nearT !== Infinity) {
      _stack[top] = nearNode;
      _stackT[top] = nearT;
      top += 1;
    }
  }
}
