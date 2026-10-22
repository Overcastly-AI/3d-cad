// @vitest-environment jsdom
/**
 * What the part camera frames: a part that OPENS on sketches only is framed
 * on them; a first sketch saved in the session is not auto-framed (finishing
 * a sketch never zooms, and the first extrude re-frames on the body, FB-20),
 * though Fit still frames it.
 */
import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { sceneOriginBasis } from "../sketch/plane";
import type { SketchEntity } from "../sketch/tools";
import { type FramedSketch, useSketchFraming } from "./useSketchFraming";

const OUTLINE: FramedSketch = {
  featureId: "s1",
  basis: sceneOriginBasis("XY"),
  entities: [
    {
      id: "e1",
      kind: "line",
      construction: false,
      start: { x: 0, y: 0 },
      end: { x: 7315.2, y: 4876.8 },
    } as SketchEntity,
  ],
};

function frame(initial: readonly FramedSketch[] | undefined) {
  return renderHook(
    ({ layers }: { layers: readonly FramedSketch[] | undefined }) =>
      useSketchFraming(null, undefined, layers),
    { initialProps: { layers: initial } },
  );
}

describe("useSketchFraming", () => {
  it("opens framed on a part of sketches only", () => {
    const hook = frame(undefined);
    expect(hook.result.current.framesSketches).toBe(false);
    hook.rerender({ layers: [OUTLINE] });
    expect(hook.result.current.framesSketches).toBe(true);
    expect(hook.result.current.fitBounds?.max.x).toBeCloseTo(7315.2, 1);
  });

  it("does not auto-frame a sketch saved after an empty open, but Fit frames it", () => {
    const hook = frame(undefined);
    hook.rerender({ layers: [] });
    hook.rerender({ layers: [OUTLINE] });
    expect(hook.result.current.framesSketches).toBe(false);
    expect(hook.result.current.fitBounds?.max.x).toBeCloseTo(7315.2, 1);
  });
});
