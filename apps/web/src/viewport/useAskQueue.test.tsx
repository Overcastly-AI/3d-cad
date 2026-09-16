/**
 * THE ASK QUEUE'S REACT WIRING — the half that the pure rules cannot cover.
 *
 * `@loft/design`'s `gauge.test.ts` proves the five transitions. What it cannot
 * see is whether they are reached at the right moments, and the moments are the
 * subtle part: the acknowledgement effect must fire when THE OWNER SPEAKS and
 * at no other time, which is one dependency array away from restoring the very
 * lost update the queue exists to prevent.
 *
 * The case that matters most here is "a new track identity does not disturb the
 * queue". An owner that builds its track inline hands the gauge a new object on
 * every render; if that ever became a dependency of the effect, reconciliation
 * would run between a key press and its acknowledgement, find no match for an
 * ask the owner has not echoed yet, read that as a stranger's edit, and clear
 * the queue. That failure is invisible to a normal browser run — it needs two
 * inputs to collide inside one round trip — and it is one line long.
 */
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useAskQueue, type AskQueueActions } from "./useAskQueue";

/** The extrude track's own tolerance. */
const near = (a: number, b: number) => Math.abs(a - b) <= 1e-4;

/**
 * A harness that plays the OWNER: it holds the value, and `echo` is the owner
 * finally getting round to publishing an ask. `authoring` is the drag flag the
 * component owns in real life.
 */
function harness(initial = 10) {
  const asked: number[] = [];
  const state = { value: initial, dragging: false, trackNonce: 0 };

  const view = renderHook(
    ({ value, nonce }: { value: number; nonce: number }) =>
      useAskQueue({
        value,
        // A fresh closure every render, exactly as an inline-built track gives.
        same: (a, b) => (nonce >= 0 ? near(a, b) : false),
        onChange: (next) => asked.push(next),
        authoring: () => state.dragging,
      }),
    { initialProps: { value: initial, nonce: 0 } },
  );

  const rerender = () =>
    view.rerender({ value: state.value, nonce: state.trackNonce });

  return {
    asked,
    state,
    shown: () => view.result.current[0],
    actions: (): AskQueueActions => view.result.current[1],
    /** The owner publishes `value` — a prop change, which is the only trigger. */
    echo(value: number) {
      state.value = value;
      act(rerender);
    },
    /** A re-render that changes nothing the queue should care about. */
    churn() {
      state.trackNonce += 1;
      act(rerender);
    },
  };
}

