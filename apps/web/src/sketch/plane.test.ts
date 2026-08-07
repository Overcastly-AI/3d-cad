import { describe, expect, it } from "vitest";

import {
  DATUM_PLANES,
  deterministicXDir,
  describePlane,
  faceBasis,
  faceSpecFromDatum,
  midplaneBasis,
  occtToSceneTuple,
  offsetBasis,
  offsetFromBasis,
  originBasis,
  type PlanarFaceSignature,
  PLANE_BASES,
  planeCameraPose,
  planeRefFromSpec,
  planeToWorld,
  resolveDatumBasis,
  resolveDatumPlaneOptions,
  resolveSpecBasis,
  sceneOriginBasis,
  snapPoint,
  snapValue,
  worldToPlane,
} from "./plane";

describe("plane bases", () => {
  it("matches build123d's datum planes (normal = u × v)", () => {
    for (const plane of DATUM_PLANES) {
      const { u, v, normal } = PLANE_BASES[plane];
      const cross = [
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
      ];
      expect(cross).toEqual([...normal]);
    }
    expect(PLANE_BASES.XZ.normal).toEqual([0, -1, 0]); // build123d Plane.XZ
    // Origin datums sit through the world origin.
    for (const plane of DATUM_PLANES) {
      expect([...PLANE_BASES[plane].origin]).toEqual([0, 0, 0]);
    }
  });

  it("maps plane points into the right world axes (origin datums)", () => {
    expect(planeToWorld(originBasis("XY"), { x: 3, y: 4 })).toEqual([3, 4, 0]);
    expect(planeToWorld(originBasis("XZ"), { x: 3, y: 4 })).toEqual([3, 0, 4]);
    expect(planeToWorld(originBasis("YZ"), { x: 3, y: 4 })).toEqual([0, 3, 4]);
  });

  it("round-trips world → plane → world on the plane", () => {
    for (const plane of DATUM_PLANES) {
      const basis = originBasis(plane);
      const point = { x: -12.5, y: 7.25 };
      expect(worldToPlane(basis, planeToWorld(basis, point))).toEqual(point);
    }
  });

  it("projects off-plane world points along the normal", () => {
    expect(worldToPlane(originBasis("XY"), [3, 4, 99])).toEqual({ x: 3, y: 4 });
    expect(worldToPlane(originBasis("XZ"), [3, -99, 4])).toEqual({
      x: 3,
      y: 4,
    });
  });
});

describe("offsetBasis — the sketch-at-a-height math", () => {
  it("slides the origin along the base normal by offset_mm", () => {
    // XY normal is +Z, so a +30 offset lifts the plane to z=30.
    const up = offsetBasis("XY", 30, false);
    expect([...up.origin]).toEqual([0, 0, 30]);
    // Orientation is unchanged from the base, so u/v are identical.
    expect([...up.u]).toEqual([1, 0, 0]);
    expect([...up.v]).toEqual([0, 1, 0]);
    expect([...up.normal]).toEqual([0, 0, 1]);
    // A plane point maps to world at the offset height.
    expect(planeToWorld(up, { x: 5, y: 7 })).toEqual([5, 7, 30]);
  });

  it("uses the base normal's sign (XZ normal is −Y)", () => {
    const back = offsetBasis("XZ", 10, false);
    expect([...back.origin]).toEqual([0, -10, 0]);
    expect(planeToWorld(back, { x: 2, y: 3 })).toEqual([2, -10, 3]);
  });

  it("flip reverses the normal and v, keeps u and the offset origin", () => {
    const flipped = offsetBasis("XY", 30, true);
    // Origin still slides along the ORIGINAL base normal (offset unchanged).
    expect([...flipped.origin]).toEqual([0, 0, 30]);
    expect([...flipped.u]).toEqual([1, 0, 0]); // +u unchanged
    expect(flipped.v[1]).toBe(-1); // +v flips
    expect(flipped.normal[2]).toBe(-1); // normal flips (was +1)
    // A negative offset selects the other side.
    expect([...offsetBasis("XY", -12, false).origin]).toEqual([0, 0, -12]);
  });

  it("offset 0 coincides with the origin datum", () => {
    expect([...offsetBasis("XY", 0, false).origin]).toEqual([0, 0, 0]);
    expect(planeToWorld(offsetBasis("YZ", 0, false), { x: 3, y: 4 })).toEqual(
      planeToWorld(originBasis("YZ"), { x: 3, y: 4 }),
    );
  });
});

