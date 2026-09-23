/**
 * IS A COMMAND PROPOSING SOMETHING RIGHT NOW, IS A HAND ON IT, AND WHAT EXACTLY
 * IS IT PROPOSING? — two counters and one subject, read from the render loop.
 *
 * ## What the camera needs and why the scene graph cannot tell it
 *
 * The preview re-fit (CRAFT-12) has to answer "is the open command drawing
 * something the modeler cannot see?". The hard half is "is a command drawing at
 * all", because the `command-layer` subtree also holds the resting sketch ink,
 * which is always there and must never be read as a proposal; a camera that
 * re-framed on ink it has already framed would fight the modeler on page load.
 *
 * The tempting answer is to match the preview subtrees by NAME. Do not: the
 * nine mounts call theirs `extrude-ghost`, `fillet-preview`, `chamfer-preview`,
 * `revolve-sweep-preview`, `pattern-ghosts`, `shell-inner-offset` and
 * `datum-offset-sheet`, and a regex over that set is an audit that matches an
 * idiom rather than asking the question. It would miss the tenth verb in
 * silence, and the symptom of missing it is the ABSENCE of a re-fit — which
 * nothing fails on.
 *
 * ## The other half of the same question, and the defect it cost (2026-09-18)
 *
 * The paragraph above says the ink "must never be read as a proposal", and the
 * mount counter was written to enforce it. It cannot: the counter decides
 * WHETHER to read the command layer's box, never WHAT goes into it, so the
 * moment any command opened, the box was the whole layer — ink included.
 * Measured in the running app on a 20 mm cube with a second sketch SHOWN from
 * the feature tree (one click, the ordinary way to look at the profile driving
 * a feature), picking a single edge for a 2 mm fillet:
 *
 * | reading                     | before        | after the re-fit |
 * | --------------------------- | ------------- | ---------------- |
 * | re-fit subject              | `[-2.4, 0, -100] .. [160, 20, 2.4]` — the SKETCH |
 * | `fillet-gauge`'s own box    | `[-2.4, 0, -2] .. [2, 20, 2.4]`   |
 * | overrun                     | **11.78** against a 1.02 threshold |
 * | the body on screen          | **532 px wide** | **82 px** (-85 %) |
 * | camera travel               | **297 mm**    |
 *
 * The modeler framed the part, asked for a 2 mm fillet, and the camera flew
 * back to frame a sketch that had been sitting there all along. That is the
 * exact failure the note above names, arriving through the door it left open.
 *
 * ## So the subject is DECLARED, and the tag goes on the ANNOTATION
 *
 * The command layer holds two kinds of thing. A PROPOSAL is geometry that does
 * not exist yet — ghosts, offset sheets, and the instruments that state their
 * size. ANNOTATION is everything else: resting sketch ink, pick marks and their
 * bands, measure dimensions, highlight outlines. Annotation stands on geometry
 * the camera has ALREADY framed, or on ink the modeler asked to see; either way
 * it is not news, and re-framing on it moves the camera for something that was
 * already there.
 *
 * {@link ANNOTATION_LAYER} tags the annotation and {@link proposalBoxOf} skips
 * it. The asymmetry is the whole design and it is chosen for its FAILURE
 * DIRECTION, not for its tidiness:
 *
 *  · a new VERB joins the re-fit automatically, by drawing anything at all —
 *    there is no list to remember, which is what the name-regex above could
 *    never offer;
 *  · a new OVERLAY that forgets the tag fails LOUDLY — the camera lurches for
 *    something already on screen, which is the defect measured above and which
 *    anybody can see;
 *  · the inverse (an inclusion list) fails SILENTLY — the re-fit just stops
 *    happening for the verb nobody registered, and no gate in this repo can
 *    fail on a behaviour that is merely absent.
 *
 * The WHETHER half is registered the same way, for the same reason: the mount
 * counter is written by the one component every proposing command mounts,
 * `ParametricGauge`. A verb with no instrument has nothing to arm and nothing
 * to propose; a verb that adds one gets the re-fit for free, with no list to
 * remember to update.
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
import { Box3, type Object3D } from "three";

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

/** The `userData` key {@link ANNOTATION_LAYER} carries. Exported for probes. */
export const ANNOTATION_LAYER_KEY = "loftAnnotationLayer";

