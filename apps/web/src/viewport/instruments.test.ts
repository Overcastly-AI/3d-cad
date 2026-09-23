import { Box3, BoxGeometry, Group, Mesh, Vector3 } from "three";
import { beforeEach, describe, expect, it } from "vitest";

import {
  ANNOTATION_LAYER,
  beginHand,
  handUnderway,
  instrumentsMounted,
  isAnnotationLayer,
  mountInstrument,
  proposalBoxOf,
  releaseHand,
  resetInstruments,
  unmountInstrument,
} from "./instruments";

/**
 * The two ways a boolean would have been wrong, for each counter. Neither
 * failure has a symptom of its own in the running app — the consequence is that
 * the preview re-fit silently stops happening, or happens under a live hand,
 * i.e. the ABSENCE or the MIS-TIMING of a behaviour rather than an error.
 * That is the hardest kind of defect to notice, which is why it is pinned here.
 */
describe("instruments", () => {
  beforeEach(() => resetInstruments());

  it("reports nothing mounted and no hand at rest", () => {
    expect(instrumentsMounted()).toBe(false);
    expect(handUnderway()).toBe(false);
  });

  it("stays mounted while a SECOND instrument is still on screen", () => {
    // The hole verb mounts depth and Ø together; the pattern layer mounts a
    // count and a spacing. A flag lets the first to leave speak for both.
    mountInstrument();
    mountInstrument();
    unmountInstrument();
    expect(instrumentsMounted()).toBe(true);
    unmountInstrument();
    expect(instrumentsMounted()).toBe(false);
  });

  it("stays held while a SECOND instrument is still under the pointer", () => {
    beginHand();
    beginHand();
    releaseHand();
    expect(handUnderway()).toBe(true);
    releaseHand();
    expect(handUnderway()).toBe(false);
  });

  it("cannot be driven negative by an unbalanced release", () => {
    // A cancel path can fire the no-button backstop AND the real pointerup. At
    // -1 the NEXT grab would read as no grab at all, and the camera would be
    // free to move under a live hand — the one thing the flag exists to stop.
    releaseHand();
    releaseHand();
    unmountInstrument();
    expect(handUnderway()).toBe(false);
    expect(instrumentsMounted()).toBe(false);
    beginHand();
    mountInstrument();
    expect(handUnderway()).toBe(true);
    expect(instrumentsMounted()).toBe(true);
  });

  it("keeps the two counters independent", () => {
    // An instrument on screen with nobody touching it is the resting state of
    // every open command, and it must not read as a drag.
    mountInstrument();
    expect(instrumentsMounted()).toBe(true);
    expect(handUnderway()).toBe(false);
  });
});

/** A unit cube of world geometry seated at `centre`, under a named root. */
function block(name: string, centre: Vector3, size: number): Group {
  const root = new Group();
  root.name = name;
  const mesh = new Mesh(new BoxGeometry(size, size, size));
  mesh.position.copy(centre);
  root.add(mesh);
  root.updateMatrixWorld(true);
  return root;
}

/**
 * THE RE-FIT SUBJECT IS THE PROPOSAL, NOT THE WHOLE COMMAND LAYER.
 *
 * The numbers below are the shape of the defect this exists for, scaled down
 * from the measurement in `instruments.ts`: a 2 mm gauge beside a 20 mm body,
 * and a shown sketch 100 mm away. Before the annotation tag the subject was the
 * union of all three, the overrun read 11.78 against a 1.02 threshold, and the
 * camera travelled 297 mm to frame ink that had been on screen the whole time.
 *
 * Note the assertions are about the BOX and not about a boolean: "did it skip
 * the ink" is only interesting as "what did the camera end up being asked to
 * frame", and a predicate that returned the right answer for the wrong subtree
 * would satisfy any test that only counted children.
 */
describe("proposalBoxOf", () => {
  it("leaves annotation out of the subject entirely", () => {
    const layer = new Group();
    const ink = block("sketch-ink", new Vector3(100, 0, 0), 20);
    ink.userData = { ...ANNOTATION_LAYER };
    layer.add(ink);
    layer.add(block("fillet-gauge", new Vector3(0, 0, 0), 2));
    layer.updateMatrixWorld(true);

    const box = proposalBoxOf(layer, new Box3());
    expect(box.min.toArray()).toEqual([-1, -1, -1]);
    expect(box.max.toArray()).toEqual([1, 1, 1]);
    // Said as the thing that actually went wrong: the ink is 100 mm away, so a
    // subject that reached it would be fifty times too wide.
    expect(box.getSize(new Vector3()).x).toBeLessThan(10);
  });

  it("counts a proposal subtree nobody registered anywhere", () => {
    // The whole point of tagging the ANNOTATION: a verb added tomorrow draws
    // into this layer under a name this file has never heard of, and is framed
    // for free. An inclusion list would silently skip it, and a re-fit that
    // does not happen fails no test.
    const layer = new Group();
    layer.add(block("verb-nobody-has-written-yet", new Vector3(0, 0, 30), 4));
    layer.updateMatrixWorld(true);

    const box = proposalBoxOf(layer, new Box3());
    expect(box.isEmpty()).toBe(false);
    expect(box.max.z).toBeCloseTo(32, 6);
  });

  it("is empty when the layer holds nothing but annotation", () => {
    // "No proposal" and "a proposal at the origin" must stay distinguishable:
    // `Viewport.readProposal` returns null on an empty box, and the rig reads
    // null as "no command is drawing" — the state that resets the per-proposal
    // navigation grace.
    const layer = new Group();
    const ink = block("sketch-ink", new Vector3(100, 0, 0), 20);
    ink.userData = { ...ANNOTATION_LAYER };
    layer.add(ink);
    layer.updateMatrixWorld(true);

    expect(proposalBoxOf(layer, new Box3()).isEmpty()).toBe(true);
  });

  it("empties the box it is handed, so a stale subject cannot survive a frame", () => {
    // The box is REUSED across frames (the render loop allocates nothing). A
    // version that unioned into whatever it was given would grow monotonically
    // and the camera would keep standing back from geometry that is gone.
    const reused = new Box3(
      new Vector3(-500, -500, -500),
      new Vector3(9, 9, 9),
    );
    const layer = new Group();
    layer.add(block("fillet-gauge", new Vector3(0, 0, 0), 2));
    layer.updateMatrixWorld(true);

    const box = proposalBoxOf(layer, reused);
    expect(box).toBe(reused);
    expect(box.min.toArray()).toEqual([-1, -1, -1]);
  });

  it("treats only the exact tag as annotation", () => {
    // A near-miss key must NOT silence a subtree: the failure direction that
    // matters is a proposal quietly dropped, and a loose match (any userData,
    // a truthy value, a similar name) is how that would happen.
    const near = new Group();
    near.userData = { loftAnnotation: true, annotation: true };
    expect(isAnnotationLayer(near)).toBe(false);
    const truthy = new Group();
    truthy.userData = { loftAnnotationLayer: "yes" };
    expect(isAnnotationLayer(truthy)).toBe(false);
    const tagged = new Group();
    tagged.userData = { ...ANNOTATION_LAYER };
    expect(isAnnotationLayer(tagged)).toBe(true);
    expect(isAnnotationLayer(new Group())).toBe(false);
  });
});