describe("plane spec ↔ wire ref", () => {
  it("resolves an origin spec to its world-frame basis", () => {
    expect([
      ...resolveSpecBasis({ kind: "origin", base: "XZ" }).origin,
    ]).toEqual([0, 0, 0]);
  });

  // SCENE frame, not the kernel's: `resolveSpecBasis` is the RENDERER's entry
  // point, and everything it feeds (sketch ink, grid, pointer catcher, camera,
  // extrude ghost) draws into a Y-up scene. An XY sketch 25 mm up therefore
  // sits at scene y=25 — the direction the body it makes will grow. Before
  // FB-7c this branch returned the kernel's [0,0,25] while the `on_face` branch
  // returned scene coordinates, so the same call site got a basis 90° apart
  // depending on which plane the user had picked (FB-9).
  it("resolves an offset spec to its placed basis, in SCENE coordinates", () => {
    const basis = resolveSpecBasis({
      kind: "offset",
      base: "XY",
      offsetMm: 25,
      flip: false,
      datumFeatureId: "f-1",
    });
    expect([...basis.origin]).toEqual([0, 25, 0]);
    expect([...basis.normal]).toEqual([0, 1, 0]);
    // The kernel-frame algebra is untouched — one call in, one rotation out.
    expect([...offsetBasis("XY", 25, false).origin]).toEqual([0, 0, 25]);
  });

  it("builds a datum_plane ref for an origin spec", () => {
    expect(planeRefFromSpec({ kind: "origin", base: "YZ" })).toEqual({
      kind: "datum_plane",
      plane: "YZ",
    });
  });

  it("builds a FeatureRef for an offset spec", () => {
    expect(
      planeRefFromSpec({
        kind: "offset",
        base: "XY",
        offsetMm: 30,
        flip: false,
        datumFeatureId: "f-p001",
      }),
    ).toEqual({ kind: "feature", feature_id: "f-p001" });
  });
});

describe("planeCameraPose", () => {
  it("looks normal-on with the sketch +v axis up (origin datums)", () => {
    expect(planeCameraPose(originBasis("XY"), 140)).toEqual({
      position: [0, 0, 140],
      up: [0, 1, 0],
      target: [0, 0, 0],
    });
    // XZ's normal is −Y (build123d), so the camera sits below the ground.
    expect(planeCameraPose(originBasis("XZ"), 140).position).toEqual([
      0, -140, 0,
    ]);
    expect(planeCameraPose(originBasis("YZ"), 140).up).toEqual([0, 0, 1]);
  });

  it("sits normal-on above an offset plane, looking at its centre", () => {
    const pose = planeCameraPose(offsetBasis("XY", 30, false), 140);
    expect(pose.position).toEqual([0, 0, 170]); // 30 + 140 along +Z
    expect(pose.target).toEqual([0, 0, 30]); // the plane centre
  });
});

/** A planar-face signature helper for the on-face basis tests. */
function signature(
  normal: [number, number, number],
  centroid: [number, number, number],
): PlanarFaceSignature {
  return {
    normal: { x: normal[0], y: normal[1], z: normal[2] },
    centroid: { x: centroid[0], y: centroid[1], z: centroid[2] },
    area_mm2: 100,
    subshape_type: "face",
    surface: "plane",
  };
}

