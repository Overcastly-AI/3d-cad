/**
 * IS A COMMAND PROPOSING SOMETHING RIGHT NOW, AND IS A HAND ON IT? — two
 * counters, read from the render loop, written by the instruments themselves.
 *
 * ## What the camera needs and why the scene graph cannot tell it
 *
 * The preview re-fit (CRAFT-12) has to answer "is the open command drawing
 * something the modeler cannot see?". The *something* is easy — it is the
 * `command-layer` group's world box. The hard half is "is a command drawing at
 * all", because that subtree also holds the resting sketch ink, which is always
 * there and must never be read as a proposal; a camera that re-framed on ink it
 * has already framed would fight the modeler on page load.
 *
 * The tempting answer is to match the preview subtrees by NAME. Do not: the
 * nine mounts call theirs `extrude-ghost`, `fillet-preview`, `chamfer-preview`,
 * `revolve-sweep-preview`, `pattern-ghosts`, `shell-inner-offset` and
 * `datum-offset-sheet`, and a regex over that set is an audit that matches an
 * idiom rather than asking the question. It would miss the tenth verb in
 * silence, and the symptom of missing it is the ABSENCE of a re-fit — which
 * nothing fails on.
 *
 * So the registration is explicit and lives with the one component every
 * proposing command mounts: `ParametricGauge`. A verb with no instrument has
 * nothing to arm and nothing to propose; a verb that adds one gets the re-fit
 * for free, with no list to remember to update.
 *
 * ## Why counters, not booleans, and not state
 *
 * COUNTERS because two instruments can be mounted at once — the hole verb ships
 * depth and Ø together, the pattern layer a count and a spacing — so a flag
 * lets whichever one leaves first speak for both. Both counters floor at zero:
 * an unbalanced release (a cancel path that fires the no-button backstop AND
 * the real `pointerup`) must not drive the count negative, because a negative
 * count reads as "no drag" on the NEXT grab, which is the direction that lets
 * the camera move under a live hand.
 *
 * NOT React state because the only consumer is `CameraRig`'s `useFrame`, which
 * runs before React could have committed anything. A `useState` would answer
 * one commit late, and one commit late is exactly the window in which the
 * camera would move under a pointer that is still down. A store would work and
 * would cost a subscription plus a re-render per grab for a value that nothing
 * renders.
 */
let mounted = 0;
let held = 0;

/** An instrument has been drawn. Pair with exactly one {@link unmountInstrument}. */
export function mountInstrument(): void {
  mounted += 1;
}

/** An instrument has left with its command. */
export function unmountInstrument(): void {
  mounted = Math.max(0, mounted - 1);
}

/** Is any command currently proposing — i.e. is an instrument on screen? */
export function instrumentsMounted(): boolean {
  return mounted > 0;
}

/** An instrument has taken a pointer. Pair with exactly one {@link releaseHand}. */
export function beginHand(): void {
  held += 1;
}

/** An instrument has let go (or been cancelled, or unmounted mid-drag). */
export function releaseHand(): void {
  held = Math.max(0, held - 1);
}

/**
 * True while any instrument holds a pointer.
 *
 * The camera must not reframe while this is true. A gauge computes its value by
 * projecting the pointer ray onto the track in SCREEN space, so moving the
 * camera mid-drag does not merely disorient — it moves the ruler under the hand
 * and the number jumps by however far the camera went.
 */
export function handUnderway(): boolean {
  return held > 0;
}

/** Test seam: forget every mount and every grab. Never called by the product. */
export function resetInstruments(): void {
  mounted = 0;
  held = 0;
}
