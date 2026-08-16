import { describe, expect, it } from "vitest";

import {
  DATUM_ORIGIN_ID,
  DATUM_PICKS,
  DATUM_X_AXIS_ID,
  DATUM_Y_AXIS_ID,
  datumEntities,
  datumFrame,
  datumOf,
  datumPickCandidates,
  datumPickState,
  datumPins,
  datumSafeSolve,
  DEFAULT_FRAME_HALF_HEIGHT_MM,
  groundDatums,
  isDatumId,
  isDatumPin,
  pickWithDatums,
  selectionTouchesDatum,
  withDatums,
  withoutDatums,
} from "./datum";
import type { SketchConstraint, SolveInfo } from "./constraints";
import {
  ORIGIN_AXIS_FRACTION,
  ORIGIN_RING_FRACTION,
  parkedFrameHalfHeightMm,
} from "./origin";
import { toggleSelection, type SketchPick } from "./pick";
import type { SketchEntity } from "./tools";

/** The camera's parking frame on a datum sheet, near enough for the maths. */
const FRAME_HALF_MM = 80;
const frame = datumFrame(FRAME_HALF_MM);

const line: SketchEntity = {
  id: "e1",
  kind: "line",
  start: { x: 10, y: 10 },
  end: { x: 40, y: 10 },
  construction: false,
};

describe("the frame's identity", () => {
  it("reserves three ids that a drawn entity can never mint", () => {
    expect(isDatumId(DATUM_ORIGIN_ID)).toBe(true);
    expect(isDatumId(DATUM_X_AXIS_ID)).toBe(true);
    expect(isDatumId(DATUM_Y_AXIS_ID)).toBe(true);
    // `entityId` mints e1, e2, … — no overlap with the reserved words.
    expect(isDatumId("e1")).toBe(false);
    expect(isDatumId("origin-plate")).toBe(false);
  });

  it("names which datum a pick addresses, entity or point grain", () => {
    expect(datumOf({ kind: "entity", id: DATUM_X_AXIS_ID })).toBe(
      DATUM_X_AXIS_ID,
    );
    expect(
      datumOf({ kind: "point", entity: DATUM_ORIGIN_ID, point: "position" }),
    ).toBe(DATUM_ORIGIN_ID);
    expect(datumOf({ kind: "point", entity: "e1", point: "start" })).toBeNull();
  });

  it("reports whether a selection reaches the frame at all", () => {
    expect(selectionTouchesDatum([{ kind: "entity", id: "e1" }])).toBe(false);
    expect(
      selectionTouchesDatum([
        { kind: "point", entity: "e1", point: "start" },
        { kind: "entity", id: DATUM_Y_AXIS_ID },
      ]),
    ).toBe(true);
  });
});

describe("datumFrame", () => {
  it("derives the pick geometry from the same fractions that draw the ink", () => {
    expect(frame.ringRadiusMm).toBeCloseTo(
      FRAME_HALF_MM * ORIGIN_RING_FRACTION,
    );
    expect(frame.axisHalfLengthMm).toBeCloseTo(
      FRAME_HALF_MM * ORIGIN_AXIS_FRACTION,
    );
  });

  it("falls back to the parked frame when the scene has not measured one", () => {
    expect(datumFrame(0).axisHalfLengthMm).toBeGreaterThan(0);
    expect(datumFrame(-5)).toEqual(datumFrame(0));
  });
});

