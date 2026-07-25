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
import { DocumentUnitProvider } from "../units/documentUnit";
import { BodyInspector } from "./BodyInspector";
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

function renderInspector(
  unit: LengthUnit,
  properties: ShapeProperties | null = PROPERTIES,
) {
  return render(
    <DocumentUnitProvider unit={unit}>
      <BodyInspector properties={properties} status="up-to-date" partId="p1" />
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
