/**
 * GLB → BufferGeometry pipeline for the viewport, kept free of React so the
 * failure paths are unit-testable. A corrupt payload that leaves a stale
 * model on screen while the inspector shows fresh numbers is the worst CAD
 * failure mode — every parse here must end in exactly one visible outcome.
 *
 * FACE IDENTITY is the other load-bearing job of this module. Every downstream
 * face reference — `on_face` datums, shell openings, hole placement,
 * sketch-on-face, the feature-localized selection tint — is keyed on a face
 * ORDINAL that must mean the same face here as it does in the kernel's
 * `body.faces()` order. The kernel ships the face partition of the mesh two
 * ways and this module normalises both into one lookup (`faceStarts`):
 *
 *  * **fused** (PERF-4b, the kernel's `tessellate.fuse_faces`): a few large
 *    primitives, each carrying its per-face triangle counts in
 *    `extras.LOFT_face_triangles`; and
 *  * **unfused** (what OCCT writes, and what the kernel still emits for
 *    triangle-dense parts): one primitive per B-rep face.
 *
 * Both give the same ordinals for the same body — that equality is asserted
 * against real kernel output in `glbGeometry.test.ts`.
 */
import {
  BufferGeometry,
  EdgesGeometry,
  Float32BufferAttribute,
  Mesh,
} from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

/** GLB scenes are metres (glTF spec); the app works in millimetres. */
const METRES_TO_MM = 1000;

/**
 * glTF primitive `extras` key carrying a fused primitive's per-face triangle
 * counts, in face order. Mirrors `FACE_TRIANGLES_KEY` in
 * `services/geometry/src/geometry/kernel/tessellate.py` — this string is the
 * whole contract between the two ends.
 */
const FACE_TRIANGLES_KEY = "LOFT_face_triangles";

/**
 * Where `faceStarts` caches the face partition. Cumulative index-buffer
 * offsets, length `faces + 1`: face `i` owns index range
 * `[starts[i], starts[i + 1])`.
 */
const FACE_STARTS_KEY = "loftFaceStarts";

/**
 * Parse GLB bytes off the wire into one render-ready BufferGeometry, scaled
 * to mm. The scene's meshes are baked through their world matrices (OCCT adds
 * a Z-up→Y-up node rotation) and merged into one buffer. Embedded materials
 * are disposed — the surface material comes from the design tokens, same
 * palette as the DOM.
 *
 * The merged geometry carries the body's FACE PARTITION (see the module doc):
 * `faceStarts` gives face `i`'s index range, and the initial draw groups are
 * one per face so `group ordinal === face ordinal === OverlayFace.index`.
 * `setFaceMaterials` later rewrites those groups into the minimum number of
 * runs the current material assignment needs — the face lookup does not depend
 * on the groups, so collapsing them costs nothing and saves draw calls.
 *
 * Rejects on corrupt/truncated payloads; resolves `null` when the scene has
 * no renderable mesh. Callers must route both to a visible error state —
 * prefer `loadGlbGeometry`, which does this and never rejects.
 */
