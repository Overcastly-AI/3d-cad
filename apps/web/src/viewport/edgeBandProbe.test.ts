/**
 * The band's hit-test against REAL three.js objects: a `LineSegments2` band
 * and a surface mesh, raycast exactly as `EdgeBandLayer` does.
 *
 * The case is the review finding on EDGE-MARK-OVERLAP, reproduced from the
 * reviewer's scratch test: the front wall of a thin-walled box (outer face
 * z = 30, inner face z = 28, rim at y = 40) seen from just BELOW the rim. The
 * inner rim is behind the outer wall face there, but the body-scale occlusion
 * bias (2.69 mm on this box) is wider than the 2 mm wall, so the bias alone
 * let the hidden inner rim beat the visible outer one on screen distance.
 */
import {
  BufferGeometry,
  DoubleSide,
  Float32BufferAttribute,
  Mesh,
  MeshBasicMaterial,
  OrthographicCamera,
  PerspectiveCamera,
  Vector3,
} from "three";
import type { Camera } from "three";
import {
  LineMaterial,
  LineSegments2,
  LineSegmentsGeometry,
} from "three-stdlib";
import { describe, expect, it } from "vitest";

import { bandRadius, EDGE_BAND_WIDTH_PX, edgeOcclusionBias } from "./edgeBand";
import { resolveBandAt, type BandProbeTargets } from "./edgeBandProbe";

const W = 1280;
const H = 800;
const OUTER = 0;
const INNER = 1;

function scene(cameraY: number, pose?: Camera): BandProbeTargets {
  // Y up. Outer rim edge on the outer face (z = 30), inner rim on z = 28.
  const geometry = new LineSegmentsGeometry();
  geometry.setPositions([-40, 40, 30, 40, 40, 30, -38, 40, 28, 38, 40, 28]);
  const material = new LineMaterial({ linewidth: EDGE_BAND_WIDTH_PX });
  material.resolution.set(W, H);
  const band = new LineSegments2(geometry, material);
  band.updateMatrixWorld();

  // The drawn surface: the outer front face, the rim face, and the inner face.
  const skin = new BufferGeometry();
  skin.setAttribute(
    "position",
    new Float32BufferAttribute(
      [
        ...[-40, 0, 30, 40, 0, 30, 40, 40, 30],
        ...[-40, 0, 30, 40, 40, 30, -40, 40, 30],
        ...[-40, 40, 28, 40, 40, 28, 40, 40, 30],
        ...[-40, 40, 28, 40, 40, 30, -40, 40, 30],
        ...[-38, 0, 28, 38, 0, 28, 38, 40, 28],
        ...[-38, 0, 28, 38, 40, 28, -38, 40, 28],
      ],
      3,
    ),
  );
  const surface = new Mesh(skin, new MeshBasicMaterial({ side: DoubleSide }));
  surface.updateMatrixWorld();

  const corners: [number, number, number][] = [];
  for (const x of [-40, 40])
    for (const y of [0, 40]) for (const z of [-30, 30]) corners.push([x, y, z]);

  const camera = pose ?? new PerspectiveCamera(35, W / H, 1, 5000);
  if (pose === undefined) {
    camera.position.set(0, cameraY, 160);
    camera.lookAt(0, 30, 0);
  }
  camera.updateMatrixWorld();

  return {
    camera,
    width: W,
    height: H,
    band,
    surface,
    edgeOfSegment: Uint32Array.from([OUTER, INNER]),
    bias: edgeOcclusionBias(bandRadius(corners)),
  };
}

/** Screen row (CSS px) of a scene point. */
function rowOf(targets: BandProbeTargets, y: number, z: number): number {
  const q = new Vector3(0, y, z).project(targets.camera);
  return ((1 - q.y) / 2) * H;
}

/** Resolve at column x = centre, screen row `py`. */
function at(targets: BandProbeTargets, py: number): number | null {
  return resolveBandAt(0, 1 - (2 * py) / H, targets);
}

describe("resolveBandAt — a hidden edge never beats the visible one", () => {
  it("the fixture's bias really is wider than the wall (the premise)", () => {
    expect(scene(36).bias).toBeGreaterThan(2);
  });

  for (const cameraY of [30, 36, 38]) {
    it(`from below the rim (camera y = ${cameraY}), every row in the outer rim's corridor picks the outer rim`, () => {
      const t = scene(cameraY);
      const outer = rowOf(t, 40, 30);
      const wrong: string[] = [];
      let rows = 0;
      // Every cursor row inside the outer rim's corridor (a pixel short of
      // its 12 px edge), where the hidden inner rim is ALSO in the corridor
      // and nearer the cursor on half of them.
      for (
        let py = Math.ceil(outer - 11);
        py <= Math.floor(outer + 11);
        py += 1
      ) {
        rows += 1;
        const pick = at(t, py);
        if (pick !== OUTER) wrong.push(`row ${py}: ${pick}`);
      }
      expect(rows).toBeGreaterThan(20);
      expect(wrong).toEqual([]);
    });
  }

  it("from ABOVE, the cursor on either rim picks that rim (the fix still holds)", () => {
    const t = scene(90);
    expect(at(t, Math.round(rowOf(t, 40, 30)))).toBe(OUTER);
    expect(at(t, Math.round(rowOf(t, 40, 28)))).toBe(INNER);
  });
});

/**
 * EDGE-HIDDEN-LONE, the reviewer's pose: ORTHOGRAPHIC, 20 px/mm, looking at
 * the rim from `degrees` below it. The inner rim is 2 mm / cos(30) = 2.31 mm
 * behind the outer face along the view, inside the 2.69 mm slack, and over a
 * ~20 px strip of the face it is the ONLY edge in the corridor.
 */
function orthoBelow(degrees: number): OrthographicCamera {
  const camera = new OrthographicCamera(
    -W / 2 / 10,
    W / 2 / 10,
    H / 2 / 10,
    -H / 2 / 10,
    1,
    20000,
  );
  camera.zoom = 2; // 10 px per unit at zoom 1, so 20 px/mm
  camera.updateProjectionMatrix();
  const r = (-degrees * Math.PI) / 180;
  camera.position.set(0, 40 + 500 * Math.sin(r), 500 * Math.cos(r));
  camera.lookAt(0, 40, 0);
  return camera;
}

describe("resolveBandAt — a LONE hidden edge is refused (EDGE-HIDDEN-LONE)", () => {
  for (const degrees of [30, 60]) {
    it(`orthographic, ${degrees} degrees below the rim: no row over the outer face picks the hidden inner rim`, () => {
      const t = scene(0, orthoBelow(degrees));
      const outer = rowOf(t, 40, 30);
      const inner = rowOf(t, 40, 28);
      const hidden: number[] = [];
      let outerRows = 0;
      for (
        let py = Math.floor(Math.min(outer, inner)) - 14;
        py <= Math.ceil(Math.max(outer, inner)) + 14;
        py += 1
      ) {
        const pick = at(t, py);
        if (pick === INNER) hidden.push(py);
        if (pick === OUTER) outerRows += 1;
      }
      expect(hidden).toEqual([]);
      // Non-vacuity: the visible outer rim still answers its corridor.
      expect(outerRows).toBeGreaterThan(15);
    });
  }
});
