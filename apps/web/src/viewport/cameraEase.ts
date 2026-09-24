/**
 * HOW FAR ONE FRAME OF A CAMERA EASE MOVES — the exponential step both camera
 * rigs (the part rig in `Viewport.tsx`, the sketch rig in `SketchScene.tsx`)
 * take toward their goal.
 *
 * ## The defect (PERF-REAL-1)
 *
 * Both rigs stepped by `1 - exp(-min(delta, 0.1) * 10)`. The clamp is there for
 * one frame: the FIRST frame of an ease under `frameloop="demand"`, whose
 * `delta` is however long the scene sat idle, so an unclamped step would snap
 * the camera to its goal. But the clamp applied to every frame, so below 10 fps
 * the ease stopped being frame-rate independent and became a fixed ~11 frames
 * — and on the gauntlet's 399 478-triangle gearbox under software GL, where a
 * frame costs ~2.4 s, that was ~26 s of the camera crawling into the
 * plane-pick vantage before the face pick could even show its prompt (React's
 * commits queue behind those frames). Measured frame by frame, not inferred.
 *
 * ## The rule now
 *
 * The first frame of an ease keeps the old clamp, so at any frame rate that
 * frame moves exactly as it always did. Every CONTINUING frame — one whose
 * predecessor also stepped, so its `delta` really is a frame duration — is
 * clamped far higher, which keeps the ease time-based down to 2 fps. At 60 fps
 * no clamp is reached at all, so nothing a modeller sees at an interactive
 * frame rate changes.
 */

/** The ease's rate, per second: the step is `1 - exp(-dt * rate)`. */
export const CAMERA_EASE_RATE = 10;

/** The longest `dt` the FIRST frame of an ease may take, s — see above. */
export const CAMERA_EASE_FIRST_STEP_S = 0.1;

/** The longest `dt` a CONTINUING frame of an ease may take, s. */
export const CAMERA_EASE_MAX_STEP_S = 0.5;

/**
 * The fraction of the remaining distance to cover this frame, given r3f's
 * `delta` and whether the previous rendered frame also took an ease step.
 */
export function cameraEaseStep(delta: number, continuing: boolean): number {
  const cap = continuing ? CAMERA_EASE_MAX_STEP_S : CAMERA_EASE_FIRST_STEP_S;
  const dt = Math.min(Math.max(delta, 0), cap);
  return 1 - Math.exp(-dt * CAMERA_EASE_RATE);
}
