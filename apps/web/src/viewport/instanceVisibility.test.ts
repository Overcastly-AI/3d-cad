import { describe, expect, it } from "vitest";

import {
  EMPTY_VISIBILITY,
  hiddenInstanceCount,
  isInstanceVisible,
  isolateInstance,
  isolatedInstanceId,
  instanceView,
  showAllInstances,
  toggleInstanceHidden,
  visibilityModeOf,
  withVisibilityMode as withMode,
  type VisibilityState,
} from "./instanceVisibility";

const IDS = ["a", "b", "c"];

describe("instance visibility — defaults", () => {
  it("an untouched instance is shown and solid", () => {
    expect(instanceView(EMPTY_VISIBILITY, "a")).toEqual({
      hidden: false,
      ghost: false,
    });
    expect(visibilityModeOf(EMPTY_VISIBILITY, "a")).toBe("solid");
    expect(isInstanceVisible(EMPTY_VISIBILITY, "a")).toBe(true);
    expect(hiddenInstanceCount(EMPTY_VISIBILITY, IDS)).toBe(0);
  });
});

describe("instance visibility — writing a stop", () => {
  it("GHOST keeps the instance drawn", () => {
    const state = withMode(EMPTY_VISIBILITY, "a", "ghost");
    expect(visibilityModeOf(state, "a")).toBe("ghost");
    expect(isInstanceVisible(state, "a")).toBe(true);
  });

  it("HIDE stops it being drawn", () => {
    const state = withMode(EMPTY_VISIBILITY, "a", "hidden");
    expect(visibilityModeOf(state, "a")).toBe("hidden");
    expect(isInstanceVisible(state, "a")).toBe(false);
  });

  it("SOLID and GHOST both un-hide (choosing an opacity means 'show me')", () => {
    const hidden = withMode(
      withMode(EMPTY_VISIBILITY, "a", "ghost"),
      "a",
      "hidden",
    );
    expect(isInstanceVisible(withMode(hidden, "a", "solid"), "a")).toBe(true);
    expect(isInstanceVisible(withMode(hidden, "a", "ghost"), "a")).toBe(true);
  });

  it("leaves the other instances alone", () => {
    const state = withMode(EMPTY_VISIBILITY, "a", "hidden");
    expect(visibilityModeOf(state, "b")).toBe("solid");
  });
});

describe("instance visibility — the eye preserves the opacity stop", () => {
  it("hide then show returns a ghosted instance to GHOST, not SOLID", () => {
    const ghosted = withMode(EMPTY_VISIBILITY, "a", "ghost");
    const hidden = toggleInstanceHidden(ghosted, "a");
    expect(visibilityModeOf(hidden, "a")).toBe("hidden");
    const shownAgain = toggleInstanceHidden(hidden, "a");
    expect(visibilityModeOf(shownAgain, "a")).toBe("ghost");
  });

  it("toggles a solid instance hidden and back", () => {
    const hidden = toggleInstanceHidden(EMPTY_VISIBILITY, "a");
    expect(visibilityModeOf(hidden, "a")).toBe("hidden");
    expect(visibilityModeOf(toggleInstanceHidden(hidden, "a"), "a")).toBe(
      "solid",
    );
  });
});

describe("instance visibility — isolate", () => {
  it("hides every other instance and shows the kept one solid", () => {
    const ghosted = withMode(EMPTY_VISIBILITY, "b", "ghost");
    const state = isolateInstance(ghosted, IDS, "b");
    expect(visibilityModeOf(state, "b")).toBe("solid");
    expect(visibilityModeOf(state, "a")).toBe("hidden");
    expect(visibilityModeOf(state, "c")).toBe("hidden");
    expect(hiddenInstanceCount(state, IDS)).toBe(2);
  });

  it("keeps the neighbours' ghost stops so showAll restores the working view", () => {
    const ghosted = withMode(EMPTY_VISIBILITY, "c", "ghost");
    const isolated = isolateInstance(ghosted, IDS, "a");
    const restored = showAllInstances(isolated, IDS);
    expect(visibilityModeOf(restored, "c")).toBe("ghost");
    expect(visibilityModeOf(restored, "a")).toBe("solid");
    expect(hiddenInstanceCount(restored, IDS)).toBe(0);
  });
});

describe("instance visibility — the isolated instance is DERIVED", () => {
  it("names the one shown instance", () => {
    expect(
      isolatedInstanceId(isolateInstance(EMPTY_VISIBILITY, IDS, "c"), IDS),
    ).toBe("c");
  });

  it("is null when more than one is shown", () => {
    const state = withMode(EMPTY_VISIBILITY, "a", "hidden");
    expect(isolatedInstanceId(state, IDS)).toBe(null);
  });

  it("is null when everything is hidden", () => {
    let state: VisibilityState = EMPTY_VISIBILITY;
    for (const id of IDS) state = withMode(state, id, "hidden");
    expect(isolatedInstanceId(state, IDS)).toBe(null);
    expect(hiddenInstanceCount(state, IDS)).toBe(3);
  });

  it("is null for a single-instance assembly (nothing was isolated FROM)", () => {
    expect(isolatedInstanceId(EMPTY_VISIBILITY, ["a"])).toBe(null);
  });

  it("catches a hand-hidden view, not just the isolate verb", () => {
    const byHand = withMode(
      withMode(EMPTY_VISIBILITY, "a", "hidden"),
      "c",
      "hidden",
    );
    expect(isolatedInstanceId(byHand, IDS)).toBe("b");
  });
});
