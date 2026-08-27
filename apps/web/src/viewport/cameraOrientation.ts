/**
 * The scene camera's ORIENTATION, published for chrome that lives outside the
 * scene's own canvas — today just the reference cube ({@link ViewCube}).
 *
 * WHY A CHANNEL AND NOT A PROP: the cube draws into its OWN canvas (see
 * `ViewCube.tsx` for the measured reason), so it cannot reach the scene camera
 * through r3f context. It needs one number sixty times a second and nothing
 * else, which is a broadcast, not state — a zustand store would re-render React
 * on every orbit frame for a value no component renders from.
 *
 * Allocation-free by construction: one `Quaternion` for the whole app, copied
 * into and read out of by reference. The publisher runs inside a `useFrame`, so
 * anything that allocates here allocates per frame (mandate: keep the render
 * loop allocation-free), and subscribers are notified only when the value
 * actually MOVES — a still camera wakes nobody, which is what keeps the cube's
 * `frameloop="demand"` canvas genuinely idle.
 */
import { Quaternion } from "three";

const current = new Quaternion();
const listeners = new Set<() => void>();

/**
 * Publish the scene camera's orientation. Cheap enough for a per-frame call:
 * it compares before it copies and notifies nobody when the camera is at rest.
 */
export function publishViewQuaternion(next: Quaternion): void {
  if (
    current.x === next.x &&
    current.y === next.y &&
    current.z === next.z &&
    current.w === next.w
  ) {
    return;
  }
  current.copy(next);
  for (const listener of listeners) listener();
}

/**
 * The live orientation. Returned BY REFERENCE — read it inside a frame and
 * copy what you need; never retain it expecting a snapshot.
 */
export function readViewQuaternion(): Quaternion {
  return current;
}

/** Subscribe to orientation changes. Returns the unsubscribe. */
export function subscribeViewQuaternion(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
