/**
 * BodyInspector — the part title block, tested as the SIBLING of
 * `AssemblyInspector`.
 *
 * FINDINGS burn-down 2026-07-25 #7 was a drift defect: the part panel honoured
 * the document unit and the assembly panel silently did not, so one product
 * spoke two conventions and the same solid read `1.9156 in³` in one place and
 * `31,391.38 mm³` in the other. Covering only the panel that broke would leave
 * the pair free to drift again in the other direction, so both are pinned to
 * the same fixture and the same expectations.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Material } from "../api/materials";
import type { ShapeProperties } from "../api/tessellate";
import type { BodyMaterialRow } from "../features/materials";
import type { PartBuild } from "../features/partBuild";
import type { MaterialControls } from "./MaterialSection";
import {
  brokenFillet,
  cleanCube,
  rolledBack,
  strandedDownstream,
  unverified,
} from "../test/partBuildFixture";
import { DocumentUnitProvider } from "../units/documentUnit";
import { BodyInspector } from "./BodyInspector";
import { PartExportControls } from "./PartExportControls";
import type { LengthUnit } from "@loft/design";

/** The same 25.4 × 50.8 × 76.2 mm solid the assembly panel test uses. */
const PROPERTIES: ShapeProperties = {
  volume: 31391.38,
  surface_area: 6451.6,
  centroid: { x: 25.4, y: 50.8, z: 0 },
  bounding_box: {
    min: { x: 0, y: 0, z: 0 },
    max: { x: 25.4, y: 50.8, z: 76.2 },
  },
  topology: { faces: 6, edges: 12, shells: 1 },
};

/**
 * The library AS SERVED (`GET /api/v1/materials`) — two real entries with their
 * handbook densities. Nothing in `apps/web` may type a density, so a fixture is
 * the only place one appears on this side of the wire.
 */
const LIBRARY: Material[] = [
  { key: "aluminium_6061", name: "Aluminium 6061", density_kg_m3: 2700 },
  { key: "steel_1018", name: "Steel (AISI 1018)", density_kg_m3: 7870 },
];

function bodyRow(
  ordinal: number,
  name: string,
  material: BodyMaterialRow["material"],
  massG: number | null,
  override: BodyMaterialRow["override"] = null,
): BodyMaterialRow {
  return {
    baseFeatureId: `feat-${ordinal}`,
    name,
    ordinal,
    material,
    massG,
    override,
    evaluated: true,
  };
}

function controls(over: Partial<MaterialControls> = {}): MaterialControls {
  return {
    library: LIBRARY,
    libraryError: null,
    assignment: { default_material: null, bodies: [] },
    rows: [bodyRow(1, "Extrude1", null, null)],
    busy: false,
    error: null,
    onAssignDefault: vi.fn(),
    onAssignBody: vi.fn(),
    ...over,
  };
}

/**
 * The panel AS THE WORKSPACE COMPOSES IT: the readouts and the export strip are
 * siblings fed by ONE `PartBuild` (the strip is pinned by `FloatingPanel.footer`
 * so a clamped panel can never push it under the fold — UI-REVIEW P1). The
 * honesty this file exists to pin is that the two agree, which is exactly what
 * asserting across the composed pair proves.
 */
function renderInspector(
  unit: LengthUnit,
  properties: ShapeProperties | null = PROPERTIES,
  build: PartBuild = cleanCube(),
  material: MaterialControls = controls(),
) {
  return render(
    <DocumentUnitProvider unit={unit}>
      <BodyInspector
        properties={properties}
        build={build}
        material={material}
      />
      <PartExportControls partId="p1" build={build} />
    </DocumentUnitProvider>,
  );
}

