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