describe("deterministicXDir — the kernel's _deterministic_x_dir port", () => {
  it("picks world +X for a +Z face (box top)", () => {
    expect([...deterministicXDir([0, 0, 1])]).toEqual([1, 0, 0]);
  });

  it("breaks axis ties by order X < Y < Z (a +X face → +Y)", () => {
    // |x·n|=1, |y·n|=|z·n|=0 → the earliest least-aligned axis (Y) wins.
    expect([...deterministicXDir([1, 0, 0])]).toEqual([0, 1, 0]);
    // A +Y face: |y·n|=1, X and Z tie at 0 → X wins.
    expect([...deterministicXDir([0, 1, 0])]).toEqual([1, 0, 0]);
  });

  it("returns a unit vector orthogonal to the normal (a tilted face)", () => {
    const n: [number, number, number] = [0, 0.6, 0.8];
    const x = deterministicXDir(n);
    expect(Math.hypot(...x)).toBeCloseTo(1, 12);
    expect(x[0] * n[0] + x[1] * n[1] + x[2] * n[2]).toBeCloseTo(0, 12);
  });
});

describe("occtToSceneTuple — the one OCCT(Z-up)→scene(Y-up) rotation", () => {
  it("maps (x, y, z) → (x, z, −y)", () => {
    expect([...occtToSceneTuple([1, 2, 3])]).toEqual([1, 3, -2]);
    expect([...occtToSceneTuple([0, 0, 1])]).toEqual([0, 1, 0]); // +Z → up
  });

  it("never emits -0 for a zero Y", () => {
    const [, , z] = occtToSceneTuple([5, 0, 7]);
    expect(Object.is(z, 0)).toBe(true);
  });
});

describe("scene-frame bases — the frame every renderer must draw from", () => {
  // THE regression pin for FB-7c / FB-9. The GLB bakes OCCT's Z-up→Y-up
  // rotation, so the body renders in a Y-up scene while the datum algebra is
  // stated in the kernel's Z-up frame. Drawing from the un-rotated basis stood
  // an XY sketch (and its ink, its sheet and its live extrude ghost) VERTICAL,
  // at right angles to the body the same sketch had just produced. Measured in
  // a real browser before the fix: body at scene y∈[0,10] z∈[−15.4,16.6], its
  // own ghost at y∈[−16.6,15.4] z∈[0,10].
  it("puts XY on the ground plane, not standing up", () => {
    const scene = sceneOriginBasis("XY");
    // The adaptive ground grid IS the XY plane; its normal is scene up.
    expect([...scene.normal]).toEqual([0, 1, 0]);
    expect([...scene.u]).toEqual([1, 0, 0]);
    expect([...scene.v]).toEqual([0, 0, -1]);
    // The kernel-frame basis is deliberately unchanged (it mirrors build123d).
    expect([...originBasis("XY").normal]).toEqual([0, 0, 1]);
  });

  it("keeps every scene basis right-handed (normal = u × v)", () => {
    // `extrudeGhostPose` orients local +Z onto `normal` via a rotation matrix;
    // a left-handed basis would silently produce a mirrored quaternion.
    for (const plane of DATUM_PLANES) {
      const { u, v, normal } = sceneOriginBasis(plane);
      expect(
        [
          u[1] * v[2] - u[2] * v[1],
          u[2] * v[0] - u[0] * v[2],
          u[0] * v[1] - u[1] * v[0],
          // `+ 0` folds a -0 term (0 * -1) so the triple compares cleanly.
        ].map((component) => component + 0),
      ).toEqual([...normal]);
    }
  });

  it("preserves the (u,v) meaning the server resolves", () => {
    // The rotation is a change of coordinates, not of geometry: a plane point
    // maps to the same physical place, so sketch entities on the wire (which
    // are (u,v) mm) mean exactly what they did before.
    for (const plane of DATUM_PLANES) {
      const point = { x: 7, y: -3 };
      expect([...planeToWorld(sceneOriginBasis(plane), point)]).toEqual([
        ...occtToSceneTuple(planeToWorld(originBasis(plane), point)),
      ]);
    }
  });

  it("agrees with faceBasis, which was already scene-frame", () => {
    // A sketch on a box's top face and a sketch on XY are the same plane, one
    // resolved through the face signature and one through the datum table.
    // They disagreed by 90° before the fix — the whole defect in one line.
    const top = faceBasis(signature([0, 0, 1], [0, 0, 0]), 0);
    expect([...top.normal]).toEqual([...sceneOriginBasis("XY").normal]);
  });
});

