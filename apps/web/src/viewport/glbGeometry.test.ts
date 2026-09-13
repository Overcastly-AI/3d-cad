import { readFileSync } from "node:fs";

import { BufferGeometry, EdgesGeometry, Float32BufferAttribute } from "three";
import { describe, expect, it, vi } from "vitest";

import { faceLumps } from "./bodyPartition";
import {
  faceBoundaryEdges,
  faceCount,
  faceOrdinalOfTriangle,
  faceStarts,
  loadGlbGeometry,
  parseGlbGeometry,
  setFaceMaterials,
  subsetEdges,
} from "./glbGeometry";

const notCancelled = () => false;

/** Real kernel output — see `__fixtures__/README.md`. */
function fixture(name: string): ArrayBuffer {
  const bytes = new Uint8Array(
    readFileSync(new URL(`./__fixtures__/${name}`, import.meta.url)),
  );
  return bytes.buffer;
}

describe("loadGlbGeometry", () => {
  it("routes a parse rejection to onError and never to onGeometry", async () => {
    const failure = new Error("Unexpected magic: 0x0BADF00D");
    const parse = vi.fn().mockRejectedValue(failure);
    const onGeometry = vi.fn();
    const onError = vi.fn();

    await expect(
      loadGlbGeometry(
        new ArrayBuffer(8),
        {
          isCancelled: notCancelled,
          onGeometry,
          onError,
        },
        parse,
      ),
    ).resolves.toBeUndefined(); // never rejects — no unhandled rejection

    expect(onError).toHaveBeenCalledExactlyOnceWith(failure);
    expect(onGeometry).not.toHaveBeenCalled();
  });

  it("normalizes non-Error rejection values", async () => {
    const parse = vi.fn().mockRejectedValue("bad chunk");
    const onError = vi.fn();

    await loadGlbGeometry(
      new ArrayBuffer(8),
      {
        isCancelled: notCancelled,
        onGeometry: vi.fn(),
        onError,
      },
      parse,
    );

    expect(onError).toHaveBeenCalledOnce();
    const error = onError.mock.calls[0]?.[0] as Error;
    expect(error).toBeInstanceOf(Error);
    expect(error.message).toContain("bad chunk");
  });

  it("treats a mesh-less scene as an error (no silent stale viewport)", async () => {
    const parse = vi.fn().mockResolvedValue(null);
    const onGeometry = vi.fn();
    const onError = vi.fn();

    await loadGlbGeometry(
      new ArrayBuffer(8),
      {
        isCancelled: notCancelled,
        onGeometry,
        onError,
      },
      parse,
    );

    expect(onGeometry).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledOnce();
    expect((onError.mock.calls[0]?.[0] as Error).message).toMatch(
      /no renderable mesh/,
    );
  });

  it("delivers the geometry on success", async () => {
    const geometry = new BufferGeometry();
    const parse = vi.fn().mockResolvedValue(geometry);
    const onGeometry = vi.fn();
    const onError = vi.fn();

    await loadGlbGeometry(
      new ArrayBuffer(8),
      {
        isCancelled: notCancelled,
        onGeometry,
        onError,
      },
      parse,
    );

    expect(onGeometry).toHaveBeenCalledExactlyOnceWith(geometry);
    expect(onError).not.toHaveBeenCalled();
  });

  it("fires no callbacks after cancellation and disposes the result", async () => {
    const geometry = new BufferGeometry();
    const dispose = vi.spyOn(geometry, "dispose");
    const onGeometry = vi.fn();
    const onError = vi.fn();

    await loadGlbGeometry(
      new ArrayBuffer(8),
      {
        isCancelled: () => true,
        onGeometry,
        onError,
      },
      vi.fn().mockResolvedValue(geometry),
    );
    await loadGlbGeometry(
      new ArrayBuffer(8),
      {
        isCancelled: () => true,
        onGeometry,
        onError,
      },
      vi.fn().mockRejectedValue(new Error("boom")),
    );

    expect(onGeometry).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
    expect(dispose).toHaveBeenCalledOnce();
  });
});

describe("parseGlbGeometry", () => {
  it("rejects on a truncated/corrupt GLB payload", async () => {
    // Valid GLB magic ("glTF") but a truncated body — the wire-corruption case.
    const truncated = new Uint8Array([0x67, 0x6c, 0x54, 0x46, 2, 0, 0, 0]);
    await expect(parseGlbGeometry(truncated.buffer)).rejects.toThrow();
  });
});

