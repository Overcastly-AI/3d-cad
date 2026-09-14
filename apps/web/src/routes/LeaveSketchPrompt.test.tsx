/**
 * The exit ticket (FLOW-A2) — the three things a keyboard cannot prove in e2e,
 * and the one thing the copy must never stop doing.
 *
 * The mandate's failure case (FB-13) is an exit whose consequence you learn
 * afterwards, so the load-bearing assertion here is that EVERY rung carries a
 * consequence in words. A test that only checked the verbs would pass on a
 * bare OK/Cancel box, which is the defect this surface exists to remove.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LeaveSketchPrompt } from "./LeaveSketchPrompt";

/**
 * The workspace's own shortcuts, in the two positions this app registers them:
 * `SketchScene`'s draw-dimension Enter is a bubble-phase window listener,
 * `FeatureTreePanel`'s drag-escape is a capture-phase one. Both are attached
 * here AFTER the gate module is loaded — the position every real listener is
 * in, since they all register inside effects.
 */
function workspaceShortcuts() {
  const capture = vi.fn();
  const bubble = vi.fn();
  window.addEventListener("keydown", capture, true);
  window.addEventListener("keydown", bubble);
  return {
    capture,
    bubble,
    release: () => {
      window.removeEventListener("keydown", capture, true);
      window.removeEventListener("keydown", bubble);
    },
  };
}

function setup(
  overrides: Partial<Parameters<typeof LeaveSketchPrompt>[0]> = {},
) {
  const handlers = {
    onSaveAndLeave: vi.fn(),
    onLeave: vi.fn(),
    onStay: vi.fn(),
  };
  render(
    <LeaveSketchPrompt
      partName="Bracket"
      destination="Parts"
      entityCount={4}
      constraintCount={9}
      draftHeld
      saving={false}
      error={null}
      {...handlers}
      {...overrides}
    />,
  );
  return handlers;
}

/** The same prompt, with the props it is re-rendered with (saving turns true). */
function setupRerenderable() {
  const handlers = {
    onSaveAndLeave: vi.fn(),
    onLeave: vi.fn(),
    onStay: vi.fn(),
  };
  const props = {
    partName: "Bracket",
    destination: "Parts",
    entityCount: 4,
    constraintCount: 9,
    draftHeld: true,
    saving: false,
    error: null,
    ...handlers,
  };
  const view = render(<LeaveSketchPrompt {...props} />);
  return {
    handlers,
    rerender: (next: Partial<typeof props>) =>
      view.rerender(<LeaveSketchPrompt {...props} {...next} />),
  };
}