describe("useAskQueue", () => {
  it("shows the owner's value until it is asked for something else", () => {
    const h = harness(10);
    expect(h.shown()).toBe(10);
    act(() => h.actions().ask(12));
    expect(h.shown()).toBe(12);
    expect(h.asked).toEqual([12]);
  });

  it("lets the SECOND of two fast presses step off the first ASK, not the prop", () => {
    // The measured regression: `Up, Up, Shift+Up` with nothing acknowledged.
    const h = harness(10);
    act(() => h.actions().ask(h.actions().readBase() + 0.5));
    act(() => h.actions().ask(h.actions().readBase() + 0.5));
    act(() => h.actions().ask(h.actions().readBase() + 5));
    expect(h.asked).toEqual([10.5, 11, 16]);
    expect(h.shown()).toBe(16);
  });

  it("the ack for press ONE does not throw away press TWO", () => {
    const h = harness(10);
    act(() => h.actions().ask(10.5));
    act(() => h.actions().ask(11));
    h.echo(10.5); // the owner is one press behind
    expect(h.shown()).toBe(11);
    expect(h.actions().readBase()).toBe(11);
    h.echo(11);
    expect(h.shown()).toBe(11);
  });

  it("A NEW TRACK IDENTITY DOES NOT DISTURB THE QUEUE", () => {
    // The dependency-array case. Three renders with a fresh `same` closure and
    // a fresh `authoring` closure, between a press and its acknowledgement.
    const h = harness(10);
    act(() => h.actions().ask(10.5));
    act(() => h.actions().ask(11));
    h.churn();
    h.churn();
    h.churn();
    expect(h.shown()).toBe(11); // still ours, not reset to the prop
    h.echo(10.5);
    expect(h.shown()).toBe(11);
    expect(h.actions().readBase()).toBe(11);
  });

  it("a stranger's edit wins outright", () => {
    const h = harness(10);
    act(() => h.actions().ask(10.5));
    act(() => h.actions().ask(11));
    h.echo(40); // typed into the rail field
    expect(h.shown()).toBe(40);
    expect(h.actions().readBase()).toBe(40);
  });

  it("stands aside mid-drag: the prop chasing the pointer changes nothing", () => {
    const h = harness(10);
    h.state.dragging = true;
    act(() => h.actions().hold());
    act(() => h.actions().ask(20));
    // The owner's echo of an earlier frame arrives while the pointer is down.
    h.echo(14);
    expect(h.shown()).toBe(20); // the pointer is still the author
    expect(h.actions().readBase()).toBe(20);
  });

  it("keeps drawing what the drag ended at until the owner answers", () => {
    // THE MEASURED DEFECT, as a unit case. This used to assert `shown() === 10`
    // — the owner's stale echo — and that assertion was the springback: in a
    // real browser the rod reverted a step on pointer-up and held the wrong
    // number for 236-241 ms while the panel already read the new one.
    const h = harness(10);
    h.state.dragging = true;
    act(() => h.actions().hold());
    act(() => h.actions().ask(12.4713)); // a free (Ctrl) drag
    h.state.dragging = false;
    act(() => h.actions().release());
    // The first arrow press afterwards steps off what you dragged to...
    expect(h.actions().readBase()).toBe(12.4713);
    // ...and the arrow keeps DRAWING it rather than reverting to a prop that
    // has not caught up yet.
    expect(h.shown()).toBe(12.4713);
    // The owner echoing retires the ask, and nothing moves on screen.
    h.echo(12.4713);
    expect(h.shown()).toBe(12.4713);
  });

  it("the owner still wins a release it disagrees with — by SPEAKING", () => {
    // The sovereignty half of the release change: holding the last ask must not
    // become "the gauge ignores a clamp". A max of 12 answers 12.4713 with 12,
    // and the gauge takes it.
    const h = harness(10);
    h.state.dragging = true;
    act(() => h.actions().hold());
    act(() => h.actions().ask(12.4713));
    h.state.dragging = false;
    act(() => h.actions().release());
    h.echo(12); // the owner clamps
    expect(h.shown()).toBe(12);
    expect(h.actions().readBase()).toBe(12);
  });

  it("a release with nothing dragged leaves the prop in charge", () => {
    // `endDrag` also runs on the no-button backstop and on pointercancel, where
    // there may have been no ask at all. Re-recording `base` must be a no-op
    // there rather than pinning the gauge to a value nobody asked for.
    const h = harness(10);
    act(() => h.actions().release());
    expect(h.shown()).toBe(10);
    h.echo(31); // a stranger's edit still lands
    expect(h.shown()).toBe(31);
  });

  it("taking the grip shows BASE, not the prop", () => {
    const h = harness(10);
    act(() => h.actions().ask(10.5)); // a key press, unacknowledged
    h.state.dragging = true;
    act(() => h.actions().hold());
    expect(h.shown()).toBe(10.5);
  });

  it("holds ONE actions identity for the life of the gauge", () => {
    // Same contract as `useGaugeOverride`: the pointer handlers and the ladder
    // callback depend on this, and they sit on a portalled DOM grip.
    const h = harness(10);
    const first = h.actions();
    act(() => h.actions().ask(12));
    h.echo(12);
    h.churn();
    expect(h.actions()).toBe(first);
  });

  it("calls the owner exactly once per ask, after recording it", () => {
    const order: string[] = [];
    const view = renderHook(() =>
      useAskQueue({
        value: 10,
        same: near,
        onChange: vi.fn(() => order.push("sent")),
        authoring: () => false,
      }),
    );
    const [, actions] = view.result.current;
    act(() => {
      actions.ask(12);
      // Recorded already, even though no render has happened.
      order.push(`base=${actions.readBase()}`);
    });
    expect(order).toEqual(["sent", "base=12"]);
  });
});
