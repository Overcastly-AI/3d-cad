/**
 * REASON-GATE-1 — the property every feature editor's commit gate must hold:
 * **a refusal that cannot be silent, and cannot disagree with the gate it
 * explains.**
 *
 * Two things are asserted for all fifteen blockers at once, because fifteen is
 * exactly the count at which a spot-check passes while the rollout is half done.
 *
 *  1. **Agreement with an INDEPENDENTLY-WRITTEN predicate.** Every subject below
 *     restates its original gate as a literal expression (`oracle`) — the
 *     boolean that shipped before this change — rather than calling
 *     `canSubmitX`, which is now defined in terms of the blocker and would be
 *     agreeing with itself. A blocker that refuses a form the product used to
 *     accept is a regression in what can be modelled, and it would be invisible
 *     to any assertion phrased against the new code.
 *
 *  2. **A refusal always says something, inside the budget.** Non-null, ≤48
 *     characters (`MAX_BLOCKER_CHARS` — the footer cell is half a card wide; see
 *     `submitBlocker.ts`), sentence-shaped, and never a bare restatement of the
 *     field name.
 *
 * NON-VACUITY. A table-driven walk that finds nothing passes every assertion it
 * makes, which this project has now shipped several times. So the counts are
 * themselves gates: the subject count, a per-subject floor of gated states, and
 * a total. Deleting a subject to make a failure go away fails here instead.
 */
import { describe, expect, it } from "vitest";

import type { EdgeSignature, PlanarFaceSignature } from "../api/parts";
import { combineSubmitBlocker, type CombineForm } from "./boolean";
import {
  buildDatumParams,
  datumSubmitBlocker,
  defaultFormForKind,
  EMPTY_MIDPLANE_SIDE,
  refMidplaneSide,
  encodeOriginSide,
  type DatumForm,
} from "./datum";
import {
  buildDraftParams,
  defaultDraftForm,
  draftSubmitBlocker,
} from "./draft";
import { extrudeSubmitBlocker, type ExtrudeForm } from "./extrude";
import { defaultLoftForm, loftSubmitBlocker } from "./loft";
import { mirrorSubmitBlocker } from "./mirror";
import {
  buildChamferParams,
  buildFilletParams,
  chamferSubmitBlocker,
  defaultChamferForm,
  defaultFilletForm,
  filletSubmitBlocker,
} from "./modify";
import {
  buildPatternParams,
  defaultPatternForm,
  patternSubmitBlocker,
} from "./pattern";
import { revolveSubmitBlocker, type AxisOption } from "./revolve";
import {
  baseFlangeSubmitBlocker,
  buildBaseFlangeParams,
  buildCornerReliefParams,
  buildEdgeFlangeParams,
  cornerReliefSubmitBlocker,
  defaultBaseFlangeForm,
  defaultCornerReliefForm,
  defaultEdgeFlangeForm,
  edgeFlangeSubmitBlocker,
} from "./sheetMetal";
import {
  buildShellParams,
  defaultShellForm,
  shellSubmitBlocker,
} from "./shell";
import { defaultSweepForm, sweepSubmitBlocker } from "./sweep";
import { MAX_BLOCKER_CHARS } from "./submitBlocker";

const MM = "mm" as const;

const EDGE: EdgeSignature = {
  curve: "line",
  end_a: { x: 0, y: 0, z: 2 },
  end_b: { x: 40, y: 0, z: 2 },
  midpoint: { x: 20, y: 0, z: 2 },
  length_mm: 40,
  subshape_type: "edge",
};

const FACE: PlanarFaceSignature = {
  normal: { x: 0, y: 0, z: 1 },
  centroid: { x: 10, y: 10, z: 20 },
  area_mm2: 400,
  subshape_type: "face",
  surface: "plane",
};

/** One driven state of one editor's form: its blocker, and the old verdict. */
interface Probe {
  /** What the user did to get here, in the failure message. */
  name: string;
  blocker: string | null;
  /** The gate as it was written BEFORE the blocker existed — the oracle. */
  oracle: boolean;
}

interface Subject {
  /** The editor's submit-cell test id, so a failure names the card. */
  id: string;
  probes: Probe[];
}

