/**
 * HoleEditor — the TAPPED half of the hole authoring loop.
 *
 * A tapped hole is the one feature whose result is invisible: the kernel proves
 * the `/evaluate` response is byte-identical with and without the thread, so no
 * viewport assertion and no geometry golden can tell you the editor published
 * the right callout. That makes this tier the only place the contract is
 * checked end-to-end on the client: does ticking Tapped DERIVE the ISO tap
 * drill into the bore, does the wire carry `thread` as a SIBLING of `type`, and
 * do the two typed server errors (`hole_thread_unsupported` /
 * `hole_thread_mismatch`) get caught here before a round-trip that would build
 * no body at all?
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { HoleParams } from "../api/parts";
import {
  applyHoleFace,
  defaultHoleForm,
  formFromHoleParams,
  type HoleForm,
} from "../features/hole";
import { DocumentUnitProvider } from "../units/documentUnit";
import { HoleEditor } from "./HoleEditor";
import type { LengthUnit } from "@loft/design";

const TOP = {
  normal: { x: 0, y: 0, z: 1 },
  centroid: { x: 5, y: 5, z: 10 },
  area_mm2: 100,
  subshape_type: "face" as const,
  surface: "plane" as const,
};

/** A form with a picked face + seeded point — the state Create is reachable from. */
const placed = (): HoleForm =>
  applyHoleFace(defaultHoleForm(), { signature: TOP, anchorId: "extrude-1" });

function renderEditor(
  overrides: { initial?: HoleForm; unit?: LengthUnit } = {},
) {
  const onSubmit = vi.fn<(params: HoleParams) => void>();
  const view = render(
    <DocumentUnitProvider unit={overrides.unit ?? "mm"}>
      <HoleEditor
        mode="create"
        initial={overrides.initial ?? placed()}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        saving={false}
        error={null}
        canPickFace
        activePick={null}
        onTogglePick={vi.fn()}
        facePick={null}
        pointPick={null}
        pickError={null}
        onPreviewChange={vi.fn()}
      />
    </DocumentUnitProvider>,
  );
  return { ...view, onSubmit };
}

const tapped = () => screen.getByTestId("hole-tapped");
const diameter = () => screen.getByTestId("hole-diameter") as HTMLInputElement;
const size = () => screen.getByTestId("hole-thread-size") as HTMLSelectElement;
const pitch = () =>
  screen.getByTestId("hole-thread-pitch") as HTMLSelectElement;
const submit = () => screen.getByTestId("hole-submit");

/** The params the editor published on Create. */
function submitted(onSubmit: ReturnType<typeof vi.fn>): HoleParams {
  fireEvent.click(submit());
  expect(onSubmit).toHaveBeenCalledTimes(1);
  return onSubmit.mock.calls[0]![0] as HoleParams;
}

describe("HoleEditor — the Tapped toggle", () => {
  it("is a toggle beside Type, not a fourth segment inside it", () => {
    renderEditor();
    // Threading is orthogonal to the recess: the Type control still offers
    // exactly the three recess shapes, and Tapped is its own checkbox.
    expect(screen.getByTestId("hole-type-simple")).toBeInTheDocument();
    expect(screen.getByTestId("hole-type-counterbore")).toBeInTheDocument();
    expect(screen.getByTestId("hole-type-countersink")).toBeInTheDocument();
    expect(screen.queryByTestId("hole-type-tapped")).not.toBeInTheDocument();
    expect(tapped()).toHaveAttribute("aria-checked", "false");
  });

  it("hides the thread controls until the hole is tapped", () => {
    renderEditor();
    expect(
      screen.queryByTestId("hole-thread-designation"),
    ).not.toBeInTheDocument();
    fireEvent.click(tapped());
    expect(screen.getByTestId("hole-thread-designation")).toBeInTheDocument();
  });

  it("composes with a counterbore — a counterbored tapped hole is ONE feature", () => {
    const { onSubmit } = renderEditor();
    fireEvent.click(screen.getByTestId("hole-type-counterbore"));
    fireEvent.click(tapped());
    fireEvent.change(size(), { target: { value: "6" } });
    const params = submitted(onSubmit);
    expect(params.type?.kind).toBe("counterbore");
    expect(params.thread).toEqual({
      standard: "iso_metric",
      nominal_diameter_mm: 6,
      pitch_mm: 1,
    });
  });

  it("omits `thread` entirely when untapped (the pre-tapped wire, unchanged)", () => {
    const { onSubmit } = renderEditor();
    const params = submitted(onSubmit);
    expect(params.thread).toBeUndefined();
    expect("thread" in params).toBe(false);
  });
});

