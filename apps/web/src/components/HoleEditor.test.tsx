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

import type { OverlayEdge } from "../api/measure";
import type { HoleParams } from "../api/parts";
import {
  applyHoleFace,
  defaultHoleForm,
  formFromHoleParams,
  type HoleForm,
  type HolePickTarget,
} from "../features/hole";
import { DocumentUnitProvider } from "../units/documentUnit";
import { HoleEditor } from "./HoleEditor";
import type { LengthUnit } from "@loft/design";
import { expectGated } from "../test/gated";

const TOP = {
  normal: { x: 0, y: 0, z: 1 },
  centroid: { x: 5, y: 5, z: 10 },
  area_mm2: 100,
  subshape_type: "face" as const,
  surface: "plane" as const,
};

/** A form with a picked face + seeded point — the state Create is reachable from. */
const placed = (): HoleForm =>
  applyHoleFace(
    defaultHoleForm(null, "mm"),
    { signature: TOP, anchorId: "extrude-1" },
    "mm",
  );

function renderEditor(
  overrides: {
    initial?: HoleForm;
    unit?: LengthUnit;
    activePick?: HolePickTarget | null;
    onTogglePick?: (target: HolePickTarget) => void;
    placementHidden?: boolean;
    edges?: readonly OverlayEdge[] | null;
    canPickFace?: boolean;
    pickBlockedReason?: string | null;
  } = {},
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
        canPickFace={overrides.canPickFace ?? true}
        activePick={overrides.activePick ?? null}
        onTogglePick={overrides.onTogglePick ?? vi.fn()}
        facePick={null}
        pointPick={null}
        pickError={null}
        pickBlockedReason={overrides.pickBlockedReason ?? null}
        placementHidden={overrides.placementHidden ?? false}
        edges={overrides.edges ?? null}
        onPreviewChange={vi.fn()}
      />
    </DocumentUnitProvider>,
  );
  return { ...view, onSubmit };
}

/**
 * The Tapped toggle — disclosing the Thread block first when it is shut.
 * Threading is progressively disclosed (UI-W4: it was ~5 of the card's 12 rows
 * and the everyday hole is a clearance hole), so reaching the toggle on an
 * untapped hole means opening the block. An already-tapped hole opens with it
 * showing, and the helper is a no-op there.
 */
const tapped = () => {
  if (screen.queryByTestId("hole-tapped") === null) {
    fireEvent.click(screen.getByTestId("hole-thread-toggle"));
  }
  return screen.getByTestId("hole-tapped");
};
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

describe("HoleEditor — the pinned anchor block (UI-W3 / UI-W4)", () => {
  it("opens PLACED when the cursor already had a face selected", () => {
    // The reported defect: you select a face, invoke Hole, and are asked to
    // select the same face again. Seeded from the pre-selection, the anchor
    // block reads as confirmation and Create is reachable immediately.
    const { onSubmit } = renderEditor({
      initial: defaultHoleForm({ signature: TOP, anchorId: "extrude-1" }, "mm"),
    });
    expect(screen.getByTestId("hole-face")).toHaveTextContent(
      "Face at 5, 5, 10",
    );
    expect(screen.queryByTestId("hole-face-empty")).not.toBeInTheDocument();
    // …and the drill point came with it (the face centre).
    expect(screen.getByTestId("hole-position")).toHaveTextContent(
      "Centre of face",
    );
    expect(submitted(onSubmit).position).toEqual({ x: 5, y: 5, z: 10 });
  });

  it("offers CHANGE, not PICK, once a face is set — arming is the fallback", () => {
    renderEditor({ initial: placed() });
    expect(screen.getByTestId("hole-face-pick")).toHaveTextContent("Change");
  });

  it("says what to do with the cursor while a pick is armed", () => {
    renderEditor({ initial: defaultHoleForm(null, "mm"), activePick: "face" });
    expect(screen.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByTestId("hole-face-empty")).toHaveTextContent(
      "Click a face",
    );
  });

  it("blames the viewport click, not an arming step, when nothing is placed", () => {
    renderEditor({ initial: defaultHoleForm(null, "mm") });
    const gate = submit();
    expectGated(gate);
    expect(gate).toHaveAccessibleDescription(
      "Click a face in the viewport to place the hole.",
    );
  });

  it("keeps the gated point pick reachable and self-explaining", () => {
    // The disabled-trap rule: gated by aria-disabled, still focusable, and the
    // reason is in the accessible name AND on screen.
    const onTogglePick = vi.fn();
    renderEditor({ initial: defaultHoleForm(null, "mm"), onTogglePick });
    const pick = screen.getByTestId("hole-point-pick");
    expect(pick).toHaveAttribute("aria-disabled", "true");
    expect(pick).toHaveAccessibleName(/point is placed on it/);
    expect(screen.getByTestId("hole-point-pick-reason")).toBeInTheDocument();
    fireEvent.click(pick);
    expect(onTogglePick).not.toHaveBeenCalled();
  });

  it("puts the references OUTSIDE the scrolling body so they cannot scroll away", () => {
    // UI-W4's structural claim, asserted structurally: the anchor block is a
    // sibling of the scrolling parameter body, not a row inside it.
    renderEditor({ initial: placed() });
    const anchor = screen.getByTestId("hole-anchor");
    const params = screen.getByTestId("hole-editor");
    expect(params.contains(anchor)).toBe(false);
  });
});