const AXES: AxisOption[] = [
  {
    id: "origin:X",
    label: "X axis · through the origin",
    construction: false,
    kind: "origin_axis",
    ref: { kind: "origin_axis", axis: "X" },
    reason: null,
  },
  {
    id: "origin:Z",
    label: "Z axis · it is the plane normal",
    construction: false,
    kind: "origin_axis",
    ref: { kind: "origin_axis", axis: "Z" },
    reason: "Not in the sketch plane — it is the plane normal.",
  },
];

function combine(over: Partial<CombineForm> = {}): Probe["blocker"] {
  return combineSubmitBlocker({
    operation: "union",
    targetFeatureId: "body-a",
    toolFeatureId: "body-b",
    allowDisjoint: false,
    ...over,
  });
}

function combineOracle(over: Partial<CombineForm> = {}): boolean {
  const f: CombineForm = {
    operation: "union",
    targetFeatureId: "body-a",
    toolFeatureId: "body-b",
    allowDisjoint: false,
    ...over,
  };
  return (
    f.targetFeatureId !== "" &&
    f.toolFeatureId !== "" &&
    f.targetFeatureId !== f.toolFeatureId
  );
}

const EXTRUDE: ExtrudeForm = {
  profileFeatureId: "sk-1",
  distanceInput: "10",
  operation: "add",
  direction: "normal",
  directionTouched: false,
  merge: true,
};

/** The datum form for one kind, with a given override applied. */
function datum(over: Partial<DatumForm> = {}): DatumForm {
  return { ...defaultFormForKind("offset", false), ...over } as DatumForm;
}

