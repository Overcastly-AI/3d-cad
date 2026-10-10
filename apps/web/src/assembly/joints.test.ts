import { describe, expect, it } from "vitest";

import type { JointMate, MateResponse } from "../api/assemblies";
import type { EdgeSignature, PlanarFaceSignature } from "../api/parts";
import { useJointDialogStore } from "./jointDialogStore";
import {
  applyJointEdit,
  buildJointMate,
  circleCentre,
  draftFromJoint,
  driveLimits,
  driveValue,
  jointDetail,
  jointDraftReducer,
  type JointOriginPick,
  jointLabels,
  jointUpdate,
  newJointDraft,
  originLocalPoint,
  parseJointDraft,
  positionedBy,
  visibleFields,
} from "./joints";
import { mateNamesById } from "./mates";

/** The hole-plate's top rim: a Ø10 circle centred at (20, 12.5, 10). */
const rim: EdgeSignature = {
  subshape_type: "edge",
  curve: "circle",
  end_a: { x: 25, y: 12.5, z: 10 },
  end_b: { x: 25, y: 12.5, z: 10 },
  midpoint: { x: 15, y: 12.5, z: 10 },
  length_mm: 31.4159,
};
const face: PlanarFaceSignature = {
  subshape_type: "face",
  surface: "plane",
  normal: { x: 0, y: 0, z: 1 },
  centroid: { x: 20, y: 12.5, z: 10 },
  area_mm2: 921.46,
};
const pickA: JointOriginPick = {
  instanceId: "a",
  kind: "circle_centre",
  signature: rim,
  at: null,
  key: "circle-3",
};
const pickB: JointOriginPick = { ...pickA, instanceId: "b", key: "circle-2" };

function joint(over: Partial<JointMate> = {}): JointMate {
  return {
    type: "joint",
    motion: "revolute",
    a: {
      instance_id: "a",
      kind: "circle_centre",
      signature: rim,
      at: null,
      flip: false,
      quarter_turns: 0,
    },
    b: {
      instance_id: "b",
      kind: "circle_centre",
      signature: rim,
      at: null,
      flip: false,
      quarter_turns: 0,
    },
    offset_mm: 0,
    angle_deg: 0,
    limits: null,
    value: { rot_deg: null, lin_mm: null },
    ...over,
  };
}
const row = (id: string, mate: JointMate | MateResponse["mate"]) => ({
  id,
  mate,
});

describe("joint names", () => {
  it("numbers joints per motion in mate order, as the server names them", () => {
    const lock = {
      type: "lock" as const,
      a_instance_id: "a",
      b_instance_id: "b",
    };
    const mates = [
      row("1", joint()),
      row("2", lock),
      row("3", joint({ motion: "slider" })),
      row("4", joint()),
    ];
    const labels = jointLabels(mates);
    expect([...labels.entries()]).toEqual([
      ["1", "Revolute 1"],
      ["3", "Slider 1"],
      ["4", "Revolute 2"],
    ]);
    // The diagnosis names the same object the tree does.
    expect(mateNamesById(mates).get("4")?.name).toBe("M4 Revolute 2");
  });

  it("echoes the driven value on the free axis only", () => {
    expect(jointDetail(joint(), "mm")).toBeNull();
    expect(jointDetail(joint({ value: { rot_deg: 45 } }), "mm")).toBe("45°");
    expect(
      jointDetail(joint({ motion: "slider", value: { lin_mm: 25.4 } }), "in"),
    ).toBe("1 in");
  });
});

describe("positionedBy", () => {
  const failed = new Set<string>();
  it("says what placed the part when every DOF left is a driven joint", () => {
    const mates = [row("1", joint({ value: { rot_deg: 30, lin_mm: null } }))];
    expect(positionedBy("under_constrained", 1, mates, failed)).toBe(
      "Positioned by Revolute 1",
    );
  });

  it("stays out of the way otherwise", () => {
    const free = [row("1", joint())];
    expect(positionedBy("under_constrained", 1, free, failed)).toBeNull();
    const driven = [row("1", joint({ value: { rot_deg: 30 } }))];
    // A second free DOF somewhere else: still genuinely under constrained.
    expect(positionedBy("under_constrained", 2, driven, failed)).toBeNull();
    expect(positionedBy("well_constrained", 0, driven, failed)).toBeNull();
    // A joint that failed to resolve places nothing.
    expect(
      positionedBy("under_constrained", 1, driven, new Set(["1"])),
    ).toBeNull();
  });
});

describe("origin points", () => {
  it("puts a full circle's centre halfway from its seam to its midpoint", () => {
    expect(circleCentre(rim)).toEqual({ x: 20, y: 12.5, z: 10 });
  });

  it("puts an arc's centre at the circumcentre of its ends and middle", () => {
    const arc: EdgeSignature = {
      ...rim,
      end_a: { x: 5, y: 0, z: 0 },
      end_b: { x: 0, y: 5, z: 0 },
      midpoint: { x: 5 * Math.SQRT1_2, y: 5 * Math.SQRT1_2, z: 0 },
    };
    const c = circleCentre(arc);
    expect(c.x).toBeCloseTo(0, 9);
    expect(c.y).toBeCloseTo(0, 9);
    expect(c.z).toBeCloseTo(0, 9);
  });

  it("reads a face centre and the solver's start / mid / end of an edge", () => {
    const origin = joint().a;
    expect(
      originLocalPoint({ ...origin, kind: "face_centre", signature: face }),
    ).toEqual(face.centroid);
    const line: EdgeSignature = {
      ...rim,
      curve: "line",
      end_a: { x: 0, y: 0, z: 0 },
      end_b: { x: 40, y: 0, z: 0 },
      midpoint: { x: 20, y: 0, z: 0 },
    };
    const at = (which: "start" | "mid" | "end") =>
      originLocalPoint({
        ...origin,
        kind: "edge_point",
        signature: line,
        at: which,
      }).x;
    expect([at("start"), at("mid"), at("end")]).toEqual([0, 20, 40]);
  });
});