describe("HoleEditor — the bore is derived from the designation", () => {
  it("fills the bore with the ISO tap drill when Tapped is ticked", () => {
    renderEditor();
    expect(diameter().value).toBe("6");
    fireEvent.click(tapped());
    // M6x1 (the default designation) → D - P = 5.0.
    expect(screen.getByTestId("hole-thread-designation")).toHaveTextContent(
      "M6x1",
    );
    expect(diameter().value).toBe("5");
  });

  it("re-derives the bore when the size changes, and resets to the COARSE pitch", () => {
    renderEditor();
    fireEvent.click(tapped());
    fireEvent.change(size(), { target: { value: "10" } });
    expect(pitch().value).toBe("1.5"); // coarse, not the previous 1
    expect(screen.getByTestId("hole-thread-designation")).toHaveTextContent(
      "M10x1.5",
    );
    expect(diameter().value).toBe("8.5"); // the published M10x1.5 tap drill
  });

  it("re-derives the bore when a FINE pitch is chosen", () => {
    renderEditor();
    fireEvent.click(tapped());
    fireEvent.change(size(), { target: { value: "8" } });
    expect(diameter().value).toBe("6.75");
    fireEvent.change(pitch(), { target: { value: "1" } });
    expect(screen.getByTestId("hole-thread-designation")).toHaveTextContent(
      "M8x1",
    );
    expect(diameter().value).toBe("7");
  });

  it("derives in the DOCUMENT unit — the designation stays metric", () => {
    // An M10x1.5 in an inch drawing is still an M10x1.5; only the bore field
    // converts (8.5 mm = 0.3346 in).
    renderEditor({ unit: "in" });
    fireEvent.click(tapped());
    fireEvent.change(size(), { target: { value: "10" } });
    expect(screen.getByTestId("hole-thread-designation")).toHaveTextContent(
      "M10x1.5",
    );
    expect(Number(diameter().value)).toBeCloseTo(8.5 / 25.4, 5);
    expect(screen.getByTestId("hole-thread-tap-drill")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("does NOT lock the bore — an override sticks and the chip restores it", () => {
    const { onSubmit } = renderEditor();
    fireEvent.click(tapped());
    fireEvent.change(size(), { target: { value: "8" } });
    // The shop's rounded stock drill for M8x1.25 (D - P is 6.75). The kernel
    // accepts the whole [minor, nominal) band, so this must submit.
    fireEvent.change(diameter(), { target: { value: "6.8" } });
    expect(screen.getByTestId("hole-thread-tap-drill")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(submitted(onSubmit).diameter_mm).toBe(6.8);

    // ...and one click puts the derived value back.
    fireEvent.click(screen.getByTestId("hole-thread-tap-drill"));
    expect(diameter().value).toBe("6.75");
  });

  it("leaves the bore alone when Tapped is unticked (no silent resize)", () => {
    renderEditor();
    fireEvent.click(tapped());
    expect(diameter().value).toBe("5");
    fireEvent.click(tapped());
    expect(diameter().value).toBe("5");
  });
});

describe("HoleEditor — hole_thread_mismatch, caught before the round-trip", () => {
  it("blocks Create and names the tap drill when the bore is too small", () => {
    const { onSubmit } = renderEditor();
    fireEvent.click(tapped());
    fireEvent.change(size(), { target: { value: "10" } });
    // Below the M10x1.5 minor diameter (8.376) — the tap cannot enter.
    fireEvent.change(diameter(), { target: { value: "8" } });
    expect(screen.getByTestId("hole-editor")).toHaveTextContent(
      "Too small to tap M10x1.5",
    );
    expect(screen.getByTestId("hole-editor")).toHaveTextContent(
      "Ø8.5 mm tap drill",
    );
    expect(submit()).toBeDisabled();
    fireEvent.click(submit());
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("blocks Create when the bore is at or above the nominal diameter", () => {
    renderEditor();
    fireEvent.click(tapped());
    fireEvent.change(size(), { target: { value: "10" } });
    fireEvent.change(diameter(), { target: { value: "12" } });
    expect(screen.getByTestId("hole-editor")).toHaveTextContent(
      "Too wide to tap M10x1.5",
    );
    expect(submit()).toBeDisabled();
  });

  it("marks the DIAMETER field invalid — the field that has to change", () => {
    renderEditor();
    fireEvent.click(tapped());
    fireEvent.change(diameter(), { target: { value: "3" } });
    expect(diameter()).toHaveAttribute("aria-invalid", "true");
  });
});

describe("HoleEditor — hole_thread_unsupported, shown and repairable", () => {
  /** A hole authored elsewhere (API/script) with a designation off ISO 261. */
  function offSeriesParams(): HoleParams {
    return {
      face: {
        kind: "subshape",
        feature_id: "extrude-1",
        subshape_type: "face",
        selector: { selector_version: 1, signature: TOP },
      },
      position: { x: 5, y: 5, z: 10 },
      diameter_mm: 6,
      depth: { kind: "through_all" },
      thread: {
        standard: "iso_metric",
        nominal_diameter_mm: 7,
        pitch_mm: 1,
      },
    };
  }

  it("shows the stored designation verbatim rather than rewriting it", () => {
    renderEditor({ initial: formFromHoleParams(offSeriesParams(), "mm") });
    expect(tapped()).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("hole-thread-designation")).toHaveTextContent(
      "M7x1",
    );
    expect(size().value).toBe("7");
  });

  it("says why it can't be cut and blocks Create", () => {
    const { onSubmit } = renderEditor({
      initial: formFromHoleParams(offSeriesParams(), "mm"),
    });
    expect(screen.getByTestId("hole-editor")).toHaveTextContent(
      "M7 isn't a standard ISO size",
    );
    expect(submit()).toBeDisabled();
    fireEvent.click(submit());
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("repairs in one pick — choosing a listed size clears the error", () => {
    const { onSubmit } = renderEditor({
      initial: formFromHoleParams(offSeriesParams(), "mm"),
    });
    fireEvent.change(size(), { target: { value: "8" } });
    expect(screen.getByTestId("hole-editor")).not.toHaveTextContent(
      "standard ISO size",
    );
    const params = submitted(onSubmit);
    expect(params.thread).toEqual({
      standard: "iso_metric",
      nominal_diameter_mm: 8,
      pitch_mm: 1.25,
    });
    expect(params.diameter_mm).toBe(6.75);
  });

  it("names the standard pitches when only the PITCH is off", () => {
    const params = offSeriesParams();
    params.thread = {
      standard: "iso_metric",
      nominal_diameter_mm: 10,
      pitch_mm: 1.75,
    };
    params.diameter_mm = 8.5;
    renderEditor({ initial: formFromHoleParams(params, "mm") });
    // The server's own guidance, client-side: M10 is standardised at these.
    expect(screen.getByTestId("hole-editor")).toHaveTextContent(
      "M10 is standardised at 1.5, 1.25, 1, 0.75 mm",
    );
    expect(submit()).toBeDisabled();
  });
});