export async function parseGlbGeometry(
  glb: ArrayBuffer,
): Promise<BufferGeometry | null> {
  const gltf = await new GLTFLoader().parseAsync(glb, "");
  gltf.scene.updateMatrixWorld(true);
  const parts: BufferGeometry[] = [];
  const tables: (readonly number[] | null)[] = [];
  gltf.scene.traverse((object) => {
    if (object instanceof Mesh) {
      const mesh = object as Mesh;
      const clone = mesh.geometry.clone().applyMatrix4(mesh.matrixWorld);
      parts.push(clone);
      tables.push(faceTriangleTable(mesh.geometry));
      mesh.geometry.dispose();
      const material = mesh.material;
      for (const m of Array.isArray(material) ? material : [material]) {
        m.dispose();
      }
    }
  });
  if (parts.length === 0) {
    return null;
  }
  const geometry = mergeGeometries(parts, true);
  for (const part of parts) {
    part.dispose();
  }
  if (geometry === null) {
    return null;
  }
  applyFacePartition(geometry, tables);
  geometry.scale(METRES_TO_MM, METRES_TO_MM, METRES_TO_MM);
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

/** A fused primitive's per-face triangle counts, or `null` when unfused. */
function faceTriangleTable(source: BufferGeometry): readonly number[] | null {
  const table: unknown = source.userData[FACE_TRIANGLES_KEY];
  if (!Array.isArray(table)) return null;
  return table.every((value) => typeof value === "number" && value >= 0)
    ? (table as readonly number[])
    : null;
}

/**
 * Record the merged geometry's face partition and lay one draw group per face.
 *
 * `mergeGeometries(parts, true)` leaves one group per SOURCE PRIMITIVE, which
 * is one face only on the unfused path. When every part shipped a face table
 * the groups are re-cut along it; the tables are checked against the actual
 * merged index ranges first, because a face partition that disagrees with the
 * buffer would mis-resolve picks silently — the failure this module exists to
 * prevent. A mismatch falls back to per-primitive groups.
 */
function applyFacePartition(
  geometry: BufferGeometry,
  tables: readonly (readonly number[] | null)[],
): void {
  const groups = geometry.groups;
  const starts: number[] = [];
  let ok = groups.length === tables.length;
  for (let part = 0; ok && part < groups.length; part += 1) {
    const group = groups[part];
    const table = tables[part];
    if (group === undefined || table === undefined || table === null) {
      ok = false;
      break;
    }
    let offset = group.start;
    for (const triangles of table) {
      starts.push(offset);
      offset += triangles * 3;
    }
    ok = offset === group.start + group.count;
  }
  if (!ok) {
    // Unfused (or an unreadable table): one primitive per face already.
    geometry.userData[FACE_STARTS_KEY] = startsFromGroups(geometry);
    return;
  }
  const total = groups.reduce((sum, group) => sum + group.count, 0);
  starts.push(total);
  const table = Uint32Array.from(starts);
  geometry.userData[FACE_STARTS_KEY] = table;
  geometry.clearGroups();
  for (let face = 0; face + 1 < table.length; face += 1) {
    geometry.addGroup(
      table[face] as number,
      (table[face + 1] as number) - (table[face] as number),
      0,
    );
  }
}

function startsFromGroups(geometry: BufferGeometry): Uint32Array {
  const groups = geometry.groups;
  const starts = new Uint32Array(groups.length + 1);
  groups.forEach((group, index) => {
    starts[index] = group.start;
    starts[index + 1] = group.start + group.count;
  });
  return starts;
}

/**
 * The body's face partition: cumulative index-buffer offsets, length
 * `faceCount + 1`, so face `i` owns `[starts[i], starts[i + 1])`.
 *
 * Geometries from `parseGlbGeometry` carry this; anything else (a hand-built
 * test geometry) is read from its draw groups, which is the same thing before
 * `setFaceMaterials` collapses them.
 */
export function faceStarts(geometry: BufferGeometry): Uint32Array {
  const cached: unknown = geometry.userData[FACE_STARTS_KEY];
  if (cached instanceof Uint32Array) return cached;
  return startsFromGroups(geometry);
}

/** Number of B-rep faces the merged geometry is partitioned into. */
export function faceCount(geometry: BufferGeometry): number {
  const starts = faceStarts(geometry);
  return starts.length === 0 ? 0 : starts.length - 1;
}

/**
 * The face ordinal owning triangle `triangle` (a `ThreeEvent.faceIndex`), or
 * `null` when it falls outside the partition.
 *
 * Binary search, not the linear group scan this replaced: hover fires per
 * pointer move and the scan was O(faces) — 2 006 comparisons per move on the
 * heat-sink part, on the main thread, to answer one pick.
 */
export function faceOrdinalOfTriangle(
  geometry: BufferGeometry,
  triangle: number,
): number | null {
  const starts = faceStarts(geometry);
  const faces = starts.length - 1;
  if (faces < 1) return null;
  const target = triangle * 3;
  if (target < (starts[0] as number) || target >= (starts[faces] as number)) {
    return null;
  }
  let low = 0;
  let high = faces - 1;
  while (low < high) {
    const mid = (low + high + 1) >> 1;
    if ((starts[mid] as number) <= target) low = mid;
    else high = mid - 1;
  }
  // Zero-triangle faces share a start with their successor; walk to the face
  // that actually owns the triangle.
  while (low + 1 < faces && (starts[low + 1] as number) <= target) low += 1;
  return low;
}

/**
 * Re-cut the draw groups so each one covers a maximal RUN of consecutive faces
 * sharing a material index — the minimum number of groups that still renders
 * the requested per-face materials.
 *
 * Draw calls follow groups, not faces: three.js pushes one render item per
 * group whenever a mesh has a material ARRAY, so per-face groups meant one
 * draw call per B-rep face the moment a body was ghosted, hidden, or
 * feature-selected (2 006 on the heat-sink part). Faces of one body are
 * contiguous in face order, so the four-way body/selection split collapses to
 * a handful of runs. Face identity is unaffected — it lives in `faceStarts`.
 */
export function setFaceMaterials(
  geometry: BufferGeometry,
  materialOf: (face: number) => number,
): void {
  const starts = faceStarts(geometry);
  const faces = starts.length - 1;
  if (faces < 1) return;
  geometry.clearGroups();
  let runFace = 0;
  let runMaterial = materialOf(0);
  for (let face = 1; face <= faces; face += 1) {
    const material = face < faces ? materialOf(face) : -1;
    if (material === runMaterial) continue;
    geometry.addGroup(
      starts[runFace] as number,
      (starts[face] as number) - (starts[runFace] as number),
      runMaterial,
    );
    runFace = face;
    runMaterial = material;
  }
}

/**
 * B-rep edges of a FACE SUBSET of a merged body geometry — the brass-edge
 * emphasis on a feature-localized selection (FINDINGS #9). This gathers the
 * index ranges of the requested face ordinals into a throwaway geometry
 * (sharing the source position buffer — no vertex copy) and returns its
 * `EdgesGeometry`, ready to overlay in the selection brass. The caller owns
 * disposing the result.
 *
 * Returns `null` when the geometry carries no face partition or the subset
 * selects no triangles — the caller then draws no emphasis (never throws
 * mid-render).
 */
export function subsetEdges(
  geometry: BufferGeometry,
  faceOrdinals: ReadonlySet<number>,
): EdgesGeometry | null {
  const subset = subsetSurface(geometry, faceOrdinals);
  if (subset === null) return null;
  return new EdgesGeometry(subset, 25);
}

/**
 * Vertex welding cached on the geometry — see {@link faceBoundaryEdges}.
 *
 * Keyed on the geometry's own `userData` because the merged buffer outlives
 * every edge rebuild (a ghost or hide toggle re-derives the edges but never
 * re-parses the GLB), and the weld is the expensive half.
 */
const WELD_KEY = "loftWeldedVertices";

/**
 * Grid the weld quantises to, in mm. The kernel's linear tolerance is 1e-7 m
 * = 1e-4 mm, so two vertices this close are the same point by the only
 * definition upstream has.
 *
 * The failure direction if two coincident vertices straddle a grid line anyway
 * is benign and worth stating: they do not weld, so the shared edge is emitted
 * once per face instead of once in total, and the SAME line is drawn twice.
 * Nothing
 * disappears — which is the property a rounding tolerance in a drawing path
 * has to have.
 */
const WELD_TOLERANCE_MM = 1e-4;

interface WeldTable {
  /** Weld id of each source vertex. */
  ids: Uint32Array;
  /** A source vertex index per weld id — where to read its position. */
  representative: Uint32Array;
  /** Number of distinct welded positions. */
  count: number;
}

function isWeldTable(value: unknown): value is WeldTable {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as WeldTable).ids instanceof Uint32Array &&
    (value as WeldTable).representative instanceof Uint32Array
  );
}