describe("the exit ticket", () => {
  it("counts the work at stake and names the part and the destination", () => {
    setup();
    expect(screen.getByTestId("leave-sketch-entities")).toHaveTextContent("4");
    expect(screen.getByTestId("leave-sketch-constraints")).toHaveTextContent(
      "9",
    );
    expect(screen.getByTestId("leave-sketch-destination")).toHaveTextContent(
      "Parts",
    );
    expect(screen.getByTestId("leave-sketch-prompt")).toHaveTextContent(
      "None of it is in Bracket yet",
    );
  });

  it("says what EVERY rung does, not just the recommended one", () => {
    setup();
    // The FB-13 assertion. Each of these is the consequence, not the verb — a
    // prompt that lost them would still pass a verb-only check.
    expect(screen.getByTestId("leave-sketch-save")).toHaveTextContent(
      "adds them to Bracket, then goes to Parts",
    );
    expect(screen.getByTestId("leave-sketch-leave")).toHaveTextContent(
      "restored when you reopen this part",
    );
    expect(screen.getByTestId("leave-sketch-stay")).toHaveTextContent(
      "nothing changes",
    );
  });

  it("is an alert dialog that opens with the recommended rung focused", () => {
    setup();
    const panel = screen.getByTestId("leave-sketch-prompt");
    expect(panel).toHaveAttribute("role", "alertdialog");
    expect(panel).toHaveAttribute("aria-modal", "true");
    expect(screen.getByTestId("leave-sketch-save")).toHaveFocus();
  });

  it("treats Escape and a click on the ground as STAY, never as leave", () => {
    const handlers = setup();
    fireEvent.keyDown(screen.getByTestId("leave-sketch-prompt"), {
      key: "Escape",
    });
    expect(handlers.onStay).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId("leave-sketch-backdrop"));
    expect(handlers.onStay).toHaveBeenCalledTimes(2);
    // The ambiguous-exit rule: the safe dismissals must not do either of the
    // other two things.
    expect(handlers.onLeave).not.toHaveBeenCalled();
    expect(handlers.onSaveAndLeave).not.toHaveBeenCalled();
  });

  it("routes each rung to its own answer", () => {
    const handlers = setup();
    fireEvent.click(screen.getByTestId("leave-sketch-save"));
    fireEvent.click(screen.getByTestId("leave-sketch-leave"));
    expect(handlers.onSaveAndLeave).toHaveBeenCalledTimes(1);
    expect(handlers.onLeave).toHaveBeenCalledTimes(1);
  });

  it("holds the prompt open on a failed save and keeps the other exits usable", () => {
    const handlers = setup({
      error: "The sketch could not be saved — reload and try again.",
    });
    expect(screen.getByTestId("leave-sketch-error")).toHaveTextContent(
      "leave without saving to keep it as a draft",
    );
    // No dead end: the way out still works while the reason is on screen.
    fireEvent.click(screen.getByTestId("leave-sketch-leave"));
    expect(handlers.onLeave).toHaveBeenCalledTimes(1);
  });

  it("reads in the singular for a one-entity sketch", () => {
    setup({ entityCount: 1, constraintCount: 1 });
    const panel = screen.getByTestId("leave-sketch-prompt");
    expect(panel).toHaveTextContent("entity");
    expect(panel).not.toHaveTextContent("entities");
    expect(screen.getByTestId("leave-sketch-save")).toHaveTextContent(
      "adds it to Bracket",
    );
  });

  it("stops promising a rescue the browser refused to hold", () => {
    // Quota, private mode, storage switched off. A middle rung that still said
    // "restored when you reopen this part" would be a brand-new ambiguous exit
    // inside the fix for ambiguous exits.
    setup({ draftHeld: false });
    const leave = screen.getByTestId("leave-sketch-leave");
    expect(leave).toHaveTextContent("Leave and lose them");
    expect(leave).toHaveTextContent("gone for good");
    expect(leave).not.toHaveTextContent("restored when you reopen this part");
  });

  it("blocks the save rung while the save is in flight", () => {
    const handlers = setup({ saving: true });
    const save = screen.getByTestId("leave-sketch-save");
    // `aria-disabled`, not `disabled` — see below for what the native attribute
    // did to focus. The refusal is still real: the rung does not fire.
    expect(save).toHaveAttribute("aria-disabled", "true");
    expect(save).toHaveTextContent("Saving");
    fireEvent.click(save);
    expect(handlers.onSaveAndLeave).not.toHaveBeenCalled();
    // …but Stay is never disabled: the user must always be able to go back.
    expect(screen.getByTestId("leave-sketch-stay")).toBeEnabled();
  });

  it("never puts the native disabled attribute on a focused rung (W0 finding 2)", () => {
    // A native `disabled` on the element that HAS focus blurs it to
    // `document.body`, and the save rung is the focused one the instant a save
    // begins — so the keyboard user was left with a dialog they could neither
    // dismiss nor act on for as long as the create round trip took. Measured by
    // the reviewer in real Chromium: `activeElement after disable: BODY`,
    // keydowns the panel handler saw: [].
    //
    // THIS CASE ASSERTS THE MECHANISM, NOT THE FOCUS, and that is deliberate:
    // JSDOM DOES NOT MOVE FOCUS WHEN AN ELEMENT IS DISABLED (measured —
    // `activeElement after disable: BUTTON`), so an `expect(activeElement).not
    // .toBe(document.body)` here would pass against the defect and be worth
    // nothing. The focus itself is measured in the real browser, in
    // `sketch-exit-guard.spec.ts` ("a save in flight cannot blur the dialog").
    const { rerender, handlers } = setupRerenderable();
    expect(screen.getByTestId("leave-sketch-save")).toHaveFocus();
    rerender({ saving: true });
    const panel = screen.getByTestId("leave-sketch-prompt");
    expect(panel.querySelectorAll("button[disabled]")).toHaveLength(0);
    // Still refused, and still reachable: the refusal is in the handler.
    fireEvent.click(screen.getByTestId("leave-sketch-save"));
    expect(handlers.onSaveAndLeave).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByTestId("leave-sketch-save"), {
      key: "Escape",
    });
    expect(handlers.onStay).toHaveBeenCalledTimes(1);
  });

  it("takes the keyboard away from the workspace (W0 finding 1)", () => {
    // THE BLOCKING DEFECT: with the draw-dimension strip armed behind the
    // dialog, Enter on this very button ran `SketchScene`'s window listener,
    // which applied the dimension and `preventDefault()`ed the activation — so
    // the button never fired. `Ctrl+Z` leaked the same way to `SketchStrip` and
    // undid in the sketch behind the modal.
    const handlers = setup();
    const shortcuts = workspaceShortcuts();
    const save = screen.getByTestId("leave-sketch-save");
    const enter = new KeyboardEvent("keydown", {
      key: "Enter",
      bubbles: true,
      cancelable: true,
    });
    save.dispatchEvent(enter);
    fireEvent.keyDown(save, { key: "z", ctrlKey: true });
    shortcuts.release();
    expect(shortcuts.capture).not.toHaveBeenCalled();
    expect(shortcuts.bubble).not.toHaveBeenCalled();
    // …and the dialog did not cancel the button's own activation either: the
    // gate stops propagation, never the default action.
    expect(enter.defaultPrevented).toBe(false);
    expect(handlers.onStay).not.toHaveBeenCalled();
  });

  it("pulls focus back when a key arrives from outside the dialog", () => {
    const handlers = setup();
    const stray = document.body.appendChild(document.createElement("input"));
    fireEvent.keyDown(stray, { key: "a" });
    expect(screen.getByTestId("leave-sketch-save")).toHaveFocus();
    expect(handlers.onLeave).not.toHaveBeenCalled();
    stray.remove();
  });
});
