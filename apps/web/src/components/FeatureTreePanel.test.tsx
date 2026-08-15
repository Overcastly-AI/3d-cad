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
import { makeBuild } from "../test/partBuildFixture";
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

/** A subtractive extrude — the verb that raises `cut_removed_nothing` (CM-3). */
function extrudeCut(id: string, name: string): FeatureResponse {
  return {
    ...sketch(id, name),
    order_index: 1,
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: "f1" },
        distance_mm: 10,
        operation: "cut",
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

/**
 * The SAME hole, tapped. A tapped hole's solid is byte-identical to its bore
 * (the thread is a cosmetic callout), so the tree row is the ONLY place the
 * designation can appear — that is what the badge assertions below defend.
 */
function tappedHole(id: string, name: string): FeatureResponse {
  const base = hole(id, name);
  const feature = base.feature;
  if (feature.type !== "hole") throw new Error("expected a hole feature");
  return {
    ...base,
    feature: {
      ...feature,
      params: {
        ...feature.params,
        diameter_mm: 8.5,
        thread: {
          standard: "iso_metric",
          nominal_diameter_mm: 10,
          pitch_mm: 1.5,
        },
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
  // The panel is handed the REAL derivation over the same fixture it renders —
  // a hand-written `PartBuild` literal here would let the panel and the facts
  // drift, which is the defect this plumbing exists to prevent (J2).
  const built = tree(features);
  const view = render(
    <FeatureTreePanel
      tree={built}
      treeError={null}
      evaluation={evaluation}
      build={makeBuild({ tree: built, evaluation })}
      selectedFeatureId={null}
      onSelectFeature={vi.fn()}
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

  it("reaches the DOM with per-verb copy for a cut that removed nothing (CM-3)", () => {
    // The everyday trigger: the same pocket cut twice. The row must say so in
    // the modeler's terms, not hand back the kernel's own sentence.
    const { unmount } = renderPanel(
      [sketch("f1", "Sketch 1"), extrudeCut("f2", "Extrude 2")],
      failing(
        "f2",
        "cut_removed_nothing",
        "cut tool does not reach the target body",
      ),
    );
    const row = screen.getByTestId("feature-error-1");
    expect(row).toHaveTextContent("cut_removed_nothing");
    expect(row).toHaveTextContent("Nothing was removed");
    expect(row).toHaveTextContent("duplicates one above it");
    expect(row).not.toHaveTextContent("cut tool does not reach");
    unmount();

    // The SAME code on a revolve reads the revolve's own geometry.
    renderPanel(
      [sketch("f1", "Sketch 1"), revolve("f2", "Revolve 1")],
      failing("f2", "cut_removed_nothing"),
    );
    const revolveRow = screen.getByTestId("feature-error-1");
    expect(revolveRow).toHaveTextContent("sweeps clear of the body");
    expect(revolveRow).not.toHaveTextContent("pocket");
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

  it("humanises hole_thread_unsupported without leaking the kernel sentence", () => {
    renderPanel(
      [sketch("f1", "Sketch 1"), tappedHole("f2", "Hole1")],
      failing(
        "f2",
        "hole_thread_unsupported",
        "M7x1 is not an ISO 261 combination",
      ),
    );
    const row = screen.getByTestId("feature-error-1");
    // The code stays visible as the honest technical tag...
    expect(row).toHaveTextContent("hole_thread_unsupported");
    // ...and the copy points at the control that fixes it.
    expect(row).toHaveTextContent("choose a listed size and pitch");
    expect(row).not.toHaveTextContent("ISO 261 combination");
  });

  it("humanises hole_thread_mismatch and names the tap drill as the fix", () => {
    renderPanel(
      [sketch("f1", "Sketch 1"), tappedHole("f2", "Hole1")],
      failing(
        "f2",
        "hole_thread_mismatch",
        "A M10x1.5 thread cannot be tapped in a 20mm bore",
      ),
    );
    const row = screen.getByTestId("feature-error-1");
    expect(row).toHaveTextContent("hole_thread_mismatch");
    expect(row).toHaveTextContent("tap drill");
    expect(row).not.toHaveTextContent("cannot be tapped in a 20mm bore");
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

/**
 * AUDIT-PRODUCT N3: the strict-prefix rule drops every feature after the first
 * failure, so one bad hole pick also strands a datum plane, a far-corner dowel
 * hole and a corner fillet. Those rows used to render the bare badge "SKIP" whose
 * only accessible text was "evaluation skipped" — no reason, no link to the
 * blocker — so an independent fillet vanishing looked like a fillet bug.
 */
describe("FeatureTreePanel skipped rows", () => {
  const bracket = () => [
    sketch("f1", "Base profile"),
    extrude("f2", "Base extrude"),
    hole("f3", "Hole 1"),
    extrude("f4", "Dowel hole"),
    extrude("f5", "Corner fillets R8"),
  ];

  const stranded = (): EvaluateTreeResult => ({
    part_id: "p1",
    tree_version: 1,
    last_good_feature_id: "f2",
    mesh_glb_id: "sha256:abc",
    properties: null,
    features: [
      { feature_id: "f1", status: "ok" },
      { feature_id: "f2", status: "ok" },
      {
        feature_id: "f3",
        status: "error",
        error: {
          code: "hole_off_body",
          message: "The hole removed no material",
        },
      },
      { feature_id: "f4", status: "skipped" },
      { feature_id: "f5", status: "skipped" },
    ],
  });

  it("names the blocking feature on EVERY skipped row", () => {
    renderPanel(bracket(), stranded());
    const rows = screen.getAllByTestId("feature-row");
    [3, 4].forEach((index) => {
      const row = rows[index]!;
      expect(row).toHaveAttribute("data-blocked-by", "f3");
      expect(
        within(row).getByLabelText(
          "evaluation skipped: not attempted — Hole 1 failed first",
        ),
      ).toBeInTheDocument();
    });
  });

  it("states once, where the build stopped, that independent features were dropped", () => {
    renderPanel(bracket(), stranded());
    const note = screen.getByTestId("feature-excluded-note");
    expect(note).toHaveTextContent("Not attempted: the 2 features below");
    expect(note).toHaveTextContent("does not depend on Hole 1");
  });

  it("does not blame a failure for a row the user suppressed", () => {
    renderPanel([sketch("f1", "Sketch 1"), extrude("f2", "Extrude 1")], {
      part_id: "p1",
      tree_version: 1,
      last_good_feature_id: "f1",
      mesh_glb_id: null,
      properties: null,
      features: [
        { feature_id: "f1", status: "ok" },
        { feature_id: "f2", status: "suppressed" },
      ],
    });
    const row = screen.getAllByTestId("feature-row")[1]!;
    expect(row).not.toHaveAttribute("data-blocked-by");
    expect(
      within(row).getByLabelText("evaluation suppressed"),
    ).toBeInTheDocument();
  });

  it("keeps the SOLVE cell's verdict, now from the shared derivation", () => {
    const { unmount } = renderPanel(bracket(), stranded());
    expect(screen.getByTestId("eval-status")).toHaveTextContent("Failed");
    unmount();

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
    expect(screen.getByTestId("eval-status")).toHaveTextContent("Solved");
    expect(screen.queryByTestId("feature-excluded-note")).toBeNull();
  });
});

describe("FeatureTreePanel row badge", () => {
  it("carries the designation for a TAPPED hole — the only place it is visible", () => {
    renderPanel(
      [sketch("f1", "Sketch 1"), tappedHole("f2", "Hole1")],
      undefined,
    );
    const row = screen.getAllByTestId("feature-row")[1]!;
    expect(row).toHaveTextContent("M10x1.5");
  });

  it("says only 'hole' for an untapped one (no phantom callout)", () => {
    renderPanel([sketch("f1", "Sketch 1"), hole("f2", "Hole1")], undefined);
    const row = screen.getAllByTestId("feature-row")[1]!;
    expect(within(row).getByText("hole")).toBeInTheDocument();
    expect(within(row).queryByText(/M\d/)).not.toBeInTheDocument();
  });
});

// FB-19 — the origin set was six full-width rows saying "XY, XZ, YZ, X, Y, Z".
// It is a 3x2 datum table now. What must survive the compaction: the six
// toggles, their test hooks, their pressed state, and — the thing a smaller
// control is most likely to lose — a name that says WHICH KIND of datum it is,
// since the visible label no longer carries "plane"/"axis".
describe("FeatureTreePanel origin datum table", () => {
  const ORIGIN = [
    ["origin-plane-XY", "Show XY plane"],
    ["origin-plane-XZ", "Show XZ plane"],
    ["origin-plane-YZ", "Show YZ plane"],
    ["origin-axis-X", "Show X axis"],
    ["origin-axis-Y", "Show Y axis"],
    ["origin-axis-Z", "Show Z axis"],
  ] as const;

  it("keeps all six datums as named, pressable toggles", () => {
    renderPanel([sketch("f1", "Sketch 1")], undefined);
    for (const [testId, name] of ORIGIN) {
      const cell = screen.getByTestId(testId);
      expect(cell).toHaveAttribute("aria-pressed", "false");
      expect(cell).toHaveAccessibleName(name);
    }
    // Six cells, one list — the shape the grid is laid out on.
    expect(
      within(screen.getByTestId("origin-list")).getAllByRole("button"),
    ).toHaveLength(6);
  });

  it("draws a datum when its cell is pressed, and says so", () => {
    renderPanel([sketch("f1", "Sketch 1")], undefined);
    const cell = screen.getByTestId("origin-plane-XZ");
    fireEvent.click(cell);
    expect(cell).toHaveAttribute("aria-pressed", "true");
    expect(cell).toHaveAccessibleName("Hide XZ plane");
    fireEvent.click(cell);
    expect(cell).toHaveAttribute("aria-pressed", "false");
  });
});
