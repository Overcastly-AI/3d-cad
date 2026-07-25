/**
 * FeatureTreePanel — the rebuild-error copy a modeler actually reads, and the
 * guided recovery offered beside it.
 *
 * `friendlyFeatureError` is unit-tested as a pure lookup, but the thing that
 * fails a user is the panel WIRING: the row must pass the feature's own type
 * (FINDINGS #13 — an open-profile EXTRUDE was shown revolve-centerline advice)
 * and must keep the raw code visible as an honest technical tag. It must also
 * only offer a repair the error can actually be repaired by. Those are
 * render-time decisions, invisible to a pure test and expensive to reach in a
 * browser, so they live here.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  EvaluateTreeResult,
  FeatureResponse,
  FeatureTreeResponse,
} from "../api/parts";
import { FeatureTreePanel } from "./FeatureTreePanel";

function sketch(id: string, name: string): FeatureResponse {
  return {
    id,
    name,
    part_id: "p1",
    order_index: 0,
    created_at: "2026-07-25T00:00:00Z",
    updated_at: "2026-07-25T00:00:00Z",
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

function revolve(id: string, name: string): FeatureResponse {
  return {
    ...sketch(id, name),
    order_index: 1,
    feature: {
      type: "revolve",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: "f1" },
        axis: { kind: "sketch_line", entity: "e1" },
        angle_deg: 360,
        direction: "normal",
        operation: "add",
        merge: true,
      },
    },
  };
}

function hole(id: string, name: string): FeatureResponse {
  return {
    ...sketch(id, name),
    order_index: 1,
    feature: {
      type: "hole",
      version: 1,
      params: {
        face: {
          kind: "subshape",
          feature_id: "f2",
          subshape_type: "face",
          selector: {
            selector_version: 1,
            signature: {
              subshape_type: "face",
              surface: "plane",
              area_mm2: 100,
              centroid: { x: 5, y: 5, z: 10 },
              normal: { x: 0, y: 0, z: 1 },
            },
          },
        },
        position: { x: 5, y: 5, z: 10 },
        diameter_mm: 8,
        depth: { kind: "through_all" },
      },
    },
  };
}

function tree(features: FeatureResponse[]): FeatureTreeResponse {
  return {
    part_id: "p1",
    tree_version: 1,
    features,
    rollback_feature_id: null,
    can_undo: false,
    can_redo: false,
  };
}

function failing(
  featureId: string,
  code: string,
  message = "kernel says no",
): EvaluateTreeResult {
  return {
    part_id: "p1",
    tree_version: 1,
    last_good_feature_id: null,
    mesh_glb_id: null,
    properties: null,
    features: [
      { feature_id: featureId, status: "error", error: { code, message } },
    ],
  };
}

function renderPanel(
  features: FeatureResponse[],
  evaluation: EvaluateTreeResult | undefined,
  extra: Partial<Parameters<typeof FeatureTreePanel>[0]> = {},
) {
  const onRepickFace = vi.fn();
  const onKeepAsOneBody = vi.fn();
  const view = render(
    <FeatureTreePanel
      tree={tree(features)}
      treeError={null}
      evaluation={evaluation}
      evaluating={false}
      selectedFeatureId={null}
      onSelectFeature={vi.fn()}
      onMoveRollback={vi.fn()}
      rollbackBusy={false}
      onToggleSuppress={vi.fn()}
      onRepickFace={onRepickFace}
      onKeepAsOneBody={onKeepAsOneBody}
      {...extra}
    />,
  );
  return { ...view, onRepickFace, onKeepAsOneBody };
}

describe("FeatureTreePanel rebuild errors", () => {
  it("gives an extrude EXTRUDE advice for an open profile, not revolve advice", () => {
    renderPanel(
      [sketch("f1", "Sketch 1"), extrude("f2", "Extrude 1")],
      failing("f2", "profile_not_closed"),
    );
    const row = screen.getByTestId("feature-error-1");
    expect(row).toHaveTextContent("closed region to extrude");
    // The revolve idiom (a construction centerline) must not leak across.
    expect(row).not.toHaveTextContent("centerline");
  });

  it("gives a revolve the axis idiom for the SAME error code", () => {
    renderPanel(
      [sketch("f1", "Sketch 1"), revolve("f2", "Revolve 1")],
      failing("f2", "profile_not_closed"),
    );
    const row = screen.getByTestId("feature-error-1");
    expect(row).toHaveTextContent("closed region to revolve");
    expect(row).toHaveTextContent("centerline");
  });

  it("keeps the raw code visible as an honest technical tag", () => {
    renderPanel(
      [sketch("f1", "Sketch 1"), extrude("f2", "Extrude 1")],
      failing("f2", "profile_not_closed"),
    );
    expect(screen.getByTestId("feature-error-1")).toHaveTextContent(
      "profile_not_closed",
    );
  });

  it("falls back to the server's own message for an unmapped code", () => {
    renderPanel(
      [sketch("f1", "Sketch 1"), extrude("f2", "Extrude 1")],
      failing("f2", "some_new_kernel_code", "OCCT bailed out at edge 7."),
    );
    expect(screen.getByTestId("feature-error-1")).toHaveTextContent(
      "OCCT bailed out at edge 7.",
    );
  });

  it("announces the failure to assistive tech", () => {
    renderPanel(
      [sketch("f1", "Sketch 1"), extrude("f2", "Extrude 1")],
      failing("f2", "profile_not_closed"),
    );
    expect(screen.getByTestId("feature-error-1")).toHaveAttribute(
      "role",
      "alert",
    );
  });

  it("offers the re-pick repair for a hole whose face reference is lost", () => {
    const { onRepickFace, unmount } = renderPanel(
      [sketch("f1", "Sketch 1"), hole("f3", "Hole 1")],
      failing("f3", "subshape_unresolved"),
    );
    expect(screen.getByTestId("feature-error-1")).toHaveTextContent(
      "Re-pick the face",
    );
    fireEvent.click(screen.getByTestId("feature-repick-face-1"));
    expect(onRepickFace).toHaveBeenCalledTimes(1);
    unmount();

    // A different failure on the same feature offers no face repair — a button
    // that cannot fix anything is chrome that only decorates (mandate 3a).
    renderPanel(
      [sketch("f1", "Sketch 1"), hole("f3", "Hole 1")],
      failing("f3", "hole_too_deep"),
    );
    expect(
      screen.queryByTestId("feature-repick-face-1"),
    ).not.toBeInTheDocument();
  });

  it("shows no error row for a healthy tree", () => {
    renderPanel([sketch("f1", "Sketch 1"), extrude("f2", "Extrude 1")], {
      part_id: "p1",
      tree_version: 1,
      last_good_feature_id: "f2",
      mesh_glb_id: "sha256:abc",
      properties: null,
      features: [
        { feature_id: "f1", status: "ok" },
        { feature_id: "f2", status: "ok" },
      ],
    });
    expect(screen.queryByTestId("feature-error-1")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("lists features in build order — the row number IS the build order", () => {
    renderPanel(
      [sketch("f1", "Sketch 1"), extrude("f2", "Extrude 1")],
      undefined,
    );
    const rows = screen.getAllByTestId("feature-row");
    expect(within(rows[0]!).getByText("Sketch 1")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Extrude 1")).toBeInTheDocument();
  });
});
