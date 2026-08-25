/**
 * Whether a pick has anything to pick — the one predicate every armed pick mode
 * is gated on, in one place (PICK-2).
 *
 * WHY THIS EXISTS. Every pick overlay in the part workspace is fed by an
 * `["overlay", …]` query that carries the identical `meshGlbId !== null` guard:
 * face pick, datum face pick, hole, edge, shell and measure. When the tip
 * feature produces no body — the build stopped at a failing feature, or the only
 * body-affecting feature is suppressed — `mesh_glb_id` comes back honestly null
 * (`features/evaluate.py`: "No body … honestly null"), so all six queries go
 * `enabled: false`, `FacePickOverlay` receives `faces === null` and renders
 * NOTHING. There is no `PickSurface` and no `PickNode` in the scene: it is not a
 * raycast that misses, it is an empty scene.
 *
 * The dead end that produced the founder's report (five clicks, two camera
 * angles, nothing happens) is a pick mode ARMED over that empty scene. Arming
 * is what this module refuses. The rule, stated once so no caller has to
 * re-derive it:
 *
 *   **A pick is never armed with nothing to pick, and a pick that has nothing
 *   to pick says so where the user is looking.**
 *
 * Deliberately NOT in scope: giving the user a fallback body to pick against
 * (the last successfully-built body's mesh). That is a bigger question — which
 * mesh, and whose coordinate frame — and conflating it with closing the dead
 * end would make both harder to review.
 */

/**
 * The build produced no body, so no overlay can populate. Says what happened and
 * what to do about it: the feature tree is where the blocking error lives, and
 * it is the only place the user can clear it.
 */
export const NO_PICK_TARGETS =
  "Nothing to pick — the part has no built body. Clear the error in the feature tree, then pick again.";

/** What a pick flow knows about its targets when it is asked to arm. */
export interface PickTargetState {
  /**
   * The evaluation published a body (`mesh_glb_id !== null`) — the SAME
   * condition the six overlay queries are enabled on, so the guard and the
   * queries cannot drift apart.
   */
  readonly hasPickTargets: boolean;
  /**
   * The tree contains a body-affecting feature at all. False on a sketch-only
   * part, where the honest instruction is "add one", not "clear an error".
   */
  readonly hasBodyFeature: boolean;
}

/**
 * Why this pick cannot be armed right now, or null when it can.
 *
 * `noBodyFeature` is the flow's own sentence for a part that has never had a
 * body ("Add a feature that creates a body before drilling a hole."), which is
 * a different fact from a body-affecting feature that failed to build — and
 * telling a user to add a feature they already added is how a UI loses trust.
 */
export function pickRefusal(
  state: PickTargetState,
  noBodyFeature: string,
): string | null {
  if (state.hasPickTargets) return null;
  return state.hasBodyFeature ? NO_PICK_TARGETS : noBodyFeature;
}
