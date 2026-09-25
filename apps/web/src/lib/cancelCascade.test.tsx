/**
 * ONE ESCAPE BACKS OUT ONE STEP — the cascade's own gate.
 *
 * The defect these are written against is not a wrong handler, it is three
 * right handlers with no relationship: whoever mounted first won, and two of
 * them ran. So the cases below are about the RELATIONSHIP — which rung runs,
 * which ones do not, and that a rung nobody is standing on is skipped rather
 * than swallowing the key.
 */
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  CANCEL_ORDER,
  liveCancelRungs,
  useCancelKey,
  type CancelRung,
} from "./modalGate";

/** One Escape, dispatched the way the browser would. */
function escape(): KeyboardEvent {
  const event = new KeyboardEvent("keydown", {
    key: "Escape",
    bubbles: true,
    cancelable: true,
  });
  act(() => {
    document.body.dispatchEvent(event);
  });
  return event;
}

/** Mount a handler on `rung` and return the spy it calls. */
function standOn(
  rung: CancelRung,
  options: { whileTyping?: boolean } = {},
): {
  ran: ReturnType<typeof vi.fn>;
  unmount: () => void;
} {
  const ran = vi.fn();
  const hook = renderHook(() => useCancelKey(rung, ran, options));
  return { ran, unmount: () => act(() => hook.unmount()) };
}

describe("the cancel cascade", () => {
  it("states its order strongest-first, and the order is the contract", () => {
    // Written out rather than derived: the whole point is that this is a
    // DECLARED order, so a change to it should have to change a test that
    // says what it is.
    expect([...CANCEL_ORDER]).toEqual(["drag", "offer", "mark"]);
  });

  it("does nothing at all when no rung is live", () => {
    expect(liveCancelRungs()).toEqual([]);
    expect(escape().defaultPrevented).toBe(false);
  });

  it("runs the ONE live rung and marks the key handled", () => {
    const mark = standOn("mark");
    expect(escape().defaultPrevented).toBe(true);
    expect(mark.ran).toHaveBeenCalledTimes(1);
    mark.unmount();
  });

  it("runs the STRONGEST live rung and leaves the others standing", () => {
    // The measured defect, as a test: a chip and a band dot both went on one
    // key, and a drag took the chip with it.
    const drag = standOn("drag");
    const offer = standOn("offer");
    const mark = standOn("mark");
    escape();
    expect(drag.ran).toHaveBeenCalledTimes(1);
    expect(offer.ran).not.toHaveBeenCalled();
    expect(mark.ran).not.toHaveBeenCalled();

    // …and the next key backs out the next step, not two at once.
    drag.unmount();
    escape();
    expect(offer.ran).toHaveBeenCalledTimes(1);
    expect(mark.ran).not.toHaveBeenCalled();

    offer.unmount();
    escape();
    expect(mark.ran).toHaveBeenCalledTimes(1);
    mark.unmount();
  });

  it("skips a rung nobody is standing on rather than swallowing the key", () => {
    const mark = standOn("mark");
    escape();
    expect(mark.ran).toHaveBeenCalledTimes(1);
    mark.unmount();
    // Nothing live: the key must reach the workspace's own Escape owners.
    expect(escape().defaultPrevented).toBe(false);
  });

  it("stands down on a key another handler already claimed", () => {
    const offer = standOn("offer");
    const event = new KeyboardEvent("keydown", {
      key: "Escape",
      bubbles: true,
      cancelable: true,
    });
    event.preventDefault();
    act(() => {
      document.body.dispatchEvent(event);
    });
    expect(offer.ran).not.toHaveBeenCalled();
    offer.unmount();
  });

  it("leaves Escape alone while the user is typing", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    const offer = standOn("offer");
    act(() => {
      input.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "Escape",
          bubbles: true,
          cancelable: true,
        }),
      );
    });
    expect(offer.ran).not.toHaveBeenCalled();
    offer.unmount();
    input.remove();
  });

  it("acts while typing ONLY for a rung that asked to", () => {
    // A gesture in flight must be abandonable from anywhere — selecting a
    // fillet row leaves focus in `fillet-radius`, so a drag started there
    // could not otherwise be put down. An offer is not like that: Escape in a
    // text field belongs to the field.
    const input = document.createElement("input");
    document.body.appendChild(input);
    const drag = standOn("drag", { whileTyping: true });
    const offer = standOn("offer");
    act(() => {
      input.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "Escape",
          bubbles: true,
          cancelable: true,
        }),
      );
    });
    expect(drag.ran).toHaveBeenCalledTimes(1);
    expect(offer.ran).not.toHaveBeenCalled();

    // …and with only the offer standing, the field keeps its Escape: the
    // cascade must SKIP a rung it may not act on, never swallow the key.
    drag.unmount();
    const inField = new KeyboardEvent("keydown", {
      key: "Escape",
      bubbles: true,
      cancelable: true,
    });
    act(() => {
      input.dispatchEvent(inField);
    });
    expect(inField.defaultPrevented).toBe(false);
    expect(offer.ran).not.toHaveBeenCalled();
    offer.unmount();
    input.remove();
  });

  it("owns the key outright, so a raw listener behind it cannot also act", () => {
    // `preventDefault` alone only stops listeners that READ it, and a dozen
    // raw window listeners predate that seam. Measured in the browser while
    // landing this: abandoning a row drag ALSO cancelled the feature editor
    // behind it — the two-step defect re-created in a new pairing.
    const behind = vi.fn();
    window.addEventListener("keydown", behind);
    const drag = standOn("drag");
    escape();
    expect(drag.ran).toHaveBeenCalledTimes(1);
    expect(behind).not.toHaveBeenCalled();
    window.removeEventListener("keydown", behind);
    drag.unmount();
  });

  it("publishes the live rungs, and clears the stamp when none are", () => {
    // The observability half: "one step" is otherwise only visible as an
    // absence, and an absence cannot distinguish a cascade that chose from a
    // listener that was the only one there.
    const offer = standOn("offer");
    const drag = standOn("drag");
    expect(liveCancelRungs()).toEqual(["drag", "offer"]);
    expect(document.body.dataset["cancelRungs"]).toBe("drag offer");
    drag.unmount();
    expect(document.body.dataset["cancelRungs"]).toBe("offer");
    offer.unmount();
    expect(document.body.dataset["cancelRungs"]).toBeUndefined();
  });

  it("gives the newest surface on a rung the key", () => {
    const older = standOn("offer");
    const newer = standOn("offer");
    escape();
    expect(newer.ran).toHaveBeenCalledTimes(1);
    expect(older.ran).not.toHaveBeenCalled();
    newer.unmount();
    older.unmount();
  });
});