describe("datumPickCandidates", () => {
  const tol = 1; // ~8 screen px in plane mm at the parked camera

  it("picks the origin from ANYWHERE ON THE DRAWN RING, not just dead centre", () => {
    // The founder's gesture: a click on the ring ink. It lands
    // `ringRadiusMm` (~1.8 mm here) from zero, which a bare point tolerance
    // of 1 mm would miss — the regression this whole item exists to close.
    expect(frame.ringRadiusMm).toBeGreaterThan(tol);
    const onRing = { x: frame.ringRadiusMm, y: 0 };
    expect(datumPickCandidates(onRing, tol, frame)[0]).toEqual({
      kind: "point",
      entity: DATUM_ORIGIN_ID,
      point: "position",
    });
  });

  it("picks each axis along its drawn span, and nothing beyond it", () => {
    const onX = { x: frame.axisHalfLengthMm * 0.5, y: 0.2 };
    expect(datumPickCandidates(onX, tol, frame)).toEqual([
      { kind: "entity", id: DATUM_X_AXIS_ID },
    ]);
    const onY = { x: -0.2, y: -frame.axisHalfLengthMm * 0.5 };
    expect(datumPickCandidates(onY, tol, frame)).toEqual([
      { kind: "entity", id: DATUM_Y_AXIS_ID },
    ]);
    const pastTheTip = { x: frame.axisHalfLengthMm + 5, y: 0 };
    expect(datumPickCandidates(pastTheTip, tol, frame)).toEqual([]);
  });

  it("orders the origin ahead of the axes that cross it", () => {
    expect(
      datumPickCandidates({ x: 0, y: 0 }, tol, frame).map((pick) =>
        datumOf(pick),
      ),
    ).toEqual([DATUM_ORIGIN_ID, DATUM_X_AXIS_ID, DATUM_Y_AXIS_ID]);
  });

  it("answers nothing out in open steel", () => {
    expect(datumPickCandidates({ x: 30, y: 30 }, tol, frame)).toEqual([]);
  });
});

describe("pickWithDatums", () => {
  const onAxis: SketchEntity = {
    id: "e2",
    kind: "line",
    start: { x: 0, y: 0 },
    end: { x: 20, y: 0 },
    construction: false,
  };

  it("a PLAIN click on a line lying along the axis answers the line, and ONLY the line", () => {
    // Strictly additive: a plain click that resolved to drawn geometry before
    // resolves to exactly the same thing now — it never cycles into the
    // sheet's own datum on a second click.
    expect(pickWithDatums([onAxis], { x: 10, y: 0 }, 1, frame)).toEqual([
      { kind: "entity", id: "e2" },
    ]);
  });

  it("a MODIFIER click reaches the frame under the geometry — the corner-on-origin case", () => {
    const picks = pickWithDatums([onAxis], { x: 0, y: 0 }, 1, frame, "add");
    expect(picks[0]).toEqual({ kind: "point", entity: "e2", point: "start" });
    expect(picks.some((p) => datumOf(p) === DATUM_ORIGIN_ID)).toBe(true);
  });

  it("reaches the origin in the SECOND click — the gesture it exists for", () => {
    // A RECTANGLE CORNER, which is the shape QA measured and the hard case: two
    // stacked endpoints and two edges, so four drawn candidates sit over the
    // origin. Appended after them the walk was
    //   1 pt -> 2 pts -> 1 ent · 2 pts -> 2 ents · 2 pts -> 2 ents · 3 pts
    // and `coincident` then refused. Sorting the origin merely IN with the
    // points does not fix it either: the corner's other endpoint takes the
    // click, the readout says "2 pts", the constraint is accepted, and the
    // corner is grounded to ITSELF — right-looking and wrong.
    const corner: SketchEntity[] = [
      {
        id: "e1",
        kind: "line",
        start: { x: 0, y: 0 },
        end: { x: 24, y: 0 },
        construction: false,
      },
      {
        id: "e4",
        kind: "line",
        start: { x: 0, y: 16 },
        end: { x: 0, y: 0 },
        construction: false,
      },
    ];
    const at = { x: 0, y: 0 };
    // Click 1 is PLAIN: drawn wins, and the frame is not offered at all.
    const plain = pickWithDatums(corner, at, 1, frame);
    expect(plain.every((p) => datumOf(p) === null)).toBe(true);
    const held = [plain[0] as SketchPick];

    // Click 2 is a MODIFIER click on the point already held — it reaches
    // through to the origin rather than to the corner's other endpoint.
    const second = toggleSelection(
      held,
      pickWithDatums(corner, at, 1, frame, "add", held),
    );
    expect(second).toEqual([held[0], DATUM_PICKS[DATUM_ORIGIN_ID]]);
    // Exactly two POINT picks — the shape `coincident` accepts.
    expect(second.filter((p) => p.kind === "point")).toHaveLength(2);
  });

  it("does not hijack a modifier click that STARTS a selection at the origin", () => {
    // The other side of that rule: holding nothing, a modifier click on a
    // corner gives you the corner, not the sheet's zero underneath it.
    const first = pickWithDatums([onAxis], { x: 0, y: 0 }, 1, frame, "add", []);
    expect(first[0]).toEqual({ kind: "point", entity: "e2", point: "start" });
    expect(datumOf(first[0] as SketchPick)).toBeNull();
  });

  it("offers the frame where nothing is drawn — the reported defect", () => {
    expect(pickWithDatums([line], { x: 0, y: 0 }, 1, frame)).toHaveLength(3);
  });

  it("never doubles a datum that is already materialised in the buffer", () => {
    const grounded = [line, ...datumEntities(frame)];
    const picks = pickWithDatums(grounded, { x: 0, y: 0 }, 1, frame, "add");
    expect(picks.filter((p) => datumOf(p) === DATUM_ORIGIN_ID)).toHaveLength(1);
  });
});

