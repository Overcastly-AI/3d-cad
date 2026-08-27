/**
 * MIRROR-1 — mirroring about the sketch's OWN centreline, at store level.
 *
 * The capability's whole difficulty is that the frame is LAZY: `SketchOrigin`
 * draws the origin and the two axes, but nothing puts them in `entities` until
 * a constraint names one. Measured on the pre-fix build, with a rectangle drawn
 * and the mirror in its axis phase:
 *
 *     entities            ["e1","e2","e3","e4"]      (no "y-axis")
 *     pickMirrorAxis("y-axis")
 *     mirrorRequest       null
 *     hint                "The mirror axis must be a line — pick a line or
 *                          centerline."
 *
 * — a refusal that is FALSE (the Y axis is a line, and the one line every
 * sketch is guaranteed to have) and that offers no way forward. These cases pin
 * the fix from the store's side; the viewport's half (the frame being pickable
 * and ghost-previewable in the axis phase) is covered by
 * `e2e/sketch-mirror.spec.ts`.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { DATUM_X_AXIS_ID, DATUM_Y_AXIS_ID, datumFrame } from "./datum";
import { useSketchStore } from "./store";

/** A rectangle wholly on the +x side, so a mirror about Y is meaningful. */
const halfProfile = () => {
  const store = useSketchStore.getState;
  store().begin();
  store().choosePlane("XY");
  store().setTool("rect");
  store().placeAt({ x: 10, y: 0 });
  store().placeAt({ x: 40, y: 25 });
  store().setTool("mirror");
  store().toggleMirrorTarget("e1");
  store().advanceMirror();
};

beforeEach(() => {
  useSketchStore.getState().exit();
});

describe("pickMirrorAxis — the sketch frame", () => {
  it("arms a POINTS axis for a datum axis that was never materialised", () => {
    halfProfile();
    const store = useSketchStore.getState;
    expect(store().entities.map((e) => e.id)).not.toContain(DATUM_Y_AXIS_ID);

    store().pickMirrorAxis(DATUM_Y_AXIS_ID);

    const half = datumFrame(store().datumFrameHalfMm).axisHalfLengthMm;
    expect(store().mirrorRequest).toEqual({
      targets: ["e1"],
      axis: { kind: "points", a: { x: 0, y: -half }, b: { x: 0, y: half } },
      nonce: 1,
    });
    expect(store().hint).toBeNull();
    expect(store().editBusy).toBe(true);
    // Mirror ADDS copies, not relationships: picking the centreline must not
    // quietly grow the sketch a pinned construction line either.
    expect(store().entities).toHaveLength(4);
    expect(store().constraints.filter((c) => c.kind === "fixed")).toEqual([]);
  });

  it("takes the X axis the same way", () => {
    halfProfile();
    const store = useSketchStore.getState;
    store().pickMirrorAxis(DATUM_X_AXIS_ID);
    const half = datumFrame(store().datumFrameHalfMm).axisHalfLengthMm;
    expect(store().mirrorRequest?.axis).toEqual({
      kind: "points",
      a: { x: -half, y: 0 },
      b: { x: half, y: 0 },
    });
  });

  it("still sends a DRAWN line as an entity ref, and still refuses a non-line", () => {
    halfProfile();
    const store = useSketchStore.getState;
    store().pickMirrorAxis("e2");
    expect(store().mirrorRequest?.axis).toEqual({
      kind: "entity",
      entity: "e2",
    });

    useSketchStore.getState().exit();
    halfProfile();
    // The origin is a POINT, not an axis — the refusal survives for it.
    useSketchStore.getState().pickMirrorAxis("origin");
    expect(useSketchStore.getState().mirrorRequest).toBeNull();
    expect(useSketchStore.getState().hint).toMatch(/must be a line/i);
  });
});
