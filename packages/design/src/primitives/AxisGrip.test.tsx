import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AxisGrip } from "./AxisGrip";

/**
 * The grip on a direct-manipulation handle (T-23).
 *
 * What is worth asserting here is the CONTRACT, not the paint: that this is a
 * real slider with a value, bounds and a spoken form; that it is reachable by
 * keyboard; and that its rest state recedes while every addressed state comes
 * forward. Those four are exactly what a WebGL mesh cannot give you, and they
 * are the reason this element is DOM at all — so if any of them regresses, the
 * component has quietly become a decoration with a click handler.
 *
 * The recession is asserted on the class list rather than by a pixel census for
 * the same reason `PickNode.test.tsx` gives: this element is projected over the
 * canvas by drei `Html` and contributes zero canvas pixels, so every pixel gate
 * in the repo is structurally blind to it.
 */
function collarOf(container: HTMLElement): HTMLElement {
  const mark = container.querySelector<HTMLElement>('[role="slider"] > span');
  if (mark === null) throw new Error("no collar rendered");
  return mark;
}

describe("AxisGrip", () => {
  it("is a slider that carries its value, its bounds and its words", () => {
    render(
      <AxisGrip
        aria-label="Extrude depth"
        value={12.5}
        min={0.1}
        max={10000}
        valueText="12.5 mm"
      />,
    );
    const grip = screen.getByRole("slider", { name: "Extrude depth" });
    expect(grip).toHaveAttribute("aria-valuenow", "12.5");
    expect(grip).toHaveAttribute("aria-valuemin", "0.1");
    expect(grip).toHaveAttribute("aria-valuemax", "10000");
    // The spoken form carries the UNIT: "12.5" alone is not a length.
    expect(grip).toHaveAttribute("aria-valuetext", "12.5 mm");
  });

  it("is keyboard reachable — the whole reason it is not a mesh", () => {
    const { container } = render(
      <AxisGrip
        aria-label="Extrude depth"
        value={10}
        min={0}
        max={100}
        valueText="10 mm"
      />,
    );
    const grip = screen.getByRole("slider");
    expect(grip).toHaveAttribute("tabindex", "0");
    expect(grip.className).toContain("focus-visible:outline");
    // …and it keeps a 24px target (WCAG 2.2 SC 2.5.8) in every state.
    expect(grip.className).toContain("h-6");
    expect(grip.className).toContain("w-6");
    expect(collarOf(container)).toBeTruthy();
  });

  it("recedes at rest and comes forward when addressed", () => {
    const { container: resting } = render(
      <AxisGrip
        aria-label="Extrude depth"
        value={10}
        min={0}
        max={100}
        valueText="10 mm"
      />,
    );
    // At rest the drawn arrow underneath is the affordance, so the collar is a
    // hint rather than a second ring competing with it.
    expect(collarOf(resting).className).toContain("border-brass/40");
    expect(collarOf(resting).className).toContain(
      "group-hover/grip:border-brass",
    );

    const { container: held } = render(
      <AxisGrip
        aria-label="Extrude depth"
        value={10}
        min={0}
        max={100}
        valueText="10 mm"
        grabbed
      />,
    );
    // Held: the accent, plus a filled core — distinguishable from merely
    // addressed WITHOUT the target moving or resizing.
    expect(collarOf(held).className).toContain("border-brass-hover");
    expect(collarOf(held).className).toContain("bg-brass-hover/30");
    expect(collarOf(held).className).not.toContain("border-brass/40");
  });

  it("says which state it is in, to the pointer and to a test", () => {
    const { rerender } = render(
      <AxisGrip
        aria-label="Extrude depth"
        value={10}
        min={0}
        max={100}
        valueText="10 mm"
      />,
    );
    const grip = screen.getByRole("slider");
    expect(grip).toHaveAttribute("data-grabbed", "false");
    expect(grip.className).toContain("cursor-grab");
    rerender(
      <AxisGrip
        aria-label="Extrude depth"
        value={10}
        min={0}
        max={100}
        valueText="10 mm"
        grabbed
      />,
    );
    expect(grip).toHaveAttribute("data-grabbed", "true");
    expect(grip.className).toContain("cursor-grabbing");
  });

  it("honours prefers-reduced-motion on its one transition", () => {
    const { container } = render(
      <AxisGrip
        aria-label="Extrude depth"
        value={10}
        min={0}
        max={100}
        valueText="10 mm"
      />,
    );
    const collar = collarOf(container);
    expect(collar.className).toContain("transition-colors");
    expect(collar.className).toContain("motion-reduce:transition-none");
  });
});
