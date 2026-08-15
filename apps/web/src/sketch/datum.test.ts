import { describe, expect, it } from "vitest";

import {
  DATUM_ORIGIN_ID,
  DATUM_X_AXIS_ID,
  DATUM_Y_AXIS_ID,
  datumEntities,
  datumFrame,
  datumOf,
  datumPickCandidates,
  datumPickState,
  datumPins,
  groundDatums,
  isDatumId,
  isDatumPin,
  pickWithDatums,
  selectionTouchesDatum,
  withDatums,
  withoutDatums,
} from "./datum";
import { ORIGIN_AXIS_FRACTION, ORIGIN_RING_FRACTION } from "./origin";
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