describe("BodyInspector", () => {
  it("renders millimetre readouts unchanged in an mm part", () => {
    renderInspector("mm");
    const volume = screen.getByTestId("prop-volume");
    expect(volume).toHaveTextContent("31,391.38");
    expect(volume).toHaveTextContent("mm³");
    expect(screen.getByTestId("prop-extents")).toHaveTextContent(
      "25.4 × 50.8 × 76.2",
    );
  });

  it("converts every readout to the document unit in an inch part", () => {
    renderInspector("in");
    const volume = screen.getByTestId("prop-volume");
    expect(volume).toHaveTextContent("1.9156");
    expect(volume).toHaveTextContent("in³");
    expect(volume).not.toHaveTextContent("mm");
    expect(screen.getByTestId("prop-extents")).toHaveTextContent("1 × 2 × 3");
    expect(screen.getByTestId("prop-bbox-max")).toHaveTextContent("1, 2, 3");
  });

  it("reads the SAME numbers as the assembly panel for the same solid", () => {
    // The pair must not drift again: these are byte-for-byte the strings
    // AssemblyInspector.test.tsx asserts for the identical fixture.
    renderInspector("in");
    expect(screen.getByTestId("prop-volume")).toHaveTextContent("1.9156");
    expect(screen.getByTestId("prop-centroid")).toHaveTextContent("1, 2, 0");
    expect(screen.getByTestId("prop-extents")).toHaveTextContent("1 × 2 × 3");
  });

  it("leaves topology counts unitless — a face count is not a length", () => {
    renderInspector("in");
    const faces = screen.getByTestId("prop-faces");
    expect(faces).toHaveTextContent("6");
    expect(faces).not.toHaveTextContent("in");
  });

  it("shows an em dash rather than stale numbers with no body yet", () => {
    renderInspector("in", null);
    expect(screen.getByTestId("prop-volume")).toHaveTextContent("—");
    expect(screen.getByTestId("prop-bbox-min")).toHaveTextContent("—");
  });
});

/**
 * The J2 half: the STATUS cell and the EXPORT strip live in this panel, and both
 * used to be entitled to nothing — "Up to date" from `isFetching` and "Ready"
 * from "is there a mesh id". Both are now derived from the same build facts the
 * feature tree's SOLVE cell reads, so this panel is where the agreement (or the
 * regression) shows up in one render.
 */