describe("materialising the frame", () => {
  it("adds nothing to a sketch that never grounds to it", () => {
    const result = groundDatums([line], ["e1"], frame);
    expect(result.entities).toEqual([line]);
    expect(result.constraints).toEqual([]);
  });

  it("brings in only the datum the constraint referenced, pinned", () => {
    const result = groundDatums([line], ["e1", DATUM_ORIGIN_ID], frame);
    expect(result.entities.map((e) => e.id)).toEqual(["e1", DATUM_ORIGIN_ID]);
    expect(result.constraints).toEqual([
      { kind: "fixed", point: { entity: DATUM_ORIGIN_ID, point: "position" } },
    ]);
    // Construction geometry: it can never open the profile extrude consumes.
    expect(result.entities[1]?.construction).toBe(true);
  });

  it("pins an axis at BOTH ends — a line fixed at one end still swings", () => {
    expect(datumPins(DATUM_X_AXIS_ID)).toEqual([
      { kind: "fixed", point: { entity: DATUM_X_AXIS_ID, point: "start" } },
      { kind: "fixed", point: { entity: DATUM_X_AXIS_ID, point: "end" } },
    ]);
  });

  it("is DOF-neutral: every datum's pins remove exactly what it added", () => {
    const dof = (e: SketchEntity): number => (e.kind === "line" ? 4 : 2);
    for (const entity of datumEntities(frame)) {
      const pins = datumPins(entity.id as "origin" | "x-axis" | "y-axis");
      expect(pins.length * 2).toBe(dof(entity));
    }
  });

  it("leaves an already-present datum exactly as it was (re-open case)", () => {
    const persisted: SketchEntity = {
      id: DATUM_X_AXIS_ID,
      kind: "line",
      start: { x: -50, y: 0 },
      end: { x: 50, y: 0 },
      construction: true,
    };
    const result = groundDatums([persisted], [DATUM_X_AXIS_ID], frame);
    expect(result.entities).toEqual([persisted]);
    expect(result.constraints).toEqual([]);
  });
});

describe("isDatumPin", () => {
  it("is exact: only a `fixed` on a datum point", () => {
    expect(
      isDatumPin({
        kind: "fixed",
        point: { entity: DATUM_ORIGIN_ID, point: "position" },
      }),
    ).toBe(true);
    expect(
      isDatumPin({ kind: "fixed", point: { entity: "e1", point: "start" } }),
    ).toBe(false);
    expect(
      isDatumPin({
        kind: "coincident",
        a: { entity: "e1", point: "start" },
        b: { entity: DATUM_ORIGIN_ID, point: "position" },
      }),
    ).toBe(false);
  });
});

