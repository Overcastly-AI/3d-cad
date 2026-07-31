/**
 * Splitting ONE fused mesh back into per-body face sets (UI-W2, part half).
 *
 * The evaluate payload ships a single GLB with every body fused into it — the
 * contract carries no per-body mesh, and inventing one client-side would be a
 * hand-written API type. But a Bodies list whose eye hides the WHOLE part when
 * you click Body 2 of 3 is a control that lies, so the split has to be derived
 * from what we do have.
 *
 * Two facts make that exact rather than a guess:
 *
 *  1. the merged geometry keeps ONE DRAW GROUP PER B-REP FACE (`glbGeometry.ts`
 *     merges with `useGroups`), so a face is addressable by ordinal; and
 *  2. separate bodies are, by construction, not fused — they share no vertex —
 *     so the connected components of the mesh ARE the kernel's LUMPS.
 *
 * Components therefore partition faces into lumps, and the evaluate's per-body
 * lump COUNT (already on the wire, already shown as the Bodies panel's "N
 * solids" badge) says how many consecutive lumps each body owns. Body order and
 * face order agree because the kernel meshes the bodies in tree order.
 *
 * When the arithmetic does NOT line up — a lump count the evaluate never
 * reported, a mesh the kernel welded differently — this returns `null` rather
 * than a plausible-looking wrong answer, and the caller withholds the per-body
 * control instead of shipping one that hides the wrong solid.
 */
import type { BufferGeometry } from "three";

/** Weld tolerance for "these two faces touch" (mm). */
const WELD_MM = 1e-4;

/**
 * Connected components of a face-grouped geometry, each the sorted list of face
 * ordinals it contains, ordered by their first face. Returns one component per
 * disjoint solid (a LUMP). An ungrouped or unindexed geometry yields `null`.
 *
 * O(V) with a positional hash: OCCT writes each B-rep face as its own glTF
 * primitive with its own vertices (per-face normals), so faces of one solid do
 * not share buffer indices — only coordinates. Runs once per mesh load.
 */
export function faceLumps(geometry: BufferGeometry): number[][] | null {
  const index = geometry.getIndex();
  const position = geometry.getAttribute("position");
  if (
    index === null ||
    position === undefined ||
    geometry.groups.length === 0
  ) {
    return null;
  }
  const faceCount = geometry.groups.length;
  const parent = new Int32Array(faceCount);
  for (let i = 0; i < faceCount; i += 1) parent[i] = i;
  const find = (x: number): number => {
    let root = x;
    while (parent[root] !== root) root = parent[root] as number;
    let walk = x;
    while (parent[walk] !== root) {
      const next = parent[walk] as number;
      parent[walk] = root;
      walk = next;
    }
    return root;
  };
  const union = (a: number, b: number): void => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent[Math.max(ra, rb)] = Math.min(ra, rb);
  };

  const owner = new Map<string, number>();
  const idx = index.array;
  const quantize = (value: number): number => Math.round(value / WELD_MM);
  geometry.groups.forEach((group, ordinal) => {
    const end = group.start + group.count;
    for (let i = group.start; i < end; i += 1) {
      const vertex = idx[i] as number;
      const key = `${quantize(position.getX(vertex))},${quantize(
        position.getY(vertex),
      )},${quantize(position.getZ(vertex))}`;
      const seen = owner.get(key);
      if (seen === undefined) owner.set(key, ordinal);
      else union(seen, ordinal);
    }
  });

  const byRoot = new Map<number, number[]>();
  for (let ordinal = 0; ordinal < faceCount; ordinal += 1) {
    const root = find(ordinal);
    const bucket = byRoot.get(root);
    if (bucket === undefined) byRoot.set(root, [ordinal]);
    else bucket.push(ordinal);
  }
  return [...byRoot.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, faces]) => faces);
}

/**
 * Assign lumps to bodies, in order, by each body's lump count — the face
 * ordinals each body owns.
 *
 * Returns `null` when the arithmetic cannot be trusted (see the module doc):
 * the caller then treats the mesh as unpartitionable and offers no per-body
 * eye. The one forgiving case is a body set whose declared counts do not sum
 * but whose CARDINALITY matches the components exactly — one lump each is then
 * the only consistent reading.
 */
export function bodyFaceSets(
  lumps: readonly (readonly number[])[],
  bodies: readonly { readonly lumps: number }[],
): number[][] | null {
  if (bodies.length === 0) return null;
  const declared = bodies.reduce(
    (sum, body) => sum + Math.max(body.lumps, 1),
    0,
  );
  const counts =
    declared === lumps.length
      ? bodies.map((body) => Math.max(body.lumps, 1))
      : bodies.length === lumps.length
        ? bodies.map(() => 1)
        : null;
  if (counts === null) return null;
  const sets: number[][] = [];
  let cursor = 0;
  for (const count of counts) {
    const faces: number[] = [];
    for (let i = 0; i < count; i += 1) {
      const lump = lumps[cursor];
      cursor += 1;
      if (lump === undefined) return null;
      faces.push(...lump);
    }
    sets.push(faces);
  }
  return sets;
}
