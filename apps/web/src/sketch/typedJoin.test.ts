/**
 * TYPED-POLYLINE-UNJOINED (HARD-PARTS 2026-10-01): a point typed onto a drawn
 * point joins it exactly as a snapped click does, so a typed profile is one
 * connected loop and its first dimension cannot tear it open.
 */
import { beforeEach, describe, expect, it } from "vitest";

import type { SketchConstraint } from "./constraints";
import { DATUM_ORIGIN_ID } from "./datum";
import { TYPED_JOIN_MM, typedJoin } from "./pointEntry";
import type { Point2D } from "./plane";
import { useSketchStore } from "./store";
import type { SketchEntity } from "./tools";

const store = useSketchStore.getState;

const line = (id: string, start: Point2D, end: Point2D): SketchEntity => ({
  id,
  kind: "line",
  construction: false,
  start,
  end,
});

/** Type one point (the X / Y cells, Enter) with the current tool. */
const typePoint = (at: Point2D) => {
  store().openPointEntry(at, null);
  store().commitPointEntry(at);
};

const coincidents = (): SketchConstraint[] =>
  store().constraints.filter((c) => c.kind === "coincident");

beforeEach(() => {
  store().exit();
  store().begin();
  store().choosePlane("XY");
  store().setTool("line");
});

describe("typedJoin", () => {
  const drawn = [line("e1", { x: 10, y: 0 }, { x: 10, y: 20 })];

  it("names the drawn endpoint a typed coordinate lands on", () => {
    expect(typedJoin(drawn, { x: 10, y: 20 }, null)?.ref).toEqual({
      entity: "e1",
      point: "end",
    });
    // A solved coordinate's last-digit noise is still the same point.
    expect(
      typedJoin(drawn, { x: 10, y: 20 + TYPED_JOIN_MM / 2 }, null)?.ref,
    ).toEqual({ entity: "e1", point: "end" });
  });

  it("joins nothing off a point, or on a point with no address", () => {
    expect(typedJoin(drawn, { x: 10, y: 20.001 }, null)).toBeNull();
    // The midpoint is a snap, not an addressable point.
    expect(typedJoin(drawn, { x: 10, y: 10 }, null)).toBeNull();
  });

  it("joins the plane's origin only when it is offered", () => {
    expect(typedJoin([], { x: 0, y: 0 }, null)).toBeNull();
    expect(typedJoin([], { x: 0, y: 0 }, "Origin")?.ref).toEqual({
      entity: DATUM_ORIGIN_ID,
      point: "position",
    });
  });
});

describe("typed placement joins what it lands on", () => {
  it("a closed typed polyline is coincident at every corner, like a snapped one", () => {
    const corners: Point2D[] = [
      { x: 10, y: 0 },
      { x: 10, y: 20 },
      { x: -10, y: 20 },
      { x: -10, y: 5 },
    ];
    // Typed as if the line tool did not chain: each line's start is retyped
    // onto the previous line's end (a no-op on the open chain, LINE-CHAIN),
    // and the last line closes onto the first's start.
    corners.forEach((from, i) => {
      typePoint(from);
      typePoint(corners[(i + 1) % corners.length] as Point2D);
    });

    expect(store().entities).toHaveLength(4);
    expect(coincidents()).toEqual([
      {
        kind: "coincident",
        a: { entity: "e2", point: "start" },
        b: { entity: "e1", point: "end" },
      },
      {
        kind: "coincident",
        a: { entity: "e3", point: "start" },
        b: { entity: "e2", point: "end" },
      },
      {
        kind: "coincident",
        a: { entity: "e4", point: "start" },
        b: { entity: "e3", point: "end" },
      },
      {
        kind: "coincident",
        a: { entity: "e4", point: "end" },
        b: { entity: "e1", point: "start" },
      },
    ]);
  });

  it("matches what a snapped click on the same point authors", () => {
    typePoint({ x: 10, y: 5 });
    typePoint({ x: 10, y: 20 });
    typePoint({ x: 10, y: 20 });
    typePoint({ x: -10, y: 20 });
    const typed = coincidents();

    store().exit();
    store().begin();
    store().choosePlane("XY");
    store().setTool("line");
    for (const at of [
      { x: 10, y: 5 },
      { x: 10, y: 20 },
      { x: 10, y: 20 },
      { x: -10, y: 20 },
    ]) {
      store().placeAt(
        store().aim(at, 1, { suppressed: false, axisLock: false }),
      );
    }
    expect(typed).toHaveLength(1);
    expect(coincidents()).toEqual(typed);
  });

  it("a typed point off every drawn point stays free, exactly where typed", () => {
    typePoint({ x: 10, y: 0 });
    typePoint({ x: 10, y: 20 });
    store().escape(); // end the chain, so the next line is not joined to it
    typePoint({ x: 10.5, y: 20 });
    typePoint({ x: -10, y: 20 });
    expect(coincidents()).toEqual([]);
    expect(store().entities[1]).toMatchObject({ start: { x: 10.5, y: 20 } });
    // The held-off snap state is handed back, not left on.
    expect(store().snapSuppressed).toBe(false);
  });
});
