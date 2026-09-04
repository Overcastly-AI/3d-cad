import { BufferGeometry } from "three";
import { beforeEach, describe, expect, it } from "vitest";

import {
  bodyKey,
  bodyMode,
  entityIsDrawn,
  hiddenBodyCount,
  isolatedBodyLabel,
  ORIGIN_AXES,
  ORIGIN_PLANES,
  originAxisKey,
  originPlaneKey,
  sketchIsDrawn,
  sketchKey,
  sketchRowMode,
  usePartViewStore,
  type PartBodyView,
} from "./partView";

const BODIES: PartBodyView[] = [
  { key: bodyKey("f1"), label: "Body 1", lumps: 1 },
  { key: bodyKey("f2"), label: "Body 2", lumps: 1 },
];

function reset(): void {
  usePartViewStore.setState({ subjectId: null });
  usePartViewStore.getState().setSubject("part-a");
  usePartViewStore.getState().setBodies(BODIES);
}

describe("origin defaults", () => {
  beforeEach(reset);

  it("starts every origin plane and axis HIDDEN, as Fusion's do", () => {
    const { view } = usePartViewStore.getState();
    for (const plane of ORIGIN_PLANES) {
      expect(entityIsDrawn(view, originPlaneKey(plane))).toBe(false);
    }
    for (const axis of ORIGIN_AXES) {
      expect(entityIsDrawn(view, originAxisKey(axis))).toBe(false);
    }
  });

  it("the eye turns one on without touching its neighbours", () => {
    usePartViewStore.getState().toggle(originPlaneKey("XY"));
    const { view } = usePartViewStore.getState();
    expect(entityIsDrawn(view, originPlaneKey("XY"))).toBe(true);
    expect(entityIsDrawn(view, originPlaneKey("XZ"))).toBe(false);
    expect(entityIsDrawn(view, originAxisKey("X"))).toBe(false);
  });

  it("resets when another part becomes the subject", () => {
    usePartViewStore.getState().toggle(originPlaneKey("XY"));
    usePartViewStore.getState().setSubject("part-b");
    const state = usePartViewStore.getState();
    expect(entityIsDrawn(state.view, originPlaneKey("XY"))).toBe(false);
    expect(state.bodies).toEqual([]);
  });
});

describe("sketch stops", () => {
  beforeEach(reset);

  it("defaults to SHOWN with no body and RECEDED once a solid exists", () => {
    const { view } = usePartViewStore.getState();
    expect(sketchIsDrawn(view, "s1", false)).toBe(true);
    expect(sketchIsDrawn(view, "s1", true)).toBe(false);
    expect(sketchRowMode(view, "s1", true)).toBe("hidden");
  });

  it("an explicit stop overrides the default in EITHER direction", () => {
    // The founder's case: bring the profile back with the body on screen.
    usePartViewStore.getState().setBodyPresent(true);
    usePartViewStore.getState().toggle(sketchKey("s1"));
    let view = usePartViewStore.getState().view;
    expect(sketchIsDrawn(view, "s1", true)).toBe(true);
    // And the other way: silence a sketch on a body-less part.
    usePartViewStore.getState().setBodyPresent(false);
    usePartViewStore.getState().setMode(sketchKey("s2"), "hidden");
    view = usePartViewStore.getState().view;
    expect(sketchIsDrawn(view, "s2", false)).toBe(false);
  });

  it("toggling from the DERIVED hidden default shows it (not the reverse)", () => {
    // The row's eye reads the derived stop, so one click must agree with what
    // the row was showing — an off eye that switches further off is the class
    // of bug that makes a toggle feel broken.
    usePartViewStore.getState().setBodyPresent(true);
    usePartViewStore.getState().toggle(sketchKey("s3"));
    const { view } = usePartViewStore.getState();
    expect(sketchRowMode(view, "s3", true)).toBe("solid");
  });
});

