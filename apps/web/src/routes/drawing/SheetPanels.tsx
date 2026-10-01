/**
 * The drawing's right-hand "Views" panel stack: the views legend, the bend
 * schedule, the parts list, notes and dimensions. Split out of
 * `DrawingPage.tsx` (SPLIT-DRAWINGPAGE); behaviour unchanged.
 */
import { useState } from "react";

import { Button, Stamp, TextField, drawing } from "@loft/design";

import type {
  AnnotationResponse,
  BendTableRow,
  ComposedView,
  DimensionResponse,
  DrawingBomLine,
  DrawingViewResult,
  MeasuredDimension,
  RefDocumentKind,
  ViewProjection,
} from "../../api/drawings";
import {
  healDimensionParams,
  reanchoredAnchor,
} from "../../drawing/anchorHeal";
import { formatDimensionLabel } from "../../drawing/dimensions";
import { VIEW_LABEL } from "../../drawing/layout";

/** The right-hand "Views" panel — a functional legend + per-view line count. It
 * lists exactly the projections placed on the sheet (the standard four, or a lone
 * flat pattern), and its legend gains the FOLD-LINE swatch when a flat pattern is
 * present (the sheet-metal signature stroke), reading from the same `drawing`
 * token both renderers share. */
export function ViewsPanel({
  projecting,
  projections,
  resultByProjection,
  composedByProjection,
}: {
  projecting: boolean;
  projections: readonly ViewProjection[];
  resultByProjection: Map<ViewProjection, DrawingViewResult>;
  /**
   * The PLACED views, which for an assembly sheet are the only reading there
   * is: the part-shaped `evaluate` hop does not run for one (the gateway
   * resolves the instance graph and geometry projects the solved compound), so
   * `resultByProjection` is empty and this panel used to report "0 edges" over
   * a sheet full of geometry. A readout that is confidently wrong is worse
   * than one that is absent — same count, taken from what was drawn.
   */
  composedByProjection: Map<ViewProjection, ComposedView>;
}) {
  const flatPattern = projections.includes("flat_pattern");
  const bendCount =
    resultByProjection.get("flat_pattern")?.bend_table?.length ?? 0;
  return (
    <div className="border border-hairline bg-anvil">
      <header className="flex items-baseline gap-2 border-b border-hairline px-3 py-2">
        <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          {flatPattern ? "Flat pattern" : "Standard views"}
        </h2>
        <span className="grow" />
        {projecting ? (
          <span
            data-testid="drawing-projecting"
            className="font-data text-2xs text-brass"
          >
            Projecting…
          </span>
        ) : null}
      </header>
      <ul className="divide-y divide-hairline">
        {projections.map((projection) => {
          const result = resultByProjection.get(projection);
          const placed = composedByProjection.get(projection);
          const failed = Boolean(result?.error ?? placed?.error);
          // Prefer the evaluated reading (it exists the moment the projection
          // lands, before the compose returns); fall back to what was placed.
          const count = result?.edges?.length ?? placed?.edges?.length ?? 0;
          return (
            <li
              key={projection}
              className="flex items-center justify-between px-3 py-1.5"
              data-testid="drawing-view-row"
              data-view={projection}
            >
              <span className="font-body text-xs text-mist">
                {VIEW_LABEL[projection]}
              </span>
              <span
                className={`font-data text-2xs tabular-nums ${
                  failed ? "text-flag" : "text-gauge"
                }`}
              >
                {failed ? "failed" : `${count} edges`}
              </span>
            </li>
          );
        })}
      </ul>
      {flatPattern && bendCount > 0 ? (
        <div
          className="flex items-center justify-between border-t border-hairline px-3 py-1.5"
          data-testid="drawing-bend-count"
        >
          <span className="font-body text-xs text-mist">Bends</span>
          <span className="font-data text-2xs tabular-nums text-gauge">
            {bendCount}
          </span>
        </div>
      ) : null}
      <div className="border-t border-hairline px-3 py-2">
        <div className="flex items-center gap-2 py-0.5">
          <svg width="26" height="6" aria-hidden="true">
            <line
              x1="0"
              y1="3"
              x2="26"
              y2="3"
              stroke="currentColor"
              strokeWidth="1.5"
              className="text-mist"
            />
          </svg>
          <span className="font-body text-2xs text-gauge">
            {flatPattern ? "Cut edge" : "Visible edge"}
          </span>
        </div>
        {flatPattern ? (
          // The fold-line swatch — the sheet-metal signature stroke, drawn in the
          // exact `drawing.bend` ink AND `bendDash/Gap` pattern the real fold
          // stroke uses, so the legend can never drift from the stroke.
          <div className="flex items-center gap-2 py-0.5">
            <svg width="26" height="6" aria-hidden="true">
              <line
                x1="0"
                y1="3"
                x2="26"
                y2="3"
                stroke={drawing.bend}
                strokeWidth="1.5"
                strokeDasharray={`${drawing.bendDashMm} ${drawing.bendGapMm}`}
              />
            </svg>
            <span className="font-body text-2xs text-gauge">Fold line</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 py-0.5">
            <svg width="26" height="6" aria-hidden="true">
              <line
                x1="0"
                y1="3"
                x2="26"
                y2="3"
                stroke="currentColor"
                strokeWidth="1.5"
                // Same token pattern the hidden-edge stroke draws (was "4 3").
                strokeDasharray={`${drawing.hiddenDashMm} ${drawing.hiddenGapMm}`}
                className="text-gauge"
              />
            </svg>
            <span className="font-body text-2xs text-gauge">Hidden edge</span>
          </div>
        )}
      </div>
    </div>
  );
}