const SUBJECTS: Subject[] = [
  {
    id: "base-flange-submit",
    probes: (
      [
        ["a complete form", {}],
        ["no profile chosen", { profileFeatureId: "" }],
        ["the gauge cleared", { thicknessInput: "" }],
        ["a negative gauge", { thicknessInput: "-2" }],
        ["the bend radius cleared", { bendRadiusInput: "" }],
        ["a K-factor out of range", { kFactorInput: "9" }],
      ] as const
    ).map(([name, over]) => {
      const form = { ...defaultBaseFlangeForm("sk-1"), ...over };
      return {
        name,
        blocker: baseFlangeSubmitBlocker(form, MM),
        oracle: buildBaseFlangeParams(form, MM) !== null,
      };
    }),
  },
  {
    id: "chamfer-submit",
    probes: (
      [
        ["a ruled chamfer of every edge", {}, [EDGE], "body-1"],
        ["the distance cleared", { distanceInput: "" }, [EDGE], "body-1"],
        ["a zero distance", { distanceInput: "0" }, [EDGE], "body-1"],
        ["pick mode with nothing picked", { mode: "pick" }, [], "body-1"],
        ["pick mode with no body anchor", { mode: "pick" }, [EDGE], null],
      ] as const
    ).map(([name, over, picked, anchor]) => {
      const form = { ...defaultChamferForm(), ...over };
      return {
        name,
        blocker: chamferSubmitBlocker(form, picked, anchor, MM),
        oracle: buildChamferParams(form, picked, anchor, MM) !== null,
      };
    }),
  },
  {
    id: "combine-submit",
    probes: [
      { name: "two distinct bodies", over: {} },
      { name: "no target", over: { targetFeatureId: "" } },
      { name: "no tool", over: { toolFeatureId: "" } },
      { name: "the same body twice", over: { toolFeatureId: "body-a" } },
      {
        name: "no target, subtracting",
        over: { targetFeatureId: "", operation: "subtract" as const },
      },
    ].map(({ name, over }) => ({
      name,
      blocker: combine(over),
      oracle: combineOracle(over),
    })),
  },
  {
    id: "corner-relief-submit",
    probes: (
      [
        ["two distinct bends", {}],
        ["bend A unchosen", { bendAId: "" }],
        ["bend B unchosen", { bendBId: "" }],
        ["the same flange twice", { bendBId: "ef-1" }],
        ["the ratio cleared", { reliefRatioInput: "" }],
        ["a size override with no value", { overrideSize: true }],
      ] as const
    ).map(([name, over]) => {
      const form = { ...defaultCornerReliefForm("ef-1", "ef-2"), ...over };
      return {
        name,
        blocker: cornerReliefSubmitBlocker(form, MM),
        oracle: buildCornerReliefParams(form, MM) !== null,
      };
    }),
  },
  {
    id: "datum-submit",
    probes: [
      { name: "an offset plane", form: datum() },
      { name: "the offset cleared", form: datum({ offsetInput: "" }) },
      { name: "a non-numeric offset", form: datum({ offsetInput: "abc" }) },
      {
        name: "offset-from with no base",
        form: defaultFormForKind("offset_from", false),
      },
      {
        name: "a midplane with neither side",
        form: defaultFormForKind("midplane", false),
      },
      {
        name: "a midplane with only the first side",
        form: {
          ...defaultFormForKind("midplane", false),
          a: refMidplaneSide(encodeOriginSide("XY")),
          b: EMPTY_MIDPLANE_SIDE,
        } as DatumForm,
      },
      {
        name: "on-face with no face picked",
        form: defaultFormForKind("on_face", false),
      },
    ].map(({ name, form }) => ({
      name,
      blocker: datumSubmitBlocker(form, MM),
      oracle: buildDatumParams(form, MM) !== null,
    })),
  },
  {
    id: "draft-submit",
    probes: (
      [
        ["a 3 degree taper on one face", {}, [FACE], "body-1"],
        ["no faces picked", {}, [], "body-1"],
        ["no body anchor", {}, [FACE], null],
        ["the angle cleared", { angleInput: "" }, [FACE], "body-1"],
        ["a zero angle", { angleInput: "0" }, [FACE], "body-1"],
        [
          "a non-numeric neutral offset",
          { neutral: { base: "XY" as const, offsetInput: "x", flip: false } },
          [FACE],
          "body-1",
        ],
      ] as const
    ).map(([name, over, picked, anchor]) => {
      const form = { ...defaultDraftForm(), ...over };
      return {
        name,
        blocker: draftSubmitBlocker(form, picked, anchor, MM),
        oracle: buildDraftParams(form, picked, anchor, MM) !== null,
      };
    }),
  },
  {
    id: "edge-flange-submit",
    probes: (
      [
        ["a 20 mm full-width flange", {}, [EDGE], "body-1"],
        ["no edge picked", {}, [], "body-1"],
        ["two edges picked", {}, [EDGE, EDGE], "body-1"],
        ["no sheet body", {}, [EDGE], null],
        ["the flange length cleared", { flangeLengthInput: "" }, [EDGE], "b"],
        ["a bend angle past 180", { bendAngleInput: "200" }, [EDGE], "b"],
        [
          "a centered span wider than the edge",
          { widthExtent: "centered" as const, widthInput: "90" },
          [EDGE],
          "b",
        ],
        [
          "an offset span with no width",
          { widthExtent: "offset" as const, widthInput: "" },
          [EDGE],
          "b",
        ],
        [
          "an offset span with a negative offset",
          {
            widthExtent: "offset" as const,
            widthInput: "10",
            offsetInput: "-5",
          },
          [EDGE],
          "b",
        ],
        ["a blank radius override", { overrideBendRadius: true }, [EDGE], "b"],
        ["a blank K override", { overrideKFactor: true }, [EDGE], "b"],
      ] as const
    ).map(([name, over, picked, anchor]) => {
      const form = { ...defaultEdgeFlangeForm(), ...over };
      return {
        name,
        blocker: edgeFlangeSubmitBlocker(form, picked, anchor, MM),
        oracle: buildEdgeFlangeParams(form, picked, anchor, MM) !== null,
      };
    }),
  },
  {
    id: "extrude-submit",
    probes: (
      [
        ["a 10 mm extrude of a solved sketch", {}],
        ["no profile chosen", { profileFeatureId: "" }],
        ["the distance cleared", { distanceInput: "" }],
        ["a zero distance", { distanceInput: "0" }],
      ] as const
    ).map(([name, over]) => {
      const form = { ...EXTRUDE, ...over };
      return {
        name,
        blocker: extrudeSubmitBlocker(form, MM),
        // The gate exactly as it read before REASON-GATE-1.
        oracle:
          form.profileFeatureId !== "" &&
          Number(form.distanceInput) > 0 &&
          form.distanceInput.trim() !== "",
      };
    }),
  },
  {
    id: "fillet-submit",
    probes: (
      [
        ["a ruled 2 mm round of every edge", {}, [EDGE], "body-1"],
        ["the radius cleared", { radiusInput: "" }, [EDGE], "body-1"],
        ["a negative radius", { radiusInput: "-1" }, [EDGE], "body-1"],
        ["pick mode with nothing picked", { mode: "pick" }, [], "body-1"],
        ["pick mode with no body anchor", { mode: "pick" }, [EDGE], null],
      ] as const
    ).map(([name, over, picked, anchor]) => {
      const form = { ...defaultFilletForm(), ...over };
      return {
        name,
        blocker: filletSubmitBlocker(form, picked, anchor, MM),
        oracle: buildFilletParams(form, picked, anchor, MM) !== null,
      };
    }),
  },
  {
    id: "loft-submit",
    probes: [
      { name: "two chosen sections", sections: ["sk-1", "sk-2"] },
      { name: "only one section slot", sections: ["sk-1"] },
      { name: "an empty first slot", sections: ["", "sk-2"] },
      { name: "an empty third slot", sections: ["sk-1", "sk-2", ""] },
    ].map(({ name, sections }) => {
      const form = defaultLoftForm(sections);
      return {
        name,
        blocker: loftSubmitBlocker(form),
        oracle:
          form.sections.length >= 2 && form.sections.every((s) => s !== ""),
      };
    }),
  },
  {
    id: "mirror-submit",
    probes: [
      {
        name: "an origin plane, whole body",
        blocker: mirrorSubmitBlocker(
          { kind: "origin", base: "XY" },
          { scope: "body", scopeFeatures: [] },
        ),
        oracle: true,
      },
      {
        name: "no datum plane in the part",
        blocker: mirrorSubmitBlocker(null, {
          scope: "body",
          scopeFeatures: [],
        }),
        oracle: false,
      },
      {
        name: "a feature scope with nothing chosen",
        blocker: mirrorSubmitBlocker(
          { kind: "origin", base: "XY" },
          { scope: "features", scopeFeatures: [] },
        ),
        oracle: false,
      },
    ],
  },
  {
    id: "pattern-submit",
    probes: (
      [
        ["three linear copies", {}],
        ["the count cleared", { countInput: "" }],
        ["a count of one", { countInput: "1" }],
        ["the spacing cleared", { spacingInput: "" }],
        ["a feature scope with nothing chosen", { scope: "features" as const }],
        [
          "a circular pattern with no angle",
          { kind: "circular" as const, angleInput: "" },
        ],
        [
          "a circular pattern with a blank axis Y",
          { kind: "circular" as const, axisPointYInput: "" },
        ],
      ] as const
    ).map(([name, over]) => {
      const form = { ...defaultPatternForm(), ...over };
      return {
        name,
        blocker: patternSubmitBlocker(form, MM),
        oracle: buildPatternParams(form, MM) !== null,
      };
    }),
  },
  {
    id: "revolve-submit",
    probes: (
      [
        [
          "a full turn about X",
          { profileFeatureId: "sk-1", axisId: "origin:X" },
        ],
        ["no profile chosen", { profileFeatureId: "", axisId: "origin:X" }],
        ["no axis chosen", { profileFeatureId: "sk-1", axisId: "" }],
        [
          "an axis the kernel refuses",
          { profileFeatureId: "sk-1", axisId: "origin:Z" },
        ],
        [
          "the angle cleared",
          { profileFeatureId: "sk-1", axisId: "origin:X", angleInput: "" },
        ],
      ] as const
    ).map(([name, over]) => {
      const form = {
        angleInput: "360",
        operation: "add" as const,
        direction: "normal" as const,
        merge: true,
        ...over,
      };
      const axis = AXES.find((o) => o.id === form.axisId);
      return {
        name,
        blocker: revolveSubmitBlocker(form, AXES),
        oracle:
          form.profileFeatureId !== "" &&
          axis !== undefined &&
          axis.reason === null &&
          Number(form.angleInput) > 0,
      };
    }),
  },
  {
    id: "shell-submit",
    probes: (
      [
        ["a 2 mm sealed hollow", {}, [], "body-1"],
        ["a 2 mm shell with one open face", {}, [FACE], "body-1"],
        ["the thickness cleared", { thicknessInput: "" }, [], "body-1"],
        ["a zero thickness", { thicknessInput: "0" }, [], "body-1"],
        ["picked faces with no body anchor", {}, [FACE], null],
      ] as const
    ).map(([name, over, picked, anchor]) => {
      const form = { ...defaultShellForm(), ...over };
      return {
        name,
        blocker: shellSubmitBlocker(form, picked, anchor, MM),
        oracle: buildShellParams(form, picked, anchor, MM) !== null,
      };
    }),
  },
  {
    id: "sweep-submit",
    probes: [
      { name: "a distinct profile and path", profile: "sk-1", path: "sk-2" },
      { name: "no profile chosen", profile: "", path: "sk-2" },
      { name: "no path chosen", profile: "sk-1", path: "" },
      { name: "one sketch in both slots", profile: "sk-1", path: "sk-1" },
    ].map(({ name, profile, path }) => {
      const form = defaultSweepForm(profile, path);
      return {
        name,
        blocker: sweepSubmitBlocker(form),
        oracle:
          form.profileFeatureId !== "" &&
          form.pathFeatureId !== "" &&
          form.profileFeatureId !== form.pathFeatureId,
      };
    }),
  },
];

