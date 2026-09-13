/**
 * THE BUILD GATE — W2 review, finding 6.
 *
 * The band's proposal was `nextStepFor(tree.features)` and nothing else, so it
 * was a property of the tree's SHAPE: open a part whose last live feature is an
 * extrude, from any date, and the band wore the dot and proposed a fillet about
 * work long finished. Dismissal lives in component state keyed on the feature
 * id, so every navigation re-armed it — which is what turns a proposal into
 * furniture, and it contradicted FLOW-B3's own "written once per build, never
 * re-armed".
 *
 * The cases below are about the WHETHER. `nextStep.test.ts` covers the WHICH
 * (the table, and the much longer list of verbs that propose nothing), and this
 * file deliberately re-asserts none of it.
 */
import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";

import { useNextStepAfterBuild } from "./useNextStep";

function extrude(id: string): FeatureResponse {
  return {
    id,
    name: id,
    part_id: "p",
    order_index: 0,
    created_at: "2026-07-11T00:00:00Z",
    updated_at: "2026-07-11T00:00:00Z",
    rolled_back: false,
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: "s1" },
        distance_mm: 10,
        operation: "add",
        direction: "normal",
      },
    },
  } as FeatureResponse;
}

describe("the band's proposal is gated on a build", () => {
  it("says nothing about a tree it merely arrived to find", () => {
    // A part opened cold. Its last feature is an extrude and the TABLE has a
    // proposal for that — which is exactly why this has to be gated somewhere.
    const { result } = renderHook(
      ({ features }: { features: readonly FeatureResponse[] }) =>
        useNextStepAfterBuild(features),
      { initialProps: { features: [extrude("old")] } },
    );
    expect(result.current).toBeNull();
  });

  it("proposes about a feature it watched arrive", () => {
    const { result, rerender } = renderHook(
      ({ features }: { features: readonly FeatureResponse[] }) =>
        useNextStepAfterBuild(features),
      { initialProps: { features: [extrude("old")] } },
    );
    expect(result.current).toBeNull();

    rerender({ features: [extrude("old"), extrude("fresh")] });
    expect(result.current?.featureId).toBe("fresh");
    // NON-VACUOUS about the table too: what comes through is a real proposal,
    // with the tool and the words the band will draw. (Two body-affecting
    // features, so it is the repeat row rather than the first-body Fillet —
    // `nextStep.test.ts` owns that distinction; this only shows the gate is
    // passing the table's answer along rather than inventing one.)
    expect(result.current?.tool).toBe("new-extrude");
    expect(result.current?.caption).toBe("Another extrude on this body");

    // A refetch that changes nothing must not retire it — the arming is about
    // the feature, not about how many times the tree has been read.
    rerender({ features: [extrude("old"), extrude("fresh")] });
    expect(result.current?.featureId).toBe("fresh");
  });

  it("a feature that leaves and comes back is still one this session built", () => {
    // The undo-a-delete shape, and a deliberate choice rather than an accident:
    // the born set is session-permanent, so the restored feature is proposed
    // about again. It is not the nag this gate exists to prevent — that one is
    // a page LOAD proposing about old work — and if the user had already
    // answered this proposal, `useNextStepAccent`'s dismissal memory (keyed on
    // the same feature id, in the band) is what keeps it quiet.
    const { result, rerender } = renderHook(
      ({ features }: { features: readonly FeatureResponse[] }) =>
        useNextStepAfterBuild(features),
      { initialProps: { features: [extrude("old")] } },
    );
    rerender({ features: [extrude("old"), extrude("fresh")] });
    expect(result.current?.featureId).toBe("fresh");
    // Gone: the tree's tip is a feature that predates the session.
    rerender({ features: [extrude("old")] });
    expect(result.current).toBeNull();
    rerender({ features: [extrude("old"), extrude("fresh")] });
    expect(result.current?.featureId).toBe("fresh");
  });

  it("survives the tree being absent, then arriving", () => {
    // The real mount order: `tree.data` is undefined while the first fetch is
    // in flight, and the tree that lands after it is still the FIRST tree.
    const { result, rerender } = renderHook(
      ({ features }: { features: readonly FeatureResponse[] | undefined }) =>
        useNextStepAfterBuild(features),
      {
        initialProps: {
          features: undefined as readonly FeatureResponse[] | undefined,
        },
      },
    );
    expect(result.current).toBeNull();
    rerender({ features: [extrude("old")] });
    expect(result.current).toBeNull();
    rerender({ features: [extrude("old"), extrude("fresh")] });
    expect(result.current?.featureId).toBe("fresh");
  });
});