/**
 * Mark a command-layer subtree as ANNOTATION — drawn over geometry the camera
 * has already framed, and therefore never a re-fit subject. See the module
 * note for why the tag goes here rather than on the proposals.
 *
 * Spread onto the subtree's ROOT: `<group userData={ANNOTATION_LAYER}>`. A
 * component that renders several roots tags each of them. The tag works at
 * ANY depth — a whole overlay at the command layer's top level, or one
 * instrument's snap ladder inside a proposal's own group — because
 * {@link proposalBoxOf} leaves out every tagged subtree wherever it sits.
 */
export const ANNOTATION_LAYER: Readonly<Record<string, boolean>> = {
  [ANNOTATION_LAYER_KEY]: true,
};

/** Is this object an annotation root (see {@link ANNOTATION_LAYER})? */
export function isAnnotationLayer(object: Object3D): boolean {
  return (
    (object.userData as Record<string, unknown>)[ANNOTATION_LAYER_KEY] === true
  );
}

/**
 * The world box of what the open command is PROPOSING — the command layer's
 * subtree minus every annotation subtree, at ANY depth.
 *
 * `into` is supplied by the caller and reused: this runs on every rendered
 * frame of an open command and the viewport rule is that the render loop
 * allocates nothing. It is emptied first, so a caller may hand back the same
 * box every frame; the returned box IS `into`, and a caller that stashed the
 * reference would be holding a box that changes under it next frame.
 *
 * ## Why any depth, and not only the layer's direct children (2026-09-23)
 *
 * The first version skipped annotation ROOTS only, which covered the sketch
 * ink and the pick overlays (each a component root in the layer). It did not
 * cover the one annotation that lives INSIDE a proposal: an instrument's snap
 * ladder, drawn within the gauge's own group. Arming a ladder is a HOVER, and
 * on the pattern COUNT gauge the rungs run AHEAD of the apex (they mark the
 * copies you could add), so the hover grew the box and started a re-fit.
 * Measured on the running app at 1600x1000: 400 ms after the pointer came to
 * rest on the count rod, its seat had moved (682,657) -> (537,553) and its
 * apex (1073,766) -> (975,674) — the camera slid the instrument ~150 px out
 * from under the cursor reaching for it, so the press landed on bare canvas,
 * became an orbit, and `dragging COUNT past a rung` failed 6 runs in 8.
 *
 * The traversal mirrors `Box3.expandByObject`'s conservative branch (object-
 * level box for instanced geometry, else the geometry's box, in world space),
 * node by node, so a tagged subtree can be left out wherever it sits.
 */
export function proposalBoxOf(layer: Object3D, into: Box3): Box3 {
  into.makeEmpty();
  layer.updateWorldMatrix(false, false);
  for (const child of layer.children) expandSkippingAnnotation(into, child);
  return into;
}

/** Scratch for one node's box — module-level so the frame loop allocates nothing. */
const nodeBox = new Box3();

/** The geometry-bearing surface of an Object3D, as three duck-types it. */
interface WithGeometry {
  geometry?: {
    boundingBox: Box3 | null;
    computeBoundingBox: () => void;
  };
  boundingBox?: Box3 | null;
  computeBoundingBox?: () => void;
}

function expandSkippingAnnotation(into: Box3, object: Object3D): void {
  if (isAnnotationLayer(object)) return;
  object.updateWorldMatrix(false, false);
  const drawn = object as Object3D & WithGeometry;
  const geometry = drawn.geometry;
  if (geometry !== undefined) {
    let local: Box3 | null = null;
    if (drawn.boundingBox !== undefined) {
      // Object-level box (instanced / skinned / batched meshes).
      if (drawn.boundingBox === null) drawn.computeBoundingBox?.();
      local = drawn.boundingBox ?? null;
    } else {
      if (geometry.boundingBox === null) geometry.computeBoundingBox();
      local = geometry.boundingBox;
    }
    if (local !== null) {
      nodeBox.copy(local).applyMatrix4(object.matrixWorld);
      into.union(nodeBox);
    }
  }
  for (const child of object.children) expandSkippingAnnotation(into, child);
}
