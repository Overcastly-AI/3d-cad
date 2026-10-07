/**
 * WHICH POSE THE VIEWPORT HAS ACTUALLY DRAWN (MATE-OBS-3).
 *
 * The assembly page publishes one solve through THREE React roots, and they
 * commit in sequence, not together:
 *
 *   1. the page's react-dom root — the STATUS cell, FREE DOF, and the
 *      `data-eval-stale` stamp;
 *   2. react-three-fiber's reconciler, scheduled from the page's commit — the
 *      instance meshes at their new transforms;
 *   3. one react-dom root per drei `<Html>`, scheduled from (2)'s commit — the
 *      balloons, which carry each instance's `data-solved-*` pose.
 *
 * So when a solve lands, (1) says "Under constrained, 3 DOF, current" a
 * scheduler task or two before (2) and (3) move the part. On an idle machine
 * that is a few ms; on a loaded CI runner it was a whole 25 ms sample (t+800,
 * shard 1/6 of 0fbd6cf), and with the solve held back it is ~85 ms every
 * time: a settled verdict over the PRE-mate pose, which reads exactly like a
 * mate that did nothing.
 *
 * The fix is an acknowledgement, not a delay. Each balloon reports, from a
 * layout effect inside ITS OWN root (so after its DOM write, and therefore
 * after the R3F commit that scheduled it), the pose it has just drawn. The page
 * treats the solve as still being published while any drawn balloon shows a
 * pose other than the one the page is rendering, and `deriveAssemblySolve`
 * spends "Solving…" for that beat. The verdict can then only reach the screen
 * in the same commit as, or after, the pose it describes.
 *
 * A balloon that is not mounted (hidden instance, no WebGL) reports nothing and
 * blocks nothing: there is no pose on screen for a verdict to contradict.
 */
import type { SceneTransform } from "./placement";

/** A pose's identity — exact, because both sides run `placementToScene`. */
export function poseKey(transform: SceneTransform): string {
  return `${transform.position.join(",")}|${transform.quaternion.join(",")}`;
}

/** The pose each mounted balloon last committed, by instance id. */
export type DrawnPoses = ReadonlyMap<string, string>;

export const NO_DRAWN_POSES: DrawnPoses = new Map();

/**
 * Record one balloon's commit (`key`) or unmount (`null`). Returns the SAME
 * map when nothing changed, so a React state setter bails out of re-rendering.
 */
export function recordDrawnPose(
  drawn: DrawnPoses,
  instanceId: string,
  key: string | null,
): DrawnPoses {
  if (key === null) {
    if (!drawn.has(instanceId)) return drawn;
    const next = new Map(drawn);
    next.delete(instanceId);
    return next;
  }
  if (drawn.get(instanceId) === key) return drawn;
  return new Map(drawn).set(instanceId, key);
}

/**
 * Is any balloon on screen still showing a pose other than the one the page is
 * rendering? Instances with no mounted balloon are not on screen and so are
 * never pending.
 */
export function posesPending(
  instances: readonly { id: string; transform: SceneTransform }[],
  drawn: DrawnPoses,
): boolean {
  return instances.some((instance) => {
    const shown = drawn.get(instance.id);
    return shown !== undefined && shown !== poseKey(instance.transform);
  });
}