describe("faceBasis — sketch on a picked planar face", () => {
  it("lands the ink on the rendered top face, matching the kernel mapping", () => {
    // A box top: OCCT normal +Z, centroid (10,10,10).
    const basis = faceBasis(signature([0, 0, 1], [10, 10, 10]), 0);
    // Scene frame: origin at the face centre, normal up (+Y).
    expect([...basis.origin]).toEqual([10, 10, -10]);
    expect([...basis.normal]).toEqual([0, 1, 0]);
    // A drawn point maps to the SAME physical spot the kernel resolves: the
    // backend places (u,v)=(2,3) at OCCT (12,13,10) → scene (12,10,-13).
    expect(planeToWorld(basis, { x: 2, y: 3 })).toEqual([12, 10, -13]);
  });

  it("is orthonormal (normal = u × v)", () => {
    const { u, v, normal } = faceBasis(signature([0, 1, 0], [0, 5, 0]), 0);
    const cross = [
      u[1] * v[2] - u[2] * v[1],
      u[2] * v[0] - u[0] * v[2],
      u[0] * v[1] - u[1] * v[0],
    ];
    cross.forEach((c, i) => expect(c).toBeCloseTo(normal[i] as number, 12));
  });

  it("offsets the origin along the face normal", () => {
    // +Z face lifted 5 mm → OCCT z=15 → scene y=15.
    const basis = faceBasis(signature([0, 0, 1], [10, 10, 10]), 5);
    expect([...basis.origin]).toEqual([10, 15, -10]);
  });
});

describe("on-face plane spec ↔ wire ref", () => {
  const spec = faceSpecFromDatum(
    "d-face-1",
    signature([0, 0, 1], [1, 2, 3]),
    0,
  );

  it("resolves to the face basis", () => {
    if (spec.kind !== "on_face") throw new Error("expected on_face spec");
    expect([...resolveSpecBasis(spec).origin]).toEqual([1, 3, -2]);
  });

  it("builds a FeatureRef to the on_face datum", () => {
    expect(planeRefFromSpec(spec)).toEqual({
      kind: "feature",
      feature_id: "d-face-1",
    });
  });

  it("describes the plane as a face (with signed offset)", () => {
    expect(describePlane(spec)).toBe("Face");
    expect(
      describePlane(faceSpecFromDatum("d", signature([0, 0, 1], [0, 0, 0]), 5)),
    ).toBe("Face +5");
  });
});

describe("offsetFromBasis — offset chaining off an arbitrary base plane", () => {
  it("slides an offset datum further along its own normal", () => {
    // XY + 30, then + 10 more → z = 40 (the composite a chain resolves to).
    const base = offsetBasis("XY", 30, false);
    const chained = offsetFromBasis(base, 10, false);
    expect([...chained.origin]).toEqual([0, 0, 40]);
    expect([...chained.normal]).toEqual([0, 0, 1]);
    expect([...chained.u]).toEqual([1, 0, 0]);
  });

  it("flip reverses the normal and v, keeps u", () => {
    const flipped = offsetFromBasis(offsetBasis("XY", 30, false), 0, true);
    expect([...flipped.origin]).toEqual([0, 0, 30]);
    expect(flipped.normal[2]).toBe(-1);
    expect(flipped.v[1]).toBe(-1);
    expect([...flipped.u]).toEqual([1, 0, 0]);
  });
});

