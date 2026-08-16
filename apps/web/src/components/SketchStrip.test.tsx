/**
 * SketchStrip — the Finish group, where a caption used to contradict its own
 * key binding and one click could destroy unrecoverable work.
 *
 * UI-REVIEW 2026-07-30 F1: the `Esc` chip sat on EXIT under the caption "Esc
 * discards", but the sketch Escape cascade calls `finishSketch` at rest — the
 * SAVE handler. So Esc saved while the label promised it discarded, and the
 * button that really did discard asked nothing first. Unsaved entities were
 * never persisted, so undo cannot bring them back; this is the one exit in the
 * product that destroys work.
 *
 * These are render-and-wiring decisions about a destructive path, which is
 * exactly what a pure test cannot see and what is too expensive to re-check in
 * a browser on every change.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectGated } from "../test/gated";
import { DATUM_ORIGIN_ID, DATUM_PICKS } from "../sketch/datum";
import { useSketchStore } from "../sketch/store";
import { SketchStrip } from "./SketchStrip";

/** A drawn-but-never-saved rectangle: 4 entities, `featureId` still null. */
function drawUnsavedRectangle(): void {
  const store = () => useSketchStore.getState();
  store().begin();
  store().choosePlane("XY");
  store().setTool("rect");
  store().placeAt({ x: 0, y: 0 });
  store().placeAt({ x: 40, y: 25 });
  store().setTool("select");
}

beforeEach(() => {
  useSketchStore.getState().exit();
});

describe("no chip advertises Escape, because Escape no longer commits", () => {
  /*
   * This block used to assert the OPPOSITE — that Esc was advertised on SAVE —
   * and it was correct at the time (UI-REVIEW F1: the caption had sat on Exit
   * saying "Esc discards" while Esc actually saved). FB-13 then showed the
   * BINDING was the defect: Escape at rest ended the sketch, so the reflex
   * after a click that appeared to do nothing cost you the sketcher. `d2e2162`
   * made Escape unwind and then stop, like every tool we benchmark against.
   *
   * So the invariant survives and its sign flips: caption and binding must
   * AGREE. Neither chip may advertise a key that does not do that thing.
   */
  it("does not put Esc on SAVE — Escape no longer saves", () => {
    drawUnsavedRectangle();
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);

    const save = screen.getByTestId("sketch-save");
    expect(save.textContent).not.toContain("Esc");
    expect(save.getAttribute("aria-label")).not.toMatch(/escape/i);
  });

  it("never tells the user Esc discards, either", () => {
    drawUnsavedRectangle();
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);

    // The original F1 inversion. Still guarded: Escape destroys nothing now,
    // so claiming it discards would be as wrong as claiming it saves.
    const exit = screen.getByTestId("sketch-exit");
    expect(exit.textContent).not.toContain("Esc");
    expect(exit.getAttribute("aria-label")).not.toMatch(/escape/i);
  });

  it("says how much Exit would destroy, and that it asks first", () => {
    drawUnsavedRectangle();
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);

    const exit = screen.getByTestId("sketch-exit");
    expect(exit.textContent).toContain("discards 4");
    expect(exit.getAttribute("aria-label")).toContain("asks first");
  });
});

describe("exiting with unsaved entities asks before destroying them", () => {
  it("does not discard on the first click — it arms a confirm", () => {
    drawUnsavedRectangle();
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);

    fireEvent.click(screen.getByTestId("sketch-exit"));

    // The work must still exist. This is the assertion the old code failed.
    expect(useSketchStore.getState().entities).toHaveLength(4);
    expect(useSketchStore.getState().mode).not.toBe("off");
    expect(screen.getByTestId("sketch-discard-confirm")).toBeInTheDocument();
  });

  it("names the count and the irreversibility on the confirm itself", () => {
    drawUnsavedRectangle();
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);
    fireEvent.click(screen.getByTestId("sketch-exit"));

    const confirm = screen.getByTestId("sketch-discard-confirm");
    expect(confirm.textContent).toContain("Discard 4");
    expect(confirm.getAttribute("aria-label")).toContain("cannot be undone");
  });

  it("keeps the drawing when the user backs out", () => {
    drawUnsavedRectangle();
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);
    fireEvent.click(screen.getByTestId("sketch-exit"));

    fireEvent.click(screen.getByTestId("sketch-discard-cancel"));

    expect(useSketchStore.getState().entities).toHaveLength(4);
    expect(screen.getByTestId("sketch-exit")).toBeInTheDocument();
    expect(screen.queryByTestId("sketch-discard-confirm")).toBeNull();
  });

  it("discards only on explicit confirmation", () => {
    drawUnsavedRectangle();
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);
    fireEvent.click(screen.getByTestId("sketch-exit"));

    fireEvent.click(screen.getByTestId("sketch-discard-confirm"));

    expect(useSketchStore.getState().entities).toHaveLength(0);
    expect(useSketchStore.getState().mode).toBe("off");
  });
});

