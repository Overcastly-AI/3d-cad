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
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ShapeProperties } from "../api/tessellate";
import type { PartBuild } from "../features/partBuild";
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
) {
  return render(
    <DocumentUnitProvider unit={unit}>
      <BodyInspector properties={properties} build={build} />
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

  it("calls a broken tree's body PARTIAL and blocks the export", () => {
    renderInspector("mm", PROPERTIES, brokenFillet());
    const status = screen.getByTestId("body-status");
    expect(status).toHaveTextContent("Partial");
    expect(status).toHaveAttribute("data-body-status", "partial");
    // Not "Up to date" — the exact string the audit found on this screen.
    expect(status).not.toHaveTextContent("Up to date");
    expect(screen.getByTestId("body-status-detail")).toHaveTextContent(
      "built to Extrude1",
    );

    // ...and the file the strip would have written is refused, by name.
    expect(screen.getByTestId("part-export-status")).toHaveTextContent(
      "Fillet1 failed",
    );
    expect(screen.getByTestId("part-export-step")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByTestId("part-export-stl")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    // Each format cell carries the reason too (a gated cell a user tabs to has
    // to explain itself), and the strip adds no fourth copy of it.
    expect(screen.getByTestId("part-export-step")).toHaveTextContent(
      "Fillet1 failed",
    );
    expect(screen.queryByTestId("part-export-notice")).toBeNull();
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