describe("midplaneBasis — the plane midway between two references", () => {
  it("parallel sides: midpoint origin, side a's normal (mid point plane)", () => {
    // Between XY (z=0) and XY+40 (z=40) → the plane at z=20.
    const mid = midplaneBasis(
      originBasis("XY"),
      offsetBasis("XY", 40, false),
      false,
    );
    expect([...mid.origin]).toEqual([0, 0, 20]);
    expect([...mid.normal]).toEqual([0, 0, 1]);
    // x_dir is pinned from the normal (deterministic), y = z × x.
    expect([...mid.u]).toEqual([...deterministicXDir([0, 0, 1])]);
  });

  it("anti-parallel sides degenerate to the midway plane", () => {
    // XY (normal +Z) and a flipped XY+20 (normal −Z) → still parallel branch.
    const mid = midplaneBasis(
      originBasis("XY"),
      offsetBasis("XY", 20, true),
      false,
    );
    expect([...mid.origin]).toEqual([0, 0, 10]);
  });

  it("non-parallel sides: the angular bisector (normalize(n_a + n_b))", () => {
    // XY (normal +Z) and YZ (normal +X) meet at 90° → bisector normal is the
    // unit sum, and the origin is the min-norm point (both through the world
    // origin → the line through 0, nearest point is 0).
    const mid = midplaneBasis(originBasis("XY"), originBasis("YZ"), false);
    const inv = 1 / Math.sqrt(2);
    expect(mid.normal[0]).toBeCloseTo(inv, 12);
    expect(mid.normal[1]).toBeCloseTo(0, 12);
    expect(mid.normal[2]).toBeCloseTo(inv, 12);
    expect([...mid.origin]).toEqual([0, 0, 0]);
  });

  it("flip selects the other bisector / reverses the normal", () => {
    const mid = midplaneBasis(
      originBasis("XY"),
      offsetBasis("XY", 40, false),
      true,
    );
    expect(mid.normal[2]).toBe(-1);
  });
});

describe("resolveDatumBasis — walk any datum kind to its basis", () => {
  const offset = {
    kind: "offset",
    base: "XY",
    offset_mm: 40,
    flip: false,
  } as const;
  const offsetFrom = {
    kind: "offset_from",
    base: { kind: "feature", feature_id: "d1" },
    offset_mm: -10,
    flip: false,
  } as const;
  const midplane = {
    kind: "midplane",
    a: { kind: "datum_plane", plane: "XY" },
    b: { kind: "feature", feature_id: "d1" },
    flip: false,
  } as const;

  it("resolves an offset datum", () => {
    const byId = new Map([["d1", offset]]);
    expect([...(resolveDatumBasis("d1", byId)?.origin ?? [])]).toEqual([
      0, 0, 40,
    ]);
  });

  it("resolves an offset_from chain (d1: XY+40, d2: d1−10 → z=30)", () => {
    const byId = new Map<string, typeof offset | typeof offsetFrom>([
      ["d1", offset],
      ["d2", offsetFrom],
    ]);
    expect([...(resolveDatumBasis("d2", byId)?.origin ?? [])]).toEqual([
      0, 0, 30,
    ]);
  });

  it("resolves a midplane between an origin datum and an earlier datum", () => {
    const byId = new Map<string, typeof offset | typeof midplane>([
      ["d1", offset],
      ["d2", midplane],
    ]);
    // Between XY (z=0) and d1 (z=40) → z=20.
    expect([...(resolveDatumBasis("d2", byId)?.origin ?? [])]).toEqual([
      0, 0, 20,
    ]);
  });

  it("returns null for a missing reference or an on_face datum", () => {
    expect(resolveDatumBasis("missing", new Map())).toBeNull();
    const onFace = {
      kind: "on_face",
      face: {
        kind: "subshape",
        feature_id: "x",
        subshape_type: "face",
        selector: {
          selector_version: 1,
          signature: {
            subshape_type: "face",
            surface: "plane",
            normal: { x: 0, y: 0, z: 1 },
            centroid: { x: 0, y: 0, z: 0 },
            area_mm2: 1,
          },
        },
      },
      offset_mm: 0,
    } as const;
    expect(resolveDatumBasis("d1", new Map([["d1", onFace]]))).toBeNull();
  });
});

