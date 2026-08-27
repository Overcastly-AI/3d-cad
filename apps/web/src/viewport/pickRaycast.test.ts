import {
  BufferAttribute,
  BufferGeometry,
  Mesh,
  MeshBasicMaterial,
  Raycaster,
  Vector3,
} from "three";
import { describe, expect, it } from "vitest";

import { faceOrdinalOfTriangle } from "./glbGeometry";
import {
  drawnSurfaceRaycast,
  faceColumnRaycast,
  hiddenTriangleTest,
  nearestDrawnHit,
} from "./pickRaycast";

describe("nearestDrawnHit", () => {
  const drawn = () => false;

  it("returns null for an empty list", () => {
    expect(nearestDrawnHit([], drawn)).toBeNull();
  });

  it("takes the nearest hit when nothing is hidden", () => {
    const hits = [
      { distance: 90, faceIndex: 7 },
      { distance: 10, faceIndex: 2 },
    ];
    expect(nearestDrawnHit(hits, drawn)?.faceIndex).toBe(2);
  });

  it("SEES PAST a nearer HIDDEN hit to the drawn one behind it", () => {
    // The whole bug in one assertion. The refusal the handler used to apply
    // could only drop the near hit and report nothing; here the far, drawn
    // triangle is what the pick addresses.
    const hits = [
      { distance: 10, faceIndex: 2 },
      { distance: 90, faceIndex: 7 },
    ];
    const hidden = (faceIndex: number | null | undefined) => faceIndex === 2;
    expect(nearestDrawnHit(hits, hidden)?.faceIndex).toBe(7);
  });

  it("returns null when EVERY hit is hidden", () => {
    const hits = [
      { distance: 10, faceIndex: 2 },
      { distance: 90, faceIndex: 3 },
    ];
    expect(nearestDrawnHit(hits, () => true)).toBeNull();
  });

  it("keeps the FIRST of equally-near hits", () => {
    const hits = [
      { distance: 42, faceIndex: 5 },
      { distance: 42, faceIndex: 6 },
    ];
    expect(nearestDrawnHit(hits, drawn)?.faceIndex).toBe(5);
  });
});

describe("hiddenTriangleTest", () => {
  /** Two triangles, one draw group each, so `faceStarts` derives from groups. */
  function twoFaceGeometry(): BufferGeometry {
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      "position",
      new BufferAttribute(new Float32Array(18), 3),
    );
    geometry.setIndex([0, 1, 2, 3, 4, 5]);
    geometry.addGroup(0, 3, 0);
    geometry.addGroup(3, 3, 1);
    return geometry;
  }

  it("hides only the triangles of a hidden face ordinal", () => {
    const isHidden = hiddenTriangleTest(twoFaceGeometry(), new Set([1]));
    expect(isHidden(0)).toBe(false);
    expect(isHidden(1)).toBe(true);
  });

  it("KEEPS a triangle with no ordinal — 'no ordinal' is not 'no material'", () => {
    // The guard against the filter becoming "drop everything unresolvable".
    // An unpartitioned mesh is still solid; the `edgeBand` occlusion test has
    // to keep applying to it (see `edgeBand.test.ts`'s matching case).
    const isHidden = hiddenTriangleTest(twoFaceGeometry(), new Set([0, 1]));
    expect(isHidden(99), "a triangle outside the partition").toBe(false);
    expect(isHidden(null)).toBe(false);
    expect(isHidden(undefined)).toBe(false);
  });

  it("is inert with no geometry or an empty hidden set", () => {
    expect(hiddenTriangleTest(null, new Set([0]))(0)).toBe(false);
    expect(hiddenTriangleTest(twoFaceGeometry(), new Set())(0)).toBe(false);
  });
});