describe("the dialog draft", () => {
  it("opens as Rigid and reveals limits and a drive per motion", () => {
    expect(newJointDraft().motion).toBe("rigid");
    expect([...visibleFields("rigid")]).toEqual(["offset", "angle"]);
    expect(visibleFields("revolute").has("rotMax")).toBe(true);
    expect(visibleFields("revolute").has("linMax")).toBe(false);
    expect(visibleFields("slider").has("linValue")).toBe(true);
    expect(visibleFields("slider").has("rotValue")).toBe(false);
  });

  it("flips and turns B a quarter at a time, wrapping at a full turn", () => {
    let draft = newJointDraft();
    draft = jointDraftReducer(draft, { type: "flip" });
    expect(draft.flip).toBe(true);
    for (let i = 0; i < 5; i += 1) {
      draft = jointDraftReducer(draft, { type: "rotate" });
    }
    expect(draft.quarterTurns).toBe(1);
  });

  it("flags the visible cells that do not parse, and ignores hidden ones", () => {
    let draft = jointDraftReducer(newJointDraft(), {
      type: "motion",
      motion: "revolute",
    });
    draft = { ...draft, rotMax: "abc", linMax: "also junk" };
    const result = parseJointDraft(draft, "mm");
    expect(result.ok).toBe(false);
    if (!result.ok) expect([...result.invalid]).toEqual(["rotMax"]);
  });

  it("builds the joint: B carries flip / quarter turns, value has both axes", () => {
    let draft = jointDraftReducer(newJointDraft(), {
      type: "motion",
      motion: "revolute",
    });
    draft = jointDraftReducer(draft, { type: "flip" });
    draft = { ...draft, rotMax: "180", rotValue: "45", offset: "1 in" };
    const result = parseJointDraft(draft, "mm");
    if (!result.ok) throw new Error("draft should parse");
    const mate = buildJointMate(draft, result.parsed, pickA, pickB);
    expect(mate.a).toMatchObject({ instance_id: "a", flip: false, at: null });
    expect(mate.b).toMatchObject({ instance_id: "b", flip: true });
    expect(mate.offset_mm).toBeCloseTo(25.4, 9);
    expect(mate.limits).toEqual({
      rot_min_deg: null,
      rot_max_deg: 180,
      lin_min_mm: null,
      lin_max_mm: null,
    });
    // JOINT-VALUE-MERGE: a value replaces both axes, so both are always sent.
    expect(mate.value).toEqual({ rot_deg: 45, lin_mm: null });
  });

  it("round-trips a stored joint through the edit draft into one PATCH", () => {
    const stored = joint({
      limits: { rot_max_deg: 180 },
      value: { rot_deg: 45 },
    });
    const draft = draftFromJoint(stored, "mm");
    expect(draft).toMatchObject({ rotMax: "180", rotValue: "45", rotMin: "" });
    const cleared = { ...draft, rotMax: "", rotValue: "90" };
    const result = parseJointDraft(cleared, "mm");
    if (!result.ok) throw new Error("draft should parse");
    const patch = jointUpdate(cleared, result.parsed, 7);
    expect(patch).toMatchObject({
      expected_version: 7,
      // Cleared limits go as an explicit null — absent would keep them.
      limits: null,
      value: { rot_deg: 90, lin_mm: null },
      flip: false,
      quarter_turns: 0,
    });
    expect(applyJointEdit(stored, cleared, result.parsed).value).toEqual({
      rot_deg: 90,
      lin_mm: null,
    });
  });

  it("drives the free axis only, and stops at the limits or the wire's bound", () => {
    expect(driveValue("slider", 12)).toEqual({ rot_deg: null, lin_mm: 12 });
    expect(driveLimits(joint({ limits: { rot_max_deg: 180 } }))).toEqual([
      -3600, 180,
    ]);
    expect(driveLimits(joint({ motion: "slider" }))).toEqual([
      -100_000, 100_000,
    ]);
  });
});

describe("the dialog store", () => {
  it("opens a new joint on a fresh draft and clears a refusal on edit", () => {
    const store = useJointDialogStore.getState();
    store.openCreate(pickA, pickB);
    store.setError("Revolute 1: 200° exceeds max 180°");
    useJointDialogStore
      .getState()
      .dispatch({ type: "field", field: "rotValue", value: "170" });
    const state = useJointDialogStore.getState();
    expect(state.error).toBeNull();
    expect(state.draft.rotValue).toBe("170");
    state.close();
    expect(useJointDialogStore.getState().target).toBeNull();
  });

  it("seeds an edit from the stored joint", () => {
    useJointDialogStore
      .getState()
      .openEdit("m1", "Revolute 1", joint({ value: { rot_deg: 30 } }), "mm");
    const state = useJointDialogStore.getState();
    expect(state.target).toMatchObject({ mode: "edit", label: "Revolute 1" });
    expect(state.draft.motion).toBe("revolute");
    expect(state.draft.rotValue).toBe("30");
    state.close();
  });
});
