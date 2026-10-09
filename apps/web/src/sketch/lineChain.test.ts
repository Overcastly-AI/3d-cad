/**
 * LINE-CHAIN: the Line tool chains like Fusion's and SolidWorks'. The hub's
 * 12-segment section takes 13 clicks, the last on the start point closing it;
 * every joint is coincident; Escape ends the chain with the tool still armed,
 * a second Escape drops it; a typed point continues the chain.
 */
import { beforeEach, describe, expect, it } from "vitest";

import type { SketchConstraint } from "./constraints";
import { chainStep } from "./lineChain";
import type { Point2D } from "./plane";
import { useSketchStore } from "./store";

const store = useSketchStore.getState;

/** A pulley hub's half-section: hub, web and rim, 12 vertices. */
const HUB_SECTION: readonly Point2D[] = [
  { x: 5, y: 0 },
  { x: 30, y: 0 },
  { x: 30, y: 4 },
  { x: 40, y: 4 },
  { x: 40, y: 0 },
  { x: 50, y: 0 },
  { x: 50, y: 20 },
  { x: 40, y: 20 },
  { x: 40, y: 16 },
  { x: 30, y: 16 },
  { x: 30, y: 20 },
  { x: 5, y: 20 },
];

/** A click: the one aim path, then the placement (as the scene does). */
const click = (at: Point2D) =>
  store().placeAt(store().aim(at, 0.5, { suppressed: false, axisLock: false }));

const typePoint = (at: Point2D) => {
  store().openPointEntry(at, null);
  store().commitPointEntry(at);
};

const coincidents = (): SketchConstraint[] =>
  store().constraints.filter((c) => c.kind === "coincident");

const lineIds = () =>
  store()
    .entities.filter((e) => e.kind === "line")
    .map((e) => e.id);

/** "eN.point" for each side of every coincident, sorted per joint. */
const joints = (): string[] =>
  coincidents().map((c) => {
    if (c.kind !== "coincident") return "";
    return [c.a, c.b]
      .map((ref) => `${ref.entity}.${ref.point}`)
      .sort()
      .join("=");
  });

beforeEach(() => {
  store().exit();
  store().begin();
  store().choosePlane("XY");
  store().setTool("line");
});

describe("clicking a chain", () => {
  it("the hub's 12-segment section is 13 clicks, the last closing it", () => {
    for (const at of HUB_SECTION) click(at);
    expect(lineIds()).toHaveLength(11);
    expect(store().pending).toEqual([{ x: 5, y: 20 }]);
    click(HUB_SECTION[0] as Point2D);

    expect(lineIds()).toHaveLength(12);
    // Closed: the chain is over, the tool is still armed for the next one.
    expect(store().pending).toEqual([]);
    expect(store().chainStart).toBeNull();
    expect(store().tool).toBe("line");
    // Every joint coincident, the closing one included, each stated once.
    const expected = Array.from({ length: 12 }, (_, i) => {
      const next = (i + 1) % 12;
      return [`e${String(i + 1)}.end`, `e${String(next + 1)}.start`]
        .sort()
        .join("=");
    });
    expect(joints().sort()).toEqual(expected.sort());
    // Each segment starts exactly where the last one ended.
    const lines = store().entities.filter((e) => e.kind === "line");
    lines.forEach((line, i) => {
      const next = lines[(i + 1) % lines.length];
      if (line.kind !== "line" || next?.kind !== "line") throw new Error();
      expect(next.start).toEqual(line.end);
    });
  });

  it("Escape ends the chain with the tool armed; a second Escape drops it", () => {
    click({ x: 2, y: 2 });
    click({ x: 10, y: 0 });
    click({ x: 10, y: 10 });
    expect(store().pending).toEqual([{ x: 10, y: 10 }]);

    store().escape();
    expect(lineIds()).toHaveLength(2);
    expect(store().pending).toEqual([]);
    expect(store().tool).toBe("line");
    // The next click starts a NEW chain, joined to nothing.
    click({ x: 20, y: 20 });
    click({ x: 30, y: 20 });
    expect(joints()).toEqual(["e1.end=e2.start"]);

    store().escape();
    store().escape();
    expect(store().tool).toBe("select");
  });

  it("a click back on the last point is refused, not a zero-length line", () => {
    click({ x: 2, y: 2 });
    click({ x: 10, y: 0 });
    click({ x: 10, y: 0 });
    expect(lineIds()).toHaveLength(1);
    expect(store().pending).toEqual([{ x: 10, y: 0 }]);
  });

  it("a drag draws one line and does not chain", () => {
    store().placeAt({ x: 2, y: 2 });
    store().placeAt({ x: 10, y: 0 }, false);
    expect(store().pending).toEqual([]);
    store().placeAt({ x: 20, y: 0 });
    expect(lineIds()).toHaveLength(1);
  });

  it("a typed length moves the chain on to where that end now is", () => {
    click({ x: 2, y: 0 });
    click({ x: 10, y: 0 });
    store().commitDrawDimensions({ length: 25 });
    expect(store().pending).toEqual([{ x: 27, y: 0 }]);
    click({ x: 27, y: 10 });
    const [, second] = store().entities.filter((e) => e.kind === "line");
    expect(second).toMatchObject({ start: { x: 27, y: 0 } });
    expect(joints()).toEqual(["e1.end=e2.start"]);
  });
});

describe("typing a chain", () => {
  it("a typed point continues the chain, and the typed start closes it", () => {
    const square: Point2D[] = [
      { x: 2, y: 2 },
      { x: 20, y: 2 },
      { x: 20, y: 20 },
      { x: 2, y: 20 },
    ];
    for (const at of square) typePoint(at);
    expect(lineIds()).toHaveLength(3);
    typePoint({ x: 2, y: 2 });
    expect(lineIds()).toHaveLength(4);
    expect(store().pending).toEqual([]);
    expect(joints().sort()).toEqual(
      [
        "e1.end=e2.start",
        "e2.end=e3.start",
        "e3.end=e4.start",
        "e1.start=e4.end",
      ].sort(),
    );
  });

  it("clicks and typed points mix in one chain", () => {
    typePoint({ x: 2, y: 2 });
    click({ x: 10, y: 2 });
    // The clicked segment's length cells take typing (FB-16); dismissing
    // them leaves the chain open for the next typed point.
    store().dismissDrawDimensions();
    typePoint({ x: 10, y: 10 });
    expect(store().pending).toEqual([{ x: 10, y: 10 }]);
    expect(lineIds()).toHaveLength(2);
    expect(joints()).toEqual(["e1.end=e2.start"]);
  });
});

describe("chainStep", () => {
  it("leaves every other tool's sequence as it was", () => {
    const rect = chainStep(
      "rect",
      [{ x: 2, y: 2 }],
      { pending: [], entities: [], nextIdIndex: 5 },
      [],
      null,
    );
    expect(rect).toEqual({ pending: [], snapAnchors: [], chainStart: null });
  });
});