describe("drawnSurfaceRaycast, against REAL three", () => {
  /**
   * THE MUTATION-SENSITIVE CASE. Two parallel quads at different depths in ONE
   * `BufferGeometry`, one draw group each so `faceStarts` derives from the
   * groups and face ordinal 0 is the NEAR quad, 1 the FAR one.
   *
   * Raycasting needs no DOM, so this runs in the node project against the real
   * `Mesh.raycast` this module wraps — which is the point: restoring
   * `Mesh.prototype.raycast` on the mesh must make the hidden-near case fail.
   * A hand-rolled fake of three's intersection list could not do that.
   */
  function twoQuadMesh(): Mesh {
    const near = 0;
    const far = -10;
    /** Four corners of an axis-aligned 10 × 10 quad at depth `z`. */
    const quad = (z: number): number[] =>
      (
        [
          [-5, -5],
          [5, -5],
          [5, 5],
          [-5, 5],
        ] as const
      ).flatMap(([x, y]) => [x, y, z]);
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      "position",
      new BufferAttribute(new Float32Array([...quad(near), ...quad(far)]), 3),
    );
    // Two triangles per quad; the near quad's indices come first.
    geometry.setIndex([0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7]);
    geometry.addGroup(0, 6, 0);
    geometry.addGroup(6, 6, 0);
    const mesh = new Mesh(
      geometry,
      new MeshBasicMaterial({ side: 2 /* DoubleSide */ }),
    );
    mesh.updateMatrixWorld(true);
    return mesh;
  }

  /** A ray down -Z through the middle of both quads. */
  function centreRay(): Raycaster {
    return new Raycaster(new Vector3(0, 0, 20), new Vector3(0, 0, -1), 0, 1000);
  }

  /** The face ordinal of every intersection three reported, in order. */
  function ordinals(mesh: Mesh): number[] {
    const geometry = mesh.geometry;
    const starts = geometry.groups.map((group) => group.start);
    return centreRay()
      .intersectObject(mesh)
      .map((hit) => {
        const triangle = (hit.faceIndex ?? 0) * 3;
        return starts.filter((start) => start <= triangle).length - 1;
      });
  }

  it("reports the near quad when nothing is hidden", () => {
    const mesh = twoQuadMesh();
    mesh.raycast = drawnSurfaceRaycast(
      hiddenTriangleTest(mesh.geometry, new Set()),
    );
    expect(ordinals(mesh)).toEqual([0]);
  });

  it("reports the FAR quad when the near one is HIDDEN — exactly one hit", () => {
    const mesh = twoQuadMesh();
    mesh.raycast = drawnSurfaceRaycast(
      hiddenTriangleTest(mesh.geometry, new Set([0])),
    );
    expect(ordinals(mesh)).toEqual([1]);
  });

  it("reports NOTHING when both quads are hidden", () => {
    const mesh = twoQuadMesh();
    mesh.raycast = drawnSurfaceRaycast(
      hiddenTriangleTest(mesh.geometry, new Set([0, 1])),
    );
    expect(ordinals(mesh)).toEqual([]);
  });

  it("NEGATIVE CONTROL: stock `Mesh.raycast` answers with the hidden near quad", () => {
    // The mutation, asserted rather than described. With three's own raycast
    // the near (hidden) quad is the first hit and r3f would dedupe to exactly
    // it — which is the 7.4 % census on `seedOccludedEdgePlate`.
    const mesh = twoQuadMesh();
    expect(ordinals(mesh)[0]).toBe(0);
  });

  it("accepts an edge behind a HIDDEN body — hiding it is how you reach this", () => {
    // RELOCATED from `edgeBand.test.ts`, where it asserted a `surfaceOccludes`
    // predicate that no longer exists. The decision moved a layer down: the
    // hidden body's triangle never reaches the intersection list, so it can no
    // longer set the band's occlusion distance and refuse the edge behind it.
    // Stated on the surface rather than on the band, because that is now where
    // it is made.
    const mesh = twoQuadMesh();
    mesh.raycast = drawnSurfaceRaycast(
      hiddenTriangleTest(mesh.geometry, new Set([0])),
    );
    const hits = centreRay().intersectObject(mesh);
    expect(hits).toHaveLength(1);
    // The surviving hit is 10 units FURTHER away — the drawn material, so an
    // edge between the two quads is now accepted where it used to be refused.
    expect(hits[0]?.distance).toBeCloseTo(30, 6);
  });
});