describe("datum plane spec ↔ wire ref", () => {
  const basis = offsetBasis("XY", 20, false);
  const spec = {
    kind: "datum" as const,
    datumFeatureId: "d5",
    label: "Plane2",
    basis,
  };

  it("resolves to the carried basis and a FeatureRef, and reads its label", () => {
    expect(resolveSpecBasis(spec)).toBe(basis);
    expect(planeRefFromSpec(spec)).toEqual({
      kind: "feature",
      feature_id: "d5",
    });
    expect(describePlane(spec)).toBe("Plane2");
  });
});

describe("snap", () => {
  it("rounds to the step and disables at step <= 0", () => {
    expect(snapValue(12.4, 1)).toBe(12);
    expect(snapValue(12.5, 1)).toBe(13);
    expect(snapValue(-3.6, 1)).toBe(-4);
    expect(snapValue(12.4, 0)).toBe(12.4);
  });

  it("never produces -0", () => {
    expect(Object.is(snapValue(-0.4, 1), 0)).toBe(true);
  });

  it("snaps both coordinates of a point", () => {
    expect(snapPoint({ x: 1.2, y: -2.7 }, 1)).toEqual({ x: 1, y: -3 });
  });
});

describe("resolveDatumPlaneOptions", () => {
  // Minimal FeatureResponse-shaped nodes — the resolver reads only id/name/feature.
  const node = (id: string, name: string, feature: unknown) =>
    ({ id, name, feature }) as never;

  it("offers offset datums with a rich readout spec, skipping non-datums", () => {
    const options = resolveDatumPlaneOptions([
      node("f1", "Sketch1", { type: "sketch", params: {} }),
      node("f2", "Datum +30", {
        type: "datum",
        params: { kind: "offset", base: "XY", offset_mm: 30, flip: false },
      }),
    ]);
    expect(options).toHaveLength(1);
    expect(options[0]?.id).toBe("f2");
    expect(options[0]?.spec).toMatchObject({
      kind: "offset",
      base: "XY",
      offsetMm: 30,
      flip: false,
    });
    // Its readout reuses the sketch plane vocabulary ("XY +30").
    expect(describePlane(options[0]!.spec)).toBe("XY +30");
  });

  it("resolves a chained offset_from datum to a placed 'datum' spec", () => {
    const options = resolveDatumPlaneOptions([
      node("base", "Datum +10", {
        type: "datum",
        params: { kind: "offset", base: "XY", offset_mm: 10, flip: false },
      }),
      node("child", "Datum +25", {
        type: "datum",
        params: {
          kind: "offset_from",
          base: { kind: "feature", feature_id: "base" },
          offset_mm: 15,
          flip: false,
        },
      }),
    ]);
    expect(options).toHaveLength(2);
    const child = options.find((o) => o.id === "child");
    expect(child?.spec.kind).toBe("datum");
    if (child?.spec.kind === "datum") {
      // Chained offset lands at 10 + 15 = 25 along the base normal. The spec's
      // basis is SCENE frame (the sketcher and the section author draw with
      // it), so the kernel's +Z arrives as scene +Y.
      expect([...child.spec.basis.origin]).toEqual([0, 25, 0]);
      expect([...child.spec.basis.normal]).toEqual([0, 1, 0]);
    }
  });

  it("omits an on_face datum (resolves server-side only)", () => {
    const options = resolveDatumPlaneOptions([
      node("face", "On face", {
        type: "datum",
        params: {
          kind: "on_face",
          signature: {},
          offset_mm: 0,
          flip: false,
        },
      }),
    ]);
    expect(options).toHaveLength(0);
  });
});
