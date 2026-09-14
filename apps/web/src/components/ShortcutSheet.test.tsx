/**
 * The key card (UI-REVIEW F4) — that `?` reaches it, that it draws what the
 * registry holds, and that it does not trap a user who opened it by accident.
 *
 * WHAT the rows say is `shortcuts/registry.test.ts`'s job (it is derived from
 * the handlers' own tables); this file only checks that the derivation is
 * actually rendered and that the surface behaves.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resetModalGateAlarmForTest } from "../lib/modalGate";
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

/**
 * IT HOLDS THE KEYBOARD (W2 review, blocking finding).
 *
 * The card is `aria-modal="true"`, which promises a screen-reader user that
 * everything outside it is inert, and for as long as it has shipped that was
 * false: every workspace shortcut stayed live behind it. The path is the card's
 * own — read the row that says `E — Extrude`, press `E`, and the editor opened
 * BEHIND the sheet.
 *
 * The spy here is a raw `window.addEventListener("keydown", …)`, which is the
 * shape of the real leak (`viewport/ProposalNote.tsx` bound exactly that) and
 * not a stand-in for it.
 */
describe("while the card is up", () => {
  function spyOnTheWorkspace(): ReturnType<typeof vi.fn> {
    const seen = vi.fn();
    window.addEventListener("keydown", seen, true);
    spies.push(() => window.removeEventListener("keydown", seen, true));
    return seen;
  }

  const spies: Array<() => void> = [];
  afterEach(() => {
    for (const release of spies.splice(0)) release();
    // The alarm reports each offender ONCE per page, so a case that asserts it
    // is quiet has to start from a cleared memory — otherwise an earlier case
    // in this file could silence it and the assertion would pass for the wrong
    // reason.
    resetModalGateAlarmForTest();
    vi.restoreAllMocks();
  });

  it("a workspace shortcut gets nothing — not even the one the card teaches", () => {
    render(<ShortcutSheetHost />);
    pressQuestionMark();
    expect(screen.getByTestId("shortcut-sheet")).toBeInTheDocument();
    // Attached AFTER the card is up, so the `?` that opened it is not one of
    // the calls being counted — and attached at window CAPTURE, the position a
    // `stopPropagation()` inside the panel could never have reached.
    const workspace = spyOnTheWorkspace();
    // The whole `? then E` path, in one line.
    fireEvent.keyDown(screen.getByTestId("shortcut-sheet"), { key: "e" });
    expect(workspace).not.toHaveBeenCalled();

    // …and the workspace gets its keys back the moment the card closes, which
    // is what makes the assertion above about the CARD rather than about a
    // listener that was never reachable.
    fireEvent.keyDown(screen.getByTestId("shortcut-sheet"), { key: "Escape" });
    expect(screen.queryByTestId("shortcut-sheet")).not.toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: "e" });
    expect(workspace).toHaveBeenCalledTimes(1);
  });

  it("Enter on its Close button is the Close button's, and nobody else's", () => {
    render(<ShortcutSheetHost />);
    pressQuestionMark();
    const workspace = spyOnTheWorkspace();
    const close = screen.getByTestId("shortcut-sheet-close");
    close.focus();
    const event = new KeyboardEvent("keydown", {
      key: "Enter",
      bubbles: true,
      cancelable: true,
    });
    close.dispatchEvent(event);
    expect(workspace).not.toHaveBeenCalled();
    // NOT cancelled: the gate stops propagation and never the default action,
    // so the browser still fires this button's click. Cancelling it is what
    // made the proposal note's binding look like a broken button.
    expect(event.defaultPrevented).toBe(false);
  });

  it("closes on a second ?, which only the layer can do now", () => {
    render(<ShortcutSheetHost />);
    pressQuestionMark();
    fireEvent.keyDown(screen.getByTestId("shortcut-sheet"), { key: "?" });
    expect(screen.queryByTestId("shortcut-sheet")).not.toBeInTheDocument();
  });

  it("the gate's own alarm stays quiet, which is the second reading", () => {
    // Independently derived: the cases above say the card took the keyboard,
    // this one says the GATE agrees it did. `modalGate` shouts when an
    // `aria-modal` element is on screen while a keystroke reaches the
    // workspace, so a silent alarm here and a loud one in the gate's own test
    // are the same fact read from two sides.
    resetModalGateAlarmForTest();
    const complaint = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ShortcutSheetHost />);
    pressQuestionMark();
    fireEvent.keyDown(screen.getByTestId("shortcut-sheet"), { key: "e" });
    expect(complaint).not.toHaveBeenCalled();
  });
});
