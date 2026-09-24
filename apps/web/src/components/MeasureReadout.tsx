/**
 * The measurement readout — a title-block instrument seated in the viewport's
 * bottom-centre HUD lane, above the view rail, while the Measure tool is armed.
 * The measured distance is the hero numeral (Fragment Mono, brass — the
 * parametric-handle accent), with the signed component deltas and, for two
 * straight edges, the angle. Before both targets are picked it is a quiet
 * prompt; a failed measurement or overlay surfaces its server message legibly.
 * Chrome stays out of the model's way.
 *
 * WHICH NUMBER IS WHICH (MEASURE-LABEL-PITCH-1). The kernel reading is the
 * MINIMUM distance, and it says so whenever an edge is involved. When a pick is
 * a circle the hero becomes the CENTRE reading instead — two holes read their
 * pitch, the number an engineer came for — with its deltas beside it and the
 * minimum kept at the end of the row, labelled, never silently swapped. The
 * from/to lines name each target by what it IS (diameter and centre), not by an
 * ordinal. They are set in the body face on purpose: the data face slashes its
 * zero, so "Ø8" read as "08" there.
 */
import { CloseIcon, formatLength, MeasureIcon, Panel } from "@loft/design";
import { useId } from "react";

import {
  centreReading,
  centreReadingLabel,
  describePick,
  formatAngleDeg,
  minimumReadingLabel,
  type MeasurePick,
} from "../measure/geometry";
import { useMeasureStore } from "../measure/store";
import { useDocumentLengthUnit } from "../units/documentUnit";

/**
 * The seat: the bottom-centre HUD lane (`layout.hudLaneBottom`), which clears
 * the view rail. One anchor for all three states of this instrument — before
 * 2026-07-30 this was `bottom-16`, a step the closed spacing scale does not
 * have, so the panel fell back to STATIC and rendered at the TOP of the frame,
 * under the command band and behind its own tooltip.
 */
const SEAT = "absolute bottom-hud-lane left-1/2 -translate-x-1/2";

/** One title-block cell: tracked eyebrow over a data-face value. */
function Cell({
  eyebrow,
  value,
  tone = "mist",
  testid,
  wide = false,
}: {
  eyebrow: string;
  value: string;
  tone?: "brass" | "mist" | "gauge";
  testid?: string;
  wide?: boolean;
}) {
  const toneClass =
    tone === "brass"
      ? "text-brass"
      : tone === "gauge"
        ? "text-gauge"
        : "text-mist";
  // The eyebrow NAMES the value (a group labelled by its caption), so "which
  // number is the minimum?" has an answer a screen reader and a spec can ask.
  const eyebrowId = useId();
  return (
    <div
      role="group"
      aria-labelledby={eyebrowId}
      className={`px-3 py-2 ${wide ? "min-w-[7rem]" : "min-w-[5rem]"}`}
    >
      <span
        id={eyebrowId}
        className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge"
      >
        {eyebrow}
      </span>
      <span
        className={`block font-data ${wide ? "text-lg" : "text-md"} tabular-nums ${toneClass}`}
        data-testid={testid}
      >
        {value}
      </span>
    </div>
  );
}

