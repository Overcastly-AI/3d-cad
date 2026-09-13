import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import {
  armedPickStore,
  usePickArmed,
  useRegisterArmedPick,
} from "./armedPicks";

describe("armedPicks", () => {
  beforeEach(() => {
    armedPickStore.setState({ marks: 0 });
  });

  it("says nothing is armed when no mark is mounted", () => {
    expect(renderHook(() => usePickArmed()).result.current).toBe(false);
  });

  it("is armed while ONE mark is mounted, and not after it goes", () => {
    const armed = renderHook(() => usePickArmed());
    const mark = renderHook(() => useRegisterArmedPick());
    armed.rerender();
    expect(armed.result.current).toBe(true);
    act(() => mark.unmount());
    armed.rerender();
    expect(armed.result.current).toBe(false);
  });

  it("needs the LAST mark to leave, not the first", () => {
    // The real shape: an overlay mounts a mark per offered face and they
    // unmount independently. A flag would have flipped off on the first one.
    const armed = renderHook(() => usePickArmed());
    const first = renderHook(() => useRegisterArmedPick());
    const second = renderHook(() => useRegisterArmedPick());
    act(() => first.unmount());
    armed.rerender();
    expect(armed.result.current).toBe(true);
    act(() => second.unmount());
    armed.rerender();
    expect(armed.result.current).toBe(false);
  });

  it("cannot be driven negative by an unbalanced leave", () => {
    // The floor picks the failing direction deliberately: a negative count
    // would take MORE mounts than exist to get back to armed, i.e. it would
    // latch the cube ON during a pick — the defect, not a degraded version
    // of the fix.
    act(() => {
      armedPickStore.getState().leave();
      armedPickStore.getState().leave();
    });
    expect(armedPickStore.getState().marks).toBe(0);
    const armed = renderHook(() => usePickArmed());
    renderHook(() => useRegisterArmedPick());
    armed.rerender();
    expect(armed.result.current).toBe(true);
  });
});