/**
 * Map every vertex of the merged buffer to a welded POSITION id.
 *
 * OCCT emits one vertex set per B-rep face, so the two faces meeting at an
 * edge carry their own copies of that edge's vertices — index equality cannot
 * see that they are the same point, and the whole boundary derivation below
 * depends on seeing it.
 */
function weldTable(geometry: BufferGeometry): WeldTable | null {
  const cached: unknown = geometry.userData[WELD_KEY];
  if (isWeldTable(cached)) return cached;
  const position = geometry.getAttribute("position");
  if (position === undefined) return null;
  const ids = new Uint32Array(position.count);
  const representative: number[] = [];
  const lookup = new Map<string, number>();
  const grid = 1 / WELD_TOLERANCE_MM;
  for (let v = 0; v < position.count; v += 1) {
    const key =
      `${Math.round(position.getX(v) * grid)},` +
      `${Math.round(position.getY(v) * grid)},` +
      `${Math.round(position.getZ(v) * grid)}`;
    let id = lookup.get(key);
    if (id === undefined) {
      id = representative.length;
      lookup.set(key, id);
      representative.push(v);
    }
    ids[v] = id;
  }
  const table: WeldTable = {
    ids,
    representative: Uint32Array.from(representative),
    count: representative.length,
  };
  geometry.userData[WELD_KEY] = table;
  return table;
}

