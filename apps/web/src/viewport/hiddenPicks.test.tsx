/**
 * `useIsHiddenFaceOrdinal` — the ordinal-only half of the offer filter (SEL-7).
 *
 * The filter itself is pure and covered in `hiddenPicks.test.ts`; what this file
 * pins is the three things the pure test cannot see: that the hook SUBSCRIBES (a
 * body switched off mid-command has to re-render the caller, or the withheld
 * overlay stays on screen), its FAILURE DIRECTION (a null ordinal reads as
 * drawn — ambiguity resolves toward offering, this module's stated convention),
 * and that an ordinal against NO PUBLISHED MESH reads as drawn too.
 *
 * The fixture publishes a geometry alongside the ordinals because that is the
 * only state `ModelMesh` ever writes — the two are one fact. A test that set
 * the ordinals alone was measuring a state the app cannot reach, which is why
 * the missing null-mesh guard was invisible to it (code review, 2026-08-11).
 *
 * `.tsx` because it needs jsdom (vite.config.ts splits the vitest environment by
 * file extension), not because it renders a component.
 */
import { renderHook } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { BufferGeometry } from "three";

import { useIsHiddenFaceOrdinal } from "./hiddenPicks";
import { NO_HIDDEN_FACES, usePartViewStore } from "./partView";

/** The published mesh the ordinals below are ordinals OF. */
let mesh: BufferGeometry;

const setHidden = (ordinals: readonly number[]) =>
  act(() => {
    usePartViewStore.getState().setPickHiddenFaces(new Set(ordinals));
  });

/** What `ModelMesh` does as it unmounts: the mesh goes, and the set with it. */
const unmountMesh = () =>
  act(() => {
    usePartViewStore.getState().setPickGeometry(null);
    usePartViewStore.getState().setPickHiddenFaces(NO_HIDDEN_FACES);
  });

describe("useIsHiddenFaceOrdinal", () => {
  beforeEach(() => {
    mesh = new BufferGeometry();
    usePartViewStore.setState({
      pickGeometry: mesh,
      pickHiddenFaces: new Set<number>(),
    });
  });

  afterEach(() => {
    usePartViewStore.setState({
      pickGeometry: null,
      pickHiddenFaces: NO_HIDDEN_FACES,
    });
    mesh.dispose();
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

  it("a mesh that has UNMOUNTED hides nothing — the set goes with it", () => {
    // Roll back below the first solid, or suppress the last body, with a body
    // hidden and the hole editor still open on a cached overlay face:
    // `Viewport` mounts `ModelMesh` on the GLB, so the publisher disappears.
    // An ordinal indexes a mesh's face partition, so with no mesh it names
    // nothing and must fail toward DRAWN like every other reader of the set.
    const { result } = renderHook(() => useIsHiddenFaceOrdinal(4));
    setHidden([4]);
    expect(result.current).toBe(true);

    unmountMesh();
    expect(result.current).toBe(false);
    expect(usePartViewStore.getState().pickHiddenFaces.size).toBe(0);
  });

  it("…and answers DRAWN even if a publisher leaves the set behind", () => {
    // The reader-side guard, measured on its own: the state below is the one
    // `ModelMesh` used to leave — ordinals for a mesh that is gone. Reverting
    // the `pickGeometry !== null` guard turns this red while the test above
    // stays green, which is why both exist.
    const { result } = renderHook(() => useIsHiddenFaceOrdinal(4));
    setHidden([4]);
    act(() => {
      usePartViewStore.getState().setPickGeometry(null);
    });
    expect(usePartViewStore.getState().pickHiddenFaces.has(4)).toBe(true);
    expect(result.current).toBe(false);
  });
});
