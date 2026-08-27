/**
 * THE DIMENSION CELL BELONGS TO THE BROWSER (DIM-1).
 *
 * The founder's report — "I still cannot click dimension and actually have it
 * assign a dimension" — had a second cause behind the dead-end verb: the value
 * cell was CONTROLLED, so React restored the input's text from a render that
 * predated the keystroke and the number never went in. Measured in the real
 * browser on the pre-fix build, typing "125" over a pre-filled "43": the cell
 * ended at "43" at 0/20/40/60/80 ms per key, and "435" for "25" over "43" —
 * only surviving from 120 ms/key.
 *
 * ## What this file can and cannot gate
 *
 * It CANNOT gate the timing. jsdom renders synchronously and in microseconds,
 * so a "type three characters fast" test passes with the defect present — an
 * assertion that cannot fail is not a gate, so it is not written here. The
 * per-keystroke path is gated where the latency is real, in
 * `e2e/sketch-dimension-pick.spec.ts` (`pressSequentially`, 60 ms and 0 ms/key,
 * both measured RED before this fix).
 *
 * What it CAN gate — and what the e2e cannot say precisely — is the MECHANISM:
 * that the DOM's text survives a React render it does not know about, and that
 * a commit reads the cell rather than React's shadow of it. That is the exact
 * shape of the defect, expressed as an invariant instead of a race.
 */
// `act` from Testing Library, not from react: it sets the act environment flag
// as well, so a store update here does not warn on every case.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConstraintGlyphs } from "./ConstraintGlyphs";
import { PLANE_BASES } from "../sketch/plane";
import { useSketchStore } from "../sketch/store";
import type { DimensionEditorTarget } from "../sketch/constraints";

// drei's `Html` needs an r3f root, and a canvas needs WebGL jsdom does not
// have. The editors under test are ordinary DOM inside it, so the portal is
// all that has to be stood in for.
vi.mock("@react-three/drei", () => ({
  Html: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));

const distanceOn = (
  entity: string,
  valueMm: number,
): DimensionEditorTarget => ({
  kind: "distance",
  entity,
  entityB: null,
  noun: "Distance",
  unit: "mm",
  initialValue: valueMm,
  initialExpression: null,
  initialName: null,
  initialDriving: true,
  // The founder's own case: a line picked with the Dimension verb, dimensioned
  // for the first time, so the commit APPENDS rather than replacing.
  constraintIndex: null,
});

const openEditor = (target: DimensionEditorTarget) =>
  act(() => {
    useSketchStore.setState({ dimensionEdit: target });
  });

/** The cell, as the app's own test hook finds it. */
const cell = () => screen.getByTestId<HTMLInputElement>("dimension-input");

/**
 * A keystroke the BROWSER has already applied and React has not yet heard
 * about — the window the defect lived in. Deliberately does NOT fire `input`:
 * that is the whole point, and firing it would be testing a different thing.
 */
const typeAheadOfReact = (text: string) => {
  cell().value = text;
};

/** Any unrelated re-render of the editor — a solve landing, say. */
const reRender = () =>
  act(() => {
    useSketchStore.setState({
      solvedDimensions: [{ constraint_index: 0, value_mm: 43, driving: true }],
    });
  });

const reset = () =>
  useSketchStore.setState({
    dimensionEdit: null,
    constraints: [],
    entities: [],
    solvedDimensions: [],
    revision: 0,
  });

describe("the dimension editor's value cell", () => {
  beforeEach(reset);
  afterEach(reset);

  it("keeps text React has not seen — a render cannot overwrite the typist", () => {
    render(<ConstraintGlyphs basis={PLANE_BASES.XY} />);
    openEditor(distanceOn("e1", 43));
    expect(cell().value).toBe("43");

    typeAheadOfReact("125");
    reRender();

    // Controlled, this read "43": React re-applied the value it last rendered.
    expect(cell().value).toBe("125");
  });

  it("commits what the cell holds, not what React last rendered", () => {
    render(<ConstraintGlyphs basis={PLANE_BASES.XY} />);
    openEditor(distanceOn("e1", 43));

    typeAheadOfReact("125");
    fireEvent.click(screen.getByTestId("dimension-apply"));

    // The number that reaches the solver is the number that was typed.
    expect(useSketchStore.getState().constraints).toEqual([
      {
        kind: "distance",
        entity: "e1",
        value_mm: 125,
        expression: null,
        name: null,
        driving: null,
      },
    ]);
    expect(useSketchStore.getState().dimensionEdit).toBeNull();
  });

  it("re-prefills when the editor retargets, even mid-edit", () => {
    render(<ConstraintGlyphs basis={PLANE_BASES.XY} />);
    openEditor(distanceOn("e1", 43));
    typeAheadOfReact("125");

    // Click a second dimension's glyph without closing the first: the editor
    // stays mounted and only its target changes. An input the user has typed
    // into is DIRTY, and a dirty input ignores its value attribute — so without
    // a remount the second dimension would open showing the first one's text.
    openEditor(distanceOn("e2", 27));

    expect(cell().value).toBe("27");
  });

  it("refuses an empty value instead of silently discarding the edit", () => {
    render(<ConstraintGlyphs basis={PLANE_BASES.XY} />);
    openEditor(distanceOn("e1", 43));

    typeAheadOfReact("");
    fireEvent.click(screen.getByTestId("dimension-apply"));

    // Applying an unusable value used to fall through to cancelDimension() —
    // the same key sometimes saving and sometimes discarding (FB-13). It now
    // holds the editor open and says why.
    expect(useSketchStore.getState().dimensionEdit).not.toBeNull();
    expect(useSketchStore.getState().constraints).toEqual([]);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter a value or an expression.",
    );
  });
});