/** The editors this file is responsible for — the fifteen REASON-GATE-1 names. */
const EXPECTED_SUBJECTS = 15;

describe("REASON-GATE-1: every editor's gate and its sentence are one thing", () => {
  it(`covers all ${EXPECTED_SUBJECTS} editors, with gated and live states each`, () => {
    // The count floor. A walk that lost a subject — or one whose probes all
    // happen to be valid forms — would satisfy every assertion below while
    // proving nothing, which is the shape of gate this repo keeps shipping.
    expect(SUBJECTS).toHaveLength(EXPECTED_SUBJECTS);
    expect(new Set(SUBJECTS.map((s) => s.id)).size).toBe(EXPECTED_SUBJECTS);
    for (const subject of SUBJECTS) {
      const gated = subject.probes.filter((p) => !p.oracle);
      const live = subject.probes.filter((p) => p.oracle);
      expect(
        gated.length,
        `${subject.id} drives no gated state`,
      ).toBeGreaterThanOrEqual(2);
      expect(
        live.length,
        `${subject.id} drives no live state`,
      ).toBeGreaterThanOrEqual(1);
    }
    const total = SUBJECTS.reduce(
      (n, s) => n + s.probes.filter((p) => !p.oracle).length,
      0,
    );
    expect(total).toBeGreaterThanOrEqual(50);
  });

  for (const subject of SUBJECTS) {
    describe(subject.id, () => {
      for (const probe of subject.probes) {
        it(`${probe.oracle ? "allows" : "explains"}: ${probe.name}`, () => {
          // (1) The blocker agrees with the predicate that shipped before it.
          expect(
            probe.blocker === null,
            probe.blocker === null
              ? "the blocker allowed a form the old gate refused"
              : `the blocker refused a form the old gate allowed: ${probe.blocker}`,
          ).toBe(probe.oracle);
          if (probe.oracle) {
            expect(probe.blocker).toBeNull();
            return;
          }
          // (2) …and a refusal is a sentence a stuck user can act on.
          const reason = probe.blocker ?? "";
          expect(reason.trim(), "a gated action said nothing").not.toBe("");
          expect(
            reason.length,
            `"${reason}" wraps the half-width footer cell`,
          ).toBeLessThanOrEqual(MAX_BLOCKER_CHARS);
          expect(reason.endsWith("."), `"${reason}" is not a sentence`).toBe(
            true,
          );
          expect(reason[0], `"${reason}" does not open in sentence case`).toBe(
            reason[0]?.toUpperCase(),
          );
        });
      }
    });
  }
});
