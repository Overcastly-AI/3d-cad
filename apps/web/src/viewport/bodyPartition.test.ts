import { describe, expect, it } from "vitest";
import { BufferAttribute, BufferGeometry } from "three";

import { bodyFaceSets, faceLumps } from "./bodyPartition";

/**
 * A face-grouped geometry built the way `glbGeometry.parseGlbGeometry` builds
 * one: one draw GROUP per B-rep face, each face carrying its OWN vertices (OCCT
 * writes a glTF primitive per face, so faces of one solid share coordinates but
 * never buffer indices). `boxes` are [originX] offsets — two boxes 100 mm apart
 * share no vertex and must come back as two lumps.
 */
function grouped(faceOffsets: readonly number[][]): BufferGeometry {
  const positions: number[] = [];
  const indices: number[] = [];
  const geometry = new BufferGeometry();
  faceOffsets.forEach((corners) => {
    const start = indices.length;
    const base = positions.length / 3;
    // Every "face" is one triangle whose three corners are given in `corners`
    // flattened as [x,y,z, x,y,z, x,y,z].
    positions.push(...corners);
    indices.push(base, base + 1, base + 2);
    geometry.addGroup(start, 3, 0);
  });
  geometry.setAttribute(
    "position",
    new BufferAttribute(new Float32Array(positions), 3),
  );
  geometry.setIndex(indices);
  return geometry;
}

/** Two triangles sharing an edge — one connected solid. */
const SOLID_A = [
  [0, 0, 0, 1, 0, 0, 0, 1, 0],
  [1, 0, 0, 0, 1, 0, 1, 1, 0],
];
/** The same pair translated 100 mm along X — a second, disjoint solid. */
const SOLID_B = SOLID_A.map((face) =>
  face.map((value, i) => (i % 3 === 0 ? value + 100 : value)),
);

describe("faceLumps", () => {
  it("welds faces that share coordinates into one lump", () => {
    expect(faceLumps(grouped(SOLID_A))).toEqual([[0, 1]]);
  });

  it("separates solids that share no vertex", () => {
    expect(faceLumps(grouped([...SOLID_A, ...SOLID_B]))).toEqual([
      [0, 1],
      [2, 3],
    ]);
  });

  it("orders lumps by their first face, matching the kernel's mesh order", () => {
    const lumps = faceLumps(grouped([...SOLID_B, ...SOLID_A]));
    expect(lumps?.[0]).toEqual([0, 1]);
    expect(lumps?.[1]).toEqual([2, 3]);
  });

  it("returns null for an ungrouped geometry rather than guessing", () => {
    const flat = new BufferGeometry();
    flat.setAttribute(
      "position",
      new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), 3),
    );
    flat.setIndex([0, 1, 2]);
    expect(faceLumps(flat)).toBeNull();
  });
});

describe("bodyFaceSets", () => {
  const lumps = [
    [0, 1],
    [2, 3],
    [4, 5],
  ];

  it("hands each body its own lump when the counts are all 1", () => {
    expect(
      bodyFaceSets(lumps, [{ lumps: 1 }, { lumps: 1 }, { lumps: 1 }]),
    ).toEqual([
      [0, 1],
      [2, 3],
      [4, 5],
    ]);
  });

  it("gives a multi-solid body all of its lumps, in order", () => {
    expect(bodyFaceSets(lumps, [{ lumps: 2 }, { lumps: 1 }])).toEqual([
      [0, 1, 2, 3],
      [4, 5],
    ]);
  });

  it("falls back to one lump each when the counts do not sum but the count of bodies matches", () => {
    // The evaluate did not report lumps (defaulted to 1) for a mesh the kernel
    // welded into fewer pieces than declared — cardinality is then the only
    // consistent reading.
    expect(
      bodyFaceSets(lumps, [{ lumps: 7 }, { lumps: 7 }, { lumps: 7 }]),
    ).toEqual([
      [0, 1],
      [2, 3],
      [4, 5],
    ]);
  });

  it("returns null rather than a plausible-looking wrong answer", () => {
    // Four bodies, three lumps, counts summing to 4 — no honest assignment.
    expect(
      bodyFaceSets(lumps, [
        { lumps: 1 },
        { lumps: 1 },
        { lumps: 1 },
        { lumps: 1 },
      ]),
    ).toBeNull();
    expect(bodyFaceSets(lumps, [])).toBeNull();
  });
});
