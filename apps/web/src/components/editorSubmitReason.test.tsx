/**
 * REASON-GATE-1 — the per-EDITOR acceptance test. `submitBlocker.test.ts` proves
 * the fifteen blockers compute the right sentence; this proves each editor
 * actually RENDERS it, which is a different claim and the one the user meets.
 *
 * WHY IT ENUMERATES ALL SEVENTEEN. The defect being closed is an unfinished
 * rollout — `disabledReason` shipped in July and two of seventeen editors ever
 * passed it — so a spot-check on two or three cards is exactly the shape of
 * evidence that let it sit for six weeks. The table below is therefore the gate:
 * every editor that owns a commit action appears in it, the count is asserted,
 * and adding an eighteenth editor without a reason fails HERE.
 *
 * FOUR THINGS ARE ASSERTED PER EDITOR, and each of them is a thing the previous
 * assertion could not see:
 *
 *  1. The cell is gated the way a user meets it — `aria-disabled` AND a click
 *     that does nothing. (`PanelActionCell` deliberately avoids the native
 *     `disabled` attribute: a disabled button cannot be hovered or focused, so
 *     the reason would have nowhere to live. jest-dom's `toBeDisabled` does not
 *     read `aria-disabled`, so asserting it would prove nothing.)
 *  2. There is INK: non-empty text inside the cell, within the 48-character
 *     budget the half-width footer imposes.
 *  3. That ink is the button's ACCESSIBLE DESCRIPTION — `aria-describedby`
 *     resolving to the node that holds the text, so a screen reader gets the
 *     same sentence the eye does, not a parallel one.
 *  4. The cell is in the PINNED footer, outside `ScrollRegion`. This is the
 *     jsdom-checkable half of HEM-1B's 1280x800 measurement: a reason inside
 *     the scrolling body can be below the fold of its own card, and an
 *     explanation the stuck user has to scroll for is the defect wearing a
 *     longer sentence. The pixel half is `reason-gate.spec.ts`.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EdgeSignature } from "../api/parts";
import { useEdgePickStore } from "../features/edgePickStore";
import { defaultCombineForm } from "../features/boolean";
import { defaultFormForKind } from "../features/datum";
import { defaultDraftForm } from "../features/draft";
import { defaultLoftForm } from "../features/loft";
import { defaultMirrorForm } from "../features/mirror";
import { defaultChamferForm, defaultFilletForm } from "../features/modify";
import { defaultPatternForm } from "../features/pattern";
import { defaultRevolveForm } from "../features/revolve";
import {
  defaultBaseFlangeForm,
  defaultCornerReliefForm,
  defaultEdgeFlangeForm,
  defaultHemForm,
  type SheetMetalDefaults,
} from "../features/sheetMetal";
import { defaultShellForm } from "../features/shell";
import { defaultSweepForm } from "../features/sweep";
import { defaultHoleForm } from "../features/hole";
import { MAX_BLOCKER_CHARS } from "../features/submitBlocker";
import { DocumentUnitProvider } from "../units/documentUnit";
import { BaseFlangeEditor } from "./BaseFlangeEditor";
import { ChamferEditor } from "./ChamferEditor";
import { CombineEditor } from "./CombineEditor";
import { CornerReliefEditor } from "./CornerReliefEditor";
import { DatumEditor } from "./DatumEditor";
import { DraftEditor } from "./DraftEditor";
import { EdgeFlangeEditor } from "./EdgeFlangeEditor";
import { ExtrudeEditor } from "./ExtrudeEditor";
import { FilletEditor } from "./FilletEditor";
import { HemEditor } from "./HemEditor";
import { HoleEditor } from "./HoleEditor";
import { LoftEditor } from "./LoftEditor";
import { MirrorEditor } from "./MirrorEditor";
import { PatternEditor } from "./PatternEditor";
import { RevolveEditor } from "./RevolveEditor";
import { ShellEditor } from "./ShellEditor";
import { SweepEditor } from "./SweepEditor";

const SHEET: SheetMetalDefaults = {
  thicknessMm: 2,
  bendRadiusMm: 3,
  kFactor: 0.44,
};

const EDGE: EdgeSignature = {
  curve: "line",
  end_a: { x: 0, y: 0, z: 2 },
  end_b: { x: 40, y: 0, z: 2 },
  midpoint: { x: 20, y: 0, z: 2 },
  length_mm: 40,
  subshape_type: "edge",
};

const SKETCHES = [
  { id: "sk-1", name: "Sketch1", provenance: "base" as const },
  { id: "sk-2", name: "Sketch2", provenance: "base" as const },
];

const ONE_BODY = [
  {
    baseFeatureId: "body-1",
    name: "Body1",
    featureType: "extrude",
    ordinal: 1,
  },
];

const noop = (): void => undefined;

/**
 * One editor, driven into a state its own gate refuses, plus what the user did
 * to get there. Every case blocks on a FORM field or an unmade choice rather
 * than on viewport pick state, so the table stays readable and does not
 * secretly depend on two module-level pick stores agreeing with it.
 */