describe("HoleEditor — the placement body is switched off (SEL-7)", () => {
  it("says WHY the crosshair vanished, in the position row and a quiet note", () => {
    // The viewport withholds the whole placement overlay while the face's body
    // is hidden. Emptying the frame mid-command without a word is an ambiguous
    // exit, so the row stops instructing a click that cannot land and names the
    // view state instead.
    renderEditor({
      initial: placed(),
      activePick: "point",
      placementHidden: true,
    });
    expect(screen.getByTestId("hole-position")).toHaveTextContent(
      "Body hidden",
    );
    expect(screen.getByTestId("hole-placement-hidden-note")).toHaveTextContent(
      /Show that body in the Bodies panel/,
    );
  });

  it("is a VIEW state, not an error — nothing alerts", () => {
    // `hole-pick-error` is role="alert" in flag red. A body you switched off
    // yourself is not a failure, and crying wolf there would devalue the slot
    // that reports a real one.
    renderEditor({
      initial: placed(),
      activePick: "point",
      placementHidden: true,
    });
    expect(screen.queryByTestId("hole-pick-error")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps the pick armed and Create reachable — no dead end, no over-reach", () => {
    // Auto-disarming would cost the user a click they never asked for when the
    // body comes back, and a hole is legitimate geometry whose visibility is a
    // view decision: blocking the write would be the tool overruling the
    // modeller about their own part.
    const { onSubmit } = renderEditor({
      initial: placed(),
      activePick: "point",
      placementHidden: true,
    });
    expect(screen.getByTestId("hole-point-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(submitted(onSubmit).position).toEqual({ x: 5, y: 5, z: 10 });
  });

  it("restores the coordinate readout when the body comes back", () => {
    const view = renderEditor({ initial: placed(), placementHidden: true });
    expect(screen.getByTestId("hole-position")).toHaveTextContent(
      "Body hidden",
    );
    view.rerender(
      <DocumentUnitProvider unit="mm">
        <HoleEditor
          mode="create"
          initial={placed()}
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
          saving={false}
          error={null}
          canPickFace
          activePick={null}
          onTogglePick={vi.fn()}
          facePick={null}
          pointPick={null}
          pickError={null}
          pickBlockedReason={null}
          placementHidden={false}
          edges={null}
          onPreviewChange={vi.fn()}
        />
      </DocumentUnitProvider>,
    );
    expect(screen.getByTestId("hole-position")).toHaveTextContent(
      "Centre of face",
    );
    expect(
      screen.queryByTestId("hole-placement-hidden-note"),
    ).not.toBeInTheDocument();
  });
});

describe("HoleEditor — the disclosed thread block (UI-W4)", () => {
  it("keeps the thread controls out of the way until they are wanted", () => {
    renderEditor();
    expect(screen.queryByTestId("hole-tapped")).not.toBeInTheDocument();
    expect(screen.getByTestId("hole-thread-toggle")).toHaveTextContent("None");
  });

  it("opens by itself for a hole that IS tapped — an edit hides nothing", () => {
    const form = {
      ...placed(),
      tapped: true,
      threadNominalMm: 10,
      threadPitchMm: 1.5,
    };
    renderEditor({ initial: form });
    expect(screen.getByTestId("hole-tapped")).toBeInTheDocument();
    expect(screen.getByTestId("hole-thread-designation")).toHaveTextContent(
      "M10x1.5",
    );
  });

  it("reports the callout on the summary line, so a shut block still says what it holds", () => {
    renderEditor();
    fireEvent.click(tapped());
    fireEvent.change(size(), { target: { value: "10" } });
    fireEvent.click(screen.getByTestId("hole-thread-toggle")); // shut it again
    expect(screen.queryByTestId("hole-thread-size")).not.toBeInTheDocument();
    expect(screen.getByTestId("hole-thread-toggle")).toHaveTextContent(
      "M10x1.5",
    );
  });
});

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
    expectGated(submit());
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
    expectGated(submit());
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
    expectGated(submit());
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
    expectGated(submit());
  });
});

