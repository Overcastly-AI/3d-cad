/**
 * THE HANDLE MUST NOT CHURN — a subscription count, not a render count.
 *
 * `useGaugeOverride` sits between a viewport manipulator and the rail editor
 * that owns the value, and `PartPage` wires it into a chain that ends at a
 * WINDOW-LEVEL listener:
 *
 *     useGaugeOverride  ->  closeEditor (useCallback, deps: the handle)
 *                       ->  the global Escape effect (deps: closeEditor)
 *
 * So anything that changes the handle's identity re-subscribes a `window`
 * `keydown` listener. A drag calls `set` on every `pointermove`, and the first
 * version of the hook returned `{ override, set, reset }` from a `useMemo`
 * keyed on `override` — a new object per frame, therefore a
 * `removeEventListener` + `addEventListener` per frame. Measured at 11
 * subscribes / 10 unsubscribes across 10 simulated frames.
 *
 * THE COST IS NOT PERFORMANCE, WHICH IS WHY A RENDER-COUNT TEST WOULD BE THE
 * WRONG ASSERTION. Re-registering a listener moves it to the BACK of the
 * window's `keydown` queue, so the relative order of the cancel handlers —
 * direction §7.3's contract γ, and the ground CRAFT-7's Escape swallow is
 * built on — changes underneath a live gesture. The failure that produces is a
 * key going to the wrong handler at one moment of one drag, which is
 * unreproducible by hand and invisible to every other gate we have.
 *
 * The mimic below is deliberately a COPY of PartPage's shape rather than an
 * import of it: what is under test is the hook's contract with any such chain,
 * and PartPage needs a router, a query client and a WebGL context to render.
 * Keep the two in step — if `closeEditor` ever stops depending on the handle,
 * this file's premise is what changed, not its verdict.
 */
import { act, render } from "@testing-library/react";
import { useCallback, useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  useGaugeOverride,
  type GaugeOverrideActions,
} from "./useGaugeOverride";

/** Live count of `keydown` listeners added to / removed from `window`. */
interface ListenerTally {
  subscribes: number;
  unsubscribes: number;
}

let tally: ListenerTally;
let restore: () => void;

beforeEach(() => {
  tally = { subscribes: 0, unsubscribes: 0 };
  const add = window.addEventListener.bind(window);
  const remove = window.removeEventListener.bind(window);
  const addSpy = vi
    .spyOn(window, "addEventListener")
    .mockImplementation((type, listener, options) => {
      if (type === "keydown") tally.subscribes += 1;
      add(type, listener, options);
    });
  const removeSpy = vi
    .spyOn(window, "removeEventListener")
    .mockImplementation((type, listener, options) => {
      if (type === "keydown") tally.unsubscribes += 1;
      remove(type, listener, options);
    });
  restore = () => {
    addSpy.mockRestore();
    removeSpy.mockRestore();
  };
});

afterEach(() => restore());

/**
 * PartPage's chain, reduced to the three links that matter. `escapes` records
 * every Escape the window handler saw, so a mutation that makes the listener
 * churn cannot also quietly make it stop working.
 */
function Mimic({
  onReady,
  escapes,
}: {
  onReady: (actions: GaugeOverrideActions) => void;
  escapes: string[];
}) {
  const [override, gauge] = useGaugeOverride("mm");
  onReady(gauge);

  // ANCHOR B, as PartPage writes it: the editor's one close path resets the
  // override, so the next open of the command seeds from its own default.
  const closeEditor = useCallback(() => {
    gauge.reset();
  }, [gauge]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") escapes.push("closed");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closeEditor, escapes]);

  return <output data-testid="shown">{override ? override.mm : "none"}</output>;
}

describe("useGaugeOverride", () => {
  it("holds ONE global listener across a whole drag", () => {
    let actions: GaugeOverrideActions | null = null;
    const escapes: string[] = [];
    const view = render(
      <Mimic
        onReady={(a) => {
          actions = a;
        }}
        escapes={escapes}
      />,
    );

    expect(tally.subscribes).toBe(1);
    expect(tally.unsubscribes).toBe(0);

    // Ten `pointermove` frames of a drag, each a distinct value so nothing is
    // dropped by React's bail-out.
    for (let frame = 1; frame <= 10; frame += 1) {
      act(() => actions?.set(10 + frame * 0.5));
    }

    expect(view.getByTestId("shown").textContent).toBe("15");
    // THE ASSERTION. One subscribe at mount, none since, nothing torn down.
    expect(tally.subscribes).toBe(1);
    expect(tally.unsubscribes).toBe(0);

    // ...and the listener that never moved is still the live one.
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    expect(escapes).toEqual(["closed"]);
  });

  it("survives a reset and a repeat of the same number without re-subscribing", () => {
    let actions: GaugeOverrideActions | null = null;
    render(<Mimic onReady={(a) => (actions = a)} escapes={[]} />);

    act(() => actions?.set(12));
    act(() => actions?.reset());
    act(() => actions?.set(12));
    act(() => actions?.set(12)); // the boxed-value case — new ask, same number

    expect(tally.subscribes).toBe(1);
    expect(tally.unsubscribes).toBe(0);
  });

  it("boxes the value under the key it was created with, and clears on reset", () => {
    let actions: GaugeOverrideActions | null = null;
    const view = render(<Mimic onReady={(a) => (actions = a)} escapes={[]} />);

    expect(view.getByTestId("shown").textContent).toBe("none");
    act(() => actions?.set(37.5));
    expect(view.getByTestId("shown").textContent).toBe("37.5");
    act(() => actions?.reset());
    expect(view.getByTestId("shown").textContent).toBe("none");
  });

  it("gives a repeat of the same number a NEW box, so the editor still hears it", () => {
    // The identity contract from the module note: `{ mm: 10 }` twice must be
    // two objects, or "drag out to 20 and back to 10" is dropped by React.
    const boxes: ({ mm: number } | null)[] = [];
    let actions: GaugeOverrideActions | null = null;

    function Watcher() {
      const [override, gauge] = useGaugeOverride("mm");
      actions = gauge;
      useEffect(() => {
        boxes.push(override);
      }, [override]);
      return null;
    }

    render(<Watcher />);
    act(() => actions?.set(10));
    act(() => actions?.set(20));
    act(() => actions?.set(10));

    expect(boxes.map((b) => b?.mm ?? null)).toEqual([null, 10, 20, 10]);
    expect(boxes[1]).not.toBe(boxes[3]);
  });
});