describe("the prompt is derived, so it cannot outlive what it warns about", () => {
  it("exits straight away when there is nothing to lose", () => {
    const store = () => useSketchStore.getState();
    store().begin();
    store().choosePlane("XY");
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);

    const exit = screen.getByTestId("sketch-exit");
    expect(exit.textContent).toContain("nothing to discard");

    fireEvent.click(exit);

    // No prompt for work that does not exist.
    expect(screen.queryByTestId("sketch-discard-confirm")).toBeNull();
    expect(store().mode).toBe("off");
  });

  it("dismisses an armed confirm once the sketch is saved under it", () => {
    drawUnsavedRectangle();
    const { rerender } = render(
      <SketchStrip onSave={vi.fn()} saving={false} saveError={null} />,
    );
    fireEvent.click(screen.getByTestId("sketch-exit"));
    expect(screen.getByTestId("sketch-discard-confirm")).toBeInTheDocument();

    // The live save loop binds the session to a persisted feature. Discarding
    // now would destroy nothing, so the warning must retract itself rather than
    // keep offering to discard saved work.
    useSketchStore.setState({ featureId: "feat-1" });
    rerender(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);

    expect(screen.queryByTestId("sketch-discard-confirm")).toBeNull();
    expect(screen.getByTestId("sketch-exit").textContent).toContain(
      "keeps saved edits",
    );
  });
});

/**
 * FOUNDER, 2026-08-02: *"there are no undo or redo buttons."* True — the shared
 * `HistoryGroup` was rendered by the part and assembly bands and NOT by this
 * one, so entering the sketcher removed undo exactly where the work is most
 * reversible and most error-prone.
 *
 * The trap while fixing it was to wire the familiar chrome to the familiar
 * handler. The part band's undo pops the server's FEATURE ring; a sketch in
 * progress is not a feature, so that pairing would have produced a button
 * captioned like sketch undo which silently rolls back the extrude you did
 * before opening the sketcher — the caption-vs-binding defect (UI-REVIEW F1,
 * FB-13) with a destructive twist. So what is asserted here is the BINDING and
 * the SCOPE, not the presence of two icons.
 */