/**
 * PERF-4b's load-bearing gate. The kernel now ships the SAME body two ways —
 * one glTF primitive per B-rep face (what OCCT writes, still used for
 * triangle-dense parts) and fused primitives plus a per-face triangle table.
 * Face ordinals are what `on_face` datums, shell openings, hole placement and
 * sketch-on-face are keyed on, so the two encodings must be indistinguishable
 * from the viewport's side. Both fixtures are real kernel output of one part.
 */
describe("face partition: fused and unfused GLB agree exactly", () => {
  const FACE_TRIANGLES = [
    2, 2, 4, 4, 2, 4, 2, 2, 2, 2, 2, 8, 2, 2, 2, 2, 2, 2, 2, 2,
  ];

  async function both(): Promise<[BufferGeometry, BufferGeometry]> {
    const unfused = await parseGlbGeometry(fixture("two-bodies-unfused.glb"));
    const fused = await parseGlbGeometry(fixture("two-bodies-fused.glb"));
    expect(unfused).not.toBeNull();
    expect(fused).not.toBeNull();
    return [unfused as BufferGeometry, fused as BufferGeometry];
  }

  it("recovers the kernel's face count and per-face triangle counts", async () => {
    const [unfused, fused] = await both();
    expect(faceCount(unfused)).toBe(FACE_TRIANGLES.length);
    expect(faceCount(fused)).toBe(FACE_TRIANGLES.length);
    const triangles = (geometry: BufferGeometry): number[] => {
      const starts = faceStarts(geometry);
      return FACE_TRIANGLES.map(
        (_, face) =>
          ((starts[face + 1] as number) - (starts[face] as number)) / 3,
      );
    };
    expect(triangles(unfused)).toEqual(FACE_TRIANGLES);
    expect(triangles(fused)).toEqual(FACE_TRIANGLES);
    unfused.dispose();
    fused.dispose();
  });

  it("resolves EVERY triangle to the same face ordinal", async () => {
    const [unfused, fused] = await both();
    const total = (unfused.getIndex()?.count ?? 0) / 3;
    expect(total).toBe(52);
    // The pre-PERF-4b resolver: a linear scan of one draw group per face.
    const legacy = (geometry: BufferGeometry, triangle: number): number => {
      const start = triangle * 3;
      return geometry.groups.findIndex(
        (group) => start >= group.start && start < group.start + group.count,
      );
    };
    for (let triangle = 0; triangle < total; triangle += 1) {
      const expected = legacy(unfused, triangle);
      expect(expected).toBeGreaterThanOrEqual(0);
      expect(faceOrdinalOfTriangle(unfused, triangle)).toBe(expected);
      expect(faceOrdinalOfTriangle(fused, triangle)).toBe(expected);
    }
    expect(faceOrdinalOfTriangle(fused, total)).toBeNull();
    expect(faceOrdinalOfTriangle(fused, -1)).toBeNull();
    unfused.dispose();
    fused.dispose();
  });

  it("produces identical vertex and index buffers", async () => {
    const [unfused, fused] = await both();
    expect(Array.from(fused.getIndex()?.array ?? [])).toEqual(
      Array.from(unfused.getIndex()?.array ?? []),
    );
    for (const name of ["position", "normal"]) {
      expect(Array.from(fused.getAttribute(name).array)).toEqual(
        Array.from(unfused.getAttribute(name).array),
      );
    }
    unfused.dispose();
    fused.dispose();
  });

  it("splits into the same two bodies (per-body show/hide/ghost)", async () => {
    const [unfused, fused] = await both();
    const lumps = faceLumps(unfused);
    expect(lumps).not.toBeNull();
    expect(lumps).toHaveLength(2);
    expect(faceLumps(fused)).toEqual(lumps);
    unfused.dispose();
    fused.dispose();
  });

  it("traces the same feature-selection edges", async () => {
    const [unfused, fused] = await both();
    const subset = new Set([2, 3, 11]);
    const a = subsetEdges(unfused, subset);
    const b = subsetEdges(fused, subset);
    expect(a).toBeInstanceOf(EdgesGeometry);
    expect(Array.from(b?.getAttribute("position").array ?? [])).toEqual(
      Array.from(a?.getAttribute("position").array ?? []),
    );
    a?.dispose();
    b?.dispose();
    unfused.dispose();
    fused.dispose();
  });
});

