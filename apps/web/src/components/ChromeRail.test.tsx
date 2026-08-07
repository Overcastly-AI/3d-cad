/**
 * ChromeRail — does a feature editor actually DOCK, and does the surface that
 * has no rail keep working?
 *
 * FB-7 (founder photograph): an open editor sat on the model it was editing —
 * measured at 50 069 px2, 9.0 % of the body's screen box. The fix is
 * structural, so the thing to assert is structural too: the card must be a
 * DESCENDANT of the rail (one column, one inset), not merely styled to look
 * tidy. The pixel half of the gate lives in `e2e/founder-picking.spec.ts`,
 * which measures real lit body pixels against real chrome rects.
 *
 * The fallback matters as much as the dock: the assembly and drawing
 * workspaces mount no rail, and seventeen editors hang in this one shell.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChromeRail, ChromeRailProvider, RailDock } from "./ChromeRail";
import { EditorCard } from "./EditorCard";
import { FloatingPanel } from "./FloatingPanel";

function Workspace() {
  return (
    <ChromeRailProvider>
      {/* The editor is authored where the HUD renders it — inside the scene
          overlay, nowhere near the rail's JSX — and relocates by portal. */}
      <div data-testid="hud">
        <EditorCard footer={<button type="button">Create</button>}>
          <span data-testid="editor-body">Distance</span>
        </EditorCard>
      </div>
      <ChromeRail side="left">
        <FloatingPanel side="left" title="Feature tree" id="tree">
          <span data-testid="tree-body">Extrude 1</span>
        </FloatingPanel>
      </ChromeRail>
    </ChromeRailProvider>
  );
}

describe("ChromeRail", () => {
  it("docks an editor into the rail it was opened from", () => {
    render(<Workspace />);
    const rail = document.querySelector('[data-viewport-chrome="rail-left"]');
    const card = screen.getByTestId("editor-body").closest("div.shadow-float");
    expect(rail).not.toBeNull();
    expect(card).not.toBeNull();
    // The assertion FB-7 turns on: same column, by containment.
    expect(rail?.contains(card as Node)).toBe(true);
    // …and it did NOT stay where its JSX sits.
    expect(screen.getByTestId("hud").contains(card as Node)).toBe(false);
  });

  it("declares the column as viewport chrome, so the fit can see it", () => {
    render(<Workspace />);
    // The editor used to carry no `data-viewport-chrome` at all, so neither the
    // app's own free-rect fit nor the occlusion gate could see it without being
    // handed the selector by hand — which was itself the bug report.
    const rail = document.querySelector('[data-viewport-chrome="rail-left"]');
    const card = screen.getByTestId("editor-body").closest("div.shadow-float");
    expect(rail?.contains(card as Node)).toBe(true);
  });

  it("seats the editor ABOVE the panel it was opened from", () => {
    render(<Workspace />);
    const card = screen.getByTestId("editor-body").closest("div.shadow-float");
    const panel = document.querySelector('[data-viewport-chrome="panel-tree"]');
    expect(card).not.toBeNull();
    expect(panel).not.toBeNull();
    // DOCUMENT_POSITION_FOLLOWING: the panel comes after the card.
    expect(
      (card as Node).compareDocumentPosition(panel as Node) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("keeps the panel mounted — an editor never hides the tree", () => {
    // Auto-collapsing the neighbour was the tempting cheap fix. A panel that
    // vanishes when you open an editor is its own flow defect, and specs read
    // the tree and the inspector WHILE editors are open.
    render(<Workspace />);
    expect(screen.getByTestId("tree-body")).toBeTruthy();
    expect(screen.getByTestId("editor-body")).toBeTruthy();
  });

  it("floats exactly as before where no rail is mounted", () => {
    // The assembly and drawing workspaces, and every editor unit test.
    render(
      <EditorCard>
        <span data-testid="lonely">Draft angle</span>
      </EditorCard>,
    );
    const card = screen.getByTestId("lonely").closest("div.shadow-float");
    expect(card?.className).toContain("absolute");
    expect(card?.className).toContain("left-editor");
  });

  it("routes a same-seat notice through the rail too", () => {
    render(
      <ChromeRailProvider>
        <ChromeRail side="left">
          <FloatingPanel side="left" title="Feature tree" id="tree">
            <span>tree</span>
          </FloatingPanel>
        </ChromeRail>
        <RailDock side="left">
          <div data-testid="notice">Regenerating body</div>
        </RailDock>
      </ChromeRailProvider>,
    );
    const rail = document.querySelector('[data-viewport-chrome="rail-left"]');
    expect(rail?.contains(screen.getByTestId("notice"))).toBe(true);
  });

  it("renders no box for an empty dock", () => {
    // A zero-height flex item would still take a `gap-2` from the rail, leaving
    // a seam above the tree whenever no notice is showing — nearly always.
    const { container } = render(<RailDock side="left">{null}</RailDock>);
    expect(container.firstChild).toBeNull();
  });
});