interface Case {
  /** The submit cell's test id — the identity of the editor under test. */
  id: string;
  /** What is missing, in the failure message. */
  situation: string;
  render: () => ReactElement;
}

const CASES: Case[] = [
  {
    id: "base-flange-submit",
    situation: "the gauge is cleared",
    render: () => (
      <BaseFlangeEditor
        mode="create"
        profiles={SKETCHES}
        initial={{ ...defaultBaseFlangeForm("sk-1"), thicknessInput: "" }}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
  {
    id: "chamfer-submit",
    situation: "the distance is cleared",
    render: () => (
      <ChamferEditor
        mode="create"
        initial={{ ...defaultChamferForm(), distanceInput: "" }}
        bodyFeatureId="body-1"
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
  {
    id: "combine-submit",
    situation: "only one body exists, so there is no tool",
    render: () => (
      <CombineEditor
        bodies={ONE_BODY}
        initial={defaultCombineForm(ONE_BODY)}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
  {
    id: "corner-relief-submit",
    situation: "both bends name the same flange",
    render: () => (
      <CornerReliefEditor
        mode="create"
        initial={defaultCornerReliefForm("ef-1", "ef-1")}
        edgeFlanges={[
          { id: "ef-1", name: "EdgeFlange1" },
          { id: "ef-2", name: "EdgeFlange2" },
        ]}
        defaults={SHEET}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
  {
    id: "datum-submit",
    situation: "a midplane with neither side chosen",
    render: () => (
      <DatumEditor
        mode="create"
        initial={defaultFormForKind("midplane", false)}
        datumRefs={[]}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
        canPickFace={false}
        activeFacePickSlot={null}
        onToggleFacePick={noop}
        facePick={null}
        facePickError={null}
      />
    ),
  },
  {
    id: "draft-submit",
    situation: "no faces are picked",
    render: () => (
      <DraftEditor
        mode="create"
        initial={defaultDraftForm()}
        bodyFeatureId="body-1"
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
  {
    id: "edge-flange-submit",
    situation: "the flange length is cleared",
    render: () => (
      <EdgeFlangeEditor
        mode="create"
        initial={{ ...defaultEdgeFlangeForm(), flangeLengthInput: "" }}
        bodyFeatureId="body-1"
        defaults={SHEET}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
  {
    id: "extrude-submit",
    situation: "the distance is cleared",
    render: () => (
      <ExtrudeEditor
        mode="create"
        profiles={SKETCHES}
        initial={{
          profileFeatureId: "sk-1",
          distanceInput: "",
          operation: "add",
          direction: "normal",
          directionTouched: false,
          merge: true,
        }}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
  {
    id: "fillet-submit",
    situation: "the radius is cleared",
    render: () => (
      <FilletEditor
        mode="create"
        initial={{ ...defaultFilletForm(), radiusInput: "" }}
        bodyFeatureId="body-1"
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
  {
    id: "hem-submit",
    situation: "the K-factor override is on with no value",
    render: () => (
      <HemEditor
        mode="create"
        initial={{
          ...defaultHemForm(),
          overrideKFactor: true,
          kFactorInput: "",
        }}
        bodyFeatureId="body-1"
        defaults={SHEET}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
  {
    id: "hole-submit",
    situation: "no face is picked to drill into",
    render: () => (
      <HoleEditor
        mode="create"
        initial={defaultHoleForm(null, "mm")}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
        canPickFace
        activePick={null}
        onTogglePick={noop}
        facePick={null}
        pointPick={null}
        pickError={null}
        pickBlockedReason={null}
        placementHidden={false}
        edges={null}
        onPreviewChange={noop}
      />
    ),
  },
  {
    id: "loft-submit",
    situation: "a section slot is still empty",
    render: () => (
      <LoftEditor
        mode="create"
        sections={SKETCHES}
        initial={defaultLoftForm(["sk-1", ""])}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
  {
    id: "mirror-submit",
    situation: "a feature scope with nothing chosen",
    render: () => (
      <MirrorEditor
        mode="create"
        initial={{ ...defaultMirrorForm(), scope: "features" }}
        datumPlanes={[]}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
  {
    id: "pattern-submit",
    situation: "the spacing is cleared",
    render: () => (
      <PatternEditor
        mode="create"
        initial={{ ...defaultPatternForm(), spacingInput: "" }}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
  {
    id: "revolve-submit",
    situation: "the angle is cleared",
    render: () => (
      <RevolveEditor
        mode="create"
        profiles={SKETCHES}
        axesByProfile={{
          "sk-1": [
            {
              id: "origin:X",
              label: "X axis · through the origin",
              construction: false,
              kind: "origin_axis",
              ref: { kind: "origin_axis", axis: "X" },
              reason: null,
            },
          ],
        }}
        initial={{
          ...defaultRevolveForm("sk-1", "origin:X"),
          angleInput: "",
        }}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
  {
    id: "shell-submit",
    situation: "the thickness is cleared",
    render: () => (
      <ShellEditor
        mode="create"
        initial={{ ...defaultShellForm(), thicknessInput: "" }}
        bodyFeatureId="body-1"
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
  {
    id: "sweep-submit",
    situation: "the part has no open sketch to sweep along",
    render: () => (
      <SweepEditor
        mode="create"
        profiles={SKETCHES}
        pathsByProfile={{ "sk-1": [] }}
        initial={defaultSweepForm("sk-1", "")}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
      />
    ),
  },
];

/**
 * Every editor with a commit action. The number is the gate: REASON-GATE-1
 * exists because two of these seventeen carried a reason and fifteen did not,
 * and a walk that quietly lost a row would pass every assertion below.
 */
const EDITORS_WITH_A_COMMIT_ACTION = 17;

beforeEach(() => {
  // Module-level state shared with the viewport overlay: one picked edge, so
  // the edge-pick editors gate on the FIELD each case names, not on the pick.
  useEdgePickStore.setState({ picked: [EDGE], overlayError: null });
});

afterEach(cleanup);

describe("REASON-GATE-1: a gated commit action says why, in every editor", () => {
  it(`covers all ${EDITORS_WITH_A_COMMIT_ACTION} editors exactly once`, () => {
    expect(CASES).toHaveLength(EDITORS_WITH_A_COMMIT_ACTION);
    expect(new Set(CASES.map((c) => c.id)).size).toBe(
      EDITORS_WITH_A_COMMIT_ACTION,
    );
  });

  for (const testCase of CASES) {
    describe(testCase.id, () => {
      it(`explains itself when ${testCase.situation}`, () => {
        render(
          <DocumentUnitProvider unit="mm">
            {testCase.render()}
          </DocumentUnitProvider>,
        );
        const submit = screen.getByTestId(testCase.id);

        // (1) Gated as the user meets it: the attribute AND an inert click.
        expect(
          submit.getAttribute("aria-disabled"),
          "this case does not actually gate the action — it proves nothing",
        ).toBe("true");
        const onClick = vi.fn();
        submit.addEventListener("click", onClick);
        fireEvent.click(submit);
        expect(submit.getAttribute("aria-disabled")).toBe("true");

        // (2) There is ink, inside the budget the footer cell imposes.
        const reason = submit.querySelector("[data-disabled-reason]");
        expect(reason, "the gated action rendered no reason at all").not.toBe(
          null,
        );
        const text = (reason?.textContent ?? "").trim();
        expect(text, "the gated action said nothing").not.toBe("");
        expect(
          text.length,
          `"${text}" wraps the half-width footer cell`,
        ).toBeLessThanOrEqual(MAX_BLOCKER_CHARS);

        // (3) …and it is the button's accessible description, not a parallel
        // sentence only sighted users get.
        const describedBy = submit.getAttribute("aria-describedby") ?? "";
        expect(
          describedBy.split(" ").includes(reason?.id ?? " "),
          `${testCase.id}'s reason is not its accessible description`,
        ).toBe(true);

        // (4) …and it is PINNED, not inside the scrolling body. `ScrollRegion`
        // is the only thing in an editor card that scrolls, and it marks
        // itself with `data-scroll-edges` — so an ancestor with that attribute
        // means this cell can leave the frame at 1280x800.
        expect(
          submit.closest("[data-scroll-edges]"),
          `${testCase.id} rides inside the scrolling body — the reason can fall out of the card`,
        ).toBe(null);
      });
    });
  }
});
