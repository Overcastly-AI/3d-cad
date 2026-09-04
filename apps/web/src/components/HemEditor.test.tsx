/**
 * HemEditor — the DOM half of HEM-1C/HEM-1D: does the card state numbers the
 * evaluator ACCEPTS, and can a user reach both hem shapes?
 *
 * The defect this file locks out was a sentence, not a computation. `HemEditor`
 * hinted "A tight closed hem uses a small radius (≈1 mm)" on 2 mm sheet —
 * `Math.round(thickness * 5) / 10`, i.e. 0.5 x gauge, which is the OPEN ratio —
 * so the product's own guidance named the one value a closed hem is refused for
 * (`hem_type_radius_conflict`), and kept naming it in the EDIT form after the
 * refusal. Nothing could catch that: `buildHemParams` was correct, the unit
 * suite was green, and the string was never rendered by a test.
 *
 * So the assertion here is a PROPERTY, not a golden string: every number the
 * radius guidance names must be a radius the evaluator accepts for the chosen
 * type. The band is restated as literals (0.25 mm ceiling on 2 mm gauge) rather
 * than imported — guidance checked against the code that produced it could not
 * fail.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EdgeSignature, SheetMetalHemParams } from "../api/parts";
import { useEdgePickStore } from "../features/edgePickStore";
import {
  defaultHemForm,
  type HemForm,
  type SheetMetalDefaults,
} from "../features/sheetMetal";
import { DocumentUnitProvider } from "../units/documentUnit";
import { HemEditor } from "./HemEditor";

/** The HEM-1 fixture: 2 mm gauge under a 3 mm GENERAL part bend radius. */
const DEFAULTS: SheetMetalDefaults = {
  thicknessMm: 2,
  bendRadiusMm: 3,
  kFactor: 0.44,
};

/** The closed/open boundary on this gauge (0.125 x 2 mm) — restated, not imported. */
const BOUNDARY_MM = 0.25;

const SIG: EdgeSignature = {
  curve: "line",
  end_a: { x: 0, y: 0, z: 2 },
  end_b: { x: 50, y: 0, z: 2 },
  midpoint: { x: 25, y: 0, z: 2 },
  length_mm: 50,
  subshape_type: "edge",
};

function renderEditor(
  overrides: {
    initial?: HemForm;
    defaults?: SheetMetalDefaults | null;
  } = {},
) {
  const onSubmit = vi.fn<(params: SheetMetalHemParams) => void>();
  render(
    <DocumentUnitProvider unit="mm">
      <HemEditor
        mode="create"
        initial={overrides.initial ?? defaultHemForm()}
        bodyFeatureId="bf"
        defaults={
          overrides.defaults === undefined ? DEFAULTS : overrides.defaults
        }
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        saving={false}
        error={null}
      />
    </DocumentUnitProvider>,
  );
  return { onSubmit };
}

/** Every number in a string, as numbers — the reading a user does. */
function numbersIn(text: string): number[] {
  return (text.match(/\d+(?:\.\d+)?/g) ?? []).map(Number);
}

/** The guidance shown under the (checked) radius override. */
function radiusGuidance(): string {
  return screen.getByTestId("hem-override-radius").textContent ?? "";
}

beforeEach(() => {
  // The pick store is module-level state shared with the viewport overlay.
  useEdgePickStore.setState({ picked: [SIG], overlayError: null });
});

describe("the radius guidance names values the evaluator accepts", () => {
  it("suggests only radii a CLOSED hem can take", () => {
    renderEditor();
    fireEvent.click(screen.getByTestId("hem-override-radius"));
    const named = numbersIn(radiusGuidance());
    // Non-vacuous: guidance that named no number would pass the loop below.
    expect(named.length).toBeGreaterThan(0);
    for (const value of named) {
      expect(
        value,
        `the card offers ${value} mm, which a closed hem is refused for`,
      ).toBeLessThanOrEqual(BOUNDARY_MM);
      expect(value).toBeGreaterThan(0);
    }
    // …and it names the flat-pressed default, so the hint is usable as typed.
    expect(named).toContain(0.1);
  });

  it("suggests only radii an OPEN hem can take", () => {
    renderEditor({ initial: { ...defaultHemForm(), hemType: "open" } });
    fireEvent.click(screen.getByTestId("hem-override-radius"));
    const named = numbersIn(radiusGuidance());
    expect(named.length).toBeGreaterThan(0);
    for (const value of named) {
      expect(value).toBeGreaterThanOrEqual(BOUNDARY_MM);
    }
    expect(named).toContain(1);
  });

  it("never claims the radius is inherited from the base flange", () => {
    renderEditor();
    const radius = screen.getByTestId("hem-override-radius");
    // The false string HEM-1C reported, verbatim in shape: "Inherits 3 mm from
    // the base flange." The part's 3 mm die-bend radius has no business here.
    expect(radius.textContent).not.toMatch(/base flange/i);
    expect(radius.textContent).not.toMatch(/\b3 mm\b/);
    expect(radius.textContent).toMatch(/0\.1 mm/);
    // K-factor is the CONTROL: it IS still inherited (a material property), so
    // a change that "tidied" both would be caught here.
    expect(screen.getByTestId("hem-override-k").textContent).toMatch(
      /Inherits 0\.44 from the base flange/,
    );
  });
});