describe("withDatums / withoutDatums", () => {
  it("round-trips a drawn buffer", () => {
    expect(withoutDatums(withDatums([line], frame))).toEqual([line]);
  });

  it("appends only the members the buffer is missing", () => {
    const half = [line, datumEntities(frame)[0] as SketchEntity];
    expect(withDatums(half, frame).map((e) => e.id)).toEqual([
      "e1",
      DATUM_ORIGIN_ID,
      DATUM_X_AXIS_ID,
      DATUM_Y_AXIS_ID,
    ]);
  });
});

describe("datumPickState", () => {
  it("reads selected over hovered, and idle otherwise", () => {
    const selected = [{ kind: "entity", id: DATUM_X_AXIS_ID } as const];
    expect(datumPickState(DATUM_X_AXIS_ID, selected, null)).toBe("selected");
    expect(
      datumPickState(DATUM_X_AXIS_ID, selected, {
        kind: "entity",
        id: DATUM_X_AXIS_ID,
      }),
    ).toBe("selected");
    expect(
      datumPickState(DATUM_Y_AXIS_ID, [], {
        kind: "entity",
        id: DATUM_Y_AXIS_ID,
      }),
    ).toBe("hover");
    expect(datumPickState(DATUM_ORIGIN_ID, selected, null)).toBe("idle");
  });
});

/**
 * THE HIDDEN CONSTRAINT MUST NEVER BE THE ANSWER TO "WHICH ONE DO I DELETE?"
 *
 * Every fixture below is transcribed from a run of the REAL planegcs solver
 * (`geometry.sketch.planegcs_solver.PlanegcsSketchSolver`) against the sketch
 * the store would author, so the indices are the ones the banner would see —
 * not indices invented to make the filter look right.
 */
