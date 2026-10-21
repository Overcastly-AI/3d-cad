import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DimensionTag, DimensionTagCell } from "./DimensionTag";

/**
 * A strip whose cells read in different units (a line's length and angle,
 * SKETCH-LINE-ANGLE) writes each cell's unit after its value, in the readout
 * and the editable state alike; a strip that shares one states it once.
 */
describe("DimensionTag units", () => {
  it("states a shared unit once, at the end of the strip", () => {
    const { container } = render(
      <DimensionTag unit="mm">
        <DimensionTagCell label="W" readout="40" />
        <DimensionTagCell label="H" readout="25" />
      </DimensionTag>,
    );
    expect(container.textContent).toBe("W40H25mm");
  });

  it("writes each cell's own unit after its value", () => {
    const { container } = render(
      <DimensionTag>
        <DimensionTagCell label="L" readout="450" unit="mm" />
        <DimensionTagCell label="∠" aria-label="Angle" unit="°" />
      </DimensionTag>,
    );
    expect(container.textContent).toBe("L450mm∠°");
    const angle = screen.getByLabelText("Angle");
    expect(angle.nextElementSibling?.textContent).toBe("°");
  });
});