describe("body stops, isolate and the way back", () => {
  beforeEach(reset);

  it("writes the three stops and keeps ghost under a hide", () => {
    const key = bodyKey("f1");
    usePartViewStore.getState().setMode(key, "ghost");
    expect(bodyMode(usePartViewStore.getState().view, key, false)).toBe(
      "ghost",
    );
    usePartViewStore.getState().setMode(key, "hidden");
    expect(bodyMode(usePartViewStore.getState().view, key, false)).toBe(
      "hidden",
    );
    // Un-hiding restores the ghost you had — the small honesty that makes the
    // control feel reliable.
    usePartViewStore.getState().toggle(key);
    expect(bodyMode(usePartViewStore.getState().view, key, false)).toBe(
      "ghost",
    );
  });

  it("isolate keeps one body and hides the rest", () => {
    usePartViewStore.getState().isolate(bodyKey("f2"));
    const { view } = usePartViewStore.getState();
    expect(bodyMode(view, bodyKey("f1"), false)).toBe("hidden");
    expect(bodyMode(view, bodyKey("f2"), false)).toBe("solid");
    expect(hiddenBodyCount(view, BODIES)).toBe(1);
    expect(isolatedBodyLabel(view, BODIES)).toBe("Body 2");
  });

  it("show all is the way back, and the stamp stops claiming", () => {
    usePartViewStore.getState().isolate(bodyKey("f2"));
    usePartViewStore.getState().showAll();
    const { view } = usePartViewStore.getState();
    expect(hiddenBodyCount(view, BODIES)).toBe(0);
    expect(isolatedBodyLabel(view, BODIES)).toBeNull();
  });

  it("hiding by HAND down to one body earns the same isolated stamp", () => {
    usePartViewStore.getState().setMode(bodyKey("f1"), "hidden");
    const { view } = usePartViewStore.getState();
    expect(isolatedBodyLabel(view, BODIES)).toBe("Body 2");
  });

  it("never claims isolation on a single-body part", () => {
    const one: PartBodyView[] = [BODIES[0] as PartBodyView];
    usePartViewStore.getState().setBodies(one);
    usePartViewStore.getState().setMode(bodyKey("f1"), "hidden");
    const { view } = usePartViewStore.getState();
    expect(isolatedBodyLabel(view, one)).toBeNull();
    expect(hiddenBodyCount(view, one)).toBe(1);
  });

  it("counts BODIES only — a hidden sketch is not a missing part", () => {
    usePartViewStore.getState().setMode(sketchKey("s1"), "hidden");
    usePartViewStore.getState().toggle(originPlaneKey("XY"));
    const { view } = usePartViewStore.getState();
    expect(hiddenBodyCount(view, BODIES)).toBe(0);
  });
});

/**
 * The pick slice (SEL-1 / A2) — the mesh publishes what an armed overlay is
 * allowed to raycast, and what that raycast is allowed to answer. Every other
 * slice in this store already had coverage; this one shipped without any, which
 * is how the hidden-face half came to be missing (code review, 2026-08-06).
 */
describe("the raycast target the mesh publishes", () => {
  beforeEach(reset);

  it("starts empty — no mesh means no pick target, never 'not loaded yet'", () => {
    const state = usePartViewStore.getState();
    expect(state.pickGeometry).toBeNull();
    expect(state.pickHiddenFaces.size).toBe(0);
  });

  it("carries the hidden ordinals so an overlay can refuse them", () => {
    usePartViewStore.getState().setPickHiddenFaces(new Set([2, 5]));
    expect([...usePartViewStore.getState().pickHiddenFaces].sort()).toEqual([
      2, 5,
    ]);
  });

  it("re-publishing the SAME ordinals does not churn the store", () => {
    usePartViewStore.getState().setPickHiddenFaces(new Set([2, 5]));
    const first = usePartViewStore.getState().pickHiddenFaces;
    // `bodyFaceState` is a fresh Set on every re-derive, so an identity-only
    // guard would re-render the whole scene on any unrelated store write.
    usePartViewStore.getState().setPickHiddenFaces(new Set([5, 2]));
    expect(usePartViewStore.getState().pickHiddenFaces).toBe(first);
  });

  it("RELEASES both halves together — the set cannot outlive the mesh", () => {
    const geometry = new BufferGeometry();
    usePartViewStore.getState().setPickGeometry(geometry);
    usePartViewStore.getState().setPickHiddenFaces(new Set([4]));

    // What `ModelMesh` calls as it unmounts (a rollback below the first solid
    // with a body switched off). An ordinal indexes a mesh's face partition, so
    // keeping the set without the mesh describes a state that cannot exist.
    usePartViewStore.getState().releasePickSubject();

    const state = usePartViewStore.getState();
    expect(state.pickGeometry).toBeNull();
    expect(state.pickHiddenFaces.size).toBe(0);
    geometry.dispose();
  });

  it("releasing an already-released subject does not churn the store", () => {
    const before = usePartViewStore.getState().pickHiddenFaces;
    usePartViewStore.getState().releasePickSubject();
    expect(usePartViewStore.getState().pickHiddenFaces).toBe(before);
  });

  it("RESETS on a new subject — a pick target can never follow you", () => {
    const geometry = new BufferGeometry();
    usePartViewStore.getState().setPickGeometry(geometry);
    usePartViewStore.getState().setPickHiddenFaces(new Set([1]));

    usePartViewStore.getState().setSubject("part-b");

    const state = usePartViewStore.getState();
    // Opening another part must not leave the previous part's mesh addressable:
    // the geometry belongs to a `ModelMesh` that is being torn down, and a
    // stale ordinal set would let a pick refuse faces of a body it never saw.
    expect(state.pickGeometry).toBeNull();
    expect(state.pickHiddenFaces.size).toBe(0);
    geometry.dispose();
  });
});

