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
 * EXPORT-3 changed the answer for the middle case: refusing the failure was
 * the SILENT option, not the honest one. The strip now writes the last good
 * body and says so three times over — the cell, the notice, the filename. What
 * it must never do is write a prefix WITHOUT saying so, and it must still
 * refuse when nothing built at all.
 *
 * These tests drive the STRIP, not the gate function (that is unit-tested in
 * `features/partBuild.test.ts`): the click has to be inert when blocked, and the
 * download that IS allowed has to arrive named `-partial`.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  brokenBeforeAnyBody,
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

  it("writes the last good body of a BROKEN tree, named partial (EXPORT-3)", async () => {
    render(<PartExportControls partId="p1" build={brokenFillet()} />);
    expect(screen.getByTestId("part-export-controls")).toHaveAttribute(
      "data-export-state",
      "feature-error",
    );
    // The word, and the sentence that makes it actionable — the truncation
    // point by NAME, so a user about to send this to a machinist knows what
    // they are sending.
    expect(screen.getByTestId("part-export-status")).toHaveTextContent(
      "Partial",
    );
    expect(screen.getByTestId("part-export-notice")).toHaveTextContent(
      "Fillet1 failed, so the file stops at Extrude1 — 1 feature is excluded. " +
        "Its name will say partial.",
    );

    fireEvent.click(screen.getByTestId("part-export-step"));
    await waitFor(() => expect(downloadBlob).toHaveBeenCalledTimes(1));
    // The claim rides the FILE, not only the screen it was explained on.
    expect(downloadBlob.mock.calls[0]?.[1]).toBe("part-4f2c-partial.step");
  });

  it("still REFUSES when the failure left no body behind it — the control", async () => {
    // Acceptance criterion 3, at the component tier. Without this case,
    // "export the last good body" degenerates into "always export" and every
    // other test in this file still passes.
    render(<PartExportControls partId="p1" build={brokenBeforeAnyBody()} />);
    expect(screen.getByTestId("part-export-controls")).toHaveAttribute(
      "data-export-state",
      "no-body",
    );
    expect(screen.getByTestId("part-export-status")).toHaveTextContent(
      "Fillet1 failed",
    );
    expect(screen.getByTestId("part-export-notice")).toHaveTextContent(
      "Nothing was built before Fillet1",
    );

    fireEvent.click(screen.getByTestId("part-export-step"));
    fireEvent.click(screen.getByTestId("part-export-stl"));
    // No request, no file — and the server would have refused too (422).
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
