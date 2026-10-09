import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useEdgePickStore } from "../../features/edgePickStore";
import { isProjected } from "../../sketch/project";
import { useSketchStore } from "../../sketch/store";
import {
  PROJECT_NO_BODY_HINT,
  useSketchProjectSession,
} from "./useSketchProjectSession";

const RIM = {
  kind: "line" as const,
  start: { x: 0, y: 0, z: 0 },
  end: { x: 20, y: 0, z: 0 },
  polyline: [
    { x: 0, y: 0, z: 0 },
    { x: 20, y: 0, z: 0 },
  ],
  signature: {
    subshape_type: "edge" as const,
    curve: "line" as const,
    end_a: { x: 0, y: 0, z: 0 },
    end_b: { x: 20, y: 0, z: 0 },
    midpoint: { x: 10, y: 0, z: 0 },
    length_mm: 20,
  },
};

beforeEach(() => {
  useEdgePickStore.getState().close();
  useSketchStore.getState().exit();
  useSketchStore.getState().begin();
  useSketchStore.getState().choosePlane("XY");
});

describe("useSketchProjectSession", () => {
  it("arming Project opens a project edge pick; a pick projects the edge", () => {
    renderHook(() =>
      useSketchProjectSession({ mode: "draw", anchorFeatureId: "shell" }),
    );
    expect(useEdgePickStore.getState().active).toBe(false);
    act(() => useSketchStore.getState().setTool("project"));
    const picks = useEdgePickStore.getState();
    expect(picks.active && picks.picking).toBe(true);
    expect(picks.purpose).toBe("project");
    act(() => useEdgePickStore.getState().pick(RIM));
    const [entity] = useSketchStore.getState().entities;
    expect(isProjected(entity)).toBe(true);
    expect(
      entity !== undefined &&
        "projection" in entity &&
        entity.projection?.edge.feature_id,
    ).toBe("shell");
    // The taken edge reads as taken.
    expect(useEdgePickStore.getState().picked).toEqual([RIM.signature]);
  });

  it("another tool closes the session", () => {
    renderHook(() =>
      useSketchProjectSession({ mode: "draw", anchorFeatureId: "shell" }),
    );
    act(() => useSketchStore.getState().setTool("project"));
    act(() => useSketchStore.getState().setTool("line"));
    expect(useEdgePickStore.getState().active).toBe(false);
  });

  it("refuses to arm with no body before the sketch, and says why", () => {
    renderHook(() =>
      useSketchProjectSession({ mode: "draw", anchorFeatureId: null }),
    );
    act(() => useSketchStore.getState().setTool("project"));
    expect(useSketchStore.getState().tool).toBe("select");
    expect(useSketchStore.getState().hint).toBe(PROJECT_NO_BODY_HINT);
    expect(useEdgePickStore.getState().active).toBe(false);
  });

  it("leaves a fillet's session alone", () => {
    useEdgePickStore.getState().open([], true);
    renderHook(() =>
      useSketchProjectSession({ mode: "off", anchorFeatureId: "shell" }),
    );
    expect(useEdgePickStore.getState().active).toBe(true);
    expect(useEdgePickStore.getState().purpose).toBe("edges");
  });
});