describe("the sketcher's history buttons hold the SKETCH's stack", () => {
  it("renders the shared History group while drawing", () => {
    drawUnsavedRectangle();
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);

    expect(screen.getByTestId("undo-button")).toBeInTheDocument();
    expect(screen.getByTestId("redo-button")).toBeInTheDocument();
    // One control, one name, across all three workspaces.
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
  });

  it("un-draws the last shape — it does not touch the feature tree", () => {
    drawUnsavedRectangle();
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);

    fireEvent.click(screen.getByTestId("undo-button"));

    const state = useSketchStore.getState();
    expect(state.entities).toHaveLength(0);
    // Still in the sketch, still on the plane: a sketch edit was reversed, not
    // the session and certainly not a feature.
    expect(state.mode).toBe("draw");
    expect(state.plane).toEqual({ kind: "origin", base: "XY" });
  });

  it("redoes it back", () => {
    drawUnsavedRectangle();
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);

    fireEvent.click(screen.getByTestId("undo-button"));
    fireEvent.click(screen.getByTestId("redo-button"));

    expect(useSketchStore.getState().entities).toHaveLength(4);
  });

  it("says what one step reverses, so the scope is never implied", () => {
    drawUnsavedRectangle();
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);

    // The tooltip's second line on a READY button: this pair is scoped, and a
    // scoped pair is never silent about its scope.
    expect(screen.getByTestId("undo-button").textContent).toContain(
      "the last sketch edit",
    );
  });

  it("is honestly disabled with nothing drawn, and says why in sketch terms", () => {
    const store = () => useSketchStore.getState();
    store().begin();
    store().choosePlane("XY");
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);

    const undo = screen.getByTestId("undo-button");
    expectGated(undo);
    // NOT "Nothing to undo": there may well be features to undo, and this
    // button is not the one that would do it.
    expect(undo.textContent).toContain("Nothing drawn yet");
  });

  it("keeps Ctrl+Z on the sketch's own stack", () => {
    drawUnsavedRectangle();
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);

    fireEvent.keyDown(window, { key: "z", ctrlKey: true });
    expect(useSketchStore.getState().entities).toHaveLength(0);

    fireEvent.keyDown(window, { key: "z", ctrlKey: true, shiftKey: true });
    expect(useSketchStore.getState().entities).toHaveLength(4);
  });

  it("leaves a focused field's native undo alone", () => {
    drawUnsavedRectangle();
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);

    const field = document.createElement("input");
    document.body.appendChild(field);
    fireEvent.keyDown(field, { key: "z", ctrlKey: true, bubbles: true });
    expect(useSketchStore.getState().entities).toHaveLength(4);
    field.remove();
  });

  it("offers no history during the plane pick — there is nothing to reverse yet", () => {
    useSketchStore.getState().begin();
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);

    expect(screen.queryByTestId("undo-button")).toBeNull();
  });
});

/**
 * THE COUNT IS OF WHAT THE USER DREW. The frame materialises as a real
 * construction entity the moment a constraint reaches for it (SKETCH-2), and
 * the strip was reading `entities.length` straight — so grounding one corner of
 * a four-line rectangle turned the caption into "5 entities" and armed
 * "Discard 5 unsaved entities" over four. The constraint count already excluded
 * the frame's pins for exactly this reason; this is the other half.
 */
describe("the strip counts drawn geometry, never the frame", () => {
  it("still reads four after a corner is grounded to the origin", () => {
    drawUnsavedRectangle();
    const store = () => useSketchStore.getState();
    store().selectAt({ x: 40, y: 25 }, 1); // the far corner of the rectangle
    // The near corner already sits ON the origin, so reach the frame the way
    // the keyboard handle does rather than through a pointer pick.
    store().togglePick(DATUM_PICKS[DATUM_ORIGIN_ID]);
    expect(store().selection).toHaveLength(2);
    store().applyConstraint("coincident");
    // The frame IS in the buffer now — this is not a test that nothing changed.
    expect(store().entities).toHaveLength(5);
    expect(store().entities.some((e) => e.id === "origin")).toBe(true);

    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);
    expect(screen.getByTestId("sketch-save").textContent).toContain(
      "4 entities",
    );

    fireEvent.click(screen.getByTestId("sketch-exit"));
    expect(
      screen.getByTestId("sketch-discard-confirm").getAttribute("aria-label"),
    ).toBe("Discard 4 unsaved entities — this cannot be undone");
  });
});

/**
 * A CONTROL THAT LOOKS ENGAGED AND THEN DECLINES. `sketch-construction`
 * rendered pressed for a datum selection — an unmaterialised axis resolves to
 * no entity and `[].every(…)` is true — and pressing it hinted "Select an
 * entity to toggle construction."
 */
describe("the construction toggle never reads active for the frame", () => {
  it("is unpressed with only an axis selected, and stays unpressed", () => {
    drawUnsavedRectangle();
    const store = () => useSketchStore.getState();
    store().clearSelection();
    store().selectAt({ x: -30, y: 0 }, 1); // the X axis, off the rectangle
    expect(store().selection).toEqual([{ kind: "entity", id: "x-axis" }]);

    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);
    const chip = screen.getByTestId("sketch-construction");
    expect(chip.getAttribute("aria-pressed")).not.toBe("true");
    expect(chip.getAttribute("data-active")).not.toBe("true");
  });
});