describe("faceColumnRaycast, against REAL three", () => {
  /**
   * The MATE-1 shape, and the same two-quad fixture the nearest-hit block
   * uses: two parallel quads in ONE geometry, one draw group each, so ordinal
   * 0 is the near quad and 1 the far one. The far quad is what a BURIED mate
   * face looks like — a surface the ray reaches only after passing through
   * something else. What is under test is how many of them survive.
   */
  function twoQuadMesh(): Mesh {
    const quad = (z: number): number[] =>
      (
        [
          [-5, -5],
          [5, -5],
          [5, 5],
          [-5, 5],
        ] as const
      ).flatMap(([x, y]) => [x, y, z]);
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      "position",
      new BufferAttribute(new Float32Array([...quad(0), ...quad(-10)]), 3),
    );
    geometry.setIndex([0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7]);
    geometry.addGroup(0, 6, 0);
    geometry.addGroup(6, 6, 0);
    const mesh = new Mesh(
      geometry,
      new MeshBasicMaterial({ side: 2 /* DoubleSide */ }),
    );
    mesh.updateMatrixWorld(true);
    return mesh;
  }

  function centreRay(): Raycaster {
    return new Raycaster(new Vector3(0, 0, 20), new Vector3(0, 0, -1), 0, 1000);
  }

  function columnMesh(hidden: number[] = []): Mesh {
    const mesh = twoQuadMesh();
    const geometry = mesh.geometry;
    mesh.raycast = faceColumnRaycast(
      hiddenTriangleTest(geometry, new Set(hidden)),
      (faceIndex) =>
        faceIndex === undefined || faceIndex === null
          ? null
          : faceOrdinalOfTriangle(geometry, faceIndex),
    );
    return mesh;
  }

  it("reports BOTH faces the ray pierces, near first", () => {
    const hits = centreRay().intersectObject(columnMesh());
    expect(hits.map((hit) => hit.index)).toEqual([0, 1]);
    expect(hits.map((hit) => hit.distance)).toEqual([20, 30]);
  });

  it("stamps `index` with the FACE ORDINAL — r3f's dedupe key", () => {
    // Not decoration: `makeId` is `uuid + '/' + index + instanceId`, so without
    // a distinct `index` per face r3f collapses this mesh's hits back to ONE
    // and the column never reaches a handler at all.
    const ids = centreRay()
      .intersectObject(columnMesh())
      .map((hit) => `${hit.object.uuid}/${hit.index}${hit.instanceId}`);
    expect(new Set(ids).size).toBe(2);
  });

  it("emits ONE candidate per face, not one per triangle", () => {
    // Each quad is two triangles. A face is one candidate however finely it
    // was tessellated, or the column reads as the same face listed twice.
    expect(centreRay().intersectObject(columnMesh())).toHaveLength(2);
  });

  it("still drops a HIDDEN body's face — the column is of DRAWN faces", () => {
    expect(
      centreRay()
        .intersectObject(columnMesh([0]))
        .map((hit) => hit.index),
    ).toEqual([1]);
  });

  it("NEGATIVE CONTROL: the nearest-hit raycast reports only the NEAR face", () => {
    // The mutation this gate exists to catch, asserted rather than described.
    // Swap `faceColumnRaycast` back for `drawnSurfaceRaycast` — which is what
    // every mate pick used before MATE-1 — and the buried face is gone.
    const mesh = twoQuadMesh();
    mesh.raycast = drawnSurfaceRaycast(
      hiddenTriangleTest(mesh.geometry, new Set()),
    );
    const hits = centreRay().intersectObject(mesh);
    expect(hits).toHaveLength(1);
    expect(hits[0]?.distance).toBeCloseTo(20, 6);
  });
});
