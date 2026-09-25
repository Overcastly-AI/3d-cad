import {
  BackSide,
  BufferAttribute,
  BufferGeometry,
  DoubleSide,
  FrontSide,
  Mesh,
  MeshBasicMaterial,
  Raycaster,
  TorusKnotGeometry,
  Vector3,
} from "three";
import type { Intersection, Side } from "three";
import { describe, expect, it } from "vitest";

import {
  buildTriangleBvh,
  bvhRaycastAll,
  bvhRaycastFirst,
  hasTriangleBvh,
  nearestDrawnHit,
  type HiddenTriangleTest,
} from "./pickBvh";
import { drawnSurfaceRaycast, hiddenTriangleTest } from "./pickRaycast";

/**
 * THE HIERARCHY MUST GIVE THREE'S ANSWER, NOT A NEAR MISS OF IT.
 *
 * Every assertion here is against the REAL `Mesh.prototype.raycast` on the
 * same mesh and the same ray — the brute force the hierarchy replaces. A
 * cheaper hit-test that disagrees with the pointer's is itself the defect the
 * burial oracle's docblock warns about, so "close" is not the bar: the same
 * triangles, in the same order, with every field of the record equal —
 * distance, point, face, the interpolated normal, uv, uv1 and barycoord.
 */

/** A deterministic PRNG, so a failing ray can be reproduced by its index. */
function rng(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

/**
 * A dense closed surface with real self-occlusion: a torus knot, carrying
 * normals, uv AND uv1 so every interpolated field of a hit is exercised, and
 * optionally translated `offset` along each axis (far-from-origin geometry is
 * where float rounding in a box test would first show).
 */
function knotMesh(side: Side = FrontSide, offset = 0): Mesh {
  const geometry = new TorusKnotGeometry(10, 3, 200, 32);
  geometry.setAttribute("uv1", geometry.getAttribute("uv").clone());
  if (offset !== 0) geometry.translate(offset, -offset, offset);
  const mesh = new Mesh(geometry, new MeshBasicMaterial({ side }));
  mesh.updateMatrixWorld(true);
  return mesh;
}

/** Rays from a shell around the mesh, aimed at random points inside it. */
function rays(count: number, seed: number, radius = 40): Raycaster[] {
  const random = rng(seed);
  const out: Raycaster[] = [];
  for (let i = 0; i < count; i += 1) {
    const theta = random() * Math.PI * 2;
    const phi = Math.acos(2 * random() - 1);
    const origin = new Vector3(
      radius * Math.sin(phi) * Math.cos(theta),
      radius * Math.sin(phi) * Math.sin(theta),
      radius * Math.cos(phi),
    );
    const target = new Vector3(
      (random() - 0.5) * 26,
      (random() - 0.5) * 26,
      (random() - 0.5) * 8,
    );
    out.push(
      new Raycaster(origin, target.sub(origin).normalize(), 0, Infinity),
    );
  }
  // Axis-aligned rays: a zero direction component is where a slab test's
  // 1/0 and 0*Infinity live.
  for (const [o, d] of [
    [new Vector3(0, 13, 50), new Vector3(0, 0, -1)],
    [new Vector3(50, 0, 0), new Vector3(-1, 0, 0)],
    [new Vector3(0, -50, 1), new Vector3(0, 1, 0)],
    [new Vector3(10, 0, 0), new Vector3(0, 0, 1)],
  ] as const) {
    out.push(new Raycaster(o, d, 0, Infinity));
  }
  return out;
}

/**
 * Rays aimed EXACTLY at vertices and edge midpoints of the mesh — where a hit
 * lands on a triangle's boundary, a box face is grazed, and two triangles can
 * tie — from a random direction, a third of them axis-aligned.
 */
function vertexRays(mesh: Mesh, count: number, seed: number): Raycaster[] {
  const random = rng(seed);
  const position = mesh.geometry.getAttribute("position") as BufferAttribute;
  mesh.geometry.computeBoundingSphere();
  const reach = (mesh.geometry.boundingSphere?.radius ?? 1) * 3;
  const out: Raycaster[] = [];
  const vertex = () =>
    new Vector3()
      .fromBufferAttribute(position, Math.floor(random() * position.count))
      .applyMatrix4(mesh.matrixWorld);
  for (let i = 0; i < count; i += 1) {
    const aim = vertex();
    if (random() < 0.3) aim.lerp(vertex(), 0.5);
    const direction = new Vector3(
      random() - 0.5,
      random() - 0.5,
      random() - 0.5,
    ).normalize();
    if (random() < 0.3) {
      direction.set(0, 0, 0);
      direction.setComponent(Math.floor(random() * 3), random() < 0.5 ? 1 : -1);
    }
    const origin = aim.clone().addScaledVector(direction, -reach);
    out.push(new Raycaster(origin, direction, 0, Infinity));
  }
  return out;
}

/** Every field of a hit record, in a comparable shape. */
function facts(hits: readonly Intersection[]) {
  return hits.map((hit) => ({
    faceIndex: hit.faceIndex,
    distance: hit.distance,
    point: hit.point.toArray(),
    face: hit.face
      ? [hit.face.a, hit.face.b, hit.face.c, hit.face.materialIndex]
      : null,
    faceNormal: hit.face?.normal.toArray() ?? null,
    normal: hit.normal?.toArray() ?? null,
    uv: hit.uv?.toArray() ?? null,
    uv1: hit.uv1?.toArray() ?? null,
    barycoord: hit.barycoord?.toArray() ?? null,
    object: hit.object,
  }));
}

function bruteAll(mesh: Mesh, raycaster: Raycaster): Intersection[] {
  const out: Intersection[] = [];
  Mesh.prototype.raycast.call(mesh, raycaster, out);
  return out;
}

function bvhAll(mesh: Mesh, raycaster: Raycaster): Intersection[] {
  const out: Intersection[] = [];
  bvhRaycastAll(mesh, raycaster, out);
  return out;
}

/** Three's full list, reduced by the ONE strict minimum the product uses. */
function bruteFirst(
  mesh: Mesh,
  raycaster: Raycaster,
  isHidden: HiddenTriangleTest,
): Intersection | null {
  return nearestDrawnHit(bruteAll(mesh, raycaster), isHidden);
}

const NOTHING_HIDDEN: HiddenTriangleTest = () => false;

/** Both queries against three for one ray; returns how many hits it had. */
function expectSameAnswer(
  mesh: Mesh,
  raycaster: Raycaster,
  isHidden: HiddenTriangleTest = NOTHING_HIDDEN,
): number {
  const expected = bruteAll(mesh, raycaster);
  expect(facts(bvhAll(mesh, raycaster))).toEqual(facts(expected));
  const nearest = bruteFirst(mesh, raycaster, isHidden);
  const got = bvhRaycastFirst(mesh, raycaster, isHidden);
  expect(got === null ? null : facts([got])).toEqual(
    nearest === null ? null : facts([nearest]),
  );
  return expected.length;
}

describe("buildTriangleBvh", () => {
  it("places every triangle in exactly one leaf", () => {
    const geometry = new TorusKnotGeometry(10, 3, 64, 8);
    const bvh = buildTriangleBvh(geometry);
    const seen = new Uint8Array(bvh.triangles);
    let leafTotal = 0;
    for (let n = 0; n < bvh.nodes; n += 1) {
      if (bvh.left[n] !== -1) continue;
      for (let i = 0; i < (bvh.count[n] as number); i += 1) {
        const t = bvh.order[(bvh.start[n] as number) + i] as number;
        seen[t] = (seen[t] as number) + 1;
        leafTotal += 1;
      }
    }
    expect(bvh.triangles).toBe((geometry.index?.count ?? 0) / 3);
    expect(leafTotal).toBe(bvh.triangles);
    expect([...seen].every((times) => times === 1)).toBe(true);
  });

  it("survives a fan of coincident centroids (no split plane exists)", () => {
    const geometry = new BufferGeometry();
    const positions: number[] = [];
    for (let i = 0; i < 40; i += 1) positions.push(0, 0, 0, 1, 0, 0, 0, 1, 0);
    geometry.setAttribute(
      "position",
      new BufferAttribute(new Float32Array(positions), 3),
    );
    const bvh = buildTriangleBvh(geometry);
    expect(bvh.triangles).toBe(40);
    expect(bvh.nodes).toBeGreaterThan(1);
  });
});

describe("bvhRaycastAll is Mesh.raycast", () => {
  for (const [label, side] of [
    ["FrontSide", FrontSide],
    ["DoubleSide", DoubleSide],
    ["BackSide", BackSide],
  ] as const) {
    it(`reports the same hits in the same order (${label})`, () => {
      const mesh = knotMesh(side);
      let struck = 0;
      for (const raycaster of rays(300, 7)) {
        const expected = bruteAll(mesh, raycaster);
        struck += expected.length;
        expect(facts(bvhAll(mesh, raycaster))).toEqual(facts(expected));
      }
      // NON-VACUITY: rays that miss everything would agree trivially.
      expect(struck).toBeGreaterThan(300);
    });
  }

  it("honours the mesh's transform, near and far", () => {
    const mesh = knotMesh(DoubleSide);
    mesh.position.set(3, -2, 5);
    mesh.rotation.set(0.4, 1.1, -0.3);
    mesh.scale.set(1.5, 0.7, 2);
    mesh.updateMatrixWorld(true);
    let struck = 0;
    for (const raycaster of rays(200, 11, 60)) {
      raycaster.near = 45;
      raycaster.far = 75;
      const expected = bruteAll(mesh, raycaster);
      struck += expected.length;
      expect(facts(bvhAll(mesh, raycaster))).toEqual(facts(expected));
    }
    expect(struck).toBeGreaterThan(50);
  });

  /**
   * Three groups, one per side, over the knot. `offset` shifts the last one's
   * start, and `overlap` makes the second reach back into the first.
   */
  function groupedKnot(offset: number, overlap = 0): Mesh {
    const mesh = knotMesh();
    const geometry = mesh.geometry;
    const total = geometry.index?.count ?? 0;
    const third = Math.floor(total / 9) * 3;
    geometry.addGroup(0, third, 0);
    geometry.addGroup(third - overlap, third + overlap, 1);
    geometry.addGroup(2 * third + offset, total - 2 * third - offset, 2);
    geometry.setDrawRange(3, total - 9);
    mesh.material = [
      new MeshBasicMaterial({ side: FrontSide }),
      new MeshBasicMaterial({ side: DoubleSide }),
      new MeshBasicMaterial({ side: BackSide }),
    ];
    return mesh;
  }

  it("honours draw groups with a material ARRAY, and the draw range", () => {
    const mesh = groupedKnot(0);
    let struck = 0;
    for (const raycaster of rays(300, 13)) {
      const expected = bruteAll(mesh, raycaster);
      struck += expected.length;
      expect(facts(bvhAll(mesh, raycaster))).toEqual(facts(expected));
    }
    expect(struck).toBeGreaterThan(300);
    expect(hasTriangleBvh(mesh.geometry), "the hierarchy was used").toBe(true);
  });

  it("hands OVERLAPPING groups back to three — it reports a triangle per group", () => {
    const mesh = groupedKnot(0, 6);
    let struck = 0;
    for (const raycaster of rays(200, 41)) {
      struck += expectSameAnswer(mesh, raycaster);
    }
    expect(struck).toBeGreaterThan(200);
    expect(hasTriangleBvh(mesh.geometry)).toBe(false);
  });

  it("hands OUT-OF-ORDER groups back to three — the review's tie counterexample", () => {
    // Groups [3..6) then [0..3) over two coplanar triangles: three walks the
    // groups in array order, lists triangle 1 first and keeps it on the tie;
    // index order would keep triangle 0.
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      "position",
      new BufferAttribute(
        new Float32Array([
          -1, -1, 0, 1, -1, 0, -1, 1, 0, -2, -2, 0, 2, -2, 0, -2, 2, 0,
        ]),
        3,
      ),
    );
    geometry.addGroup(3, 3, 0);
    geometry.addGroup(0, 3, 0);
    const mesh = new Mesh(geometry, [new MeshBasicMaterial()]);
    mesh.updateMatrixWorld(true);
    const raycaster = new Raycaster(
      new Vector3(-0.5, -0.5, 5),
      new Vector3(0, 0, -1),
    );
    expect(bruteFirst(mesh, raycaster, NOTHING_HIDDEN)?.faceIndex).toBe(1);
    expect(bvhRaycastFirst(mesh, raycaster, NOTHING_HIDDEN)?.faceIndex).toBe(1);
    expectSameAnswer(mesh, raycaster);
    expect(hasTriangleBvh(geometry)).toBe(false);
  });

  it("hands a group that starts OFF a triangle boundary back to three", () => {
    // Three visits j = start, start + 3, ... so an odd start reads vertex
    // triples that are not triangles of the index; only three can answer.
    const mesh = groupedKnot(1);
    for (const raycaster of rays(100, 37)) {
      expect(facts(bvhAll(mesh, raycaster))).toEqual(
        facts(bruteAll(mesh, raycaster)),
      );
    }
    expect(hasTriangleBvh(mesh.geometry)).toBe(false);
  });

  it("handles NON-indexed geometry", () => {
    const mesh = knotMesh(DoubleSide);
    mesh.geometry = mesh.geometry.toNonIndexed();
    let struck = 0;
    for (const raycaster of rays(150, 17)) {
      const expected = bruteAll(mesh, raycaster);
      struck += expected.length;
      expect(facts(bvhAll(mesh, raycaster))).toEqual(facts(expected));
    }
    expect(struck).toBeGreaterThan(150);
  });

  it("rebuilds when the positions are rewritten", () => {
    const mesh = knotMesh();
    const raycaster = rays(1, 3)[0] as Raycaster;
    bvhAll(mesh, raycaster);
    expect(hasTriangleBvh(mesh.geometry)).toBe(true);
    const position = mesh.geometry.getAttribute("position") as BufferAttribute;
    for (let i = 0; i < position.count; i += 1) {
      position.setX(i, position.getX(i) + 4);
    }
    position.needsUpdate = true;
    mesh.geometry.computeBoundingSphere();
    for (const ray of rays(100, 19)) {
      expect(facts(bvhAll(mesh, ray))).toEqual(facts(bruteAll(mesh, ray)));
    }
  });
});

