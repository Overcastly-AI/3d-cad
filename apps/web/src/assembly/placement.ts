/**
 * Placement math — the ONE mapping from a solved assembly `Placement` (OCCT
 * world mm, Z-up, quaternion orientation) to an r3f group transform in scene
 * space (Y-up mm). The per-part GLB the geometry service returns is the part's
 * body in its LOCAL frame, already rotated Z-up→Y-up and scaled to mm by
 * `glbGeometry` (`occtToScene`, the `(x,y,z)→(x,z,-y)` node rotation). The
 * solver's transform is applied at RENDER time over that shared mesh (design
 * §4 — never baked in), so the same mesh draws N times at N solved poses.
 *
 * The frame algebra: a scene vertex is `S·local`, where `S` is the Z-up→Y-up
 * rotation (`occtToScene`, a proper rotation about +X by −90°). A solved world
 * vertex is `S·(R·local + t)` = `(S·R·S⁻¹)·(S·local) + S·t`. So the transform
 * to hang on the already-scene-space geometry is a rotation `S·R·S⁻¹`
 * (quaternion conjugation `s ⊗ q ⊗ s⁻¹`) and a translation `S·t` (= exactly
 * `occtToScene(t)`). Pure — three.js `Quaternion`/`Vector3` run headless, so
 * this is unit-tested in node without a WebGL context.
 */
import { Quaternion, Vector3 } from "three";
import type { components } from "@loft/ts-client/gateway";

export type Placement = components["schemas"]["Placement"];
export type Vec3 = components["schemas"]["Vec3"];

/** r3f group transform derived from a solved placement (scene mm, Y-up). */
export interface SceneTransform {
  /** `[x, y, z]` for `<group position={…}>`. */
  position: [number, number, number];
  /** `[x, y, z, w]` for `<group quaternion={…}>`. */
  quaternion: [number, number, number, number];
}

/**
 * `S` — the Z-up→Y-up frame rotation `occtToScene` applies: `(x,y,z)→(x,z,-y)`,
 * a proper rotation about +X by −90°. Shared as the conjugation basis so the
 * viewport frame and the kernel's world frame agree exactly (one frame source,
 * CLAUDE.md DRY rule — the sketch/measure overlays use the same `occtToScene`).
 */
const S_QUAT = new Quaternion().setFromAxisAngle(
  new Vector3(1, 0, 0),
  -Math.PI / 2,
);
const S_QUAT_INV = S_QUAT.clone().invert();

/** `occtToScene` for a `Vec3`: OCCT world mm (Z-up) → scene mm (Y-up). */
export function occtPointToScene(v: Vec3): [number, number, number] {
  // Mirrors sketch/plane.occtToSceneTuple: (x, y, z) → (x, z, -y); -0 → 0.
  return [v.x, v.z, v.y === 0 ? 0 : -v.y];
}

/**
 * A solved `Placement` → the scene-space `{position, quaternion}` to hang on
 * the shared, already-scene-space part geometry. The translation is
 * `occtToScene(position)`; the rotation is the world quaternion conjugated by
 * the frame rotation `S`, so orientation lands correctly in Y-up.
 */
export function placementToScene(placement: Placement): SceneTransform {
  const q = placement.orientation;
  // s ⊗ q ⊗ s⁻¹ (Hamilton products): rotate the OCCT-frame orientation into
  // the scene frame. A partial/zero quaternion normalises to identity.
  const world = new Quaternion(q.x, q.y, q.z, q.w);
  if (world.lengthSq() === 0) world.set(0, 0, 0, 1);
  world.normalize();
  const scene = S_QUAT.clone().multiply(world).multiply(S_QUAT_INV).normalize();
  return {
    position: occtPointToScene(placement.position),
    quaternion: [scene.x, scene.y, scene.z, scene.w],
  };
}

/** Squared scene-space distance between two placements' origins (a move probe). */
export function placementMovedSq(a: Placement, b: Placement): number {
  const pa = occtPointToScene(a.position);
  const pb = occtPointToScene(b.position);
  const dx = pa[0] - pb[0];
  const dy = pa[1] - pb[1];
  const dz = pa[2] - pb[2];
  return dx * dx + dy * dy + dz * dz;
}
