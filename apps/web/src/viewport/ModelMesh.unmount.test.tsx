/**
 * `ModelMesh`'s UNMOUNT, gated on the component itself (SEL-7, second review
 * round).
 *
 * ## Why this file exists at all
 *
 * The first fix for "a hidden-face set must not outlive its mesh" shipped with
 * a test whose own helper did the clearing — so deleting the clear from
 * `ModelMesh` left the whole 1584-case suite green. An assertion that cannot be
 * reddened by the code it claims to cover is not a gate, and the record saying
 * it was is the worse half of that defect. This file renders the REAL component
 * and unmounts it, so the store's final state is the app's own doing.
 *
 * ## Why the mesh under test carries no geometry
 *
 * `ModelMesh` renders `null` until a GLB has parsed, which is what makes it
 * testable in jsdom at all: with no geometry there is no r3f element tree to
 * host, only the effects — and the unmount cleanup is an effect. The hidden
 * ordinals are therefore written to the store directly, which is the same state
 * the mesh publishes for itself once bodies are switched off; what is under
 * test here is the RELEASE, not the publish (the publish is `ModelMesh`'s
 * `bodyFaceState` effect, covered by the pick e2e specs).
 */
import { render } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ModelMesh } from "./ModelMesh";
import { NO_HIDDEN_FACES, usePartViewStore } from "./partView";

// `useThree` throws outside a `<Canvas>`, and a canvas needs WebGL that jsdom
// does not have. Everything else in the module is left real, so drei (which
// imports it) still initialises normally.
vi.mock("@react-three/fiber", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@react-three/fiber")>();
  return {
    ...actual,
    // The component reads exactly one field; a full RootState is neither
    // available nor needed, hence the narrowed selector type.
    useThree: (selector: (state: { invalidate: () => void }) => unknown) =>
      selector({ invalidate: () => undefined }),
  };
});

// Keep the mesh in its pre-geometry state deterministically: a real parse would
// resolve on a later tick and race the unmount.
vi.mock("./glbGeometry", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./glbGeometry")>();
  return { ...actual, loadGlbGeometry: () => Promise.resolve() };
});

const reset = () =>
  usePartViewStore.setState({
    pickGeometry: null,
    pickHiddenFaces: NO_HIDDEN_FACES,
    bodyPresent: false,
    partitioned: false,
  });

describe("ModelMesh unmount", () => {
  beforeEach(reset);
  afterEach(reset);

  it("releases the hidden-ordinal set — it cannot outlive its mesh", () => {
    const view = render(<ModelMesh glb={new ArrayBuffer(8)} />);
    // Roll back below the first solid (or suppress the last body) with a body
    // switched off: the ordinals were published against a mesh that is about to
    // stop existing.
    act(() => {
      usePartViewStore.getState().setPickHiddenFaces(new Set([4]));
    });
    expect(usePartViewStore.getState().pickHiddenFaces.has(4)).toBe(true);

    view.unmount();

    expect(usePartViewStore.getState().pickHiddenFaces.size).toBe(0);
    expect(usePartViewStore.getState().pickGeometry).toBeNull();
  });

  it("still reports the part as body-less on the way out", () => {
    const view = render(<ModelMesh glb={new ArrayBuffer(8)} />);
    act(() => {
      usePartViewStore.setState({ bodyPresent: true, partitioned: true });
    });

    view.unmount();

    const state = usePartViewStore.getState();
    expect(state.bodyPresent).toBe(false);
    expect(state.partitioned).toBe(false);
  });
});