describe("bvhRaycastFirst is the strict minimum over Mesh.raycast", () => {
  it("with nothing filtered", () => {
    const mesh = knotMesh();
    let struck = 0;
    for (const raycaster of rays(300, 23)) {
      const expected = bruteFirst(mesh, raycaster, NOTHING_HIDDEN);
      if (expected !== null) struck += 1;
      const got = bvhRaycastFirst(mesh, raycaster, NOTHING_HIDDEN);
      expect(got === null ? null : facts([got])).toEqual(
        expected === null ? null : facts([expected]),
      );
    }
    expect(struck).toBeGreaterThan(100);
  });

  it("SEEING PAST filtered triangles to the nearest admitted one", () => {
    const mesh = knotMesh(DoubleSide);
    // Hide two thirds of the part — the SEL-6 hidden-body shape, at scale.
    const isHidden: HiddenTriangleTest = (faceIndex) =>
      (faceIndex ?? 0) % 3 !== 0;
    let struck = 0;
    for (const raycaster of rays(300, 29)) {
      const expected = bruteFirst(mesh, raycaster, isHidden);
      if (expected !== null) struck += 1;
      const got = bvhRaycastFirst(mesh, raycaster, isHidden);
      expect(got === null ? null : facts([got])).toEqual(
        expected === null ? null : facts([expected]),
      );
    }
    expect(struck).toBeGreaterThan(100);
  });

  it("keeps the EARLIEST triangle of an exact tie", () => {
    // Two coplanar triangles that both cover the struck point, so they tie on
    // distance exactly, and three's index-order list plus a strict minimum
    // keeps triangle 0. The hierarchy is built so it meets triangle 1 FIRST:
    // filler far out along x makes x the split axis, and triangle 1's centroid
    // sits on the near-left side of the split while triangle 0's sits right.
    // A walk that kept whichever tied hit it met first would answer 1.
    const positions = [
      ...[-1, -3, 0, 9, -3, 0, -1, 7, 0], // triangle 0, centroid x = +2.3
      ...[-4, -1, 0, 1.5, -1, 0, -4, 4.5, 0], // triangle 1, centroid x = -1.7
    ];
    for (let i = 0; i < 16; i += 1) {
      const x = i < 8 ? -100 + i * 5 : 60 + i * 5;
      positions.push(x, 50, 0, x + 1, 50, 0, x, 51, 0);
    }
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      "position",
      new BufferAttribute(new Float32Array(positions), 3),
    );
    const mesh = new Mesh(geometry, new MeshBasicMaterial());
    mesh.updateMatrixWorld(true);
    const raycaster = new Raycaster(
      new Vector3(0, 0, 10),
      new Vector3(0, 0, -1),
    );
    const all = bruteAll(mesh, raycaster);
    expect(all.map((hit) => hit.faceIndex)).toEqual([0, 1]);
    expect(all[0]?.distance).toBe(all[1]?.distance);
    expect(bruteFirst(mesh, raycaster, NOTHING_HIDDEN)?.faceIndex).toBe(0);
    expect(bvhRaycastFirst(mesh, raycaster, NOTHING_HIDDEN)?.faceIndex).toBe(0);
  });
});

