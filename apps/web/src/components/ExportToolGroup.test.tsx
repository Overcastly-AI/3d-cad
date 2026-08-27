/**
 * EXPORT in the command band — the copy of the verb that survives a collapsed
 * panel (EXPORT-1).
 *
 * Three questions no pure test can reach. (1) Does the group actually write a
 * file, with the caller's filename? (2) Is a gated group INERT, not merely
 * grey — the same standard the panel strip is held to, since a band tool uses
 * `aria-disabled` (so its reason stays hoverable/focusable) and must therefore
 * swallow the activation itself? (3) Do the two mounts of export offer the SAME
 * formats — the cross-check that fails loudly if a format is added to one list
 * and not the other, which is the drift the shared catalogue exists to prevent.
 *
 * As of EXPORT-2 there is only ONE list (`ExportRow` reads the catalogue rather
 * than carrying a copy), so the cross-check can no longer fail by drift — it now
 * guards against a future mount deciding to filter the catalogue. It is kept for
 * that, and paired with an assertion of the literal format SET, because "both
 * surfaces agree" is satisfied just as happily by both being wrong.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EXPORT_FORMATS } from "../features/exportAction";

import { ExportRow } from "./ExportRow";
import { ExportToolGroup } from "./ExportToolGroup";

const downloadBlob = vi.hoisted(() => vi.fn());

vi.mock("../api/exportPart", async () => {
  const actual =
    await vi.importActual<typeof import("../api/exportPart")>(
      "../api/exportPart",
    );
  return { ...actual, downloadBlob };
});

function exporterFor(filename: string) {
  return vi.fn(async (format: string) => ({
    blob: new Blob(["ISO-10303-21;"]),
    filename: `${filename}.${format}`,
  }));
}

beforeEach(() => {
  downloadBlob.mockReset();
});

describe("ExportToolGroup", () => {
  it("writes the caller's file when the gate is open", async () => {
    const exporter = exporterFor("bracket");
    render(
      <ExportToolGroup
        testIdPrefix="part-export-band"
        exporter={exporter}
        state="ready"
      />,
    );

    expect(screen.getByTestId("part-export-band-controls")).toHaveAttribute(
      "data-export-state",
      "ready",
    );
    fireEvent.click(screen.getByTestId("part-export-band-step"));
    await waitFor(() => expect(downloadBlob).toHaveBeenCalledTimes(1));
    expect(downloadBlob.mock.calls[0]?.[1]).toBe("bracket.step");
  });

  it("is inert when gated — the click is swallowed, not just greyed", () => {
    const exporter = exporterFor("bracket");
    render(
      <ExportToolGroup
        testIdPrefix="part-export-band"
        exporter={exporter}
        disabledReason="Fillet1 failed"
        state="feature-error"
      />,
    );

    const step = screen.getByTestId("part-export-band-step");
    expect(step).toHaveAttribute("aria-disabled", "true");
    // The reason reaches BOTH pointer and keyboard: it is the accessible name,
    // not only a tooltip a mouse has to find.
    expect(step).toHaveAccessibleName(/Fillet1 failed/);

    fireEvent.click(step);
    fireEvent.click(screen.getByTestId("part-export-band-stl"));
    expect(exporter).not.toHaveBeenCalled();
    expect(downloadBlob).not.toHaveBeenCalled();
  });

  it("says a rolled-back file will be marked partial before the click", () => {
    render(
      <ExportToolGroup
        testIdPrefix="part-export-band"
        exporter={exporterFor("bracket")}
        partial
        state="partial"
      />,
    );
    const step = screen.getByTestId("part-export-band-step");
    // Enabled, but qualified — and the qualification is in the NAME, so it is
    // not hover-only (a `ToolButton` describes by caption only while disabled).
    expect(step).toBeEnabled();
    expect(step).toHaveAccessibleName(/marks the file partial/);
  });

  it("reports a failed write where a screen reader will hear it", async () => {
    const exporter = vi.fn(() => Promise.reject(new Error("gateway down")));
    render(
      <ExportToolGroup
        testIdPrefix="assembly-export-band"
        exporter={exporter}
        state="ready"
      />,
    );

    fireEvent.click(screen.getByTestId("assembly-export-band-step"));
    const alert = await screen.findByTestId("assembly-export-band-error");
    expect(alert).toHaveTextContent(/STEP export failed/);
    expect(downloadBlob).not.toHaveBeenCalled();
  });

  it("offers all four export formats, named", () => {
    // The cross-check below only proves the two surfaces AGREE; both could
    // agree on a list missing a format the backend supports. This is the
    // independent derivation — the literal set, asserted once.
    render(
      <ExportToolGroup
        testIdPrefix="part-export-band"
        exporter={exporterFor("bracket")}
      />,
    );
    expect(EXPORT_FORMATS.map((entry) => entry.format)).toEqual([
      "step",
      "stl",
      "3mf",
      "glb",
    ]);
    for (const format of ["step", "stl", "3mf", "glb"]) {
      expect(
        screen.getByTestId(`part-export-band-${format}`),
      ).toBeInTheDocument();
    }
    // The two new cells say what the format is FOR, not just what it is
    // called — "3MF" and "GLB" mean nothing to someone who has only ever
    // exported STL.
    expect(screen.getByTestId("part-export-band-3mf")).toHaveAccessibleName(
      /slicers/,
    );
    expect(screen.getByTestId("part-export-band-glb")).toHaveAccessibleName(
      /viewers/,
    );
  });

  it("offers exactly the formats the panel strip offers", () => {
    const { unmount } = render(
      <ExportToolGroup
        testIdPrefix="x-band"
        exporter={exporterFor("bracket")}
      />,
    );
    const band = screen
      .getAllByRole("button")
      .map((el) => el.getAttribute("data-testid")?.replace("x-band-", ""))
      .sort();
    unmount();

    render(
      <ExportRow testIdPrefix="x-row" exporter={exporterFor("bracket")} />,
    );
    const row = screen
      .getAllByRole("button")
      .map((el) => el.getAttribute("data-testid")?.replace("x-row-", ""))
      .sort();

    // If this fails, a format was added to ONE of the two export surfaces:
    // fold `ExportRow`'s `FORMATS` into `features/exportAction.EXPORT_FORMATS`
    // rather than copying the new entry across (see that module's note).
    expect(band).toEqual(row);
  });
});
