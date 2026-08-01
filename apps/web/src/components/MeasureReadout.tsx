/**
 * The measurement readout — a title-block instrument seated in the viewport's
 * bottom-centre HUD lane, above the view rail, while the Measure tool is armed. The measured distance is the
 * hero numeral (Fragment Mono, brass — the parametric-handle accent), with the
 * signed component deltas and, for two straight edges, the angle. Before both
 * targets are picked it is a quiet prompt; a failed measurement or overlay
 * surfaces its server message legibly. Chrome stays out of the model's way.
 */
import { CloseIcon, formatLength, MeasureIcon, Panel } from "@loft/design";

import { describePick, formatAngleDeg } from "../measure/geometry";
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
  return (
    <div className={`px-3 py-2 ${wide ? "min-w-[7rem]" : "min-w-[5rem]"}`}>
      <span className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge">
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
    return (
      <Panel
        aria-label="Measurement"
        data-testid="measure-readout"
        className={SEAT}
      >
        {header}
        <p
          className="px-3 pb-1 pt-1.5 font-body text-2xs text-gauge"
          data-testid="measure-targets"
        >
          {describePick(picks[0]!)} → {describePick(picks[1]!)}
        </p>
        <div className="grid grid-flow-col auto-cols-auto divide-x divide-hairline">
          <Cell
            eyebrow="Distance"
            value={len(result.distance)}
            tone="brass"
            testid="measure-readout-distance"
            wide
          />
          <Cell
            eyebrow="Δx"
            value={len(result.delta.x)}
            testid="measure-readout-dx"
          />
          <Cell
            eyebrow="Δy"
            value={len(result.delta.y)}
            testid="measure-readout-dy"
          />
          <Cell
            eyebrow="Δz"
            value={len(result.delta.z)}
            testid="measure-readout-dz"
          />
          {result.angle_deg !== null && result.angle_deg !== undefined ? (
            <Cell
              eyebrow="Angle"
              value={formatAngleDeg(result.angle_deg)}
              testid="measure-readout-angle"
            />
          ) : null}
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
          <span className="mt-0.5 block font-data text-2xs text-gauge">
            {describePick(picks[0]!)}
          </span>
        ) : null}
      </div>
    </Panel>
  );
}