describe("exact vertices, exact edges, and far from the origin", () => {
  for (const [label, offset] of [
    ["at the origin", 0],
    ["1e5 mm out", 1e5],
  ] as const) {
    for (const [sideLabel, side] of [
      ["FrontSide", FrontSide],
      ["DoubleSide", DoubleSide],
      ["BackSide", BackSide],
    ] as const) {
      it(`every field matches three on vertex/edge rays (${label}, ${sideLabel})`, () => {
        const mesh = knotMesh(side, offset);
        const isHidden: HiddenTriangleTest = (faceIndex) =>
          (faceIndex ?? 0) % 2 === 1;
        let struck = 0;
        for (const raycaster of vertexRays(mesh, 250, 43)) {
          struck += expectSameAnswer(mesh, raycaster, isHidden);
        }
        expect(struck).toBeGreaterThan(250);
      });
    }
  }

  it("from INSIDE the part, with near and far both set", () => {
    const mesh = knotMesh(DoubleSide, 1e5);
    mesh.geometry.computeBoundingSphere();
    const centre = (
      mesh.geometry.boundingSphere?.center ?? new Vector3()
    ).clone();
    const random = rng(47);
    let struck = 0;
    for (let i = 0; i < 200; i += 1) {
      const direction = new Vector3(
        random() - 0.5,
        random() - 0.5,
        random() - 0.5,
      ).normalize();
      struck += expectSameAnswer(
        mesh,
        new Raycaster(centre, direction, random() * 2, 2 + random() * 8),
      );
    }
    expect(struck).toBeGreaterThan(0);
  });
});

