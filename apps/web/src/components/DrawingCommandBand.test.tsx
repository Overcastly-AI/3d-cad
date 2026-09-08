/**
 * The drawing command band's SCALE cell (SHEET-RESCALE-2).
 *
 * SHEET-RESCALE-1 gave the server a re-scale verb that rewrites all four views
 * in one transaction, and the band kept the post-layout Scale cell as a
 * read-only `Readout` — so `onSelectScale` had exactly one call site, in the
 * `hasLayout ? Readout : SelectField` FALSE branch, while the handler behind it
 * only did anything when `hasLayout` was TRUE. Mutually exclusive: dead code
 * from the UI's side, not merely a hard-to-reach control.
 *
 * These cases are written against the branch that used to be unreachable, so
 * they fail on the pre-swap component: the post-layout assertions below cannot
 * pass while the cell is a readout.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DrawingCommandBand } from "./DrawingCommandBand";
import { SCALE_OPTIONS } from "../drawing/layout";

function band(props: Partial<Parameters<typeof DrawingCommandBand>[0]> = {}) {
  return (
    <DrawingCommandBand
      sources={[{ id: "part-1", name: "Bracket", kind: "part" }]}
      selectedSourceId="part-1"
      onSelectSource={vi.fn()}
      sourceKind="part"
      scaleValue="1:2"
      onSelectScale={vi.fn()}
      sizeValue="A4"
      onSelectSize={vi.fn()}
      paperOrientation="landscape"
      paperScale="1:2"
      hasLayout={false}
      draftedSourceName="Bracket"
      onLayout={vi.fn()}
      onFlatPattern={vi.fn()}
      onToggleSection={vi.fn()}
      sectionOpen={false}
      onReproject={vi.fn()}
      onExportSvg={vi.fn()}
      onExportPdf={vi.fn()}
      onExportDxf={vi.fn()}
      exporting={false}
      busy={false}
      {...props}
    />
  );
}

function renderBand(
  props: Partial<Parameters<typeof DrawingCommandBand>[0]> = {},
) {
  return render(band(props));
}

describe("DrawingCommandBand — the Scale cell", () => {
  it("stays a live picker after the views are laid out", () => {
    renderBand({ hasLayout: true });
    const picker = screen.getByTestId("drawing-scale-select");
    // The control, not merely some element with the hook: a readout would be a
    // <span>, and `toBeEnabled` is meaningless on one.
    expect(picker.tagName).toBe("SELECT");
    expect(picker).toBeEnabled();
    // Still named, so it is operable by anyone not looking at it.
    expect(picker).toHaveAccessibleName("Scale");
  });

  it("reads back the scale the sheet is drawn at, not the first option", () => {
    renderBand({ hasLayout: true, scaleValue: "1:5" });
    expect(screen.getByTestId("drawing-scale-select")).toHaveValue("1:5");
  });

  it("calls onSelectScale with the picked value on a laid-out sheet", () => {
    const onSelectScale = vi.fn();
    renderBand({ hasLayout: true, scaleValue: "1:2", onSelectScale });
    fireEvent.change(screen.getByTestId("drawing-scale-select"), {
      target: { value: "1:5" },
    });
    expect(onSelectScale).toHaveBeenCalledWith("1:5");
  });

  it("shows a scale that is off the standard ladder instead of misreporting 1:1", () => {
    // A native select whose value matches no option displays its FIRST one, so
    // without a guard entry a sheet stored at 1:3 (an API client can write any
    // ratio) would read as whatever heads the list. The old readout could not
    // lie about this; the picker that replaced it must not either.
    renderBand({ hasLayout: true, scaleValue: "1:3" });
    const picker = screen.getByTestId("drawing-scale-select");
    expect(picker).toHaveValue("1:3");
    const guard = screen.getByRole("option", { name: "1:3" });
    // Shown, not choosable — it is a reading, not a scale we offer.
    expect(guard).toBeDisabled();
    // ...and the ladder is still all there to re-pick from.
    for (const option of SCALE_OPTIONS) {
      expect(screen.getByRole("option", { name: option.label })).toBeVisible();
    }
  });

  it("holds the PICKED value while the write is in flight, not the old one", () => {
    // The regression this replaced: `scaleValue` derives from the server and
    // React re-runs `updateOptions` on every commit, so a successful pick was
    // answered by snapping back to the scale the user had just moved away from.
    // A success that reads as a rejection, on the one gesture this ticket adds.
    const { rerender } = renderBand({ hasLayout: true, scaleValue: "1:2" });
    const picker = screen.getByTestId("drawing-scale-select");
    fireEvent.change(picker, { target: { value: "1:5" } });
    // The page now re-renders with the write in flight and the server value
    // STILL the old one — the exact prop sequence `DrawingPage` produces.
    rerender(band({ hasLayout: true, scaleValue: "1:2", rescaling: true }));
    expect(picker).toHaveValue("1:5");
    // ...and it settles on the server's own reading, with nothing to see.
    rerender(band({ hasLayout: true, scaleValue: "1:5", rescaling: false }));
    expect(picker).toHaveValue("1:5");
  });

  it("reverts to what the sheet is drawn at when the write fails", () => {
    // The other half, and the reason the pick is held only for the flight: a
    // refused write must leave the honest reading, beside the page's error.
    const { rerender } = renderBand({ hasLayout: true, scaleValue: "1:2" });
    const picker = screen.getByTestId("drawing-scale-select");
    fireEvent.change(picker, { target: { value: "1:5" } });
    rerender(band({ hasLayout: true, scaleValue: "1:2", rescaling: true }));
    expect(picker).toHaveValue("1:5");
    // The write failed: the page clears `rescaling` without the scale moving.
    rerender(band({ hasLayout: true, scaleValue: "1:2", rescaling: false }));
    expect(picker).toHaveValue("1:2");
  });

  it("marks itself busy in flight WITHOUT leaving the tab order", () => {
    const { rerender } = renderBand({ hasLayout: true, scaleValue: "1:2" });
    const picker = screen.getByTestId("drawing-scale-select");
    picker.focus();
    expect(document.activeElement).toBe(picker);

    rerender(band({ hasLayout: true, scaleValue: "1:2", rescaling: true }));
    // Inert, and said the way the band says it (`ToolButton`'s grammar).
    expect(picker).toHaveAttribute("aria-disabled", "true");
    expect(picker).toHaveAttribute("aria-busy", "true");
    // NOT the native attribute: that drops the control from the tab order, so
    // disabling at the instant of the pick threw a keyboard user to <body>
    // mid-task. jest-dom's `toBeDisabled` reads only the native attribute,
    // which is exactly why it is the right assertion here.
    expect(picker).not.toBeDisabled();
    expect(document.activeElement).toBe(picker);
  });

  it("discards a second pick while one is already in flight", () => {
    const onSelectScale = vi.fn();
    const { rerender } = renderBand({
      hasLayout: true,
      scaleValue: "1:2",
      onSelectScale,
    });
    const picker = screen.getByTestId("drawing-scale-select");
    fireEvent.change(picker, { target: { value: "1:5" } });
    expect(onSelectScale).toHaveBeenCalledTimes(1);

    rerender(band({ hasLayout: true, scaleValue: "1:2", rescaling: true }));
    fireEvent.change(picker, { target: { value: "1:10" } });
    // The writer would refuse it, so the cell does not pretend otherwise —
    // and it does not silently show a scale the sheet is not being drawn at.
    expect(onSelectScale).toHaveBeenCalledTimes(1);
    expect(picker).toHaveValue("1:5");
  });

  it("keeps Source and Size engraved after layout — those ARE re-layouts", () => {
    renderBand({ hasLayout: true });
    expect(screen.getByTestId("drawing-part-readout")).toBeVisible();
    expect(screen.getByTestId("drawing-size-readout")).toBeVisible();
    expect(screen.queryByTestId("drawing-part-select")).toBeNull();
    expect(screen.queryByTestId("drawing-size-select")).toBeNull();
  });

  it("is still the same one control before the layout", () => {
    renderBand({ hasLayout: false });
    expect(screen.getByTestId("drawing-scale-select")).toBeEnabled();
    expect(screen.queryByTestId("drawing-scale-readout")).toBeNull();
  });
});
