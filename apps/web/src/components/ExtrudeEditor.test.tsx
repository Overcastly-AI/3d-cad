/**
 * ExtrudeEditor — the DOM half of the extrude authoring loop: does the form
 * publish what the user chose, in the unit the document is in?
 *
 * This is the other end of FINDINGS burn-down 2026-07-25 #5. That defect had
 * two halves: the viewport ignored `operation` when shading the ghost (locked
 * out in `viewport/extrudeGhost.test.ts`, below the r3f seam) and nothing
 * verified the editor even PUBLISHED the operation into the preview projection.
 * A dead field is only visible where it is produced and where it is consumed;
 * these cover the producing end.
 *
 * The viewport itself is a WebGL component jsdom cannot render, so the contract
 * asserted here is the props boundary — the `ExtrudePreviewState` handed up to
 * PartPage — not the pixels.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ExtrudeParams } from "../api/parts";
import {
  defaultExtrudeForm,
  type ExtrudeForm,
  type ExtrudePreviewState,
  type ProfileOption,
} from "../features/extrude";
import { DocumentUnitProvider } from "../units/documentUnit";
import { ExtrudeEditor } from "./ExtrudeEditor";
import type { LengthUnit } from "@loft/design";
import { expectGated } from "../test/gated";

const PROFILES: ProfileOption[] = [
  { id: "sk1", name: "Sketch 1", provenance: "base" },
];

/** Two profiles: one on a datum plane, one seated on a model face (FB-4). */
const MIXED_PROFILES: ProfileOption[] = [
  { id: "sk1", name: "Sketch 1", provenance: "base" },
  { id: "sk2", name: "Sketch on face", provenance: "face" },
];

function renderEditor(
  overrides: {
    unit?: LengthUnit;
    onPreviewChange?: (p: ExtrudePreviewState | null) => void;
    onSubmit?: (p: ExtrudeParams) => void;
    error?: string | null;
    profiles?: ProfileOption[];
    initial?: ExtrudeForm;
  } = {},
) {
  const onPreviewChange = overrides.onPreviewChange ?? vi.fn();
  const onSubmit = overrides.onSubmit ?? vi.fn();
  const onCancel = vi.fn();
  const view = render(
    <DocumentUnitProvider unit={overrides.unit ?? "mm"}>
      <ExtrudeEditor
        mode="create"
        profiles={overrides.profiles ?? PROFILES}
        initial={overrides.initial ?? defaultExtrudeForm("sk1")}
        onSubmit={onSubmit}
        onCancel={onCancel}
        saving={false}
        error={overrides.error ?? null}
        onPreviewChange={onPreviewChange}
      />
    </DocumentUnitProvider>,
  );
  return { ...view, onPreviewChange, onSubmit, onCancel };
}

/** The last non-null preview the editor published. */
function lastPreview(
  spy: ReturnType<typeof vi.fn>,
): ExtrudePreviewState | null {
  const calls = spy.mock.calls as Array<[ExtrudePreviewState | null]>;
  for (let i = calls.length - 1; i >= 0; i--) {
    const preview = calls[i]?.[0] ?? null;
    if (preview !== null) return preview;
  }
  return null;
}

describe("ExtrudeEditor preview projection", () => {
  it("publishes the seeded form as a preview on open", () => {
    const onPreviewChange = vi.fn();
    renderEditor({ onPreviewChange });
    expect(lastPreview(onPreviewChange)).toEqual({
      profileFeatureId: "sk1",
      distanceMm: 10,
      direction: "normal",
      operation: "add",
    });
  });

  it("carries the CHOSEN operation into the preview (the dead-field bug)", () => {
    const onPreviewChange = vi.fn();
    renderEditor({ onPreviewChange });
    fireEvent.click(screen.getByTestId("extrude-op-cut"));
    expect(lastPreview(onPreviewChange)?.operation).toBe("cut");
    fireEvent.click(screen.getByTestId("extrude-op-add"));
    expect(lastPreview(onPreviewChange)?.operation).toBe("add");
  });

  it("carries the chosen direction into the preview", () => {
    const onPreviewChange = vi.fn();
    renderEditor({ onPreviewChange });
    fireEvent.click(screen.getByTestId("extrude-dir-reverse"));
    expect(lastPreview(onPreviewChange)?.direction).toBe("reverse");
  });

  it("publishes the distance in canonical mm from an inch document", () => {
    const onPreviewChange = vi.fn();
    renderEditor({ unit: "in", onPreviewChange });
    fireEvent.change(screen.getByTestId("extrude-distance"), {
      target: { value: "2" },
    });
    expect(lastPreview(onPreviewChange)?.distanceMm).toBeCloseTo(50.8, 9);
  });

  it("clears the ghost when the form goes incomplete", () => {
    const onPreviewChange = vi.fn();
    renderEditor({ onPreviewChange });
    onPreviewChange.mockClear();
    fireEvent.change(screen.getByTestId("extrude-distance"), {
      target: { value: "" },
    });
    expect(onPreviewChange).toHaveBeenLastCalledWith(null);
  });

  it("clears the ghost on unmount so a closed editor leaves nothing behind", () => {
    const onPreviewChange = vi.fn();
    const { unmount } = renderEditor({ onPreviewChange });
    onPreviewChange.mockClear();
    unmount();
    expect(onPreviewChange).toHaveBeenLastCalledWith(null);
  });
});

