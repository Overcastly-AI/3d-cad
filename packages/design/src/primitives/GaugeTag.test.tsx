/** @vitest-environment jsdom */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { placeGaugeTag } from "../gauge";
import { GaugeTag } from "./GaugeTag";

describe("GaugeTag", () => {
  it("writes the number in the drafting register — label, value, unit once", () => {
    render(
      <GaugeTag
        unit="mm"
        data-testid="tag"
        cells={[{ label: "D", readout: "40" }]}
      />,
    );
    const tag = screen.getByTestId("tag");
    expect(tag.textContent).toBe("D40mm");
  });

  it("puts two numbers on ONE strip rather than two tags", () => {
    // A hole has a depth AND a diameter. Two tags 20 mm apart carrying
    // different numbers is the "two dialects drawn on screen" failure literally,
    // so the companion is a second CELL, divided by the strip's own rule.
    render(
      <GaugeTag
        unit="mm"
        data-testid="tag"
        cells={[
          { label: "D", readout: "12" },
          { label: "Ø", readout: "6" },
        ]}
      />,
    );
    expect(screen.getByTestId("tag").textContent).toBe("D12Ø6mm");
    // One strip, so the unit is written once for the pair.
    expect(screen.getByTestId("tag").textContent).not.toContain("mmmm");
  });

  it("renders a READOUT as text with no input — the pointer owns the number", () => {
    render(
      <GaugeTag data-testid="tag" cells={[{ label: "D", readout: "40" }]} />,
    );
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("renders an INPUT when the caret belongs in it, same cell, same place", () => {
    // CRAFT-7 flips the extrude gauge to this by dropping `readout` and passing
    // `value`/`onChange`; the number does not move between the two states, so
    // the value you watched form is the value you type over.
    render(
      <GaugeTag
        data-testid="tag"
        cells={[{ label: "D", value: "40", onChange: () => {} }]}
      />,
    );
    expect(screen.getByRole("textbox")).toHaveValue("40");
  });

  it("draws NO leader when it has no placement — an unattached tag is opt-in", () => {
    // A leader drawn from the wrong origin points confidently at nothing, so
    // the caller has to say where the grip is before one is drawn at all.
    render(
      <GaugeTag data-testid="tag" cells={[{ label: "D", readout: "40" }]} />,
    );
    expect(screen.queryByTestId("gauge-tag-leader")).toBeNull();
  });

  it("draws a two-tone leader from the grip to the tag's near corner", () => {
    const placement = placeGaugeTag("up-right", { width: 90, height: 26 });
    render(
      <GaugeTag
        data-testid="tag"
        placement={placement}
        cells={[{ label: "D", readout: "40" }]}
      />,
    );
    const leader = screen.getByTestId("gauge-tag-leader");
    const lines = leader.querySelectorAll("line");
    // TWO strokes, not one: a single brass hairline reads on the dark bench and
    // vanishes over a lit aluminium face, which is where a manipulator lives.
    // Dark casing down first, brass core on top.
    expect(lines).toHaveLength(2);
    expect(lines[0]?.getAttribute("stroke")).toBe("#0F141A");
    expect(lines[1]?.getAttribute("stroke")).toBe("currentColor");
    expect(Number(lines[0]?.getAttribute("stroke-width"))).toBeGreaterThan(
      Number(lines[1]?.getAttribute("stroke-width")),
    );
    // Both run from the GRIP, which is this container's own origin.
    for (const line of lines) {
      expect(line.getAttribute("x1")).toBe("0");
      expect(line.getAttribute("y1")).toBe("0");
      expect(line.getAttribute("x2")).toBe(String(placement.leader.x2));
    }
    // The anchor dot marks the exact point the number is about.
    expect(leader.querySelectorAll("circle")).toHaveLength(2);
  });

  it("seats the strip where the placement put it, and says which side", () => {
    const placement = placeGaugeTag("down-left", { width: 90, height: 26 });
    render(
      <GaugeTag
        data-testid="tag"
        placement={placement}
        cells={[{ label: "D", readout: "40" }]}
      />,
    );
    const seat = screen.getByTestId("tag").parentElement;
    expect(seat?.getAttribute("data-gauge-tag-side")).toBe("down-left");
    expect(seat?.style.left).toBe(`${String(placement.tag.left)}px`);
    expect(seat?.style.top).toBe(`${String(placement.tag.top)}px`);
  });

  it("is inert to the pointer — it annotates the grip, it is not a second one", () => {
    // The tag's box sits at the same anchor as the 24 px grip. Without this the
    // strip swallows the press and the drag does nothing at all, which is
    // exactly how the extrude gauge's first browser run failed.
    const placement = placeGaugeTag("up-right", { width: 90, height: 26 });
    render(
      <GaugeTag
        data-testid="tag"
        placement={placement}
        cells={[{ label: "D", readout: "40" }]}
      />,
    );
    const root = screen.getByTestId("tag").parentElement?.parentElement;
    expect(root?.className).toContain("pointer-events-none");
  });

  it("has no transition to reduce — the instrument does not animate", () => {
    // `prefers-reduced-motion` needs no code here, and that is a decision
    // rather than an omission: a manipulator that animates into place is a
    // manipulator that is not where you left it.
    const { container } = render(
      <GaugeTag data-testid="tag" cells={[{ label: "D", readout: "40" }]} />,
    );
    expect(container.innerHTML).not.toContain("transition");
    expect(container.innerHTML).not.toContain("animate-");
  });
});
