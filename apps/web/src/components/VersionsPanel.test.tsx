/**
 * The Versions panel (LOFT-VERSIONS): newest first, each row's number, name,
 * age and author, and a Restore that asks once and says it can be undone.
 */
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PartVersion } from "../api/versions";
import {
  VersionsPanel,
  versionAge,
  type VersionsPanelProps,
} from "./VersionsPanel";

const NOW = Date.parse("2026-10-08T12:00:00Z");

function version(
  seq: number,
  overrides: Partial<PartVersion> = {},
): PartVersion {
  return {
    seq,
    name: `v${seq}`,
    message: "",
    author: null,
    created_at: "2026-10-08T11:55:00Z",
    feature_count: 2,
    tree_sha256: "0".repeat(64),
    ...overrides,
  };
}

function renderPanel(props: Partial<VersionsPanelProps> = {}) {
  const onRestore = vi.fn();
  const onSaveVersion = vi.fn();
  const onClose = vi.fn();
  const view = render(
    <VersionsPanel
      partName="Bracket"
      versions={[
        version(1, { created_at: "2026-09-01T09:00:00Z", author: "Ada" }),
        version(2, { message: "Deeper pocket" }),
      ]}
      loadError={null}
      restoringSeq={null}
      restoreError={null}
      onRestore={onRestore}
      onSaveVersion={onSaveVersion}
      onClose={onClose}
      now={NOW}
      {...props}
    />,
  );
  return { onRestore, onSaveVersion, onClose, ...view };
}

describe("VersionsPanel", () => {
  it("lists versions newest first with seq, name, age and author", () => {
    renderPanel();
    expect(screen.getByRole("dialog", { name: /Versions/ })).toHaveAttribute(
      "aria-modal",
      "true",
    );
    const rows = screen.getAllByTestId("version-row");
    expect(rows.map((row) => row.getAttribute("data-seq"))).toEqual(["2", "1"]);
    const [newest, oldest] = rows as [HTMLElement, HTMLElement];
    expect(within(newest).getByTestId("version-seq")).toHaveTextContent("V2");
    expect(within(newest).getByTestId("version-name")).toHaveTextContent("v2");
    expect(within(newest).getByTestId("version-age")).toHaveTextContent(
      "5 min ago",
    );
    expect(within(newest).getByTestId("version-message")).toHaveTextContent(
      "Deeper pocket",
    );
    expect(within(newest).queryByTestId("version-author")).toBeNull();
    // Older than a week: its date, not a count of days.
    expect(within(oldest).getByTestId("version-age")).toHaveTextContent(
      "2026-09-01",
    );
    expect(within(oldest).getByTestId("version-author")).toHaveTextContent(
      "Ada",
    );
  });

  it("asks before restoring, says Undo brings the tree back, then restores", () => {
    const { onRestore } = renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Restore V1, v1" }));
    expect(onRestore).not.toHaveBeenCalled();
    const confirm = screen.getByTestId("version-confirm");
    expect(confirm).toHaveTextContent(/Undo/);
    expect(confirm).toHaveTextContent(/brings the current tree back/);
    const action = within(confirm).getByTestId("version-restore-confirm");
    expect(action).toHaveFocus();
    fireEvent.click(action);
    expect(onRestore).toHaveBeenCalledWith(1);
  });

  it("Escape backs out of the confirm first, then closes the panel", () => {
    const { onClose, onRestore } = renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Restore V2, v2" }));
    const panel = screen.getByTestId("versions-panel");
    fireEvent.keyDown(panel, { key: "Escape" });
    expect(screen.queryByTestId("version-confirm")).toBeNull();
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.keyDown(panel, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onRestore).not.toHaveBeenCalled();
  });

  it("Cancel in the confirm puts focus back on the row's Restore", () => {
    vi.useFakeTimers();
    try {
      renderPanel();
      const restore = screen.getByRole("button", { name: "Restore V2, v2" });
      fireEvent.click(restore);
      fireEvent.click(screen.getByTestId("version-restore-cancel"));
      act(() => {
        vi.runAllTimers();
      });
      expect(
        screen.getByRole("button", { name: "Restore V2, v2" }),
      ).toHaveFocus();
    } finally {
      vi.useRealTimers();
    }
  });

  it("Save version opens the dialog; Close and the backdrop close", () => {
    const { onSaveVersion, onClose } = renderPanel();
    fireEvent.click(screen.getByTestId("versions-save"));
    expect(onSaveVersion).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId("versions-close"));
    fireEvent.click(screen.getByTestId("versions-backdrop"));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("Ctrl+S inside the panel opens Save version", () => {
    const { onSaveVersion } = renderPanel();
    fireEvent.keyDown(screen.getByTestId("versions-panel"), {
      key: "s",
      ctrlKey: true,
    });
    expect(onSaveVersion).toHaveBeenCalledTimes(1);
  });

  it("holds Restore with the reason while the tree is busy", () => {
    renderPanel({
      restoreBlockedReason: "Close the open command to restore a version.",
    });
    expect(screen.getByTestId("versions-blocked")).toHaveTextContent(
      "Close the open command",
    );
    for (const button of screen.getAllByTestId("version-restore")) {
      expect(button).toBeDisabled();
    }
  });

  it("says when there are none, when loading, and when a restore failed", () => {
    const { rerender, onRestore, onSaveVersion, onClose } = renderPanel({
      versions: [],
    });
    expect(screen.getByTestId("versions-empty")).toHaveTextContent(
      "No versions yet",
    );
    const base = {
      partName: "Bracket",
      loadError: null,
      restoringSeq: null,
      onRestore,
      onSaveVersion,
      onClose,
      now: NOW,
    };
    rerender(
      <VersionsPanel {...base} versions={undefined} restoreError={null} />,
    );
    expect(screen.getByTestId("versions-loading")).toBeInTheDocument();
    rerender(
      <VersionsPanel
        {...base}
        versions={[version(1)]}
        restoreError="The version could not be restored."
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "could not be restored",
    );
  });
});

describe("versionAge", () => {
  it("reads recent stamps relatively and old ones by date", () => {
    expect(versionAge("2026-10-08T11:59:50Z", NOW)).toBe("just now");
    expect(versionAge("2026-10-08T09:00:00Z", NOW)).toBe("3 h ago");
    expect(versionAge("2026-08-01T00:00:00Z", NOW)).toBe("2026-08-01");
    expect(versionAge("not a date", NOW)).toBe("—");
  });
});