describe("ExtrudeEditor form", () => {
  it("labels the distance cell in the document unit", () => {
    renderEditor({ unit: "in" });
    // The unit is stamped on the cell, not left implicit — an inch document
    // must never present a bare number the user reads as millimetres.
    expect(screen.getByText("in")).toBeInTheDocument();
  });

  it("submits a canonical-mm distance converted from the document unit", () => {
    const onSubmit = vi.fn();
    renderEditor({ unit: "in", onSubmit });
    fireEvent.change(screen.getByTestId("extrude-distance"), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByTestId("extrude-submit"));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const params = onSubmit.mock.calls[0]?.[0] as ExtrudeParams;
    expect(params.distance_mm).toBeCloseTo(25.4, 9);
    expect(params.profile).toEqual({ kind: "feature", feature_id: "sk1" });
  });

  it("sends the neutral merge flag on a cut, whatever the stale toggle said", () => {
    const onSubmit = vi.fn();
    renderEditor({ onSubmit });
    fireEvent.click(screen.getByTestId("extrude-merge"));
    fireEvent.click(screen.getByTestId("extrude-op-cut"));
    fireEvent.click(screen.getByTestId("extrude-submit"));
    const params = onSubmit.mock.calls[0]?.[0] as ExtrudeParams;
    expect(params.operation).toBe("cut");
    expect(params.merge).toBe(true);
  });

  it("hides the merge choice on a cut — it is meaningless there", () => {
    renderEditor();
    expect(screen.getByTestId("extrude-merge")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("extrude-op-cut"));
    expect(screen.queryByTestId("extrude-merge")).not.toBeInTheDocument();
  });

  it("explains a bad distance instead of silently disabling Save", () => {
    renderEditor();
    fireEvent.change(screen.getByTestId("extrude-distance"), {
      target: { value: "-3" },
    });
    expect(
      screen.getByText("Distance must be a positive length."),
    ).toBeInTheDocument();
    expectGated(screen.getByTestId("extrude-submit"));
  });

  it("surfaces a server failure as an alert, not a swallowed error", () => {
    renderEditor({ error: "The profile is not a closed region." });
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("The profile is not a closed region.");
  });
});

// FB-4 — the founder's cut "somehow misses everything going a different way".
// A sketch on a model face inherits that face's OUTWARD normal, so the choice
// of Cut has to carry the direction with it, and the user has to SEE it.
describe("ExtrudeEditor cut direction on a face-seated sketch", () => {
  const faceForm = defaultExtrudeForm("sk2", "face");

  it("turns a cut into the material and publishes it to the ghost", () => {
    const onPreviewChange = vi.fn();
    renderEditor({
      profiles: MIXED_PROFILES,
      initial: faceForm,
      onPreviewChange,
    });
    fireEvent.click(screen.getByTestId("extrude-op-cut"));
    expect(screen.getByTestId("extrude-dir-reverse")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const preview = lastPreview(onPreviewChange);
    expect(preview?.operation).toBe("cut");
    expect(preview?.direction).toBe("reverse");
  });

  it("submits the resolved direction, not the seeded one", () => {
    const onSubmit = vi.fn();
    renderEditor({ profiles: MIXED_PROFILES, initial: faceForm, onSubmit });
    fireEvent.click(screen.getByTestId("extrude-op-cut"));
    fireEvent.click(screen.getByTestId("extrude-submit"));
    const params = onSubmit.mock.calls[0]?.[0] as ExtrudeParams;
    expect(params.operation).toBe("cut");
    expect(params.direction).toBe("reverse");
  });

  it("keeps a direction the user picked when the operation changes", () => {
    renderEditor({ profiles: MIXED_PROFILES, initial: faceForm });
    fireEvent.click(screen.getByTestId("extrude-dir-normal"));
    fireEvent.click(screen.getByTestId("extrude-op-cut"));
    expect(screen.getByTestId("extrude-dir-normal")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("leaves a datum-plane sketch alone — no material side to infer", () => {
    renderEditor();
    fireEvent.click(screen.getByTestId("extrude-op-cut"));
    expect(screen.getByTestId("extrude-dir-normal")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("re-defaults when the profile is retargeted at a face-seated sketch", () => {
    renderEditor({ profiles: MIXED_PROFILES });
    fireEvent.click(screen.getByTestId("extrude-op-cut"));
    expect(screen.getByTestId("extrude-dir-normal")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.change(screen.getByTestId("extrude-profile"), {
      target: { value: "sk2" },
    });
    expect(screen.getByTestId("extrude-dir-reverse")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("says where the sweep goes in words, before Save", () => {
    renderEditor({ profiles: MIXED_PROFILES, initial: faceForm });
    fireEvent.click(screen.getByTestId("extrude-op-cut"));
    expect(screen.getByTestId("extrude-direction-hint")).toHaveTextContent(
      "Cuts into the part",
    );
    // …and warns when the user overrides it back out of the solid.
    fireEvent.click(screen.getByTestId("extrude-dir-normal"));
    expect(screen.getByTestId("extrude-direction-hint")).toHaveTextContent(
      "nothing to remove",
    );
  });
});

describe("ExtrudeEditor server errors", () => {
  it("surfaces a server failure as an alert, not a swallowed error", () => {
    renderEditor({ error: "The profile is not a closed region." });
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("The profile is not a closed region.");
  });
});