/**
 * THE B-REP EDGES OF A BODY, derived from its FACE PARTITION (CRAFT-1).
 *
 * ## The defect this replaces
 *
 * The body's line work used to be `new EdgesGeometry(geometry, 25)`, which is
 * a **mesh crease detector**: it emits a line only where two neighbouring
 * TRIANGLES meet at more than 25°. A fillet is tangent by construction, so the
 * boundary between the top face and the fillet has a dihedral of ~0° and no
 * line was drawn — the moment a part got an edge break, i.e. the moment it
 * stopped being a test cube and started being a part, every feature boundary
 * disappeared and the body rendered as clay (`docs/design/AUDIT-CRAFT-2026-09.md`
 * P1-2, measured at **zero** edge ink on a filleted plate).
 *
 * Raising the crease threshold cannot fix it and would make it worse: a
 * threshold low enough to catch a tangent seam carpets every curved face with
 * the tessellation's own facet lines. The question "is this a B-rep edge" is
 * not a question about angles.
 *
 * ## What it does instead
 *
 * A B-rep edge is where one FACE ends. The tessellation already carries the
 * face partition (`faceStarts`, the module doc above), so the boundary is an
 * index pass and needs nothing from the server:
 *
 *  1. weld vertices by POSITION, because OCCT duplicates them per face;
 *  2. inside each face, count how many of that face's own triangles use each
 *     welded edge — an edge used exactly ONCE is on the face's boundary;
 *  3. union those boundaries across the requested faces, deduplicated, so the
 *     edge shared by two faces is drawn once.
 *
 * Two properties fall out of doing it per face rather than per triangle, and
 * both are the reason this is the right derivation rather than a cheaper one:
 *
 *  - **Tessellation edges can never be emitted.** An edge interior to a face is
 *    used by two of that face's triangles, so step 2 excludes it structurally —
 *    not by a tolerance that could be tuned wrong.
 *  - **Seams cancel.** A closed face (a bore's cylinder) is cut along a seam
 *    whose vertices are duplicated for UV; welding them makes the seam an
 *    interior edge with two users, so it is not drawn. Which is what a CAD
 *    renderer does — a hole has no line down its side.
 *
 * `faceOrdinals` restricts the derivation to a subset (the drawn faces when a
 * body is partly hidden, or one feature's faces). The weld is always global, so
 * a subset's boundary is computed in the same coordinate identity as the whole.
 *
 * Returns a plain `BufferGeometry` of line-segment pairs, or `null` when the
 * geometry carries no usable partition or the subset selects nothing — callers
 * then draw no edges rather than throwing mid-render. The caller owns disposal.
 */
export function faceBoundaryEdges(
  geometry: BufferGeometry,
  faceOrdinals?: ReadonlySet<number> | null,
): BufferGeometry | null {
  const index = geometry.getIndex();
  const position = geometry.getAttribute("position");
  const starts = faceStarts(geometry);
  if (index === null || position === undefined || starts.length < 2) {
    return null;
  }
  const weld = weldTable(geometry);
  if (weld === null) return null;
  const source = index.array;
  const stride = weld.count;
  const boundary = new Set<number>();
  const used = new Map<number, number>();
  for (let face = 0; face + 1 < starts.length; face += 1) {
    if (
      faceOrdinals !== undefined &&
      faceOrdinals !== null &&
      !faceOrdinals.has(face)
    ) {
      continue;
    }
    const begin = starts[face] as number;
    const end = starts[face + 1] as number;
    used.clear();
    for (let i = begin; i + 2 < end; i += 3) {
      const a = weld.ids[source[i] as number] as number;
      const b = weld.ids[source[i + 1] as number] as number;
      const c = weld.ids[source[i + 2] as number] as number;
      countEdge(used, a, b, stride);
      countEdge(used, b, c, stride);
      countEdge(used, c, a, stride);
    }
    for (const [key, count] of used) {
      if (count === 1) boundary.add(key);
    }
  }
  if (boundary.size === 0) return null;
  const points = new Float32Array(boundary.size * 6);
  let offset = 0;
  for (const key of boundary) {
    const low = key % stride;
    const high = (key - low) / stride;
    writeVertex(position, weld.representative[low] as number, points, offset);
    writeVertex(
      position,
      weld.representative[high] as number,
      points,
      offset + 3,
    );
    offset += 6;
  }
  const edges = new BufferGeometry();
  edges.setAttribute("position", new Float32BufferAttribute(points, 3));
  return edges;
}