describe("datumSafeSolve", () => {
  const p = (entity: string, point: "start" | "end" | "position") => ({
    entity,
    point,
  });
  const pin = (
    entity: string,
    point: "start" | "end" | "position",
  ): SketchConstraint => ({ kind: "fixed", point: p(entity, point) });
  const info = (over: Partial<SolveInfo>): SolveInfo => ({
    status: "converged",
    dof: 0,
    conflicting: [],
    redundant: [],
    ...over,
  });

  /**
   * The blocking case. Rectangle (4 coincident + 2 horizontal + 2 vertical),
   * then `symmetric` about the X axis, then the axis's two pins. Solver:
   * `status=overconstrained  dof=3  conflicting=[]  redundant=[10]` — index 10
   * being the pin on `x-axis.end`, which carries no glyph and cannot be
   * selected or deleted. The geometry is correct (the profile centres on the
   * axis at -21.53 / +21.53).
   */
  const SYMMETRIC_ABOUT_AXIS: SketchConstraint[] = [
    { kind: "coincident", a: p("e1", "end"), b: p("e2", "start") },
    { kind: "coincident", a: p("e2", "end"), b: p("e3", "start") },
    { kind: "coincident", a: p("e3", "end"), b: p("e4", "start") },
    { kind: "coincident", a: p("e4", "end"), b: p("e1", "start") },
    { kind: "horizontal", entity: "e1" },
    { kind: "horizontal", entity: "e3" },
    { kind: "vertical", entity: "e2" },
    { kind: "vertical", entity: "e4" },
    {
      kind: "symmetric",
      a: p("e1", "start"),
      b: p("e4", "start"),
      line: "x-axis",
    },
    pin("x-axis", "start"),
    pin("x-axis", "end"),
  ];

  it("never asks the user to delete a datum pin — the blocking SKETCH-2 defect", () => {
    const safe = datumSafeSolve(
      info({ status: "overconstrained", dof: 3, redundant: [10] }),
      SYMMETRIC_ABOUT_AXIS,
    );
    // Nothing is flagged, so nothing claims to be.
    expect(safe.redundant).toEqual([]);
    // …and the DRO reports what is actually true of the sketch: three degrees
    // of freedom left in a profile that solved and centred on the axis.
    expect(safe.status).toBe("underconstrained");
    expect(safe.dof).toBe(3);
  });

  it("restates to CONVERGED when the pin-only redundancy leaves no freedom", () => {
    const safe = datumSafeSolve(
      info({ status: "overconstrained", dof: 0, redundant: [10] }),
      SYMMETRIC_ABOUT_AXIS,
    );
    expect(safe.status).toBe("converged");
  });

  it("leaves an unattributable diagnosis alone rather than smoothing it over", () => {
    // dof arrives null when planegcs could not count it. Restating from a
    // number we do not have would be inventing one.
    const safe = datumSafeSolve(
      info({ status: "overconstrained", dof: null, redundant: [10] }),
      SYMMETRIC_ABOUT_AXIS,
    );
    expect(safe.status).toBe("overconstrained");
    expect(safe.redundant).toEqual([]);
  });

  /**
   * THE TRAP: suppressing the pin must not suppress a real over-constraint.
   * Solver, on a duplicated coincident with the origin pin present:
   * `status=overconstrained  dof=2  redundant=[1]` — its OWN index. planegcs
   * reports the whole dependent set, so a user redundancy is never hidden
   * behind a pin that happens to sit in the same set.
   */
  it("keeps a GENUINE over-constraint flagged, pins and all", () => {
    const duplicated: SketchConstraint[] = [
      { kind: "coincident", a: p("e1", "start"), b: p("origin", "position") },
      { kind: "coincident", a: p("e1", "start"), b: p("origin", "position") },
      pin("origin", "position"),
    ];
    const safe = datumSafeSolve(
      info({ status: "overconstrained", dof: 2, redundant: [1] }),
      duplicated,
    );
    expect(safe.status).toBe("overconstrained");
    expect(safe.redundant).toEqual([1]);
  });

  it("keeps the user's indices when a pin is flagged BESIDE them", () => {
    // Measured: a user `fixed` fighting the origin pin returns
    // `conflicting=[0, 1, 2]`, index 2 being the pin. Drop 2, keep 0 and 1 —
    // they have glyphs and are the two the user can actually act on.
    const fighting: SketchConstraint[] = [
      { kind: "fixed", point: p("e1", "start") },
      { kind: "coincident", a: p("e1", "start"), b: p("origin", "position") },
      pin("origin", "position"),
    ];
    const safe = datumSafeSolve(
      info({ status: "conflicting", dof: 2, conflicting: [0, 1, 2] }),
      fighting,
    );
    expect(safe.status).toBe("conflicting");
    expect(safe.conflicting).toEqual([0, 1]);
  });

  it("NEVER softens a conflict, even when only a pin is named", () => {
    // A conflicting sketch did not solve, so the geometry on screen is wrong.
    // Silence here would be the opposite defect to the one being fixed.
    const safe = datumSafeSolve(
      info({ status: "conflicting", dof: 2, conflicting: [2] }),
      [
        { kind: "coincident", a: p("e1", "start"), b: p("origin", "position") },
        { kind: "coincident", a: p("e1", "end"), b: p("origin", "position") },
        pin("origin", "position"),
      ],
    );
    expect(safe.status).toBe("conflicting");
    expect(safe.conflicting).toEqual([]);
  });

  it("returns the very same object when there is nothing to hide", () => {
    const clean = info({ status: "overconstrained", dof: 1, redundant: [1] });
    expect(
      datumSafeSolve(clean, [
        { kind: "horizontal", entity: "e1" },
        { kind: "horizontal", entity: "e1" },
      ]),
    ).toBe(clean);
  });
});

describe("the parked frame the pick region falls back to", () => {
  it("is the camera's own framing, not a number written beside it", () => {
    // Shipped as a literal 80 under a comment claiming it WAS this derivation.
    // 170 x tan(20 deg) = 61.88 — the literal was 29 % high, so the pre-mount
    // ring measured 1.76 mm where the product draws 1.36 mm.
    expect(parkedFrameHalfHeightMm()).toBeCloseTo(61.875, 3);
    expect(DEFAULT_FRAME_HALF_HEIGHT_MM).toBe(parkedFrameHalfHeightMm());
    expect(datumFrame(0).ringRadiusMm).toBeCloseTo(1.361, 3);
  });
});
