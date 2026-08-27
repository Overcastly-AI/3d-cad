import { describe, expect, it } from "vitest";

import {
  clampDepth,
  columnKey,
  mateDepthStack,
  type DepthHit,
} from "./mateDepthStack";

/** One r3f-shaped intersection: a pick surface, a face ordinal, a depth. */
function hit(pickId: string | undefined, index: number, distance: number) {
  return {
    index,
    distance,
    object: { userData: pickId === undefined ? {} : { pickId } },
  } satisfies DepthHit;
}

/** Everything on offer — the default for cases not about the offer. */
const anything = () => true;

describe("mateDepthStack", () => {
  it("orders the column near → far", () => {
    const column = mateDepthStack(
      [hit("plate", 5, 30), hit("bracket", 4, 10)],
      anything,
    );
    expect(column.map((c) => `${c.instanceId}:${c.faceIndex}`)).toEqual([
      "bracket:4",
      "plate:5",
    ]);
  });

  it("REACHES A BURIED FACE — the S-15 case, stated as a list", () => {
    // A bracket seated on a plate, seen from above: the ray enters the
    // bracket's top, leaves through its bottom (the mate target), and lands on
    // the plate's top under it. The old nearest-hit pick could only ever
    // answer "bracket top"; the target is entry 1.
    const column = mateDepthStack(
      [hit("bracket", 5, 100), hit("bracket", 4, 112), hit("plate", 5, 112.01)],
      anything,
    );
    expect(column).toHaveLength(3);
    expect(column[1]).toMatchObject({ instanceId: "bracket", faceIndex: 4 });
  });

  it("keeps the NEAREST occurrence of a repeated face", () => {
    // A ray can re-enter one face's tessellation; a face is one candidate.
    const column = mateDepthStack(
      [hit("plate", 5, 40), hit("plate", 5, 12)],
      anything,
    );
    expect(column).toHaveLength(1);
    expect(column[0]?.distance).toBe(12);
  });

  it("drops hits from a surface that is not a NAMED pick target", () => {
    // A balloon's Html, an instance body's own select handler: real hits, but
    // nothing a mate can be authored on. A candidate nobody can name is a dead
    // row in a list whose whole job is to be chosen from.
    expect(mateDepthStack([hit(undefined, 3, 10)], anything)).toEqual([]);
  });

  it("drops hits carrying no face ordinal", () => {
    const unstamped = {
      distance: 10,
      object: { userData: { pickId: "plate" } },
    } satisfies DepthHit;
    expect(mateDepthStack([unstamped], anything)).toEqual([]);
  });

  it("drops a face the armed tool does not OFFER", () => {
    // A coincident mate refuses a cylindrical face — a bore wall must not
    // appear as a candidate just because the ray went through it.
    const column = mateDepthStack(
      [hit("plate", 5, 10), hit("plate", 9, 20)],
      (_instanceId, faceIndex) => faceIndex !== 9,
    );
    expect(column.map((c) => c.faceIndex)).toEqual([5]);
  });

  it("tells the same faces on DIFFERENT instances apart", () => {
    // Two instances of one part: identical ordinals, different subjects. The
    // kernel gate measured that a shared part's faces are indistinguishable by
    // count, so the instance is the only thing separating them here.
    const column = mateDepthStack([hit("a", 4, 10), hit("b", 4, 20)], anything);
    expect(column).toHaveLength(2);
    expect(column.map((c) => c.instanceId)).toEqual(["a", "b"]);
  });
});

describe("columnKey", () => {
  it("ignores DISTANCE — sliding along one face is not a new choice", () => {
    // The property that makes a deeper entry clickable at all: without it,
    // every pointer micro-move would rebuild the column and snap the chosen
    // depth back to the nearest face.
    expect(columnKey(mateDepthStack([hit("a", 4, 10)], anything))).toBe(
      columnKey(mateDepthStack([hit("a", 4, 11.5)], anything)),
    );
  });

  it("changes when the FACES change", () => {
    expect(columnKey(mateDepthStack([hit("a", 4, 10)], anything))).not.toBe(
      columnKey(mateDepthStack([hit("a", 5, 10)], anything)),
    );
  });

  it("changes when the same face belongs to another instance", () => {
    expect(columnKey(mateDepthStack([hit("a", 4, 10)], anything))).not.toBe(
      columnKey(mateDepthStack([hit("b", 4, 10)], anything)),
    );
  });
});

describe("clampDepth", () => {
  const column = mateDepthStack(
    [hit("a", 1, 10), hit("a", 2, 20), hit("a", 3, 30)],
    anything,
  );

  it("holds a valid depth", () => {
    expect(clampDepth(1, column)).toBe(1);
  });

  it("clamps past either end rather than wrapping", () => {
    // Wrapping would make "deeper" jump back to the surface, which is exactly
    // the kind of ambiguous exit the flow rule forbids.
    expect(clampDepth(9, column)).toBe(2);
    expect(clampDepth(-3, column)).toBe(0);
  });

  it("answers 0 for an empty column, so no caller indexes a hole", () => {
    expect(clampDepth(4, [])).toBe(0);
  });
});