/**
 * Tally one triangle edge of a face. Undirected: the key is ordered, so the
 * two triangles sharing an edge tally the same slot whatever their winding.
 * A degenerate edge (both ends welded to one point) is not an edge and is
 * dropped — it would otherwise read as a boundary of length zero.
 */
function countEdge(
  used: Map<number, number>,
  a: number,
  b: number,
  stride: number,
): void {
  if (a === b) return;
  const key = a < b ? b * stride + a : a * stride + b;
  used.set(key, (used.get(key) ?? 0) + 1);
}

function writeVertex(
  position: {
    getX: (i: number) => number;
    getY: (i: number) => number;
    getZ: (i: number) => number;
  },
  vertex: number,
  out: Float32Array,
  offset: number,
): void {
  out[offset] = position.getX(vertex);
  out[offset + 1] = position.getY(vertex);
  out[offset + 2] = position.getZ(vertex);
}

/**
 * The TRIANGLES of a face subset, as a geometry of their own — the face's real
 * area, for a highlight that lies inside the face's own boundary instead of
 * approximating it.
 *
 * MATE-1 / T-13. The mate pick used to highlight with an area-equivalent DISC
 * on the face's plane, which the product audit read, correctly, as "an ellipse
 * floating mostly below the plate, bearing no relation to the face's actual
 * outline". A disc of the right area is not the right shape. These are the
 * triangles the tessellator actually emitted for the face, so the highlight IS
 * the face — and it is the same partition the pick raycast resolves against,
 * so the thing lit and the thing that would be picked cannot disagree.
 *
 * Shares the source POSITION buffer and builds only a new index — no vertex
 * copy, and the returned geometry must not dispose that attribute. The caller
 * owns disposing the result. Returns `null` when the geometry carries no face
 * partition or the subset selects no triangles, so a caller draws nothing
 * rather than throwing mid-render.
 */
export function subsetSurface(
  geometry: BufferGeometry,
  faceOrdinals: ReadonlySet<number>,
): BufferGeometry | null {
  const index = geometry.getIndex();
  const position = geometry.getAttribute("position");
  const starts = faceStarts(geometry);
  if (index === null || position === undefined || starts.length < 2) {
    return null;
  }
  const source = index.array;
  const kept: number[] = [];
  for (let face = 0; face + 1 < starts.length; face += 1) {
    if (!faceOrdinals.has(face)) continue;
    const end = starts[face + 1] as number;
    for (let i = starts[face] as number; i < end; i += 1) {
      kept.push(source[i] as number);
    }
  }
  if (kept.length === 0) return null;
  const subset = new BufferGeometry();
  subset.setAttribute("position", position);
  subset.setIndex(kept);
  return subset;
}

export interface LoadGlbCallbacks {
  /** Effect-cleanup guard — when true, results are disposed, not delivered. */
  isCancelled: () => boolean;
  /** Receives the mm-scaled geometry on success. */
  onGeometry: (geometry: BufferGeometry) => void;
  /** Receives every failure: parse rejection or a mesh-less scene. */
  onError: (error: Error) => void;
}

/**
 * Drive one GLB parse to a definite outcome: exactly one of `onGeometry` /
 * `onError` fires (neither if cancelled first). Never rejects — a corrupt or
 * truncated GLB must surface in the UI, not as an unhandled rejection.
 *
 * `parse` is injectable for unit tests only; production callers use the
 * default.
 */
export async function loadGlbGeometry(
  glb: ArrayBuffer,
  callbacks: LoadGlbCallbacks,
  parse: (
    glb: ArrayBuffer,
  ) => Promise<BufferGeometry | null> = parseGlbGeometry,
): Promise<void> {
  let geometry: BufferGeometry | null;
  try {
    geometry = await parse(glb);
  } catch (cause) {
    if (!callbacks.isCancelled()) {
      callbacks.onError(
        cause instanceof Error ? cause : new Error(String(cause)),
      );
    }
    return;
  }
  if (callbacks.isCancelled()) {
    geometry?.dispose();
    return;
  }
  if (geometry === null) {
    callbacks.onError(new Error("GLB payload contains no renderable mesh"));
    return;
  }
  callbacks.onGeometry(geometry);
}
