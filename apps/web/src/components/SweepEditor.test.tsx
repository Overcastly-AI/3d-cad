/**
 * SweepEditor — twist along path (TWIST-TO-SWEEP): the Twist field writes the
 * signed angle, a stored twist survives an edit of anything else, and the
 * sweep's own rebuild refusals read in the card, in the flag slot a failed
 * save uses.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SketchEntity, SweepParams } from "../api/parts";
import { friendlyFeatureError } from "../features/featureErrors";
import {
  defaultSweepForm,
  formFromSweepParams,
  type ProfileOption,
  type SweepForm,
} from "../features/sweep";
import { SweepEditor } from "./SweepEditor";

const PROFILES: ProfileOption[] = [
  { id: "s1", name: "Sketch1", provenance: "base" },
  { id: "s2", name: "Sketch2", provenance: "base" },
  { id: "s3", name: "Sketch3", provenance: "base" },
];
const PATHS = {
  s1: [PROFILES[1]!, PROFILES[2]!],
  s2: [PROFILES[0]!, PROFILES[2]!],
  s3: [PROFILES[0]!, PROFILES[1]!],
};

function renderEditor(
  overrides: {
    initial?: SweepForm;
    rebuildError?: string | null;
    error?: string | null;
    profileEntities?: (id: string) => readonly SketchEntity[] | null;
  } = {},
) {
  const onSubmit = vi.fn<(p: SweepParams) => void>();
  render(
    <SweepEditor
      mode="edit"
      profiles={PROFILES}
      pathsByProfile={PATHS}
      initial={overrides.initial ?? defaultSweepForm("s1", "s2")}
      onSubmit={onSubmit}
      onCancel={vi.fn()}
      saving={false}
      error={overrides.error ?? null}
      rebuildError={overrides.rebuildError ?? null}
      {...(overrides.profileEntities !== undefined
        ? { profileEntities: overrides.profileEntities }
        : {})}
    />,
  );
  return { onSubmit };
}

const TWISTED: SweepParams = {
  profile: { kind: "feature", feature_id: "s1" },
  path: { kind: "feature", feature_id: "s2" },
  operation: "add",
  merge: true,
  twist_angle_deg: 30,
};

describe("SweepEditor — the Twist field", () => {
  it("is empty by default and sends no twist", () => {
    const { onSubmit } = renderEditor();
    const field = screen.getByTestId("sweep-twist");
    expect(field).toHaveValue("");
    // `text`: iOS's decimal pad has no minus, and a left-hand twist is negative.
    expect(field).toHaveAttribute("inputmode", "text");
    expect(screen.queryByTestId("sweep-twist-note")).toBeNull();
    fireEvent.click(screen.getByTestId("sweep-submit"));
    expect(Object.keys(onSubmit.mock.calls[0]?.[0] ?? {})).not.toContain(
      "twist_angle_deg",
    );
  });

  it("sends a typed left-hand twist, and says which hand it is", () => {
    const { onSubmit } = renderEditor();
    const field = screen.getByTestId("sweep-twist");
    fireEvent.change(field, { target: { value: "-90" } });
    expect(screen.getByTestId("sweep-twist-note")).toHaveTextContent(
      /Left-hand.*90°.*clockwise.*straight line perpendicular/,
    );
    fireEvent.keyDown(field, { key: "Enter" });
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({ twist_angle_deg: -90 });
  });

  it("holds Save with a reason on a twist beyond ten turns", () => {
    const { onSubmit } = renderEditor();
    fireEvent.change(screen.getByTestId("sweep-twist"), {
      target: { value: "4000" },
    });
    expect(screen.getByText(/at most 3600 either way/)).toBeInTheDocument();
    expect(screen.getByTestId("sweep-submit")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    fireEvent.click(screen.getByTestId("sweep-submit"));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("keeps a stored twist when only the path is changed (data safety)", () => {
    const { onSubmit } = renderEditor({
      initial: formFromSweepParams(TWISTED),
    });
    expect(screen.getByTestId("sweep-twist")).toHaveValue("30");
    fireEvent.change(screen.getByTestId("sweep-path"), {
      target: { value: "s3" },
    });
    fireEvent.click(screen.getByTestId("sweep-submit"));
    expect(onSubmit.mock.calls[0]?.[0]).toEqual({
      ...TWISTED,
      path: { kind: "feature", feature_id: "s3" },
    });
  });

  it("says, quietly, when this many turns on this profile may be refused", () => {
    const hexagon: SketchEntity[] = Array.from({ length: 6 }, (_, i) => {
      const a = (i / 6) * 2 * Math.PI;
      const b = ((i + 1) / 6) * 2 * Math.PI;
      return {
        id: `l${i}`,
        kind: "line" as const,
        start: { x: 10 * Math.cos(a), y: 10 * Math.sin(a) },
        end: { x: 10 * Math.cos(b), y: 10 * Math.sin(b) },
        construction: false,
      };
    });
    renderEditor({ profileEntities: () => hexagon });
    const field = screen.getByTestId("sweep-twist");
    fireEvent.change(field, { target: { value: "2880" } });
    expect(screen.queryByTestId("sweep-twist-slow")).toBeNull();
    fireEvent.change(field, { target: { value: "-3060" } });
    expect(screen.getByTestId("sweep-twist-slow")).toHaveTextContent(
      /may be slow to build, or refused/i,
    );
  });
});

describe("SweepEditor — the sweep's rebuild refusals read in the card", () => {
  for (const code of ["twist_path_unsupported", "twist_failed"]) {
    it(`shows ${code} in the flag slot until the form is changed`, () => {
      const copy = friendlyFeatureError(code, "raw", "sweep");
      renderEditor({
        initial: formFromSweepParams(TWISTED),
        rebuildError: copy,
      });
      const alert = screen.getByTestId("sweep-rebuild-error");
      expect(alert).toHaveAttribute("role", "alert");
      expect(alert).toHaveTextContent(copy);
      // Editing the twist is the user curing it: the stale reason steps aside.
      fireEvent.change(screen.getByTestId("sweep-twist"), {
        target: { value: "0" },
      });
      expect(screen.queryByTestId("sweep-rebuild-error")).toBeNull();
    });
  }

  it("a failed SAVE takes the slot over a stale rebuild reason", () => {
    renderEditor({
      initial: formFromSweepParams(TWISTED),
      rebuildError: "stale",
      error: "The sweep could not be saved.",
    });
    expect(screen.getByTestId("sweep-error")).toBeInTheDocument();
    expect(screen.queryByTestId("sweep-rebuild-error")).toBeNull();
  });
});