/**
 * The placement control (QA-REVIEW 2026-08-01, QA3-1). The hole used to be
 * placeable only at the face's area centroid or one of its corners, which on a
 * plate whose centre IS the shaft bore means it cannot be placed at all. These
 * assert the three things that fix has to get right: the numbers move the hole,
 * the frame they are in is stated, and a keystroke in progress is not called a
 * mistake.
 */
describe("HoleEditor — dialling the position in (QA3-1)", () => {
  /** A 10 mm square face at z = 10 with a Ø4 bore at its centre. */
  const FACE_EDGES: OverlayEdge[] = (() => {
    const z = 10;
    const corners = [
      { x: 0, y: 0, z },
      { x: 10, y: 0, z },
      { x: 10, y: 10, z },
      { x: 0, y: 10, z },
    ];
    const line = (a: (typeof corners)[0], b: (typeof corners)[0]) => ({
      kind: "line" as const,
      start: a,
      end: b,
      polyline: [a, b],
      signature: {
        curve: "line" as const,
        end_a: a,
        end_b: b,
        midpoint: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, z },
        length_mm: 10,
        subshape_type: "edge" as const,
      },
    });
    const ring: { x: number; y: number; z: number }[] = [];
    for (let i = 0; i <= 32; i += 1) {
      const t = (2 * Math.PI * i) / 32;
      ring.push({ x: 5 + 2 * Math.cos(t), y: 5 + 2 * Math.sin(t), z });
    }
    const first = ring[0]!;
    return [
      ...corners.map((a, i) => line(a, corners[(i + 1) % 4]!)),
      {
        kind: "circle" as const,
        start: first,
        end: first,
        polyline: ring,
        signature: {
          curve: "circle" as const,
          end_a: first,
          end_b: first,
          midpoint: { x: 3, y: 5, z },
          length_mm: 4 * Math.PI,
          subshape_type: "edge" as const,
        },
      },
    ];
  })();

  const x = () => screen.getByTestId("hole-position-x") as HTMLInputElement;
  const y = () => screen.getByTestId("hole-position-y") as HTMLInputElement;

  it("opens with the seeded point spelled out in the cells", () => {
    renderEditor({ initial: placed() });
    expect(x()).toHaveValue("5");
    expect(y()).toHaveValue("5");
  });

  it("drills where the numbers say — the placement the old UI could not express", () => {
    const { onSubmit } = renderEditor({ initial: placed() });
    fireEvent.change(x(), { target: { value: "2" } });
    fireEvent.change(y(), { target: { value: "-3.5" } });
    expect(submitted(onSubmit).position).toEqual({ x: 2, y: -3.5, z: 10 });
  });

  it("says WHERE zero is and which way the axes run", () => {
    // An X/Y entry that does not name its origin is how QA3-2's 0.065 mm
    // eccentric ring happened. The face is at z = 10, so the frame's zero is
    // the part origin projected onto it.
    renderEditor({ initial: placed() });
    const frame = screen.getByTestId("hole-frame");
    expect(frame).toHaveTextContent("0, 0, 10 mm");
    expect(frame).toHaveTextContent("X→+X");
    expect(frame).toHaveTextContent("Y→+Y");
    expect(frame).toHaveAccessibleName(/part origin projected onto it/);
  });

  it("reads a keystroke in progress as PENDING, never as a mistake", () => {
    const { onSubmit } = renderEditor({ initial: placed() });
    fireEvent.change(x(), { target: { value: "-" } });
    expect(x()).not.toHaveAttribute("aria-invalid");
    // …and it refuses to drill at the point the cells no longer spell, saying
    // which piece is missing rather than greying out in silence.
    const gate = submit();
    expectGated(gate);
    expect(gate).toHaveAccessibleDescription("Finish the X and Y position.");
    fireEvent.click(gate);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("calls a genuine mistake a mistake, on the cell that has to change", () => {
    renderEditor({ initial: placed() });
    fireEvent.change(y(), { target: { value: "12x" } });
    expect(y()).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Y must be a number.")).toBeInTheDocument();
  });

  it("checks the point against the face as it is typed, and NAMES the opening", () => {
    renderEditor({ initial: placed(), edges: FACE_EDGES });
    const check = () => screen.getByTestId("hole-position-check");
    // The seeded centre sits in the bore — the failure QA3-1 measured, said
    // before the round-trip instead of after it.
    expect(check()).toHaveAttribute("data-verdict", "opening");
    expect(check()).toHaveTextContent("Ø4 mm");

    fireEvent.change(x(), { target: { value: "2" } });
    fireEvent.change(y(), { target: { value: "2" } });
    expect(check()).toHaveAttribute("data-verdict", "material");

    fireEvent.change(x(), { target: { value: "50" } });
    expect(check()).toHaveAttribute("data-verdict", "outside");
  });

  it("WARNS about a bad point without blocking the write", () => {
    // Deliberate: the kernel's typed `hole_off_body` is the authority and the
    // control that stops a bad hole shipping silently. A client-side refusal
    // would substitute a coplanarity approximation for it — and hide it.
    const { onSubmit } = renderEditor({ initial: placed(), edges: FACE_EDGES });
    expect(screen.getByTestId("hole-position-check")).toHaveAttribute(
      "data-verdict",
      "opening",
    );
    expect(submit()).not.toHaveAttribute("aria-disabled");
    expect(submitted(onSubmit).position).toEqual({ x: 5, y: 5, z: 10 });
  });
});

/**
 * PICK-2 — a pick with nothing to pick refuses, and says why on the row the
 * user is already reading.
 *
 * The dead end this closes: when the tip feature builds no body, every pick
 * overlay's query is disabled, so the viewport contains no `PickSurface` and no
 * `PickNode` at all. Arming a pick over that scene produced the founder's
 * report — five clicks, two camera angles, nothing happens — with the panel
 * still badging `Picking`.
 */
describe("hole face pick — nothing to pick", () => {
  const REASON =
    "Nothing to pick — the part has no built body. Clear the error in the feature tree, then pick again.";

  it("keeps the Pick control, disables it, and carries the reason in its name", () => {
    renderEditor({ canPickFace: false, pickBlockedReason: REASON });
    const pick = screen.getByTestId("hole-face-pick");
    expect(pick).toHaveAttribute("aria-disabled", "true");
    expect(pick).toHaveAccessibleName(
      `Pick the planar face to drill into — ${REASON}`,
    );
    expect(screen.getByTestId("hole-face-pick-reason")).toHaveTextContent(
      REASON,
    );
  });

  it("does not arm on click", () => {
    const onTogglePick = vi.fn<(target: HolePickTarget) => void>();
    renderEditor({
      canPickFace: false,
      pickBlockedReason: REASON,
      onTogglePick,
    });
    fireEvent.click(screen.getByTestId("hole-face-pick"));
    expect(onTogglePick).not.toHaveBeenCalled();
  });

  it("does not tell a part that already HAS a body feature to add one", () => {
    // The pre-fix copy for `!canPickFace` was "Add a body to pick a face",
    // which is the wrong instruction for a body-affecting feature that failed.
    renderEditor({
      initial: defaultHoleForm(null, "mm"),
      canPickFace: false,
      pickBlockedReason: REASON,
    });
    const value = screen.getByTestId("hole-face-empty");
    expect(value).toHaveTextContent("No body built");
    expect(value).not.toHaveTextContent("Add a body");
  });

  it("still arms normally once a body is built", () => {
    // The regression guard: the healthy path must be untouched by the refusal.
    const onTogglePick = vi.fn<(target: HolePickTarget) => void>();
    renderEditor({ onTogglePick });
    const pick = screen.getByTestId("hole-face-pick");
    expect(pick).not.toHaveAttribute("aria-disabled");
    fireEvent.click(pick);
    expect(onTogglePick).toHaveBeenCalledWith("face");
  });
});
