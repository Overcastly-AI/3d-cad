/**
 * The assembly command band's EXPORT group.
 *
 * The assembly repeated the part workspace's defect at a second address: its
 * only export affordance sat inside the Inspect panel, below a Solve / Parts /
 * Clash segmented control (`AssemblyInspectorPanel`), so the file went away with
 * the panel. Export now rides the band here too — same primitive, same last
 * position, same disabled-with-a-reason grammar (EXPORT-1).
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AssemblyCommandBand } from "./AssemblyCommandBand";

function renderBand(
  props: Partial<Parameters<typeof AssemblyCommandBand>[0]> = {},
) {
  return render(
    <AssemblyCommandBand
      historyReady
      canUndo={false}
      canRedo={false}
      historyHold={null}
      onUndo={vi.fn()}
      onRedo={vi.fn()}
      canAddPart
      onAddPart={vi.fn()}
      moveActive={false}
      moveBlocker={null}
      onMove={vi.fn()}
      copyBlocker={null}
      onCopy={vi.fn()}
      canMate={false}
      activeTool={null}
      onToggleTool={vi.fn()}
      canCheckInterference={false}
      interferenceBusy={false}
      onCheckInterference={vi.fn()}
      {...props}
    />,
  );
}

const exporter = () =>
  Promise.resolve({ blob: new Blob(["x"]), filename: "assembly.step" });

describe("AssemblyCommandBand — export", () => {
  it("offers export without visiting a Solve / Parts / Clash tab first", () => {
    renderBand({ exporter });
    expect(screen.getByTestId("assembly-export-band-controls")).toBeVisible();
    expect(screen.getByTestId("assembly-export-band-step")).toBeEnabled();
    expect(screen.getByTestId("assembly-export-band-stl")).toBeEnabled();
  });

  it("states why it is inert before any instance has a body", () => {
    renderBand({ exporter, exportDisabledReason: "No body" });
    const step = screen.getByTestId("assembly-export-band-step");
    // A gated band tool uses `aria-disabled`, never the native attribute, so
    // its reason stays hoverable and focusable (jest-dom's `toBeDisabled` reads
    // only the native one; Playwright's honours both).
    expect(step).toHaveAttribute("aria-disabled", "true");
    // The reason is the DESCRIPTION, not the name (A11Y-TOOLBTN-1): the cell is
    // called the same thing whether or not it is gated.
    expect(step).toHaveAccessibleName("Export STEP (exact B-rep)");
    expect(step).toHaveAccessibleDescription(/No body/);
  });

  it("renders no export group when the workspace supplies no exporter", () => {
    renderBand();
    expect(screen.queryByTestId("assembly-export-band-controls")).toBeNull();
  });
});

describe("AssemblyCommandBand — move", () => {
  it("says why Move is unavailable for a grounded component", () => {
    const onMove = vi.fn();
    renderBand({ moveBlocker: "Grounded components stay put.", onMove });
    const button = screen.getByTestId("move-instance");
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).toHaveAccessibleDescription("Grounded components stay put.");
    button.click();
    expect(onMove).not.toHaveBeenCalled();
  });

  it("leads the Mate group with Joint (J) and arms it", () => {
    const onToggleTool = vi.fn();
    renderBand({ canMate: true, onToggleTool });
    const joint = screen.getByTestId("mate-joint");
    expect(joint).toHaveAccessibleName(/Joint/);
    joint.click();
    expect(onToggleTool).toHaveBeenCalledWith("joint");
  });

  it("keeps the five relation mates, with their keys, under More", () => {
    const onToggleTool = vi.fn();
    renderBand({ canMate: true, onToggleTool });
    expect(screen.queryByTestId("mate-coincident")).toBeNull();
    fireEvent.click(screen.getByTestId("mate-more"));
    for (const tool of ["coincident", "concentric", "distance", "angle"]) {
      expect(screen.getByTestId(`mate-${tool}`)).toBeEnabled();
    }
    expect(screen.getByTestId("mate-lock")).toHaveTextContent("K");
    fireEvent.click(screen.getByTestId("mate-lock"));
    expect(onToggleTool).toHaveBeenCalledWith("lock");
  });

  it("marks More armed while one of its mates is the active tool", () => {
    renderBand({ canMate: true, activeTool: "distance" });
    expect(screen.getByTestId("mate-more")).toHaveAttribute(
      "data-active",
      "true",
    );
    expect(screen.getByTestId("mate-joint")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("reads armed while a move is open, and a press ends it", () => {
    const onMove = vi.fn();
    renderBand({ moveActive: true, moveBlocker: null, onMove });
    const button = screen.getByTestId("move-instance");
    expect(button).toHaveAttribute("aria-pressed", "true");
    button.click();
    expect(onMove).toHaveBeenCalledOnce();
  });
});

describe("AssemblyCommandBand — copy", () => {
  it("sits next to Move with its chord, and copies on a press", () => {
    const onCopy = vi.fn();
    renderBand({ onCopy });
    const button = screen.getByTestId("copy-instance");
    expect(button).toHaveAccessibleName(/^Copy — (Ctrl\+D|⌘D)$/);
    const move = screen.getByTestId("move-instance");
    const cells = [...document.querySelectorAll("[data-testid]")].map((el) =>
      el.getAttribute("data-testid"),
    );
    expect(cells.indexOf("copy-instance")).toBeGreaterThan(
      cells.indexOf(move.getAttribute("data-testid")),
    );
    expect(cells.indexOf("copy-instance")).toBeLessThan(
      cells.indexOf("mate-coincident"),
    );
    button.click();
    expect(onCopy).toHaveBeenCalledOnce();
  });

  it("says why it is unavailable with nothing selected", () => {
    const onCopy = vi.fn();
    renderBand({ copyBlocker: "Select a component to copy", onCopy });
    const button = screen.getByTestId("copy-instance");
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).toHaveAccessibleDescription("Select a component to copy");
    button.click();
    expect(onCopy).not.toHaveBeenCalled();
  });
});
