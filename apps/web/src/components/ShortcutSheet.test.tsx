/**
 * The key card (UI-REVIEW F4) — that `?` reaches it, that it draws what the
 * registry holds, and that it does not trap a user who opened it by accident.
 *
 * WHAT the rows say is `shortcuts/registry.test.ts`'s job (it is derived from
 * the handlers' own tables); this file only checks that the derivation is
 * actually rendered and that the surface behaves.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { shortcutGroups } from "../shortcuts/registry";
import { ShortcutSheetHost } from "./ShortcutSheet";

function pressQuestionMark(): void {
  fireEvent.keyDown(window, { key: "?" });
}

describe("opening", () => {
  it("is closed until ? is pressed, and closed again by Escape", () => {
    render(<ShortcutSheetHost />);
    expect(screen.queryByTestId("shortcut-sheet")).not.toBeInTheDocument();

    pressQuestionMark();
    const sheet = screen.getByTestId("shortcut-sheet");
    expect(sheet).toBeInTheDocument();
    expect(sheet).toHaveAttribute("role", "dialog");

    fireEvent.keyDown(sheet, { key: "Escape" });
    expect(screen.queryByTestId("shortcut-sheet")).not.toBeInTheDocument();
  });

  it("ignores ? typed into a field", () => {
    render(
      <>
        <input data-testid="field" />
        <ShortcutSheetHost />
      </>,
    );
    const field = screen.getByTestId("field");
    field.focus();
    fireEvent.keyDown(field, { key: "?" });
    expect(screen.queryByTestId("shortcut-sheet")).not.toBeInTheDocument();
  });

  it("closes on the Close verb and on the ground behind it", () => {
    render(<ShortcutSheetHost />);
    pressQuestionMark();
    fireEvent.click(screen.getByTestId("shortcut-sheet-close"));
    expect(screen.queryByTestId("shortcut-sheet")).not.toBeInTheDocument();

    pressQuestionMark();
    fireEvent.click(screen.getByTestId("shortcut-sheet-backdrop"));
    expect(screen.queryByTestId("shortcut-sheet")).not.toBeInTheDocument();
  });

  it("a click inside does NOT dismiss it", () => {
    render(<ShortcutSheetHost />);
    pressQuestionMark();
    fireEvent.click(screen.getAllByTestId("shortcut-row")[0]!);
    expect(screen.getByTestId("shortcut-sheet")).toBeInTheDocument();
  });
});

describe("what it draws", () => {
  it("renders every group and every row the registry holds", () => {
    render(<ShortcutSheetHost />);
    pressQuestionMark();
    const groups = shortcutGroups();
    expect(screen.getAllByTestId("shortcut-group")).toHaveLength(groups.length);
    expect(screen.getAllByTestId("shortcut-row")).toHaveLength(
      groups.reduce((total, entry) => total + entry.shortcuts.length, 0),
    );
    for (const entry of groups) {
      expect(screen.getByText(entry.title)).toBeInTheDocument();
    }
  });

  it("advertises its own key, so the reference is self-describing", () => {
    render(<ShortcutSheetHost />);
    pressQuestionMark();
    expect(screen.getByTestId("shortcut-sheet")).toHaveTextContent(
      "Show this reference",
    );
  });

  // FB-11. The founder tests from a Codespace, so "is that fixed in the build
  // you were on?" is currently unanswerable from either side. Assert the stamp
  // is REACHABLE and READABLE — a stamp that renders "Build undefined" answers
  // the question wrongly, which is worse than not shipping one.
  it("carries a readable build stamp", () => {
    render(<ShortcutSheetHost />);
    pressQuestionMark();
    const stamp = screen.getByTestId("build-stamp");
    expect(stamp).toHaveTextContent(/^Build \S/);
    expect(stamp.textContent).not.toMatch(/undefined|null|NaN/);
  });
});
