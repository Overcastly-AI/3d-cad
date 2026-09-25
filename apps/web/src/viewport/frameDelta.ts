/**
 * WHEN r3f's `delta` IS A FRAME TIME — the rule every per-frame budget in
 * this viewport shares (the camera ease in `cameraEase.ts`, the face-mark
 * seat slice in `useSurfaceMarkBurial.ts`).
 *
 * The canvas is `frameloop="demand"`: nothing renders until something
 * invalidates. So `delta` on the FIRST frame after the scene sat still is the
 * whole idle span — seconds, or minutes — and it says nothing about how long a
 * frame takes. Only a frame whose predecessor was ALSO asked for by the same
 * piece of work (it called `invalidate()` from its own frame callback, so the
 * next rendered frame follows immediately) carries a `delta` that measures a
 * frame. Each caller tracks that with a `continuing` flag: set when its frame
 * callback did work and requested the next frame, cleared when it went idle.
 *
 * PERF-REAL-1's review found the seat slice trusting the first-frame `delta`:
 * a 60 fps orbit that began after a second of idle spent its first frame on a
 * 250 ms slice, all of it thrown away when the next orbit frame re-armed the
 * pass. Having one rule in one place is what keeps the two budgets from
 * disagreeing about it again.
 */

/**
 * `delta` as a measured frame duration in seconds, or `null` when it is not
 * one: the first frame of a run of work (`continuing` false), or a value that
 * is not a finite, non-negative duration.
 */
export function measuredFrameSeconds(
  delta: number,
  continuing: boolean,
): number | null {
  if (!continuing) return null;
  if (!Number.isFinite(delta) || delta < 0) return null;
  return delta;
}