/**
 * A RUNG THAT DECLINES PASSES THE KEY ON.
 *
 * A rung is armed from render state, and render state lags. The measured case
 * is the gauge's drag rung straight after a release. `pointerup` has ended the
 * grab, but the rung is still armed until the gauge re-renders, one Scheduler
 * task later. An Escape inside that task reached a handler with nothing to
 * revert. The cascade took the key anyway, and the command stayed open
 * (`craft9b-gauges.spec.ts`, "a reopened command..."). The handler now says so
 * by returning `false`, and these cases hold the cascade to it.
 */
describe("a declining rung", () => {
  /** Stand on `rung` with a handler that has nothing to back out of. */
  function standIdle(rung: CancelRung): {
    asked: ReturnType<typeof vi.fn>;
    unmount: () => void;
  } {
    const asked = vi.fn(() => false);
    const hook = renderHook(() => useCancelKey(rung, asked));
    return { asked, unmount: () => act(() => hook.unmount()) };
  }

  it("hands the key to the next live rung", () => {
    const drag = standIdle("drag");
    const offer = standOn("offer");
    const event = escape();
    expect(drag.asked).toHaveBeenCalledTimes(1);
    expect(offer.ran).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
    offer.unmount();
    drag.unmount();
  });

  it("leaves the key to the workspace when no rung takes it", () => {
    // The craft9b case exactly: the stale drag rung is the only one standing,
    // and the command's own cancel, a plain window listener, must get the key.
    const workspace = vi.fn();
    window.addEventListener("keydown", workspace);
    const drag = standIdle("drag");
    const event = escape();
    expect(drag.asked).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(false);
    expect(workspace).toHaveBeenCalledTimes(1);
    window.removeEventListener("keydown", workspace);
    drag.unmount();
  });

  it("still owns the key outright when it does take it", () => {
    // Declining must not weaken taking: a handler that returns nothing (every
    // rung but the gauge's) keeps the key, and nothing behind it hears it.
    const behind = vi.fn();
    window.addEventListener("keydown", behind);
    const drag = standOn("drag");
    expect(escape().defaultPrevented).toBe(true);
    expect(behind).not.toHaveBeenCalled();
    window.removeEventListener("keydown", behind);
    drag.unmount();
  });

  it("still owns the key when its handler throws", () => {
    // Review N3 on 3478273: run-first-stop-second meant a throwing handler
    // skipped the stop, and the editor's cancel behind it ALSO ran — the
    // two-steps-from-one-key defect the cascade exists to end.
    const behind = vi.fn();
    window.addEventListener("keydown", behind);
    const hook = renderHook(() =>
      useCancelKey("drag", () => {
        throw new Error("handler failed");
      }),
    );
    // jsdom reports a listener's throw as a window `error` event rather than
    // rethrowing it from dispatchEvent; claim it so the run stays clean.
    const swallow = (event: ErrorEvent) => event.preventDefault();
    window.addEventListener("error", swallow);
    const event = escape();
    window.removeEventListener("error", swallow);
    expect(event.defaultPrevented).toBe(true);
    expect(behind).not.toHaveBeenCalled();
    window.removeEventListener("keydown", behind);
    act(() => hook.unmount());
  });
});