describe("BodyInspector status + export honesty", () => {
  it("says Up to date only for a whole body built from the current tree", () => {
    renderInspector("mm");
    expect(screen.getByTestId("body-status")).toHaveTextContent("Up to date");
    expect(screen.getByTestId("body-status")).toHaveAttribute(
      "data-body-status",
      "up-to-date",
    );
    expect(screen.queryByTestId("body-status-detail")).toBeNull();
    expect(screen.getByTestId("part-export-status")).toHaveTextContent("Ready");
  });

  it("calls a broken tree's body PARTIAL in the STATUS cell and in the strip", () => {
    renderInspector("mm", PROPERTIES, brokenFillet());
    const status = screen.getByTestId("body-status");
    expect(status).toHaveTextContent("Partial");
    expect(status).toHaveAttribute("data-body-status", "partial");
    // Not "Up to date" — the exact string the audit found on this screen.
    expect(status).not.toHaveTextContent("Up to date");
    expect(screen.getByTestId("body-status-detail")).toHaveTextContent(
      "built to Extrude1",
    );

    // ...and the strip agrees, in the SAME word the status cell just used
    // (EXPORT-3: the strip used to say "Fillet1 failed" and go inert, which
    // told the truth about the tree and nothing about the file). The two cells
    // now report one fact — this body is a prefix — and the strip adds what
    // that costs the artifact.
    expect(screen.getByTestId("part-export-status")).toHaveTextContent(
      "Partial",
    );
    expect(screen.getByTestId("part-export-notice")).toHaveTextContent(
      "the file stops at Extrude1",
    );
    expect(screen.getByTestId("part-export-step")).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
    // The cell is a live action again, so it reads as one — the caption is the
    // format's own ("B-rep"), and what makes the file a prefix is said once,
    // in the notice, rather than stamped on all four cells.
    expect(screen.getByTestId("part-export-step")).toHaveTextContent("B-rep");
  });

  it("names the failure and the state on screen in ONE register line", () => {
    // The title block gets a tabular clause, not a paragraph: four lines of
    // prose here push the EXPORT strip below the fold at 1366x768, and the
    // gated export is the thing that matters most on a broken part. The full
    // sentence is the viewport notice's job (asserted in e2e).
    renderInspector("mm", PROPERTIES, strandedDownstream());
    expect(screen.getByTestId("body-status-detail")).toHaveTextContent(
      "Hole 1 failed · built to Base extrude",
    );
  });

  it("lets a deliberate rollback export, labelled partial", () => {
    renderInspector("mm", PROPERTIES, rolledBack());
    expect(screen.getByTestId("body-status")).toHaveTextContent("Rolled back");
    expect(screen.getByTestId("part-export-status")).toHaveTextContent(
      "Partial",
    );
    expect(screen.getByTestId("part-export-step")).not.toHaveAttribute(
      "aria-disabled",
    );
    expect(screen.getByTestId("part-export-notice")).toHaveTextContent(
      "name will say partial",
    );
  });

  it("refuses to vouch for a body whose tree has moved on", () => {
    renderInspector("mm", PROPERTIES, unverified());
    expect(screen.getByTestId("body-status")).toHaveTextContent("Unverified");
    expect(screen.getByTestId("part-export-status")).toHaveTextContent(
      "Unverified",
    );
    expect(screen.getByTestId("part-export-step")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });
});

/**
 * THE MASS HALF (#57b, docs/design/materials.md §6). The wire made `mass_g`
 * nullable precisely so a surface can tell "nobody said what this is made of"
 * from "it weighs nothing". These pin the four places that distinction is easy
 * to collapse: the TITLE, the mass ROW, the glyph absence renders as, and the
 * name of the body responsible.
 */
describe("BodyInspector — mass is claimed only once a material exists", () => {
  const WITH_MASS: ShapeProperties = {
    ...PROPERTIES,
    mass_g: 27,
    center_of_mass: { x: 25.4, y: 50.8, z: 0 },
  };

  it("is titled PROPERTIES, with no mass row, while nothing is assigned", () => {
    renderInspector("mm");
    expect(screen.getByRole("group", { name: "Properties" })).toBeTruthy();
    // The exact string the audit found over a panel with no mass in it.
    expect(screen.queryByRole("group", { name: "Mass properties" })).toBeNull();
    expect(screen.queryByTestId("prop-mass")).toBeNull();
  });

  it("renders absence as absence — never `0 g`", () => {
    const { container } = renderInspector("mm");
    expect(container.textContent).not.toMatch(/\b0 (g|kg|lb)\b/);
    expect(screen.getByTestId("material-hint")).toHaveTextContent(
      "Assign a material to get a mass",
    );
    expect(screen.getByTestId("material-default-select")).toHaveValue("");
  });

  it("earns the MASS PROPERTIES title once a mass exists", () => {
    renderInspector(
      "mm",
      WITH_MASS,
      cleanCube(),
      controls({
        assignment: { default_material: "aluminium_6061", bodies: [] },
        rows: [bodyRow(1, "Extrude1", "aluminium_6061", 27)],
      }),
    );
    expect(screen.getByRole("group", { name: "Mass properties" })).toBeTruthy();
    const mass = screen.getByTestId("prop-mass");
    // materials.md §8: 10000 mm³ of aluminium 6061 = 27.0 g exactly.
    expect(mass).toHaveTextContent("27");
    expect(mass).toHaveTextContent("g");
    expect(screen.queryByTestId("material-hint")).toBeNull();
    // The density that produced it, straight from the served library.
    expect(screen.getByTestId("material-density")).toHaveTextContent("2,700");
  });

  it("reads the mass in POUNDS in an inch document (one units seam)", () => {
    renderInspector(
      "in",
      WITH_MASS,
      cleanCube(),
      controls({
        assignment: { default_material: "aluminium_6061", bodies: [] },
        rows: [bodyRow(1, "Extrude1", "aluminium_6061", 27)],
      }),
    );
    const mass = screen.getByTestId("prop-mass");
    expect(mass).toHaveTextContent("0.0595");
    expect(mass).toHaveTextContent("lb");
    expect(mass).not.toHaveTextContent(/\bg\b/);
  });

  it("shows the centre of MASS apart from the volume centroid", () => {
    // The mixed-material golden's numbers: the centre of mass sits 7.34 mm
    // toward the steel body, where the volume centroid stays at x=25.
    renderInspector(
      "mm",
      {
        ...PROPERTIES,
        mass_g: 84.56,
        centroid: { x: 25, y: 0, z: 0 },
        center_of_mass: { x: 32.3368, y: 0, z: 0 },
      },
      cleanCube(),
      controls({
        assignment: {
          default_material: "aluminium_6061",
          bodies: [{ base_feature_id: "feat-2", material: "steel_1018" }],
        },
        rows: [
          bodyRow(1, "Extrude1", "aluminium_6061", 27),
          bodyRow(2, "Extrude2", "steel_1018", 57.56, "steel_1018"),
        ],
      }),
    );
    expect(screen.getByTestId("prop-center-of-mass")).toHaveTextContent(
      "32.34, 0, 0",
    );
    expect(screen.getByTestId("prop-centroid")).toHaveTextContent("25, 0, 0");
    // A mixed part quotes no single density headline — the bodies carry theirs.
    expect(screen.queryByTestId("material-density")).toBeNull();
    expect(screen.getByTestId("material-body-mass-2")).toHaveTextContent(
      "57.56 g",
    );
  });

  it("hides the centre-of-mass row when there is no material", () => {
    renderInspector("mm");
    expect(screen.queryByTestId("prop-center-of-mass")).toBeNull();
    expect(screen.getByTestId("prop-centroid")).toHaveTextContent("25.4, 50.8");
  });

  it("NAMES the body that has no material instead of saying unknown", () => {
    renderInspector(
      "mm",
      PROPERTIES,
      cleanCube(),
      controls({
        assignment: { default_material: null, bodies: [] },
        rows: [
          bodyRow(1, "Extrude1", "aluminium_6061", 27),
          bodyRow(2, "Boss", null, null),
        ],
      }),
    );
    const notice = screen.getByTestId("material-unassigned");
    expect(notice).toHaveTextContent(
      "Boss has no material, so the part has no total mass.",
    );
    expect(notice).not.toHaveTextContent("unknown");
    expect(screen.queryByTestId("prop-mass")).toBeNull();
    expect(screen.getByTestId("material-body-mass-2")).toHaveTextContent("—");
  });
});

describe("BodyInspector — assigning a material", () => {
  it("writes the document default the user picked", () => {
    const onAssignDefault = vi.fn();
    renderInspector(
      "mm",
      PROPERTIES,
      cleanCube(),
      controls({ onAssignDefault }),
    );
    fireEvent.change(screen.getByTestId("material-default-select"), {
      target: { value: "steel_1018" },
    });
    expect(onAssignDefault).toHaveBeenCalledWith("steel_1018");
  });

  it("clears back to no material (mass becomes unknown again)", () => {
    const onAssignDefault = vi.fn();
    renderInspector(
      "mm",
      PROPERTIES,
      cleanCube(),
      controls({
        assignment: { default_material: "steel_1018", bodies: [] },
        onAssignDefault,
      }),
    );
    fireEvent.change(screen.getByTestId("material-default-select"), {
      target: { value: "" },
    });
    expect(onAssignDefault).toHaveBeenCalledWith(null);
  });

  it("overrides ONE body of a multi-body part", () => {
    const onAssignBody = vi.fn();
    renderInspector(
      "mm",
      PROPERTIES,
      cleanCube(),
      controls({
        assignment: { default_material: "aluminium_6061", bodies: [] },
        rows: [
          bodyRow(1, "Extrude1", "aluminium_6061", 27),
          bodyRow(2, "Pin", "aluminium_6061", 27),
        ],
        onAssignBody,
      }),
    );
    // The body cell offers the document's material as its first choice; the
    // cell above it is what NAMES that material, so this one stays short
    // enough not to push the mass readout out of the row.
    expect(screen.getByTestId("material-body-select-2")).toHaveTextContent(
      "Default",
    );
    fireEvent.change(screen.getByTestId("material-body-select-2"), {
      target: { value: "steel_1018" },
    });
    expect(onAssignBody).toHaveBeenCalledWith("feat-2", "steel_1018");
  });

  it("disables the picker and says why when the library is unavailable", () => {
    renderInspector(
      "mm",
      PROPERTIES,
      cleanCube(),
      controls({
        library: [],
        libraryError: "The material library is offline.",
      }),
    );
    expect(screen.getByTestId("material-default-select")).toBeDisabled();
    expect(screen.getByTestId("material-library-error")).toHaveTextContent(
      "offline",
    );
  });

  it("holds the picker while an assignment is in flight", () => {
    renderInspector("mm", PROPERTIES, cleanCube(), controls({ busy: true }));
    expect(screen.getByTestId("material-default-select")).toBeDisabled();
  });
});
