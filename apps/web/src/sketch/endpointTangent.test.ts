/**
 * SKETCH-ENDPOINT-TANGENT, client side: a Tangent between a line and an arc
 * that share an end becomes the endpoint tangent (which IS the join), and an
 * endpoint tangent follows its ends through a trim like a coincident does.
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  applyConstraintAction,
  groundingAnchor,
  type SketchConstraint,
} from "./constraints";
import { endpointTangentFor, joinedPoints } from "./endpointTangent";
import type { SketchPick } from "./pick";
import type { Point2D } from "./plane";
import { reconcileEditedConstraints } from "./reconcileEdit";
import { useSketchStore } from "./store";
import type { SketchEntity } from "./tools";

const line = (id: string, start: Point2D, end: Point2D): SketchEntity => ({
  id,
  kind: "line",
  construction: false,
  start,
  end,
});

/** A leg running up into a quarter arc, joined end to start. */
const LEG = line("l1", { x: 10, y: -20 }, { x: 10, y: 0 });
const ARC: SketchEntity = {
  id: "a1",
  kind: "arc",
  construction: false,
  center: { x: 0, y: 0 },
  start: { x: 10, y: 0 },
  end: { x: 0, y: 10 },
};
const CIRCLE: SketchEntity = {
  id: "c1",
  kind: "circle",
  construction: false,
  center: { x: 30, y: 0 },
  radius: 5,
};
const JOIN: SketchConstraint = {
  kind: "coincident",
  a: { entity: "a1", point: "start" },
  b: { entity: "l1", point: "end" },
};
const ENDPOINT_TANGENT: SketchConstraint = {
  kind: "tangent",
  a: "l1",
  b: "a1",
  a_point: "end",
  b_point: "start",
};
const pick = (id: string): SketchPick => ({ kind: "entity", id });

describe("endpoint tangent authoring", () => {
  it("a Tangent on a joined line and arc is the endpoint tangent, replacing the join", () => {
    expect(
      applyConstraintAction(
        "tangent",
        [pick("l1"), pick("a1")],
        [LEG, ARC],
        [JOIN],
      ),
    ).toEqual({
      outcome: "added",
      constraints: [ENDPOINT_TANGENT],
      replaces: [JOIN],
    });
  });

  it("curves that share no end keep the whole-curve tangent", () => {
    expect(
      applyConstraintAction(
        "tangent",
        [pick("l1"), pick("a1")],
        [LEG, ARC],
        [],
      ),
    ).toEqual({
      outcome: "added",
      constraints: [{ kind: "tangent", a: "l1", b: "a1" }],
    });
    // A circle has no ends, whatever touches it.
    const onCircle: SketchConstraint = {
      kind: "coincident",
      a: { entity: "l1", point: "end" },
      b: { entity: "c1", point: "center" },
    };
    expect(endpointTangentFor(LEG, CIRCLE, [onCircle])).toBeNull();
  });

  it("the store swaps the coincident for the endpoint tangent", () => {
    const store = useSketchStore.getState;
    store().begin();
    store().choosePlane("XY");
    useSketchStore.setState({
      entities: [LEG, ARC],
      constraints: [JOIN],
      selection: [pick("l1"), pick("a1")],
    });
    store().applyConstraint("tangent");
    expect(store().constraints).toEqual([ENDPOINT_TANGENT]);
  });
});

describe("an endpoint tangent is a join", () => {
  beforeEach(() => useSketchStore.getState().begin());

  it("reads as the two points it makes one", () => {
    expect(joinedPoints(ENDPOINT_TANGENT)).toEqual([
      { entity: "l1", point: "end" },
      { entity: "a1", point: "start" },
    ]);
    expect(joinedPoints({ kind: "tangent", a: "l1", b: "a1" })).toBeNull();
  });

  it("carries a Fix through to the other curve's end", () => {
    const fixed: SketchConstraint = {
      kind: "fixed",
      point: { entity: "a1", point: "start" },
    };
    expect(
      groundingAnchor({ entity: "l1", point: "end" }, [
        ENDPOINT_TANGENT,
        fixed,
      ]),
    ).toEqual({ entity: "a1", point: "start" });
  });

  it("is dropped when a trim moves its end, kept when the far end moves", () => {
    const trimmedAtJoin = line("l1", { x: 10, y: -20 }, { x: 10, y: -5 });
    expect(
      reconcileEditedConstraints(
        [ENDPOINT_TANGENT],
        [LEG, ARC],
        [trimmedAtJoin, ARC],
        "l1",
      ),
    ).toEqual({ constraints: [], removed: 1 });
    const trimmedFar = line("l1", { x: 10, y: -12 }, { x: 10, y: 0 });
    expect(
      reconcileEditedConstraints(
        [ENDPOINT_TANGENT],
        [LEG, ARC],
        [trimmedFar, ARC],
        "l1",
      ),
    ).toEqual({ constraints: [ENDPOINT_TANGENT], removed: 0 });
  });

  it("follows its end onto the piece of a split that owns it", () => {
    const pieces = [
      line("l1", { x: 10, y: -20 }, { x: 10, y: -15 }),
      ARC,
      line("l1.1", { x: 10, y: -8 }, { x: 10, y: 0 }),
    ];
    expect(
      reconcileEditedConstraints([ENDPOINT_TANGENT], [LEG, ARC], pieces, "l1")
        .constraints,
    ).toEqual([{ ...ENDPOINT_TANGENT, a: "l1.1" }]);
  });
});
