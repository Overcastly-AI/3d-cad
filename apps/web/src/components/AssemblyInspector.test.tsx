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

import type {
  EvaluateAssemblyResult,
  InstanceResponse,
} from "../api/assemblies";
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

/** An instance row as the graph stores it — only `id`/`name` matter here. */
function instance(id: string, name: string): InstanceResponse {
  return {
    id,
    assembly_id: "a1",
    name,
    ref_document_id: "p1",
    ref_document_kind: "part",
    ref_pinned_version: null,
    order_index: 0,
    grounded: false,
    placement: {
      position: { x: 0, y: 0, z: 0 },
      orientation: { x: 0, y: 0, z: 0, w: 1 },
    },
    created_at: "2026-07-30T09:00:00Z",
    updated_at: "2026-07-30T09:00:00Z",
  };
}

/** The evaluation above, plus per-instance masses (null = no material). */
function weighed(
  total: number | null,
  per: readonly (number | null)[],
): EvaluateAssemblyResult {
  const base = evaluation();
  const one = base.properties;
  if (one === undefined || one === null) throw new Error("fixture");
  return {
    ...base,
    properties: {
      ...one,
      mass_g: total,
      center_of_mass: total === null ? null : { x: 12.7, y: 25.4, z: 0 },
    },
    instances: per.map((mass, i) => ({
      instance_id: `i${i + 1}`,
      part_mesh_glb_id: "sha256:abc",
      placement: {
        position: { x: 0, y: 0, z: 0 },
        orientation: { x: 0, y: 0, z: 0, w: 1 },
      },
      properties: { ...one, mass_g: mass },
    })),
  };
}

function renderMass(
  unit: LengthUnit,
  total: number | null,
  per: readonly (number | null)[],
) {
  return render(
    <DocumentUnitProvider unit={unit}>
      <AssemblyInspector
        evaluation={weighed(total, per)}
        evaluating={false}
        instances={[instance("i1", "Housing"), instance("i2", "Pin")]}
      />
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

/**
 * The section used to be TITLED "Combined mass" over Volume / Area / Centroid —
 * the part inspector's #57b defect at a second address. These assert the title
 * is earned, that absence is absence (never `0 g`), and that the panel names the
 * component the roll-up could not weigh.
 */
describe("AssemblyInspector — the combined-mass claim", () => {
  it("earns the words COMBINED MASS only when a mass exists", () => {
    renderMass("mm", 84.56, [27, 57.56]);
    const panel = screen.getByLabelText("Assembly inspector");
    expect(within(panel).getByText("Combined mass")).toBeInTheDocument();
    const mass = screen.getByTestId("assembly-mass");
    expect(mass).toHaveTextContent("84.56");
    expect(mass).toHaveTextContent("g");
    expect(screen.queryByTestId("assembly-mass-notice")).toBeNull();
  });

  it("drops the title and the row when the roll-up has no mass", () => {
    renderMass("mm", null, [27, null]);
    const panel = screen.getByLabelText("Assembly inspector");
    expect(within(panel).queryByText("Combined mass")).toBeNull();
    expect(within(panel).getByText("Combined properties")).toBeInTheDocument();
    // Absence is absence — the one thing it must never be is a zero.
    expect(screen.queryByTestId("assembly-mass")).toBeNull();
    expect(panel).not.toHaveTextContent("0 g");
    // ...and the volume/area/centroid it CAN report are still there.
    expect(screen.getByTestId("assembly-volume")).toHaveTextContent(
      "31,391.38",
    );
  });

  it("names the component that has no material", () => {
    renderMass("mm", null, [27, null]);
    expect(screen.getByTestId("assembly-mass-notice")).toHaveTextContent(
      "Pin has no material, so the assembly has no total mass.",
    );
  });

  it("converts the total through the one units seam", () => {
    renderMass("in", 453.59237, [453.59237]);
    const mass = screen.getByTestId("assembly-mass");
    expect(mass).toHaveTextContent("1");
    expect(mass).toHaveTextContent("lb");
    expect(mass).not.toHaveTextContent("453");
  });

  it("shows the centre of MASS apart from the centroid", () => {
    renderMass("mm", 84.56, [27, 57.56]);
    expect(screen.getByTestId("assembly-center-of-mass")).toHaveTextContent(
      "12.7, 25.4, 0",
    );
    expect(screen.getByTestId("assembly-centroid")).toHaveTextContent(
      "25.4, 50.8, 0",
    );
  });

  it("says nothing about mass before the first solve", () => {
    render(
      <DocumentUnitProvider unit="mm">
        <AssemblyInspector evaluation={undefined} evaluating={false} />
      </DocumentUnitProvider>,
    );
    expect(screen.queryByTestId("assembly-mass")).toBeNull();
    expect(screen.queryByTestId("assembly-mass-notice")).toBeNull();
  });
});
