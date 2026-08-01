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
    expect(bodyMode(usePartViewStore.getState().view, key)).toBe("ghost");
    usePartViewStore.getState().setMode(key, "hidden");
    expect(bodyMode(usePartViewStore.getState().view, key)).toBe("hidden");
    // Un-hiding restores the ghost you had — the small honesty that makes the
    // control feel reliable.
    usePartViewStore.getState().toggle(key);
    expect(bodyMode(usePartViewStore.getState().view, key)).toBe("ghost");
  });

  it("isolate keeps one body and hides the rest", () => {
    usePartViewStore.getState().isolate(bodyKey("f2"));
    const { view } = usePartViewStore.getState();
    expect(bodyMode(view, bodyKey("f1"))).toBe("hidden");
    expect(bodyMode(view, bodyKey("f2"))).toBe("solid");
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
