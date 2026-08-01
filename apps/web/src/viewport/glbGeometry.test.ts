import { readFileSync } from "node:fs";

import { BufferGeometry, EdgesGeometry, Float32BufferAttribute } from "three";
import { describe, expect, it, vi } from "vitest";

import { faceLumps } from "./bodyPartition";
import {
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
