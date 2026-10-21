/**
 * The cut dialogs' Objects To Cut list (CUT-OBJECTS-TO-CUT): hidden on a
 * one-body part, a sentence for a cut not built yet, a ticked row per body
 * met once it is, and the one action a cut saved before the list has.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { BodyInfo } from "../features/bodies";
import { ObjectsToCut } from "./ObjectsToCut";

const BODIES: BodyInfo[] = ["b1", "b2", "b3"].map((id, i) => ({
  baseFeatureId: id,
  name: `Wall ${i + 1}`,
  featureType: "extrude",
  ordinal: i + 1,
}));

describe("ObjectsToCut", () => {
  it("is absent on a one-body part", () => {
    const { container } = render(
      <ObjectsToCut
        choice="all"
        context={{ bodies: BODIES.slice(0, 1), met: ["b1"] }}
        onChange={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("says what a new cut will cut before it has met anything", () => {
    render(
      <ObjectsToCut
        choice="all"
        context={{ bodies: BODIES, met: null }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByTestId("objects-to-cut-every")).toHaveTextContent(
      "Every body the cut meets.",
    );
  });

  it("ticks every body met, and unticking one narrows the cut", () => {
    const onChange = vi.fn();
    render(
      <ObjectsToCut
        choice="all"
        context={{ bodies: BODIES, met: ["b1", "b3"] }}
        onChange={onChange}
      />,
    );
    const rows = screen.getAllByRole("checkbox");
    expect(rows.map((row) => row.textContent)).toEqual([
      "Body 1 · Wall 1",
      "Body 3 · Wall 3",
    ]);
    expect(
      rows.every((row) => row.getAttribute("aria-checked") === "true"),
    ).toBe(true);
    fireEvent.click(screen.getByTestId("objects-to-cut-b3"));
    expect(onChange).toHaveBeenCalledWith([
      { kind: "feature", feature_id: "b1" },
    ]);
  });

  it("offers a cut saved before the list every body it meets", () => {
    const onChange = vi.fn();
    render(
      <ObjectsToCut
        choice={undefined}
        context={{ bodies: BODIES, met: ["b3"] }}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId("objects-to-cut-all"));
    expect(onChange).toHaveBeenCalledWith("all");
  });
});