describe("the gap readout", () => {
  it("reads 0.1 x gauge closed and 1 x gauge open", () => {
    renderEditor();
    expect(screen.getByTestId("hem-gap-readout")).toHaveTextContent(
      "0.2 mm (0.1 × gauge)",
    );
    fireEvent.click(screen.getByTestId("hem-type-open"));
    expect(screen.getByTestId("hem-gap-readout")).toHaveTextContent(
      "2 mm (1 × gauge)",
    );
    expect(screen.getByTestId("hem-fold-readout")).toHaveTextContent(
      "180° (open)",
    );
  });

  it("tracks an override — the gap is exactly twice the radius", () => {
    renderEditor();
    fireEvent.click(screen.getByTestId("hem-override-radius"));
    fireEvent.change(screen.getByTestId("hem-bend-radius"), {
      target: { value: "0.2" },
    });
    expect(screen.getByTestId("hem-gap-readout")).toHaveTextContent(
      "0.4 mm (0.2 × gauge)",
    );
  });

  it("says nothing rather than guessing when there is no gauge", () => {
    renderEditor({ defaults: null });
    expect(screen.getByTestId("hem-gap-readout")).toHaveTextContent("—");
  });
});

describe("the hem type is authorable (HEM-1D)", () => {
  it("publishes the chosen type", () => {
    const { onSubmit } = renderEditor();
    fireEvent.click(screen.getByTestId("hem-type-open"));
    fireEvent.click(screen.getByTestId("hem-submit"));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0]?.[0]?.hem_type).toBe("open");
  });

  it("offers exactly the two shapes this fold can build", () => {
    renderEditor();
    const group = screen.getByRole("group", { name: "Type" });
    const labels = within(group)
      .getAllByRole("button")
      .map((b) => b.textContent);
    expect(labels).toEqual(["Closed", "Open"]);
    // teardrop/rolled wrap past 180°: naming them would be the HEM-1 defect in
    // the other direction (a label the fold cannot honour).
    expect(group.textContent).not.toMatch(/teardrop|rolled/i);
  });
});

describe("a conflicting radius is stated before the rebuild, not enforced", () => {
  it("names the gap and the one-click fix", () => {
    renderEditor();
    fireEvent.click(screen.getByTestId("hem-override-radius"));
    fireEvent.change(screen.getByTestId("hem-bend-radius"), {
      target: { value: "1" },
    });
    const note = screen.getByTestId("hem-radius-conflict");
    expect(note).toHaveTextContent("2 mm gap");
    expect(note).toHaveTextContent("Switch the type to Open");
    expect(note).toHaveTextContent("at most 0.25 mm");
    // Advisory: the evaluator owns the rule, so Save stays live and the typed
    // `hem_type_radius_conflict` remains the gate (a mirror that drifted must
    // cost a wrong sentence, never a lockout on a legal value).
    expect(screen.getByTestId("hem-submit")).not.toBeDisabled();
    // Switching the type resolves it — the fix the sentence names.
    fireEvent.click(screen.getByTestId("hem-type-open"));
    expect(screen.queryByTestId("hem-radius-conflict")).toBe(null);
  });

  it("stays quiet on a radius that agrees with the type", () => {
    renderEditor();
    fireEvent.click(screen.getByTestId("hem-override-radius"));
    fireEvent.change(screen.getByTestId("hem-bend-radius"), {
      target: { value: String(BOUNDARY_MM) },
    });
    expect(screen.queryByTestId("hem-radius-conflict")).toBe(null);
  });
});
