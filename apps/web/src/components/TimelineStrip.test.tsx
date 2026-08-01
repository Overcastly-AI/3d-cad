/**
 * TimelineStrip — the bottom machine way (UI-W1).
 *
 * What is pinned here is everything that a screenshot cannot see and Playwright
 * pays 40 seconds to reach: the SLOT WIRING (which `rollback_feature_id` each
 * control writes — get it off by one and the build silently loses a feature),
 * the solid/dashed encoding boundary, the keyboard contract on the travel stop,
 * the optimistic-then-honest stop position, and the per-state chip treatment.
 *
 * Drag itself is a Playwright concern (jsdom has no layout, so measured slot
 * anchors are meaningless here); its math is `nearestSlotIndex`, unit-tested in
 * `features/rollback.test.ts`.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  EvaluateTreeResult,
  FeatureResponse,
  FeatureTreeResponse,
} from "../api/parts";
import { TimelineStrip } from "./TimelineStrip";
import { expectGated } from "../test/gated";

function sketch(id: string, name: string): FeatureResponse {
  return {
    id,
    name,
    part_id: "p1",
    order_index: 0,
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
    rolled_back: false,
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [],
        constraints: [],
      },
    },
  };
}

function extrude(id: string, name: string): FeatureResponse {
  return {
    ...sketch(id, name),
    order_index: 1,
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: "f1" },
        distance_mm: 10,
        operation: "add",
        direction: "normal",
        merge: true,
      },
    },
  };
}

function fillet(id: string, name: string): FeatureResponse {
  return {
    ...sketch(id, name),
    order_index: 2,
    feature: {
      type: "fillet",
      version: 1,
      params: { edges: { kind: "all_edges" }, radius_mm: 2 },
    },
  };
}

const FEATURES = [
  sketch("f1", "Sketch1"),
  extrude("f2", "Extrude1"),
  fillet("f3", "Fillet1"),
];

function tree(
  features: readonly FeatureResponse[],
  rollbackFeatureId: string | null = null,
): FeatureTreeResponse {
  return {
    part_id: "p1",
    tree_version: 1,
    features: [...features],
    rollback_feature_id: rollbackFeatureId,
    can_undo: false,
    can_redo: false,
  };
}

function evaluated(
  statuses: Record<string, "ok" | "error" | "suppressed" | "skipped">,
): EvaluateTreeResult {
  return {
    part_id: "p1",
    tree_version: 1,
    last_good_feature_id: null,
    mesh_glb_id: null,
    properties: null,
    features: Object.entries(statuses).map(([feature_id, status]) => ({
      feature_id,
      status,
      ...(status === "error"
        ? { error: { code: "kernel_failed", message: "no" } }
        : {}),
    })),
  };
}

interface Options {
  features?: readonly FeatureResponse[];
  rollbackFeatureId?: string | null;
  evaluation?: EvaluateTreeResult | undefined;
  selectedFeatureId?: string | null;
  busy?: boolean;
  loading?: boolean;
}

function renderStrip(options: Options = {}) {
  const onMoveRollback = vi.fn();
  const onSelectFeature = vi.fn();
  const props = {
    tree:
      options.loading === true
        ? undefined
        : tree(options.features ?? FEATURES, options.rollbackFeatureId ?? null),
    evaluation: options.evaluation,
    selectedFeatureId: options.selectedFeatureId ?? null,
    onSelectFeature,
    onMoveRollback,
    busy: options.busy ?? false,
  };
  const view = render(<TimelineStrip {...props} />);
  const rerender = (next: Partial<typeof props>) =>
    view.rerender(<TimelineStrip {...props} {...next} />);
  return { ...view, rerender, onMoveRollback, onSelectFeature };
}

describe("TimelineStrip — the way", () => {
  it("draws one chip per feature, in build order, with its ordinal and name", () => {
    renderStrip();
    const chips = [0, 1, 2].map((i) =>
      screen.getByTestId(`timeline-chip-${i}`),
    );
    expect(chips[0]).toHaveTextContent("01");
    expect(chips[0]).toHaveTextContent("Sketch1");
    expect(chips[1]).toHaveTextContent("02");
    expect(chips[1]).toHaveTextContent("Extrude1");
    expect(chips[2]).toHaveTextContent("03");
    expect(chips[2]).toHaveTextContent("Fillet1");
    // Each chip carries a real verb glyph (the shared VERB_GLYPHS map).
    for (const chip of chips) {
      expect(chip.querySelector("svg")).not.toBeNull();
    }
  });

  it("reads the stop position against the build size", () => {
    renderStrip({ rollbackFeatureId: "f1" });
    expect(screen.getByTestId("timeline-position")).toHaveTextContent("01/03");
  });

  it("marks ONLY the features past the stop as not built", () => {
    // Stop after Extrude1 → Fillet1 alone is past it.
    renderStrip({ rollbackFeatureId: "f2" });
    expect(screen.getByTestId("timeline-chip-0")).not.toHaveAttribute(
      "data-rolled-back",
    );
    expect(screen.getByTestId("timeline-chip-1")).not.toHaveAttribute(
      "data-rolled-back",
    );
    expect(screen.getByTestId("timeline-chip-2")).toHaveAttribute(
      "data-rolled-back",
      "true",
    );
  });

  it("dashes the chips past the stop and keeps the travelled ones solid", () => {
    renderStrip({ rollbackFeatureId: "f2" });
    expect(screen.getByTestId("timeline-chip-1").className).toContain(
      "border-solid",
    );
    expect(screen.getByTestId("timeline-chip-2").className).toContain(
      "border-dashed",
    );
  });

  it("puts the solid→dashed seam of the way exactly under the stop", () => {
    // Stop after Extrude1 (slot 1): the way is solid up to the stop's centre and
    // dashed from there on — the drafting "not present" convention.
    renderStrip({ rollbackFeatureId: "f2" });
    const halves = (slotIndex: number): string[] => {
      const slot = screen.getByTestId(
        `rollback-slot-${slotIndex}`,
      ).parentElement;
      return [...(slot?.querySelectorAll("span") ?? [])].map((s) =>
        s.className.includes("border-dashed") ? "dashed" : "solid",
      );
    };
    expect(halves(0)).toEqual(["solid", "solid"]);
    expect(halves(1)).toEqual(["solid", "dashed"]);
    expect(halves(2)).toEqual(["dashed", "dashed"]);
  });

  it("says so in the accessible name, not only in the border", () => {
    renderStrip({ rollbackFeatureId: "f2" });
    expect(screen.getByTestId("timeline-chip-2")).toHaveAccessibleName(
      /not built/i,
    );
    expect(screen.getByTestId("timeline-chip-1")).toHaveAccessibleName(
      /step 2 of 3/i,
    );
  });

  it("selecting a chip hands the feature up (it is not a second selection model)", () => {
    const { onSelectFeature } = renderStrip();
    fireEvent.click(screen.getByTestId("timeline-chip-1"));
    expect(onSelectFeature).toHaveBeenCalledWith(FEATURES[1]);
  });

  it("flags an errored feature and strikes a suppressed one", () => {
    renderStrip({
      evaluation: evaluated({ f1: "ok", f2: "error", f3: "suppressed" }),
    });
    const errored = screen.getByTestId("timeline-chip-1");
    expect(errored.className).toContain("border-flag");
    expect(errored.querySelector("svg")?.getAttribute("class")).toContain(
      "text-flag",
    );
    const suppressed = screen.getByTestId("timeline-chip-2");
    expect(suppressed).toHaveAttribute("data-suppressed", "true");
    expect(within(suppressed).getByText("Fillet1").className).toContain(
      "line-through",
    );
  });

  it("invites the first feature when the part is empty", () => {
    renderStrip({ features: [] });
    expect(screen.getByTestId("timeline-empty")).toHaveTextContent(
      "start with a sketch",
    );
    expect(screen.getByTestId("timeline-to-tip")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.queryByTestId("timeline-stop")).not.toBeInTheDocument();
  });

  it("keeps its frame while the tree loads", () => {
    renderStrip({ loading: true });
    expect(screen.getByTestId("timeline-strip")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-to-tip")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });
});

describe("TimelineStrip — the travel stop", () => {
  it("sits at the tip by default and says the build is whole", () => {
    renderStrip();
    const stop = screen.getByTestId("timeline-stop");
    expect(stop).toHaveAttribute("role", "slider");
    expect(stop).toHaveAttribute("aria-valuenow", "3");
    expect(stop).toHaveAttribute("aria-valuemax", "3");
    expect(stop).toHaveAttribute(
      "aria-valuetext",
      expect.stringContaining("Tip"),
    );
  });

  it("sits in the slot the tree names, and names the last built feature", () => {
    renderStrip({ rollbackFeatureId: "f1" });
    const stop = screen.getByTestId("timeline-stop");
    expect(stop).toHaveAttribute("aria-valuenow", "1");
    expect(stop).toHaveAttribute(
      "aria-valuetext",
      "After Sketch1 — 1 of 3 built",
    );
  });

  it("travels one op per arrow key, writing the LAST INCLUDED feature id", () => {
    const { onMoveRollback } = renderStrip();
    const stop = screen.getByTestId("timeline-stop");
    // From the tip, one step back = "everything up to Extrude1".
    fireEvent.keyDown(stop, { key: "ArrowLeft" });
    expect(onMoveRollback).toHaveBeenCalledWith("f2");
  });

  it("rolls forward to the tip with null (the API's tip sentinel)", () => {
    const { onMoveRollback } = renderStrip({ rollbackFeatureId: "f1" });
    fireEvent.keyDown(screen.getByTestId("timeline-stop"), {
      key: "ArrowRight",
    });
    expect(onMoveRollback).toHaveBeenCalledWith("f2");
    onMoveRollback.mockClear();
    fireEvent.keyDown(screen.getByTestId("timeline-stop"), { key: "End" });
    expect(onMoveRollback).toHaveBeenCalledWith(null);
  });

  it("Home travels back to the first op", () => {
    const { onMoveRollback } = renderStrip();
    fireEvent.keyDown(screen.getByTestId("timeline-stop"), { key: "Home" });
    expect(onMoveRollback).toHaveBeenCalledWith("f1");
  });

  it("does not travel past the tip", () => {
    const { onMoveRollback } = renderStrip();
    fireEvent.keyDown(screen.getByTestId("timeline-stop"), {
      key: "ArrowRight",
    });
    expect(onMoveRollback).not.toHaveBeenCalled();
  });

  it("does not travel before the first op", () => {
    const { onMoveRollback } = renderStrip({ rollbackFeatureId: "f1" });
    fireEvent.keyDown(screen.getByTestId("timeline-stop"), {
      key: "ArrowLeft",
    });
    expect(onMoveRollback).not.toHaveBeenCalled();
  });

  it("holds still while a tree write is in flight", () => {
    const { onMoveRollback } = renderStrip({ busy: true });
    fireEvent.keyDown(screen.getByTestId("timeline-stop"), {
      key: "ArrowLeft",
    });
    expect(onMoveRollback).not.toHaveBeenCalled();
    expect(screen.getByTestId("timeline-stop")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("LOOKS held too — no grab cursor, and every gate names the in-flight move", () => {
    // UI-REVIEW P2-D: the stop kept `cursor: ew-resize`, full opacity and its
    // brass hover while `aria-disabled`, the slots took the NATIVE disabled
    // attribute, and TO TIP still captioned "Include all". Three controls
    // advertising an action that was being silently swallowed.
    const { onMoveRollback } = renderStrip({ busy: true });
    const stop = screen.getByTestId("timeline-stop");
    expect(stop.className).not.toContain("cursor-ew-resize");
    expect(stop.className).not.toContain("hover:text-brass-hover");

    const slot = screen.getByTestId("rollback-slot-0");
    expectGated(slot);
    fireEvent.click(slot);
    expect(onMoveRollback).not.toHaveBeenCalled();

    expect(screen.getByTestId("timeline-to-tip")).toHaveTextContent(
      "Moving the stop…",
    );
  });

  it("shows the new position immediately, then snaps back if the write fails", () => {
    const { rerender } = renderStrip();
    expect(screen.getByTestId("timeline-position")).toHaveTextContent("03/03");
    fireEvent.keyDown(screen.getByTestId("timeline-stop"), { key: "Home" });
    // Optimistic: the stop is where the user put it before the server answers.
    expect(screen.getByTestId("timeline-position")).toHaveTextContent("01/03");
    rerender({ busy: true });
    expect(screen.getByTestId("timeline-position")).toHaveTextContent("01/03");
    // The write settled and the tree did NOT move (a rejected move) → the strip
    // must tell the truth rather than keep claiming the rollback.
    rerender({ busy: false });
    expect(screen.getByTestId("timeline-position")).toHaveTextContent("03/03");
  });
});

describe("TimelineStrip — slots and the escape hatch", () => {
  it("clicking a slot on the way rolls the build back to after that op", () => {
    const { onMoveRollback } = renderStrip();
    fireEvent.click(screen.getByTestId("rollback-slot-0"));
    expect(onMoveRollback).toHaveBeenCalledWith("f1");
  });

  it("marks the occupied slot active and inert (the stop is already there)", () => {
    // Gated the product's way — `aria-disabled`, still in the a11y tree — not
    // the native attribute that made it a disabled trap (UI-REVIEW P2-D).
    renderStrip({ rollbackFeatureId: "f2" });
    const active = screen.getByTestId("rollback-slot-1");
    expect(active).toHaveAttribute("data-active", "true");
    expectGated(active);
    expect(screen.getByTestId("rollback-slot-0")).not.toHaveAttribute(
      "data-active",
    );
  });

  it("TO TIP is the escape hatch, and is honestly gated once it is taken", () => {
    const { onMoveRollback } = renderStrip({ rollbackFeatureId: "f1" });
    const toTip = screen.getByTestId("timeline-to-tip");
    expect(toTip).not.toHaveAttribute("aria-disabled");
    fireEvent.click(toTip);
    expect(onMoveRollback).toHaveBeenCalledWith(null);
  });

  it("says WHY TO TIP is gated at the tip instead of just greying out", () => {
    renderStrip();
    const toTip = screen.getByTestId("timeline-to-tip");
    expect(toTip).toHaveAttribute("aria-disabled", "true");
    expect(toTip).toHaveTextContent(/already at the tip/i);
  });
});
