/**
 * The surfaces of SKETCH-PROJECT-EDGES that a pure test cannot see: the
 * strip's Project button and guide, the tree row's "Projection lost" notice,
 * the timeline chip's hazard mark, and the sketcher's right-click Break link.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  EvaluateTreeResult,
  FeatureResponse,
  FeatureTreeResponse,
} from "../api/parts";
import { useEdgePickStore } from "../features/edgePickStore";
import { sketchMenuSections } from "../routes/part/contextMenus";
import { isProjected } from "../sketch/project";
import { useSketchStore } from "../sketch/store";
import { makeBuild } from "../test/partBuildFixture";
import { FeatureTreePanel } from "./FeatureTreePanel";
import { SketchStrip } from "./SketchStrip";
import { TimelineStrip } from "./TimelineStrip";

const SKETCH: FeatureResponse = {
  id: "s2",
  name: "Sketch2",
  part_id: "p1",
  order_index: 0,
  created_at: "2026-10-08T00:00:00Z",
  updated_at: "2026-10-08T00:00:00Z",
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

const TREE: FeatureTreeResponse = {
  part_id: "p1",
  tree_version: 1,
  features: [SKETCH],
  rollback_feature_id: null,
  can_undo: false,
  can_redo: false,
};

/** Sketch2 solved, with `sick` of its three projections gone sick. */
function evaluated(sick: number): EvaluateTreeResult {
  return {
    part_id: "p1",
    tree_version: 1,
    last_good_feature_id: null,
    mesh_glb_id: null,
    properties: null,
    features: [
      {
        feature_id: "s2",
        status: "ok",
        data: {
          kind: "solved_sketch",
          status: "converged",
          entities: [],
          projections: ["e1", "e2", "e3"].map((entity, i) =>
            i < sick
              ? {
                  entity,
                  state: "sick" as const,
                  reason: "unresolved" as const,
                }
              : { entity, state: "ok" as const, tier: "exact" as const },
          ),
        },
      },
    ],
  } as EvaluateTreeResult;
}

const RIM = {
  kind: "line" as const,
  start: { x: 0, y: 0, z: 0 },
  end: { x: 20, y: 0, z: 0 },
  polyline: [
    { x: 0, y: 0, z: 0 },
    { x: 20, y: 0, z: 0 },
  ],
  signature: {
    subshape_type: "edge" as const,
    curve: "line" as const,
    end_a: { x: 0, y: 0, z: 0 },
    end_b: { x: 20, y: 0, z: 0 },
    midpoint: { x: 10, y: 0, z: 0 },
    length_mm: 20,
  },
};

beforeEach(() => {
  useSketchStore.getState().exit();
  useEdgePickStore.getState().close();
});

describe("SketchStrip — the Project tool", () => {
  it("offers Project with its key, and arms it", () => {
    useSketchStore.getState().begin();
    useSketchStore.getState().choosePlane("XY");
    render(<SketchStrip onSave={vi.fn()} saving={false} saveError={null} />);
    const button = screen.getByTestId("tool-project");
    expect(button.getAttribute("aria-label")).toMatch(/^Project tool \(P\)/);
    fireEvent.click(button);
    expect(useSketchStore.getState().tool).toBe("project");
  });

  it("guides the pick and counts what the sketch already follows", () => {
    useSketchStore.getState().begin();
    useSketchStore.getState().choosePlane("XY");
    useSketchStore.getState().setTool("project");
    useEdgePickStore.getState().open([], true, { purpose: "project" });
    const view = render(
      <SketchStrip onSave={vi.fn()} saving={false} saveError={null} />,
    );
    // The overlay has not come back yet: say so rather than look dead.
    expect(screen.getByTestId("project-prompt")).toHaveTextContent(
      "Loading the body",
    );
    useEdgePickStore
      .getState()
      .setOverlay({ faces: [], edges: [], vertices: [] } as never);
    useSketchStore.getState().projectEdge(RIM, "anchor");
    view.rerender(
      <SketchStrip onSave={vi.fn()} saving={false} saveError={null} />,
    );
    expect(screen.getByTestId("project-prompt")).toHaveTextContent(
      "Click body edges to project them",
    );
    expect(screen.getByTestId("project-count")).toHaveTextContent(
      "1 projected",
    );
  });
});

describe("FeatureTreePanel — Projection lost", () => {
  function renderPanel(
    evaluation: EvaluateTreeResult,
    onDismissWarning = vi.fn(),
  ) {
    render(
      <FeatureTreePanel
        tree={TREE}
        treeError={null}
        evaluation={evaluation}
        build={makeBuild({ tree: TREE, evaluation })}
        selectedFeatureId={null}
        onSelectFeature={vi.fn()}
        onToggleSuppress={vi.fn()}
        onDismissWarning={onDismissWarning}
      />,
    );
    return onDismissWarning;
  }

  it("says how many projected edges are gone, under an OK row", () => {
    const dismiss = renderPanel(evaluated(2));
    const notice = screen.getByTestId("feature-projection-0");
    expect(notice).toHaveTextContent("Projection lost");
    expect(notice).toHaveTextContent(
      "2 projected edges no longer exist; the sketch keeps their last position.",
    );
    fireEvent.click(screen.getByTestId("feature-projection-dismiss-0"));
    expect(dismiss).toHaveBeenCalledTimes(1);
  });

  it("says nothing while every projection follows its edge", () => {
    renderPanel(evaluated(0));
    expect(screen.queryByTestId("feature-projection-0")).toBeNull();
  });
});

describe("TimelineStrip — the hazard on the chip", () => {
  function renderStrip(evaluation: EvaluateTreeResult) {
    render(
      <TimelineStrip
        tree={TREE}
        evaluation={evaluation}
        selectedFeatureId={null}
        onSelectFeature={vi.fn()}
        onMoveRollback={vi.fn()}
        busy={false}
        previewing={false}
      />,
    );
  }

  it("marks the sketch chip and says why, to the pointer and aloud", () => {
    renderStrip(evaluated(1));
    expect(screen.getByTestId("timeline-projection-0")).toBeTruthy();
    const chip = screen.getByTestId("timeline-chip-0");
    expect(chip.getAttribute("aria-label")).toContain(
      "1 projected edge no longer exists",
    );
    expect(chip.getAttribute("title")).toContain("Sketch2:");
  });

  it("leaves a healthy sketch chip alone", () => {
    renderStrip(evaluated(0));
    expect(screen.queryByTestId("timeline-projection-0")).toBeNull();
  });
});

describe("the sketcher's right-click menu — Break link", () => {
  it("offers Break link only for a selection holding projected geometry", () => {
    const store = () => useSketchStore.getState();
    store().begin();
    store().choosePlane("XY");
    store().projectEdge(RIM, "anchor");
    const breakItem = () =>
      sketchMenuSections()[0]?.items.find((item) => item.key === "break-link");
    expect(breakItem()?.disabled).toBe(true);
    store().togglePick({ kind: "entity", id: "e1" });
    expect(breakItem()?.disabled).toBe(false);
    breakItem()?.onSelect?.();
    expect(isProjected(store().entities[0])).toBe(false);
  });
});
