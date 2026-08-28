/**
 * The part command band's EXPORT group — the fix for the defect the founder
 * named on 2026-08-17: *"the button to export should not be with all the mass
 * properties."*
 *
 * The band question these tests answer is placement, not plumbing (the group
 * itself is covered in `ExportToolGroup.test.tsx`): export must be a child of
 * the always-present command surface rather than of a collapsible readout
 * panel, it must carry the workspace's real gate reason, and — like every other
 * tool in this band — it must hold with the ONE honest lock reason while a
 * command is open, so no click can discard an in-progress selection.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CreateStrip } from "./CreateStrip";

function renderStrip(props: Partial<Parameters<typeof CreateStrip>[0]> = {}) {
  return render(
    <CreateStrip
      treeReady
      onNewSketch={vi.fn()}
      canExtrude={false}
      onNewExtrude={vi.fn()}
      canRevolve={false}
      onNewRevolve={vi.fn()}
      canSweep={false}
      onNewSweep={vi.fn()}
      canLoft={false}
      onNewLoft={vi.fn()}
      {...props}
    />,
  );
}

const exporter = () =>
  Promise.resolve({ blob: new Blob(["x"]), filename: "part.step" });

describe("CreateStrip — export", () => {
  it("puts EXPORT in the band, not in a panel", () => {
    renderStrip({ onExport: exporter, exportState: "ready" });

    const group = screen.getByTestId("part-export-band-controls");
    expect(group).toBeVisible();
    expect(group).toHaveAttribute("data-export-state", "ready");
    // Inside the band's own tool-group container — i.e. it cannot be collapsed
    // away with the Inspector, which is the whole point of the ticket.
    expect(screen.getByTestId("tool-groups")).toContainElement(group);
    expect(screen.getByTestId("part-export-band-step")).toBeEnabled();
    expect(screen.getByTestId("part-export-band-stl")).toBeEnabled();
  });

  it("carries the workspace's export gate reason", () => {
    renderStrip({
      onExport: exporter,
      exportDisabledReason: "No body",
      exportState: "no-body",
    });

    const step = screen.getByTestId("part-export-band-step");
    // A gated band tool uses `aria-disabled`, never the native attribute, so
    // its reason stays hoverable and focusable (jest-dom's `toBeDisabled` reads
    // only the native one; Playwright's honours both).
    expect(step).toHaveAttribute("aria-disabled", "true");
    // The reason is the DESCRIPTION, not the name (A11Y-TOOLBTN-1): the cell is
    // called the same thing whether or not it is gated.
    expect(step).toHaveAccessibleName("Export STEP (exact B-rep)");
    expect(step).toHaveAccessibleDescription(/No body/);
  });

  it("holds with the open command's reason, like every other band tool", () => {
    renderStrip({
      onExport: exporter,
      activeCommand: "Fillet",
      exportState: "ready",
    });

    const step = screen.getByTestId("part-export-band-step");
    // A gated band tool uses `aria-disabled`, never the native attribute, so
    // its reason stays hoverable and focusable (jest-dom's `toBeDisabled` reads
    // only the native one; Playwright's honours both).
    expect(step).toHaveAttribute("aria-disabled", "true");
    expect(step).toHaveAccessibleName("Export STEP (exact B-rep)");
    expect(step).toHaveAccessibleDescription(/Finish Fillet first/);
  });

  it("renders no export group at all when the workspace supplies no exporter", () => {
    renderStrip();
    expect(screen.queryByTestId("part-export-band-controls")).toBeNull();
  });
});
