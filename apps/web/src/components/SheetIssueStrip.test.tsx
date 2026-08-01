/**
 * SheetIssueStrip — does the strip say what the composer measured, and is its
 * action real?
 *
 * Two rendering questions no pure test can reach. (1) The strip must print the
 * COMPOSER's sentence, not a client paraphrase — that sentence is the same one
 * stamped on the PDF, and a second phrase table here is exactly how the screen
 * and the print start disagreeing (the defect this whole item exists to fix).
 * (2) "Auto-place" must be offered only for views the write can actually move: a
 * pair the composer placed itself cannot be fixed by another auto-layout pass, so
 * a button there would be chrome that only decorates (design mandate 3c).
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ComposedLayoutIssue, ViewProjection } from "../api/drawings";
import { SheetIssueStrip } from "./SheetIssueStrip";

function overlap(
  views: [ViewProjection, ViewProjection] = ["front", "top"],
): ComposedLayoutIssue {
  return {
    code: "views_overlap",
    severity: "error",
    views,
    overlap_x_mm: 6.33,
    overlap_y_mm: 60,
    clearance_mm: 0,
    message:
      "FRONT / TOP VIEWS OVERLAP BY 6.33 x 60.00 MM - REPOSITION BEFORE RELEASE",
    at: { x_mm: 13, y_mm: 15 },
  };
}

function crowded(): ComposedLayoutIssue {
  return {
    code: "views_crowded",
    severity: "warning",
    views: ["top", "iso"],
    overlap_x_mm: -0.7,
    overlap_y_mm: -20,
    clearance_mm: 0.7,
    message:
      "TOP / ISOMETRIC VIEWS CLEAR BY ONLY 0.70 MM (MINIMUM 4.00 MM) - CROWDED SHEET",
    at: { x_mm: 13, y_mm: 19.2 },
  };
}

const NONE: ReadonlySet<ViewProjection> = new Set();

describe("SheetIssueStrip", () => {
  it("renders nothing for a clean sheet", () => {
    const { container } = render(
      <SheetIssueStrip issues={[]} handPlaced={NONE} onAutoPlace={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("prints the composer's own sentence, verbatim", () => {
    render(
      <SheetIssueStrip
        issues={[overlap()]}
        handPlaced={NONE}
        onAutoPlace={vi.fn()}
      />,
    );
    expect(screen.getByTestId("sheet-issue-message")).toHaveTextContent(
      "FRONT / TOP VIEWS OVERLAP BY 6.33 x 60.00 MM - REPOSITION BEFORE RELEASE",
    );
  });

  it("interrupts for a collision and merely reports a crowded pair", () => {
    const { unmount } = render(
      <SheetIssueStrip
        issues={[overlap()]}
        handPlaced={NONE}
        onAutoPlace={vi.fn()}
      />,
    );
    expect(screen.getByTestId("sheet-issue-strip")).toHaveAttribute(
      "role",
      "alert",
    );
    unmount();

    render(
      <SheetIssueStrip
        issues={[crowded()]}
        handPlaced={NONE}
        onAutoPlace={vi.fn()}
      />,
    );
    expect(screen.getByTestId("sheet-issue-strip")).toHaveAttribute(
      "role",
      "status",
    );
  });

  it("counts every issue and stamps each row's severity", () => {
    render(
      <SheetIssueStrip
        issues={[overlap(), crowded()]}
        handPlaced={NONE}
        onAutoPlace={vi.fn()}
      />,
    );
    expect(screen.getByTestId("sheet-issue-count")).toHaveTextContent("2");
    const rows = screen.getAllByTestId("sheet-issue-row");
    expect(rows).toHaveLength(2);
    expect(
      within(rows[0] as HTMLElement).getByTestId("sheet-issue-severity"),
    ).toHaveTextContent("ERROR");
    expect(
      within(rows[1] as HTMLElement).getByTestId("sheet-issue-severity"),
    ).toHaveTextContent("WARNING");
  });

  it("offers auto-place ONLY for the hand-placed views of the pair", () => {
    const onAutoPlace = vi.fn();
    render(
      <SheetIssueStrip
        issues={[overlap(["front", "top"])]}
        handPlaced={new Set<ViewProjection>(["top"])}
        onAutoPlace={onAutoPlace}
      />,
    );
    const action = screen.getByTestId("sheet-issue-autoplace");
    expect(action).toHaveAccessibleName("Return the Top view to auto-layout");
    fireEvent.click(action);
    expect(onAutoPlace).toHaveBeenCalledWith(["top"]);
  });

  it("names both views when both were hand-placed", () => {
    render(
      <SheetIssueStrip
        issues={[overlap(["front", "top"])]}
        handPlaced={new Set<ViewProjection>(["front", "top"])}
        onAutoPlace={vi.fn()}
      />,
    );
    expect(screen.getByTestId("sheet-issue-autoplace")).toHaveAccessibleName(
      "Return the Front and Top views to auto-layout",
    );
  });

  it("advises instead of offering a no-op reset when nothing was hand-placed", () => {
    render(
      <SheetIssueStrip
        issues={[overlap()]}
        handPlaced={NONE}
        onAutoPlace={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("sheet-issue-autoplace")).toBeNull();
    expect(screen.getByTestId("sheet-issue-advice")).toHaveTextContent(
      "Choose a larger sheet or a smaller scale",
    );
  });

  it("rests its actions while a placement write is in flight", () => {
    const onAutoPlace = vi.fn();
    render(
      <SheetIssueStrip
        issues={[overlap()]}
        handPlaced={new Set<ViewProjection>(["front"])}
        onAutoPlace={onAutoPlace}
        busy
      />,
    );
    const action = screen.getByTestId("sheet-issue-autoplace");
    expect(action).toBeDisabled();
    fireEvent.click(action);
    expect(onAutoPlace).not.toHaveBeenCalled();
  });
});