describe("setFaceMaterials", () => {
  /** Six "faces" of one triangle each — the draw-group ledger in miniature. */
  function sixFaces(): BufferGeometry {
    const geometry = new BufferGeometry();
    const positions: number[] = [];
    const indices: number[] = [];
    for (let face = 0; face < 6; face += 1) {
      const base = face * 3;
      positions.push(face, 0, 0, face + 1, 0, 0, face, 1, 0);
      indices.push(base, base + 1, base + 2);
      geometry.addGroup(face * 3, 3, 0);
    }
    geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
    geometry.setIndex(indices);
    return geometry;
  }

  it("collapses consecutive faces sharing a material into ONE draw group", () => {
    const geometry = sixFaces();
    // A hidden body (faces 4-5) over a base body — the per-body hide case.
    setFaceMaterials(geometry, (face) => (face >= 4 ? 3 : 0));
    expect(geometry.groups).toEqual([
      { start: 0, count: 12, materialIndex: 0 },
      { start: 12, count: 6, materialIndex: 3 },
    ]);
    geometry.dispose();
  });

  it("keeps a face's material even when the runs interleave", () => {
    const geometry = sixFaces();
    const material = (face: number): number => (face % 2 === 0 ? 0 : 1);
    setFaceMaterials(geometry, material);
    expect(geometry.groups).toHaveLength(6);
    geometry.groups.forEach((group, index) => {
      expect(group.materialIndex).toBe(material(index));
      expect(group.start).toBe(index * 3);
      expect(group.count).toBe(3);
    });
    geometry.dispose();
  });

  it("covers every triangle exactly once, whatever the assignment", () => {
    const geometry = sixFaces();
    setFaceMaterials(geometry, (face) => (face === 2 ? 2 : face > 3 ? 1 : 0));
    const covered = geometry.groups.flatMap((group) =>
      Array.from({ length: group.count }, (_, i) => group.start + i),
    );
    expect(covered).toEqual(Array.from({ length: 18 }, (_, i) => i));
    // One group per run: [0,1] base, [2] ghost, [3] base, [4,5] selected.
    expect(geometry.groups.map((group) => group.materialIndex)).toEqual([
      0, 2, 0, 1,
    ]);
    geometry.dispose();
  });

  it("leaves a single group when every face shares a material (1 draw call)", () => {
    const geometry = sixFaces();
    setFaceMaterials(geometry, () => 0);
    expect(geometry.groups).toEqual([
      { start: 0, count: 18, materialIndex: 0 },
    ]);
    geometry.dispose();
  });
});

describe("subsetEdges", () => {
  /**
   * A quad split into two triangles that read as two B-rep "faces" — one draw
   * group each (group ordinal === face ordinal), exactly as the GLB merge lays
   * a real body out (one glTF primitive per face).
   */
  function twoFaceQuad(): BufferGeometry {
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      "position",
      new Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0], 3),
    );
    geometry.setIndex([0, 1, 2, 2, 1, 3]);
    geometry.addGroup(0, 3, 0);
    geometry.addGroup(3, 3, 1);
    return geometry;
  }

  it("traces only the requested face ordinals", () => {
    const geometry = twoFaceQuad();
    const one = subsetEdges(geometry, new Set([0]));
    const both = subsetEdges(geometry, new Set([0, 1]));
    expect(one).toBeInstanceOf(EdgesGeometry);
    expect(both).toBeInstanceOf(EdgesGeometry);
    // One triangle has fewer boundary edges than the merged pair.
    const oneCount = one?.getAttribute("position")?.count ?? 0;
    const bothCount = both?.getAttribute("position")?.count ?? 0;
    expect(oneCount).toBeGreaterThan(0);
    expect(bothCount).toBeGreaterThan(oneCount);
    one?.dispose();
    both?.dispose();
    geometry.dispose();
  });

  it("returns null for an empty subset (nothing to emphasise)", () => {
    const geometry = twoFaceQuad();
    expect(subsetEdges(geometry, new Set())).toBeNull();
    geometry.dispose();
  });

  it("returns null for an ungrouped geometry (single-material body)", () => {
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      "position",
      new Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3),
    );
    geometry.setIndex([0, 1, 2]);
    expect(subsetEdges(geometry, new Set([0]))).toBeNull();
    geometry.dispose();
  });
});

