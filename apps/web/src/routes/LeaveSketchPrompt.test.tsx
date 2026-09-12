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
    setup({ saving: true });
    expect(screen.getByTestId("leave-sketch-save")).toBeDisabled();
    expect(screen.getByTestId("leave-sketch-save")).toHaveTextContent("Saving");
    // …but Stay is never disabled: the user must always be able to go back.
    expect(screen.getByTestId("leave-sketch-stay")).toBeEnabled();
  });
});