export function MeasureReadout() {
  const unit = useDocumentLengthUnit();
  // Measured lengths format in the document unit with the unit stamped
  // lowercase adjacent to the value (`25.4 mm`) — the app-wide convention, so
  // the eyebrow stays a bare caption. The angle is always degrees.
  const len = (mm: number) => formatLength(mm, unit, { unitSuffix: true });
  const active = useMeasureStore((s) => s.active);
  const overlay = useMeasureStore((s) => s.overlay);
  const picks = useMeasureStore((s) => s.picks);
  const result = useMeasureStore((s) => s.result);
  const overlayError = useMeasureStore((s) => s.overlayError);
  const measureError = useMeasureStore((s) => s.measureError);
  const reset = useMeasureStore((s) => s.reset);
  const deactivate = useMeasureStore((s) => s.deactivate);

  if (!active) return null;

  const header = (
    <div className="flex items-center justify-between gap-3 border-b border-hairline px-3 py-1.5">
      <span className="flex items-center gap-2 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
        <span aria-hidden className="text-brass">
          <MeasureIcon size={14} />
        </span>
        Measure
      </span>
      <div className="flex items-center gap-1">
        {picks.length > 0 ? (
          <button
            type="button"
            data-testid="measure-clear"
            onClick={reset}
            className="rounded-sm px-1.5 py-0.5 font-display text-2xs uppercase tracking-[0.14em] text-gauge hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
          >
            Clear
          </button>
        ) : null}
        <button
          type="button"
          data-testid="measure-exit"
          aria-label="Close measure tool"
          onClick={deactivate}
          className="rounded-sm p-0.5 text-gauge hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
        >
          <CloseIcon size={14} />
        </button>
      </div>
    </div>
  );

  // Failure envelopes — surfaced legibly, never a crash.
  const error = overlayError ?? measureError;
  if (error !== null) {
    return (
      <Panel
        aria-label="Measurement"
        data-testid="measure-readout"
        className={SEAT}
      >
        {header}
        <p
          role="alert"
          data-testid="measure-error"
          className="max-w-sm px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      </Panel>
    );
  }

  // Resolved measurement — the title-block reading.
  if (result !== null && picks.length === 2) {
    const [a, b] = picks as [MeasurePick, MeasurePick];
    const centre = centreReading(a, b, overlay);
    const minimum = (
      <Cell
        eyebrow={minimumReadingLabel(result.kind)}
        value={len(result.distance)}
        tone={centre === null ? "brass" : "mist"}
        testid="measure-readout-distance"
        wide
      />
    );
    // The deltas belong to the HERO reading and sit beside it: the centre
    // offsets when there is a centre reading, else the kernel's own.
    const delta = centre?.delta ?? result.delta;
    return (
      <Panel
        aria-label="Measurement"
        data-testid="measure-readout"
        className={SEAT}
      >
        {header}
        <dl
          className="grid grid-cols-[auto_1fr] items-baseline gap-x-2 px-3 pb-1 pt-1.5"
          data-testid="measure-targets"
        >
          <dt className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            From
          </dt>
          <dd
            className="font-body text-2xs tabular-nums text-mist"
            data-testid="measure-target-a"
          >
            {describePick(a, overlay, unit)}
          </dd>
          <dt className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            To
          </dt>
          <dd
            className="font-body text-2xs tabular-nums text-mist"
            data-testid="measure-target-b"
          >
            {describePick(b, overlay, unit)}
          </dd>
        </dl>
        <div className="grid grid-flow-col auto-cols-auto divide-x divide-hairline border-t border-hairline">
          {centre !== null ? (
            <Cell
              eyebrow={centreReadingLabel(centre)}
              value={len(centre.distance)}
              tone="brass"
              testid="measure-readout-centre"
              wide
            />
          ) : (
            minimum
          )}
          <Cell eyebrow="Δx" value={len(delta.x)} testid="measure-readout-dx" />
          <Cell eyebrow="Δy" value={len(delta.y)} testid="measure-readout-dy" />
          <Cell eyebrow="Δz" value={len(delta.z)} testid="measure-readout-dz" />
          {result.angle_deg !== null && result.angle_deg !== undefined ? (
            <Cell
              eyebrow="Angle"
              value={formatAngleDeg(result.angle_deg)}
              testid="measure-readout-angle"
            />
          ) : null}
          {centre !== null ? minimum : null}
        </div>
      </Panel>
    );
  }

  // Prompt — an invitation to act (the empty state).
  return (
    <Panel
      aria-label="Measurement"
      data-testid="measure-readout"
      className={SEAT}
    >
      {header}
      <div className="px-3 py-2" data-testid="measure-prompt">
        <span className="block font-body text-xs text-mist">
          {picks.length === 0
            ? "Pick a point or edge"
            : "Pick the second point or edge"}
        </span>
        {picks.length === 1 ? (
          <span className="mt-0.5 block font-body text-2xs text-gauge">
            {describePick(picks[0]!, overlay, unit)}
          </span>
        ) : null}
      </div>
    </Panel>
  );
}
