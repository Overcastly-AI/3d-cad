/**
 * The EXPORT strip of the part workspace — the cell where a wrong label becomes
 * a wrong FILE.
 *
 * AUDIT-ENGINEERING J2 named this the worst of the batch: the strict-prefix rule
 * returns a `mesh_glb_id` for the last-good PREFIX, so `hasBody` was true over a
 * truncated rebuild and the strip said "Ready". A user reads "Ready", clicks
 * STEP, and receives a solid that is missing every feature from the failure
 * onward — with nothing on the file or the screen to say so.
 *
 * These tests drive the STRIP, not the gate function (that is unit-tested in
 * `features/partBuild.test.ts`): the click has to be inert when blocked, and the
 * download that IS allowed has to arrive named `-partial`.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  brokenFillet,
  cleanCube,
  rolledBack,
  sketchOnly,
} from "../test/partBuildFixture";
import { PartExportControls } from "./PartExportControls";

const exportPartTree = vi.hoisted(() => vi.fn());
const downloadBlob = vi.hoisted(() => vi.fn());

vi.mock("../api/exportPart", async () => {
  // The filename marker itself stays REAL — it is the thing under test here.
  const actual =
    await vi.importActual<typeof import("../api/exportPart")>(
      "../api/exportPart",
    );
  return { ...actual, exportPartTree, downloadBlob };
});

beforeEach(() => {
  exportPartTree.mockReset();
  downloadBlob.mockReset();
  exportPartTree.mockResolvedValue({
    blob: new Blob(["ISO-10303-21;"]),
    filename: "part-4f2c.step",
  });
});

describe("PartExportControls", () => {
  it("writes the server's own filename for a whole, current body", async () => {
    render(<PartExportControls partId="p1" build={cleanCube()} />);
    expect(screen.getByTestId("part-export-status")).toHaveTextContent("Ready");
    expect(screen.getByTestId("part-export-controls")).toHaveAttribute(
      "data-export-state",
      "ready",
    );

    fireEvent.click(screen.getByTestId("part-export-step"));
    await waitFor(() => expect(downloadBlob).toHaveBeenCalledTimes(1));
    expect(downloadBlob.mock.calls[0]?.[1]).toBe("part-4f2c.step");
  });

  it("refuses to export a broken tree — and the click is inert, not just grey", async () => {
    render(<PartExportControls partId="p1" build={brokenFillet()} />);
    expect(screen.getByTestId("part-export-controls")).toHaveAttribute(
      "data-export-state",
      "feature-error",
    );
    expect(screen.getByTestId("part-export-status")).toHaveTextContent(
      "Fillet1 failed",
    );

    fireEvent.click(screen.getByTestId("part-export-step"));
    fireEvent.click(screen.getByTestId("part-export-stl"));
    // The whole point: no request, no file, no silently partial STEP.
    expect(exportPartTree).not.toHaveBeenCalled();
    expect(downloadBlob).not.toHaveBeenCalled();
  });

  it("marks a rolled-back export partial in the FILENAME, not only on screen", async () => {
    render(<PartExportControls partId="p1" build={rolledBack()} />);
    expect(screen.getByTestId("part-export-status")).toHaveTextContent(
      "Partial",
    );

    fireEvent.click(screen.getByTestId("part-export-step"));
    await waitFor(() => expect(downloadBlob).toHaveBeenCalledTimes(1));
    // A file outlives the screen that explained it.
    expect(downloadBlob.mock.calls[0]?.[1]).toBe("part-4f2c-partial.step");
  });

  it("keeps the sketch-only tree's honest No body state (and no notice to add)", () => {
    render(<PartExportControls partId="p1" build={sketchOnly()} />);
    expect(screen.getByTestId("part-export-status")).toHaveTextContent(
      "No body",
    );
    expect(screen.getByTestId("part-export-step")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.queryByTestId("part-export-notice")).toBeNull();
  });
});