describe("faceBoundaryEdges", () => {
  /**
   * TWO COPLANAR FACES sharing a diagonal — the tangent case in its smallest
   * form. The dihedral across the shared edge is 0 degrees, so a crease
   * detector at ANY positive threshold draws nothing; the face partition says
   * one face ends there.
   */
  function tangentPair(): BufferGeometry {
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      "position",
      new Float32BufferAttribute(
        [
          // face 0: (0,0) (1,0) (0,1)
          0, 0, 0, 1, 0, 0, 0, 1, 0,
          // face 1: (0,1) (1,0) (1,1) — its own copies of the shared vertices,
          // exactly as OCCT emits them (one vertex set per B-rep face).
          0, 1, 0, 1, 0, 0, 1, 1, 0,
        ],
        3,
      ),
    );
    geometry.setIndex([0, 1, 2, 3, 4, 5]);
    geometry.addGroup(0, 3, 0);
    geometry.addGroup(3, 3, 1);
    return geometry;
  }

  /** Undirected segment keys of a line geometry, rounded to the weld grid. */
  function segments(edges: BufferGeometry | null): Set<string> {
    const position = edges?.getAttribute("position");
    const out = new Set<string>();
    if (position === undefined) return out;
    const at = (i: number) =>
      [position.getX(i), position.getY(i), position.getZ(i)]
        .map((v) => Math.round(v * 1e4))
        .join(",");
    for (let i = 0; i + 1 < position.count; i += 2) {
      const a = at(i);
      const b = at(i + 1);
      out.add(a < b ? `${a}|${b}` : `${b}|${a}`);
    }
    return out;
  }

  it("draws a TANGENT face boundary that the crease detector cannot see", () => {
    const geometry = tangentPair();
    const DIAGONAL = "0,10000,0|10000,0,0"; // the boundary between the faces

    // THE DEFECT, pinned. A crease detector keeps what it cannot explain — the
    // UNMATCHED outer edges — and drops the one edge that is actually a face
    // boundary, because the two faces meet at 0 degrees. No positive threshold
    // changes that, which is why this was never a tuning problem. (On a CLOSED
    // solid there are no unmatched edges either, and the whole body comes out
    // blank: `06-filleted-body-no-edges.png`.)
    for (const threshold of [25, 1, 0.001]) {
      const creases = new EdgesGeometry(geometry, threshold);
      expect(segments(creases).has(DIAGONAL)).toBe(false);
      expect(segments(creases).size).toBe(4); // the outer ring only
      creases.dispose();
    }

    const edges = faceBoundaryEdges(geometry);
    // Two faces, one shared boundary: the outer ring plus the diagonal.
    expect(segments(edges).size).toBe(5);
    expect(segments(edges).has("0,0,0|10000,0,0")).toBe(true);
    expect(segments(edges).has(DIAGONAL)).toBe(true);
    edges?.dispose();
    geometry.dispose();
  });

  it("never emits an edge INTERIOR to a face, however finely it is cut", () => {
    // One square face cut into 8 triangles around a centre vertex, plus a
    // second face so the partition is non-trivial. A tessellation wireframe of
    // this geometry has 16 interior segments; a face boundary has none.
    const geometry = new BufferGeometry();
    const positions: number[] = [];
    const index: number[] = [];
    const ring = [
      [-1, -1],
      [0, -1],
      [1, -1],
      [1, 0],
      [1, 1],
      [0, 1],
      [-1, 1],
      [-1, 0],
    ];
    positions.push(0, 0, 0); // centre
    for (const [x, y] of ring) positions.push(x as number, y as number, 0);
    for (let i = 0; i < ring.length; i += 1) {
      index.push(0, 1 + i, 1 + ((i + 1) % ring.length));
    }
    geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
    geometry.setIndex(index);
    geometry.addGroup(0, index.length, 0);

    const edges = faceBoundaryEdges(geometry);
    const drawn = segments(edges);
    // The 8 ring segments, and nothing running to the centre.
    expect(drawn.size).toBe(8);
    for (const key of drawn) {
      expect(key.split("|")).not.toContain("0,0,0"); // the centre vertex
    }
    edges?.dispose();
    geometry.dispose();
  });

  it("cancels a closed face's SEAM (a bore has no line down its side)", () => {
    // A two-triangle strip whose far edge is the seam: the seam vertices are
    // DUPLICATED, as a UV seam always is, so an index-based boundary test
    // would emit it. Welding by position makes it interior, with two users.
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      "position",
      new Float32BufferAttribute(
        [
          0,
          0,
          0,
          1,
          0,
          0,
          0,
          1,
          0,
          1,
          1,
          0, // the strip
          0,
          0,
          0,
          0,
          1,
          0,
          -1,
          0.5,
          0, // wraps back to the SAME seam line
        ],
        3,
      ),
    );
    geometry.setIndex([0, 1, 2, 2, 1, 3, 4, 5, 6]);
    geometry.addGroup(0, 9, 0);
    const drawn = segments(faceBoundaryEdges(geometry));
    // The seam (0,0,0)-(0,1,0) is used by two of this face's triangles once
    // welded, so it is NOT drawn.
    expect(drawn.has("0,0,0|0,10000,0")).toBe(false);
    expect(drawn.size).toBeGreaterThan(0);
    geometry.dispose();
  });

  it("restricts to the requested faces, and returns null for none", () => {
    const geometry = tangentPair();
    const one = faceBoundaryEdges(geometry, new Set([0]));
    expect(segments(one).size).toBe(3); // one triangle, three sides
    expect(faceBoundaryEdges(geometry, new Set())).toBeNull();
    expect(faceBoundaryEdges(geometry, new Set([99]))).toBeNull();
    one?.dispose();
    geometry.dispose();
  });

  it("returns null for a geometry with no index", () => {
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      "position",
      new Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3),
    );
    expect(faceBoundaryEdges(geometry)).toBeNull();
    geometry.dispose();
  });

  describe("on real kernel output", () => {
    /**
     * EVERY EMITTED SEGMENT SEPARATES TWO B-REP FACES — derived a different
     * way from the code under test.
     *
     * `faceBoundaryEdges` counts, per face, how many of THAT FACE's triangles
     * use each edge. This walks the whole index buffer once and records which
     * FACES use each edge, then asks a question the implementation never asks:
     * is every drawn segment on a boundary between two different faces? A
     * tessellation wireframe fails it (both users are the same face), and so
     * does any answer derived from dihedral angles.
     */
    function facesPerEdge(geometry: BufferGeometry): Map<string, Set<number>> {
      const index = geometry.getIndex();
      const position = geometry.getAttribute("position");
      const starts = faceStarts(geometry);
      const key = (v: number) =>
        [position.getX(v), position.getY(v), position.getZ(v)]
          .map((c) => Math.round(c * 1e4))
          .join(",");
      const out = new Map<string, Set<number>>();
      for (let face = 0; face + 1 < starts.length; face += 1) {
        const end = starts[face + 1] as number;
        for (let i = starts[face] as number; i + 2 < end; i += 3) {
          const v = [
            key((index?.array[i] as number) ?? 0),
            key((index?.array[i + 1] as number) ?? 0),
            key((index?.array[i + 2] as number) ?? 0),
          ];
          for (let e = 0; e < 3; e += 1) {
            const a = v[e] as string;
            const b = v[(e + 1) % 3] as string;
            const id = a < b ? `${a}|${b}` : `${b}|${a}`;
            const seen = out.get(id) ?? new Set<number>();
            seen.add(face);
            out.set(id, seen);
          }
        }
      }
      return out;
    }

    it("a FILLETED plate: the crease detector draws nothing, this draws its B-rep", async () => {
      const geometry = await parseGlbGeometry(fixture("filleted-plate.glb"));
      expect(geometry).not.toBeNull();
      const body = geometry as BufferGeometry;
      expect(faceCount(body)).toBe(26);

      // THE DEFECT, on real kernel output: an all-edges fillet is tangent
      // everywhere, so the shipped crease detector produced NO line work at
      // all. This is `06-filleted-body-no-edges.png` in one number.
      const creases = new EdgesGeometry(body, 25);
      expect(creases.getAttribute("position").count).toBe(0);
      creases.dispose();

      const edges = faceBoundaryEdges(body);
      const drawn = segments(edges);
      expect(drawn.size).toBeGreaterThan(100);

      // WHERE THE INK IS. Every drawn segment separates two distinct B-rep
      // faces — none is interior to a face, i.e. none is a tessellation line.
      const users = facesPerEdge(body);
      let shared = 0;
      for (const id of drawn) {
        const faces = users.get(id);
        expect(faces).toBeDefined();
        expect((faces as Set<number>).size).toBeGreaterThan(1);
        shared += 1;
      }
      expect(shared).toBe(drawn.size);

      // AND IT IS NOT A WIREFRAME. The body's own triangulation has an order
      // of magnitude more edges than its B-rep does; a wireframe would draw
      // ~1.5 segments per triangle.
      const triangles = ((body.getIndex()?.count ?? 0) / 3) | 0;
      expect(drawn.size).toBeLessThan(triangles * 0.6);

      edges?.dispose();
      body.dispose();
    });

    it("the two-body fixture: same segments from the fused and unfused encodings", async () => {
      const unfused = await parseGlbGeometry(fixture("two-bodies-unfused.glb"));
      const fused = await parseGlbGeometry(fixture("two-bodies-fused.glb"));
      const a = faceBoundaryEdges(unfused as BufferGeometry);
      const b = faceBoundaryEdges(fused as BufferGeometry);
      expect(segments(a).size).toBeGreaterThan(0);
      expect([...segments(b)].sort()).toEqual([...segments(a)].sort());
      a?.dispose();
      b?.dispose();
      unfused?.dispose();
      fused?.dispose();
    });
  });
});
