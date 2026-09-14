/**
 * IS THE TOOL ASKING THE MODELLER TO PICK SOMETHING IN THE SCENE?
 *
 * One boolean, derived by counting the pick affordances actually mounted, so
 * nothing has to be told about a new pick mode for the answer to be right.
 *
 * ## The defect it exists for (cross-item QA, 2026-09-13, P2)
 *
 * CRAFT-6 made the reference cube persist through plane pick and sketch, on the
 * good argument that orientation matters MORE while you are working on a plane
 * in space than while you are turning a finished body. The cost nobody measured
 * is that the cube's 108x108 seat sits in the HUD layer, above every pick mark
 * (drei `Html`, `zIndexRange` at most [30, 10]; `z-hud` is 40) — so with a body
 * panned into that corner at 1280x800, **5 of 6 `plane-pick-face-N` marks
 * resolved to `view-cube`**, a 7x7 grid of the seat resolved to the cube at 49
 * of 49 points, and the SURFACE pick under it was gone too. An offered control
 * a pointer cannot reach is the defect class this repo has now paid for four
 * times.
 *
 * ## Why yielding, and not re-stacking
 *
 * Raising the marks above `z-hud` fixes the cube and breaks the ViewBar, the
 * visibility stamp and the proposal chip instead — the same defect with a
 * different victim. The asymmetry that does resolve it is the one CRAFT-6's own
 * comment states: **the cube is an orientation READOUT before it is a
 * control.** A readout costs nothing while it is only being read, so while a
 * pick is armed the cube keeps its pixels and gives up its pointer, and the
 * corner of the model underneath becomes pickable again. The moment the pick
 * ends it is a control again. Orbit, pan and zoom are untouched throughout —
 * they are canvas gestures, and the cube was never in their way.
 *
 * ## Why a count, and where it is written
 *
 * It is written in `PickMark`, the ONE primitive every armed pick affordance
 * mounts through (six overlays today: face, edge, shell face, hole point,
 * measure, instance mate). So this cannot drift out of step with the modes
 * that exist — the way a hand-maintained list of "picking" booleans plumbed
 * from `PartPage` certainly would — and a seventh overlay gets the behaviour by
 * using the primitive, which is this repo's standing rule about fixing the
 * primitive rather than the instance.
 *
 * A count rather than a flag because several marks are mounted at once and they
 * unmount independently; the last one out turns it off.
 *
 * NB the sketcher's own snap marks are NOT pick marks (`sketch/pickMark.ts`, a
 * different module and a different host), so DRAWING never yields the cube —
 * which is the state CRAFT-6 cared most about and the one its e2e asserts.
 */
import { useEffect } from "react";
import { create } from "zustand";

interface ArmedPickState {
  /** How many pick affordances are mounted right now. */
  marks: number;
  enter: () => void;
  leave: () => void;
}

const useArmedPickStore = create<ArmedPickState>((set) => ({
  marks: 0,
  enter: () => set((state) => ({ marks: state.marks + 1 })),
  // Floored at 0 so an unbalanced unmount cannot leave the count negative and
  // latch the cube ON while a pick is armed — failing toward the cube being
  // interactive is the direction that reproduces the defect.
  leave: () => set((state) => ({ marks: Math.max(0, state.marks - 1) })),
}));

/**
 * Count this component as one armed pick affordance for as long as it is
 * mounted. Called by `PickMark` and nowhere else.
 */
export function useRegisterArmedPick(): void {
  const enter = useArmedPickStore((state) => state.enter);
  const leave = useArmedPickStore((state) => state.leave);
  useEffect(() => {
    enter();
    return leave;
  }, [enter, leave]);
}

/** Is a pick armed — i.e. must ambient chrome yield its pointer to the scene? */
export function usePickArmed(): boolean {
  return useArmedPickStore((state) => state.marks > 0);
}

/** Test seam: the raw count, and a reset between cases. */
export const armedPickStore = useArmedPickStore;
