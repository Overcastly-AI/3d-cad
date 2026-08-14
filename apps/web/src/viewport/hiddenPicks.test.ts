import { BufferAttribute, BufferGeometry } from "three";
import { describe, expect, it } from "vitest";

import type { Vec3 } from "../api/measure";
import { faceLumps } from "./bodyPartition";
import { hiddenPickFilter, OFFER_EVERYTHING } from "./hiddenPicks";

/**
 * TWO DISJOINT BOXES IN ONE FUSED MESH — `seedOccludedEdgePlate` in miniature,
 * and the only fixture that can tell this filter from a no-op.
 *
 * Positions are SCENE space (the geometry `ModelMesh` publishes is the GLB
 * baked through OCCT's Z-up→Y-up rotation and scaled to mm), so the OCCT-space
 * points the overlay carries have to survive `occtToScene` to match — a
 * conversion this filter owns and the tests below exercise by passing OCCT
 * coordinates, never scene ones.
 *
 * OCCT (x, y, z) → scene (x, z, -y). Body A occupies OCCT y = 0…20, body B
 * OCCT y = 30…50, so nothing is shared and no bucket is ambiguous.
 */
const BODY_A_OCCT: readonly [number, number, number][] = [
  [0, 0, 0],
  [10, 0, 0],
  [10, 20, 0],
  [0, 20, 0],
];
const BODY_B_OCCT: readonly [number, number, number][] = [
  [0, 30, 0],
  [10, 30, 0],
  [10, 50, 0],
  [0, 50, 0],
];

const occt = (p: readonly [number, number, number]): Vec3 => ({
  x: p[0],
  y: p[1],
  z: p[2],
});

/** The scene position of an OCCT point, as the mesh would carry it. */
const scene = (p: readonly [number, number, number]): number[] => [
  p[0],
  p[2],
  -p[1],
];

/**
 * One quad per body, one draw group each, so `faceStarts` derives from the
 * groups: face ordinal 0 is body A, ordinal 1 is body B.
 */
function twoBodyGeometry(): BufferGeometry {
  const geometry = new BufferGeometry();
  geometry.setAttribute(
    "position",
    new BufferAttribute(
      new Float32Array([
        ...BODY_A_OCCT.flatMap(scene),
        ...BODY_B_OCCT.flatMap(scene),
      ]),
      3,
    ),
  );
  geometry.setIndex([0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7]);
  geometry.addGroup(0, 6, 0);
  geometry.addGroup(6, 6, 1);
  return geometry;
}

/** Body A's bottom edge, as `/overlay` reports it (OCCT mm, start..end). */
const EDGE_A: readonly Vec3[] = [occt(BODY_A_OCCT[0]!), occt(BODY_A_OCCT[1]!)];
/** Body B's bottom edge. */
const EDGE_B: readonly Vec3[] = [occt(BODY_B_OCCT[0]!), occt(BODY_B_OCCT[1]!)];

