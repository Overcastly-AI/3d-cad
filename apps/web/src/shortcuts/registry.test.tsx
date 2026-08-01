/**
 * The key card's BEHAVIOURAL pin (UI-REVIEW F4) — see `registry.test.ts` for
 * the derivation half.
 *
 * `V` / `⇧V` body isolation is the one binding this slice could not wire to the
 * registry: its handler lives in `viewport/partView.ts`, held by a concurrent
 * agent. Rather than let the sheet carry one hand-typed row — a claim nothing
 * checks, which is the exact defect the registry exists to prevent — the row is
 * pinned by driving the REAL hook with the key the registry declares and
 * asserting the store moved. That is a stronger guarantee than a shared
 * constant: it proves the key works, not that two files agree about a string.
 *
 * `.tsx` because it needs jsdom (vite.config.ts splits the vitest environment
 * by file extension), not because it renders a component.
 */
import { renderHook } from "@testing-library/react";
import { act } from "react";
import { beforeEach, describe, expect, it } from "vitest";

import { usePartViewHotkeys, usePartViewStore } from "../viewport/partView";
import { KEY_ISOLATE } from "./registry";

describe("behavioural pin: body isolation", () => {
  beforeEach(() => {
    usePartViewStore.setState({
      subjectId: null,
      addressedKey: null,
      bodyPresent: true,
    });
    usePartViewStore.getState().setSubject("part-1");
    usePartViewStore.setState({ bodyPresent: true });
    // Two bodies, so ⇧V has something to isolate FROM and the show-all branch
    // (which counts hidden BODIES) is reachable — with an empty body list the
    // hook would take the isolate branch and the assertion would pass for the
    // wrong reason.
    usePartViewStore.getState().setBodies([
      { key: "body:1", label: "Body 1", lumps: 1 },
      { key: "body:2", label: "Body 2", lumps: 1 },
    ]);
    usePartViewStore.getState().setAddressed("body:1");
  });

  function press(key: string, shift = false): void {
    act(() => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key, shiftKey: shift, bubbles: true }),
      );
    });
  }

  it("KEY_ISOLATE really is the key the visibility handler listens for", () => {
    renderHook(() => usePartViewHotkeys(true));
    expect(usePartViewStore.getState().view["body:1"]?.hidden ?? false).toBe(
      false,
    );

    press(KEY_ISOLATE);
    expect(usePartViewStore.getState().view["body:1"]?.hidden).toBe(true);

    // ...and Shift is the isolate/show-all half the sheet advertises.
    press(KEY_ISOLATE, true);
    expect(usePartViewStore.getState().view["body:1"]?.hidden ?? false).toBe(
      false,
    );
  });

  it("a key the registry does NOT declare leaves the store alone", () => {
    // Guards the test itself: without this, a handler that reacted to every
    // keystroke would pass the assertion above for the wrong reason.
    renderHook(() => usePartViewHotkeys(true));
    press("q");
    expect(usePartViewStore.getState().view["body:1"]?.hidden ?? false).toBe(
      false,
    );
  });
});
