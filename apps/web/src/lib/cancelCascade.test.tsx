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
