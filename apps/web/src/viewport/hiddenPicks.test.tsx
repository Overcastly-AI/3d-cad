/**
 * `useIsHiddenFaceOrdinal` — the ordinal-only half of the offer filter (SEL-7).
 *
 * The filter itself is pure and covered in `hiddenPicks.test.ts`; what this file
 * pins is the two things the pure test cannot see: that the hook SUBSCRIBES (a
 * body switched off mid-command has to re-render the caller, or the withheld
 * overlay stays on screen), and its FAILURE DIRECTION (a null ordinal reads as
 * drawn — ambiguity resolves toward offering, this module's stated convention).
 *
 * `.tsx` because it needs jsdom (vite.config.ts splits the vitest environment by
 * file extension), not because it renders a component.
 */
import { renderHook } from "@testing-library/react";
import { act } from "react";
import { beforeEach, describe, expect, it } from "vitest";

import { useIsHiddenFaceOrdinal } from "./hiddenPicks";
import { usePartViewStore } from "./partView";

const setHidden = (ordinals: readonly number[]) =>
  act(() => {
    usePartViewStore.getState().setPickHiddenFaces(new Set(ordinals));
  });

describe("useIsHiddenFaceOrdinal", () => {
  beforeEach(() => {
    usePartViewStore.setState({ pickHiddenFaces: new Set<number>() });
  });

  it("reports membership of the published hidden-ordinal set", () => {
    setHidden([4, 5]);
    expect(renderHook(() => useIsHiddenFaceOrdinal(4)).result.current).toBe(
      true,
    );
    expect(renderHook(() => useIsHiddenFaceOrdinal(9)).result.current).toBe(
      false,
    );
  });

  it("treats an UNRESOLVED ordinal as drawn, never as hidden", () => {
    // The overlay listed no pickable face for the signature. Withholding a mark
    // the modeller can see would be a worse defect than the one the gate closes.
    setHidden([4]);
    expect(renderHook(() => useIsHiddenFaceOrdinal(null)).result.current).toBe(
      false,
    );
  });

  it("follows the store — switching a body off flips it mid-command", () => {
    const { result } = renderHook(() => useIsHiddenFaceOrdinal(4));
    expect(result.current).toBe(false);
    setHidden([4]);
    expect(result.current).toBe(true);
    setHidden([]);
    expect(result.current).toBe(false);
  });

  it("ordinal 0 is an ordinal, not a falsy nothing", () => {
    setHidden([0]);
    expect(renderHook(() => useIsHiddenFaceOrdinal(0)).result.current).toBe(
      true,
    );
  });
});