describe("hiddenPickFilter", () => {
  it("is inert with nothing hidden, and with no mesh at all", () => {
    expect(hiddenPickFilter(twoBodyGeometry(), new Set())).toBe(
      OFFER_EVERYTHING,
    );
    expect(hiddenPickFilter(null, new Set([0]))).toBe(OFFER_EVERYTHING);
  });

  it("withholds the HIDDEN body's edge and keeps the drawn one's", () => {
    // The review's finding in one assertion: a switched-off body no longer
    // EATS picks (`pickRaycast.ts`) but still OFFERED them.
    const filter = hiddenPickFilter(twoBodyGeometry(), new Set([0]));
    expect(filter.isHiddenEdge(EDGE_A), "the hidden body's edge").toBe(true);
    expect(filter.isHiddenEdge(EDGE_B), "the drawn body's edge").toBe(false);
  });

  it("withholds the HIDDEN body's snap points and keeps the drawn one's", () => {
    const filter = hiddenPickFilter(twoBodyGeometry(), new Set([1]));
    expect(filter.isHiddenPoint(occt(BODY_B_OCCT[2]!))).toBe(true);
    expect(filter.isHiddenPoint(occt(BODY_A_OCCT[2]!))).toBe(false);
  });

  it("reports the hidden FACE ordinals it was given", () => {
    const filter = hiddenPickFilter(twoBodyGeometry(), new Set([1]));
    expect(filter.isHiddenFace(1)).toBe(true);
    expect(filter.isHiddenFace(0)).toBe(false);
  });

  it("matches a corner the float32 mesh quantized one bucket away", () => {
    // The mesh is float32 METRES scaled to mm; the overlay is the kernel's
    // float64. The same corner can therefore land either side of a weld
    // boundary, and a strict bucket lookup would silently keep offering a
    // hidden edge. 6e-5 mm is deliberately the far side of the boundary
    // (`round(0.6) === 1`, not 0) and still inside the 1e-4 mm weld tolerance,
    // so deleting the one-bucket neighbourhood makes THIS case fail and no
    // other — which is what makes it a test of the widening rather than of the
    // lookup.
    const filter = hiddenPickFilter(twoBodyGeometry(), new Set([0]));
    const nudged = EDGE_A.map((p) => ({
      x: p.x + 6e-5,
      y: p.y - 6e-5,
      z: p.z + 6e-5,
    }));
    expect(filter.isHiddenEdge(nudged)).toBe(true);
  });

  it("KEEPS an edge whose endpoints are not mesh corners at all", () => {
    // The conservative direction, and the one that matters: withholding a pick
    // the modeller can SEE would be worse than the defect being fixed. An
    // endpoint that matches no bucket (a mesh with a different partition, a
    // sketch entity, a rounding regime nobody anticipated) stays on offer.
    const filter = hiddenPickFilter(twoBodyGeometry(), new Set([0]));
    expect(
      filter.isHiddenEdge([
        { x: 999, y: 999, z: 999 },
        { x: 998, y: 999, z: 999 },
      ]),
    ).toBe(false);
  });

  it("KEEPS an edge with one endpoint on each body", () => {
    // Ambiguity resolves to the status quo, never to withholding.
    const filter = hiddenPickFilter(twoBodyGeometry(), new Set([0]));
    expect(
      filter.isHiddenEdge([occt(BODY_A_OCCT[0]!), occt(BODY_B_OCCT[0]!)]),
    ).toBe(false);
  });

  it("KEEPS a corner a hidden face SHARES with a drawn one", () => {
    // The other ambiguity, and the one a two-disjoint-body fixture cannot
    // stage: a bucket carrying BOTH bits. It arises when solids touch (the
    // lump split then refuses to divide them, but a filter that trusted a
    // hidden match alone would still withhold) — so "hidden" means hidden AND
    // NOT drawn, not merely "matched something hidden".
    const shared = occt(BODY_A_OCCT[1]!);
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      "position",
      new BufferAttribute(
        new Float32Array([
          ...BODY_A_OCCT.flatMap(scene),
          // A second face hanging off body A's corner 1 — same position, so
          // the same weld bucket, but a DRAWN face ordinal.
          ...scene(BODY_A_OCCT[1]!),
          ...scene([20, 0, 0]),
          ...scene([20, 20, 0]),
        ]),
        3,
      ),
    );
    geometry.setIndex([0, 1, 2, 0, 2, 3, 4, 5, 6]);
    geometry.addGroup(0, 6, 0);
    geometry.addGroup(6, 3, 1);
    const filter = hiddenPickFilter(geometry, new Set([0]));
    expect(filter.isHiddenPoint(shared), "shared by a drawn face").toBe(false);
    expect(
      filter.isHiddenPoint(occt(BODY_A_OCCT[3]!)),
      "the hidden face's own corner",
    ).toBe(true);
  });

  it("KEEPS everything when the mesh carries no face partition", () => {
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      "position",
      new BufferAttribute(
        new Float32Array(BODY_A_OCCT.flatMap(scene) as number[]),
        3,
      ),
    );
    geometry.setIndex([0, 1, 2, 0, 2, 3]);
    const filter = hiddenPickFilter(geometry, new Set([0]));
    expect(filter.isHiddenEdge(EDGE_A)).toBe(false);
  });

  it("agrees with the lump split about which faces are one body", () => {
    // The two derivations share `weldKey`, so this pins the property the
    // filter leans on: the fixture really is two disjoint bodies, one face
    // each — if it were one lump the whole premise (a bucket belongs to
    // exactly one body) would not hold and this fixture would prove nothing.
    expect(faceLumps(twoBodyGeometry())).toEqual([[0], [1]]);
  });
});
