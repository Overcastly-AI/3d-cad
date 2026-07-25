/**
 * AssemblyInspector — does the panel render the unit it was GIVEN?
 *
 * FINDINGS burn-down 2026-07-25 #7 shipped with zero coverage at this tier: the
 * panel hardcoded `mm³`/`mm²`/`mm` label strings while the page above it already
 * supplied a document unit, so an inch assembly read `18,429.2 mm³` — the value
 * unconverted and the label wrong. The pure projection (`assemblyReadout`) had
 * unit tests; the COMPONENT that had to call it did not, and that is exactly
 * where the defect lived. These render the panel through the real
 * `DocumentUnitProvider` and assert the numbers + unit labels a user reads, so
 * a future panel that stops consulting the context fails here instead of in a
 * 40-minute e2e run (or in front of the founder).
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { EvaluateAssemblyResult } from "../api/assemblies";
import { DocumentUnitProvider } from "../units/documentUnit";
import { AssemblyInspector } from "./AssemblyInspector";
import type { LengthUnit } from "@loft/design";

/** A solved 25.4 × 50.8 × 76.2 mm assembly — round inches, so both readings
 *  below are exact and a conversion slip is unmistakable. */
function evaluation(): EvaluateAssemblyResult {
  return {
    assembly_id: "a1",
    version: 1,
    status: "well_constrained",
    instances: [],
    properties: {
      volume: 31391.38,
      surface_area: 6451.6,
      centroid: { x: 25.4, y: 50.8, z: 0 },
      bounding_box: {
        min: { x: 0, y: 0, z: 0 },
        max: { x: 25.4, y: 50.8, z: 76.2 },
      },
      topology: { faces: 6, edges: 12, shells: 1 },
    },
    bounding_box: {
      min: { x: 0, y: 0, z: 0 },
      max: { x: 25.4, y: 50.8, z: 76.2 },
    },
  };
}

function renderInspector(unit: LengthUnit, evaluating = false) {
  return render(
    <DocumentUnitProvider unit={unit}>
      <AssemblyInspector evaluation={evaluation()} evaluating={evaluating} />
    </DocumentUnitProvider>,
  );
}

describe("AssemblyInspector", () => {
  it("renders millimetre readouts unchanged in an mm assembly", () => {
    renderInspector("mm");
    const volume = screen.getByTestId("assembly-volume");
    expect(volume).toHaveTextContent("31,391.38");
    expect(volume).toHaveTextContent("mm³");
    expect(screen.getByTestId("assembly-extents")).toHaveTextContent(
      "25.4 × 50.8 × 76.2",
    );
    expect(screen.getByTestId("assembly-extents")).toHaveTextContent("mm");
  });

  it("converts every readout to the document unit in an inch assembly", () => {
    renderInspector("in");
    const volume = screen.getByTestId("assembly-volume");
    expect(volume).toHaveTextContent("1.9156");
    expect(volume).toHaveTextContent("in³");
    // The regression that shipped: a converted-looking panel still stamped mm.
    expect(volume).not.toHaveTextContent("mm");

    const centroid = screen.getByTestId("assembly-centroid");
    expect(centroid).toHaveTextContent("1, 2, 0");
    expect(centroid).toHaveTextContent("in");

    const extents = screen.getByTestId("assembly-extents");
    expect(extents).toHaveTextContent("1 × 2 × 3");
    expect(extents).not.toHaveTextContent("mm");
  });

  it("labels the area cell in the document unit squared", () => {
    renderInspector("in");
    const area = screen.getByLabelText("Assembly inspector");
    expect(within(area).getByText("in²")).toBeInTheDocument();
    expect(within(area).queryByText("mm²")).not.toBeInTheDocument();
  });

  it("reads the typed solve status, not a parsed message", () => {
    renderInspector("mm");
    expect(screen.getByTestId("assembly-solve-status")).toHaveTextContent(
      "Well constrained",
    );
  });

  it("says it is solving while an evaluation is in flight", () => {
    renderInspector("mm", true);
    expect(screen.getByTestId("assembly-solve-status")).toHaveTextContent(
      "Solving",
    );
  });

  it("shows an em dash instead of stale numbers before the first solve", () => {
    render(
      <DocumentUnitProvider unit="in">
        <AssemblyInspector evaluation={undefined} evaluating={false} />
      </DocumentUnitProvider>,
    );
    expect(screen.getByTestId("assembly-volume")).toHaveTextContent("—");
    expect(screen.getByTestId("assembly-extents")).toHaveTextContent("—");
  });
});