/** The formatted display cells for one bend-schedule row — the same values the
 * SVG bend table stamps (angle°, R-radius, UP/DOWN, allowance), so the DOM text
 * a screen reader reads matches the printed sheet. */
function bendScheduleCells(row: BendTableRow): {
  angle: string;
  radius: string;
  dir: string;
  allow: string;
} {
  return {
    angle: `${row.angle_deg.toFixed(1)}°`,
    radius: `R${row.radius_mm.toFixed(2)}`,
    dir: row.direction === "up" ? "UP" : "DOWN",
    allow: row.bend_allowance_mm.toFixed(2),
  };
}

/**
 * The Bend schedule — a TEXT-accessible twin of the flat-pattern sheet's SVG
 * bend table (which renders inside a `role="img"` sheet, so assistive tech never
 * reads the per-bend values). A real `<table>` with column headers so AT reads
 * each cell's meaning (angle / radius / direction / allowance); each row keys
 * POSITIONALLY to the flat view's `edge_role="bend"` fold lines — the i-th row ↔
 * the i-th bend edge (`data-bend-index`), the SAME contract the visual table
 * uses, never a `bend_id` join. Rendered only for a flat pattern with bends.
 */
export function BendSchedulePanel({ rows }: { rows: readonly BendTableRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div
      className="border border-hairline bg-anvil"
      data-testid="bend-schedule-panel"
    >
      <header className="flex items-baseline gap-2 border-b border-hairline px-3 py-2">
        <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Bend schedule
        </h2>
        <span className="grow" />
        <span className="font-data text-2xs tabular-nums text-gauge">
          {rows.length}
        </span>
      </header>
      <table
        className="w-full border-collapse"
        aria-label={`Bend schedule, ${rows.length} bends`}
      >
        <caption className="sr-only">
          Fold instructions per bend, in fold-position order: fold angle, inner
          radius in millimetres, direction, and bend allowance in millimetres.
        </caption>
        <thead>
          <tr className="border-b border-hairline">
            <th
              scope="col"
              className="px-3 py-1.5 text-left font-display text-2xs uppercase tracking-[0.14em] text-gauge"
            >
              Bend
            </th>
            <th
              scope="col"
              className="px-2 py-1.5 text-right font-display text-2xs uppercase tracking-[0.14em] text-gauge"
            >
              Angle
            </th>
            <th
              scope="col"
              className="px-2 py-1.5 text-right font-display text-2xs uppercase tracking-[0.14em] text-gauge"
            >
              Radius
            </th>
            <th
              scope="col"
              className="px-2 py-1.5 text-right font-display text-2xs uppercase tracking-[0.14em] text-gauge"
            >
              Dir
            </th>
            <th
              scope="col"
              className="px-3 py-1.5 text-right font-display text-2xs uppercase tracking-[0.14em] text-gauge"
            >
              Allow mm
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {rows.map((row, i) => {
            const cells = bendScheduleCells(row);
            return (
              <tr
                key={i}
                data-testid="bend-schedule-row"
                data-bend-index={String(i)}
              >
                <td className="px-3 py-1.5 text-left font-data text-2xs text-mist">
                  {row.bend_id}
                </td>
                <td className="px-2 py-1.5 text-right font-data text-2xs tabular-nums text-mist">
                  {cells.angle}
                </td>
                <td className="px-2 py-1.5 text-right font-data text-2xs tabular-nums text-mist">
                  {cells.radius}
                </td>
                <td className="px-2 py-1.5 text-right font-data text-2xs text-gauge">
                  {cells.dir}
                </td>
                <td className="px-3 py-1.5 text-right font-data text-2xs tabular-nums text-mist">
                  {cells.allow}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The Parts list — the sheet's numbered item table (design §7 BOM), the block a
 * shop reads to know WHAT to make and HOW MANY. Sibling of the Notes panel, and
 * the only surface in the workspace that names other documents, so each row is
 * the way to open the one it names.
 *
 * The item NUMBER is the signature: a drafting balloon, the circled numeral
 * that ties a row to the geometry on the paper. It is not decoration — the
 * number is content here, DERIVED server-side from the assembly's stable
 * instance order, which is why two reads of an unchanged assembly number
 * identically and a rename never renumbers anything.
 *
 * A PART-sourced sheet has no bill of materials, and that is a fact worth
 * stating rather than hiding: the block still renders, disabled, carrying the
 * reason. The reason is focusable (`tabIndex={0}`) because a caption a mouse
 * can read and a keyboard cannot is only half-shipped — this is the on-screen
 * form of the server's own `drawing_bom_source_not_assembly`, made legible
 * before anyone can hit it.
 */
export function PartsListPanel({
  sourceKind,
  lines,
  totalInstances,
  loading,
  error,
  onOpen,
}: {
  sourceKind: RefDocumentKind;
  lines: readonly DrawingBomLine[];
  totalInstances: number;
  loading: boolean;
  error: unknown;
  onOpen: (line: DrawingBomLine) => void;
}) {
  const unavailable = sourceKind !== "assembly";
  return (
    <div
      className="border border-hairline bg-anvil"
      data-testid="parts-list-panel"
      data-source-kind={sourceKind}
      data-disabled={unavailable ? "true" : "false"}
    >
      <header className="flex items-baseline gap-2 border-b border-hairline px-3 py-2">
        <h2
          className={`font-display text-2xs uppercase tracking-[0.18em] ${
            unavailable ? "text-gauge/60" : "text-gauge"
          }`}
        >
          Parts list
        </h2>
        <span className="grow" />
        {unavailable ? null : (
          <span
            data-testid="parts-list-total"
            className="font-data text-2xs tabular-nums text-gauge"
          >
            {totalInstances}
          </span>
        )}
      </header>
      {unavailable ? (
        <p
          tabIndex={0}
          role="note"
          data-testid="parts-list-unavailable"
          className="px-3 py-2.5 font-body text-2xs text-gauge focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass"
        >
          A parts list needs an assembly source. This sheet drafts a part —
          draft an assembly to number its items.
        </p>
      ) : error ? (
        <p
          role="alert"
          data-testid="parts-list-error"
          className="px-3 py-2.5 font-body text-2xs text-flag"
        >
          {error instanceof Error
            ? error.message
            : "The parts list could not be loaded."}
        </p>
      ) : loading ? (
        <p
          data-testid="parts-list-loading"
          className="px-3 py-2.5 font-body text-2xs text-gauge"
        >
          Numbering the items…
        </p>
      ) : lines.length === 0 ? (
        <p
          data-testid="parts-list-empty"
          className="px-3 py-2.5 font-body text-2xs text-gauge"
        >
          This assembly has no instances yet. Add parts to it and the items
          number themselves.
        </p>
      ) : (
        <table
          className="w-full border-collapse"
          aria-label={`Parts list, ${lines.length} items, ${totalInstances} instances`}
        >
          <caption className="sr-only">
            One row per referenced document in item-number order: item number,
            name, and the quantity of instances.
          </caption>
          <thead>
            <tr className="border-b border-hairline">
              <th
                scope="col"
                className="px-3 py-1.5 text-left font-display text-2xs uppercase tracking-[0.14em] text-gauge"
              >
                No.
              </th>
              <th
                scope="col"
                className="px-2 py-1.5 text-left font-display text-2xs uppercase tracking-[0.14em] text-gauge"
              >
                Item
              </th>
              <th
                scope="col"
                className="px-3 py-1.5 text-right font-display text-2xs uppercase tracking-[0.14em] text-gauge"
              >
                Qty
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {lines.map((line) => (
              <tr
                key={`${line.item_number}:${line.ref_document_id}`}
                data-testid="parts-list-row"
                data-item-number={String(line.item_number)}
                data-ref-document-id={line.ref_document_id}
                data-ref-kind={line.ref_document_kind}
              >
                <td className="px-3 py-1.5">
                  {/* The balloon — the drafting artifact, not an ornament: a
                      circled numeral is how an item list points at the paper. */}
                  <span
                    data-testid="parts-list-item-number"
                    className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-etch font-data text-2xs tabular-nums text-mist"
                  >
                    {line.item_number}
                  </span>
                </td>
                <td className="px-2 py-1.5">
                  {line.missing ? (
                    <span
                      data-testid="parts-list-name"
                      className="font-body text-2xs text-flag"
                    >
                      Deleted document
                    </span>
                  ) : (
                    <button
                      type="button"
                      data-testid="parts-list-name"
                      title={line.name ?? undefined}
                      aria-label={`Open ${line.name ?? "item"}`}
                      onClick={() => onOpen(line)}
                      className="block w-full truncate text-left font-body text-2xs text-mist transition-colors duration-fast hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass"
                    >
                      {line.name}
                    </button>
                  )}
                </td>
                <td
                  data-testid="parts-list-qty"
                  className="px-3 py-1.5 text-right font-data text-2xs tabular-nums text-mist"
                >
                  {line.quantity}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/**
 * The Notes panel — author a free-text note and manage the sheet's notes (design
 * §2.2). Adding a note persists it (CRUD) and re-composes the sheet, which draws
 * it at its authored point from `ComposedSheet.notes`; the list is the keyboard/
 * touch path to removing one. A quiet precision instrument, sibling of the
 * Dimensions panel — the sheet stays the hero.
 */
export function NotesPanel({
  annotations,
  busy,
  onAdd,
  onDelete,
}: {
  annotations: readonly AnnotationResponse[];
  busy: boolean;
  onAdd: (text: string) => void;
  onDelete: (annotationId: string) => void;
}) {
  const [text, setText] = useState("");
  const canAdd = text.trim().length > 0 && !busy;
  const submit = () => {
    if (!canAdd) return;
    onAdd(text);
    setText("");
  };
  return (
    <div className="border border-hairline bg-anvil" data-testid="notes-panel">
      <header className="flex items-baseline gap-2 border-b border-hairline px-3 py-2">
        <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Notes
        </h2>
        <span className="grow" />
        <span className="font-data text-2xs tabular-nums text-gauge">
          {annotations.length}
        </span>
      </header>
      <form
        className="flex items-end gap-2 border-b border-hairline px-3 py-2.5"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <TextField
          label="Add a note"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="e.g. Break all sharp edges"
          className="grow"
          data-testid="note-input"
        />
        <Button
          type="submit"
          variant="ghost"
          disabled={!canAdd}
          data-testid="note-add"
          aria-label="Add note"
        >
          Add
        </Button>
      </form>
      {annotations.length === 0 ? (
        <p className="px-3 py-2.5 font-body text-2xs text-gauge">
          Notes print on the sheet at the top-left — material callouts, finish,
          or shop instructions.
        </p>
      ) : (
        <ul className="divide-y divide-hairline">
          {annotations.map((entry) => (
            <li
              key={entry.id}
              className="flex items-center gap-2 px-3 py-1.5"
              data-testid="note-row"
            >
              <span
                data-testid="note-row-text"
                className="grow truncate font-body text-2xs text-mist"
                title={entry.annotation.text}
              >
                {entry.annotation.text}
              </span>
              <button
                type="button"
                disabled={busy}
                data-testid="note-delete"
                aria-label={`Delete note "${entry.annotation.text}"`}
                onClick={() => onDelete(entry.id)}
                className="shrink-0 rounded-sm px-1.5 py-0.5 font-display text-2xs uppercase tracking-[0.14em] text-gauge transition-colors duration-fast hover:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * The Dimensions panel — the authored dimensions with their model-true value and
 * a delete affordance (design §3 "Manage"). It is the keyboard/touch path to
 * removing a dimension and the honest place a measurement error surfaces.
 *
 * Two things the server has always shipped and this panel used to drop (audit
 * N1 frontend half):
 *
 *  - a dimension that could not be measured said only "unresolved", while
 *    `measured.error.message` carried the typed sentence the SHEET already
 *    stamps beside the marker. The words belong on both.
 *  - `measured.anchor.tier === "durable"` means the stored reference did not
 *    match after an edit and geometry re-anchored it on the rebuild invariant.
 *    The value is model-true either way, so this is not an alarm — it is the
 *    dashed "not established" {@link Stamp}, plus the one click that stores the
 *    signature geometry landed on and makes the reference exact again.
 */
export function DimensionsPanel({
  dimensions,
  measuredById,
  busy,
  movingId,
  onMove,
  onDelete,
  onHeal,
}: {
  dimensions: readonly DimensionResponse[];
  measuredById: Map<string, MeasuredDimension>;
  busy: boolean;
  /** The dimension currently being re-placed, if any — its row says so. */
  movingId: string | null;
  /** Pick this dimension up and re-enter the PLACE stage (P1-E). */
  onMove: (dimensionId: string) => void;
  onDelete: (dimensionId: string) => void;
  /** Store the re-anchored signature for this dimension (the "confirm" write). */
  onHeal: (dimensionId: string) => void;
}) {
  return (
    <div
      className="border border-hairline bg-anvil"
      data-testid="dimensions-panel"
    >
      <header className="flex items-baseline gap-2 border-b border-hairline px-3 py-2">
        <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Dimensions
        </h2>
        <span className="grow" />
        <span className="font-data text-2xs tabular-nums text-gauge">
          {dimensions.length}
        </span>
      </header>
      {dimensions.length === 0 ? (
        <p className="px-3 py-2.5 font-body text-2xs text-gauge">
          Click a highlighted edge on a view to add a dimension — a circle takes
          a diameter or radius, a straight edge a linear; pick a second edge for
          an angle or the distance across (a wall thickness).
        </p>
      ) : (
        <>
          <ul className="divide-y divide-hairline">
            {dimensions.map((dim) => {
              const measured = measuredById.get(dim.id);
              const errored = Boolean(measured?.error);
              const foreshortened = Boolean(measured?.foreshortened);
              const value =
                measured && typeof measured.value === "number"
                  ? (foreshortened ? "~" : "") +
                    formatDimensionLabel(
                      dim.dimension.type,
                      measured.value,
                      measured.unit,
                    )
                  : errored
                    ? "unresolved"
                    : "…";
              // The typed sentence the server already stamps on the sheet
              // ("REFERENCE LOST - RE-PICK THE EDGE"); the panel said only
              // "unresolved" beside it. The phrase is the SERVER's.
              const reason = measured?.error?.message ?? null;
              const anchor = reanchoredAnchor(measured);
              const healable =
                anchor !== null &&
                healDimensionParams(dim.dimension, anchor) !== null;
              return (
                <li
                  key={dim.id}
                  className="px-3 py-1.5"
                  data-testid="dimension-row"
                  data-dimension-type={dim.dimension.type}
                  // A linear dimension has three quite different meanings; the
                  // row (and any test) can tell them apart without re-parsing.
                  data-dimension-mode={
                    dim.dimension.type === "linear"
                      ? dim.dimension.measurement.mode
                      : undefined
                  }
                  data-foreshortened={foreshortened ? "true" : "false"}
                  data-anchor-tier={measured?.anchor?.tier ?? "none"}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-display text-2xs uppercase tracking-[0.14em] text-gauge">
                      {dim.dimension.type}
                    </span>
                    <span
                      data-testid="dimension-row-value"
                      // Foreshortened matches the sheet: the ~value reads in the
                      // same flag ink on BOTH renderers (was un-flagged here).
                      className={`grow text-right font-data text-2xs tabular-nums ${
                        errored || foreshortened ? "text-flag" : "text-mist"
                      }`}
                    >
                      {value}
                    </span>
                    {/* MOVE, beside Delete. The sheet's own value stamp is the
                        primary route (press it and drag), but the panel is
                        where a user looks for "what can I do to this one", and
                        before this the honest answer was "delete it and author
                        it again" (frontend-QA 2026-08-27, P1-E). */}
                    {!errored ? (
                      <button
                        type="button"
                        disabled={busy}
                        data-testid="dimension-move"
                        aria-label={`Move the ${dim.dimension.type} dimension`}
                        onClick={() => onMove(dim.id)}
                        className="shrink-0 rounded-sm px-1.5 py-0.5 font-display text-2xs uppercase tracking-[0.14em] text-gauge transition-colors duration-fast hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40"
                      >
                        {dim.id === movingId ? "Placing…" : "Move"}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      disabled={busy}
                      data-testid="dimension-delete"
                      aria-label={`Delete ${dim.dimension.type} dimension`}
                      onClick={() => onDelete(dim.id)}
                      className="shrink-0 rounded-sm px-1.5 py-0.5 font-display text-2xs uppercase tracking-[0.14em] text-gauge transition-colors duration-fast hover:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40"
                    >
                      Delete
                    </button>
                  </div>
                  {/* WHY it is unresolved, in the server's words — the print has
                      said this beside the marker since audit N1; the screen
                      said "unresolved" and stopped. */}
                  {errored && reason ? (
                    <p
                      data-testid="dimension-row-reason"
                      className="mt-1 font-body text-2xs text-flag"
                    >
                      {reason}
                    </p>
                  ) : null}
                  {anchor !== null ? (
                    <div className="mt-1 flex items-center gap-2">
                      <Stamp indeterminate data-testid="dimension-reanchored">
                        Re-anchored
                      </Stamp>
                      <span className="grow" />
                      {healable ? (
                        <button
                          type="button"
                          disabled={busy}
                          data-testid="dimension-heal"
                          aria-label={`Confirm the re-anchored reference for the ${dim.dimension.type} dimension`}
                          onClick={() => onHeal(dim.id)}
                          className="shrink-0 rounded-sm px-1.5 py-0.5 font-display text-2xs uppercase tracking-[0.14em] text-brass transition-colors duration-fast hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40"
                        >
                          Confirm
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
          {/* An ALWAYS-VISIBLE legend for the `~` flag — the sheet only explains
              it via a mouse-hover SVG <title>; this reaches keyboard + touch. */}
          {dimensions.some((dim) => measuredById.get(dim.id)?.foreshortened) ? (
            <p
              data-testid="dimension-foreshortened-note"
              className="border-t border-hairline px-3 py-2 font-body text-2xs text-flag"
            >
              <span className="font-data">~</span> shown from a true-size view
              for the drawn length (foreshortened).
            </p>
          ) : null}
          {/* The dashed stamp on its own is jargon; this is the sentence that
              makes it actionable, always visible (the `~` legend's twin). */}
          {dimensions.some(
            (dim) => reanchoredAnchor(measuredById.get(dim.id)) !== null,
          ) ? (
            <p
              data-testid="dimension-reanchored-note"
              className="border-t border-hairline px-3 py-2 font-body text-2xs text-gauge"
            >
              Re-anchored: the part changed, so this was re-measured from the
              edge that is there now. Confirm to store the new reference.
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
