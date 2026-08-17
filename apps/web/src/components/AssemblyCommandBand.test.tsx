/**
 * The assembly command band's EXPORT group.
 *
 * The assembly repeated the part workspace's defect at a second address: its
 * only export affordance sat inside the Inspect panel, below a Solve / Parts /
 * Clash segmented control (`AssemblyInspectorPanel`), so the file went away with
 * the panel. Export now rides the band here too — same primitive, same last
 * position, same disabled-with-a-reason grammar (EXPORT-1).
 */
import { render, screen } from "@testing-library/react";
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
    expect(step).toHaveAccessibleName(/No body/);
  });

  it("renders no export group when the workspace supplies no exporter", () => {
    renderBand();
    expect(screen.queryByTestId("assembly-export-band-controls")).toBeNull();
  });
});
