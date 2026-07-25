/**
 * MeasureReadout — the measured number a user reads off the screen, and the
 * unit convention it is stamped in.
 *
 * This readout has already burned us once at a tier no unit test watched: the
 * units convention change (`70ce39d`) moved the distance cell from a bare
 * `"37.42"` to `formatLength(..., { unitSuffix: true })` → `"37.4166 mm"`, and
 * the only thing that noticed was a Playwright spec asserting a stale string —
 * days later, through a timeout that read like "the readout never appears"
 * (CLAUDE.md environment recipe, 2026-07-22). A component test that renders the
 * value and the unit together makes that change loud and immediate.
 *
 * The measurement OVERLAY is WebGL and cannot render here; this covers the DOM
 * instrument only — the store transitions it reads are separately unit-tested.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { MeasureResult } from "../api/measure";
import { useMeasureStore } from "../measure/store";
import { DocumentUnitProvider } from "../units/documentUnit";
import { MeasureReadout } from "./MeasureReadout";
import type { LengthUnit } from "@loft/design";

/** 25.4 mm apart along X — exactly one inch, so a conversion slip is obvious. */
const RESULT: MeasureResult = {
  distance: 25.4,
  delta: { x: 25.4, y: 0, z: 0 },
  angle_deg: null,
  kind: "point_point",
  point_on_a: { x: 0, y: 0, z: 0 },
  point_on_b: { x: 25.4, y: 0, z: 0 },
};

function armed(result: MeasureResult | null = RESULT) {
  useMeasureStore.setState({
    active: true,
    picks: [
      { kind: "vertex", index: 0, position: { x: 0, y: 0, z: 0 } },
      { kind: "vertex", index: 1, position: { x: 25.4, y: 0, z: 0 } },
    ],
    result,
    overlayError: null,
    measureError: null,
  });
}

function renderReadout(unit: LengthUnit = "mm") {
  return render(
    <DocumentUnitProvider unit={unit}>
      <MeasureReadout />
    </DocumentUnitProvider>,
  );
}

afterEach(() => useMeasureStore.getState().deactivate());

describe("MeasureReadout", () => {
  it("renders nothing at all while the tool is disarmed", () => {
    useMeasureStore.setState({ active: false });
    renderReadout();
    expect(screen.queryByTestId("measure-readout")).not.toBeInTheDocument();
  });

  it("stamps the unit beside the distance, never a bare number", () => {
    armed();
    renderReadout("mm");
    const distance = screen.getByTestId("measure-readout-distance");
    expect(distance).toHaveTextContent("25.4");
    expect(distance).toHaveTextContent("mm");
  });

  it("measures in the document unit — an inch part reads inches", () => {
    armed();
    renderReadout("in");
    const distance = screen.getByTestId("measure-readout-distance");
    expect(distance).toHaveTextContent("1");
    expect(distance).toHaveTextContent("in");
    expect(distance).not.toHaveTextContent("mm");
  });

  it("converts the component deltas too, not just the hero numeral", () => {
    armed();
    renderReadout("in");
    expect(screen.getByTestId("measure-readout-dx")).toHaveTextContent("1 in");
    expect(screen.getByTestId("measure-readout-dy")).toHaveTextContent("0 in");
  });

  it("reports the angle in degrees regardless of the length unit", () => {
    armed({ ...RESULT, angle_deg: 90 });
    renderReadout("in");
    const angle = screen.getByTestId("measure-readout-angle");
    expect(angle).toHaveTextContent("90");
    expect(angle).not.toHaveTextContent("in");
  });

  it("omits the angle cell when the pair has no single direction", () => {
    armed();
    renderReadout();
    expect(
      screen.queryByTestId("measure-readout-angle"),
    ).not.toBeInTheDocument();
  });

  it("prompts for the next pick instead of showing a stale reading", () => {
    useMeasureStore.setState({
      active: true,
      picks: [{ kind: "vertex", index: 0, position: { x: 0, y: 0, z: 0 } }],
      result: null,
      overlayError: null,
      measureError: null,
    });
    renderReadout();
    expect(screen.getByTestId("measure-prompt")).toHaveTextContent(
      "Pick the second point or edge",
    );
    expect(
      screen.queryByTestId("measure-readout-distance"),
    ).not.toBeInTheDocument();
  });

  it("surfaces a failed measurement as an alert, not silence", () => {
    useMeasureStore.setState({
      active: true,
      picks: [],
      result: null,
      overlayError: null,
      measureError: "The two targets touch — the distance is zero.",
    });
    renderReadout();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The two targets touch — the distance is zero.",
    );
  });
});