/**
 * GHOST-1 — the solid gets out of the way while you sketch, and the modeler's
 * own word about a body is never overridden to do it.
 */
describe("bodies auto-ghost while a sketch is open", () => {
  beforeEach(reset);

  const F1 = bodyKey("f1");
  const F2 = bodyKey("f2");

  it("ghosts an untouched body on sketch entry and restores it on exit", () => {
    const { view } = usePartViewStore.getState();
    expect(bodyMode(view, F1, false)).toBe("solid");
    expect(bodyMode(view, F1, true)).toBe("ghost");
    // Nothing is STORED to make that happen, which is why there is nothing to
    // restore — and therefore nothing that can be restored wrongly.
    expect(view[F1]).toBeUndefined();
  });

  it("ghosts EVERY body, not just the one being sketched on", () => {
    // Occlusion is a property of the camera and the plane, not of which face
    // was picked: on a multi-body part the solid standing between the eye and
    // the sketch is routinely a neighbour.
    const { view } = usePartViewStore.getState();
    expect(bodyMode(view, F1, true)).toBe("ghost");
    expect(bodyMode(view, F2, true)).toBe("ghost");
  });

  it("leaves a DELIBERATE stop alone, in both directions", () => {
    // Solid on purpose stays solid — the modeler is looking at that body for a
    // reason, and silently ghosting it is what the ticket warned against.
    usePartViewStore.getState().setMode(F1, "solid");
    // Hidden on purpose stays hidden — auto-ghost must never un-hide, or the
    // ISOLATED stamp and its way back would start lying.
    usePartViewStore.getState().setMode(F2, "hidden");
    const { view } = usePartViewStore.getState();
    expect(bodyMode(view, F1, true)).toBe("solid");
    expect(bodyMode(view, F2, true)).toBe("hidden");
  });

  it("a stop set DURING the sketch wins then, and still wins afterwards", () => {
    usePartViewStore.getState().setSketchOpen(true);
    usePartViewStore.getState().setMode(F1, "solid");
    let { view } = usePartViewStore.getState();
    expect(bodyMode(view, F1, true)).toBe("solid");
    // Closing the sketch does not quietly revert it. The user's word is final;
    // an auto-restore here would be the silent override in the other direction.
    usePartViewStore.getState().setSketchOpen(false);
    view = usePartViewStore.getState().view;
    expect(bodyMode(view, F1, false)).toBe("solid");
  });

  it("the eye flips from what the row is SHOWING, so hide/show keeps the ghost", () => {
    usePartViewStore.getState().setSketchOpen(true);
    usePartViewStore.getState().toggle(F1);
    let { view } = usePartViewStore.getState();
    expect(bodyMode(view, F1, true)).toBe("hidden");
    usePartViewStore.getState().toggle(F1);
    view = usePartViewStore.getState().view;
    // Back to GHOST — what it looked like when it was touched. Coming back
    // SOLID would quietly discard the state the row was displaying.
    expect(bodyMode(view, F1, true)).toBe("ghost");
  });

  it("implies nothing about HIDE, so isolate and the stamp are untouched", () => {
    const { view } = usePartViewStore.getState();
    expect(entityIsDrawn(view, F1)).toBe(true);
    expect(hiddenBodyCount(view, BODIES)).toBe(0);
    expect(isolatedBodyLabel(view, BODIES)).toBeNull();
  });

  it("resets with the subject — a ghost cannot follow you to another part", () => {
    usePartViewStore.getState().setSketchOpen(true);
    usePartViewStore.getState().setSubject("part-b");
    expect(usePartViewStore.getState().sketchOpen).toBe(false);
  });
});