describe("the cache", () => {
  it("frees a geometry's tree the moment the geometry is disposed", () => {
    const mesh = knotMesh();
    const raycaster = rays(1, 3)[0] as Raycaster;
    bvhAll(mesh, raycaster);
    expect(hasTriangleBvh(mesh.geometry)).toBe(true);
    mesh.geometry.dispose();
    expect(hasTriangleBvh(mesh.geometry)).toBe(false);
    // A disposed geometry may be drawn again; the next raycast rebuilds, and
    // a second dispose frees that tree too.
    expect(facts(bvhAll(mesh, raycaster))).toEqual(
      facts(bruteAll(mesh, raycaster)),
    );
    expect(hasTriangleBvh(mesh.geometry)).toBe(true);
    mesh.geometry.dispose();
    expect(hasTriangleBvh(mesh.geometry)).toBe(false);
  });
});

describe("THE COST: a pick raycast no longer reads the whole part", () => {
  /**
   * PERF-REAL-1's regression gate, stated as WORK rather than as a clock: a
   * timing assertion on a shared runner is a false-red machine, but the number
   * of triangles a ray has to read is deterministic. On the gauntlet's
   * `gearbox-11752` every pick ray read all 399 478 triangles; the burial walk
   * alone casts one per offered face mark.
   */
  function countingMesh(): { mesh: Mesh; reads: () => number } {
    const mesh = new Mesh(
      new TorusKnotGeometry(10, 3, 800, 64),
      new MeshBasicMaterial(),
    );
    mesh.updateMatrixWorld(true);
    let reads = 0;
    const read = mesh.getVertexPosition.bind(mesh);
    mesh.getVertexPosition = (index, target) => {
      reads += 1;
      return read(index, target);
    };
    return { mesh, reads: () => reads };
  }

  it("the product's drawn-surface raycast reads < 0.5 % of the triangles per ray", () => {
    const { mesh, reads } = countingMesh();
    const triangles = (mesh.geometry.index?.count ?? 0) / 3;
    expect(triangles).toBeGreaterThan(100_000);
    mesh.raycast = drawnSurfaceRaycast(
      hiddenTriangleTest(mesh.geometry, new Set()),
    );
    const cast = rays(200, 31);
    let hits = 0;
    for (const raycaster of cast) {
      hits += raycaster.intersectObject(mesh).length;
    }
    expect(hits, "the rays must actually strike the part").toBeGreaterThan(50);
    const perRay = reads() / 3 / cast.length;
    expect(perRay).toBeLessThan(triangles * 0.005);
  });

  it("NEGATIVE CONTROL: three's own raycast reads EVERY triangle per ray", () => {
    // What the gate above fails against: restore `Mesh.prototype.raycast` in
    // `drawnSurfaceRaycast` and the count is this one.
    const { mesh, reads } = countingMesh();
    const triangles = (mesh.geometry.index?.count ?? 0) / 3;
    const cast = rays(3, 31);
    for (const raycaster of cast) bruteAll(mesh, raycaster);
    expect(reads() / 3 / cast.length).toBeGreaterThan(triangles * 0.5);
  });
});
