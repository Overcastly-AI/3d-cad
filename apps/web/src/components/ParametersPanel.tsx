/**
 * PARAMETERS (PART-PARAMETERS, docs/RESEARCH.md §20): the part's table of
 * named values, Fusion 360's Change Parameters as a modeless side panel.
 *
 * The columns are Fusion's: Name, Unit, Expression, Value, Comment. Every cell
 * edits in place; Enter or leaving the cell commits, and the whole table goes
 * to the server as ONE write, which is one undo step. Escape puts the cell
 * back. The Value column is the server's evaluation, never the client's, in
 * the document's unit (angles in degrees).
 *
 * A refusal is printed under the row it is about — the loop as `a → b → a`, the
 * unknown name by name — and the text that caused it stays in the cell, so the
 * user corrects it instead of re-typing it.
 *
 * Presentational: the table state and the writes live in
 * `routes/part/usePartParameters.ts`, the rules in `features/parameters.ts`.
 */
import {
  Button,
  GridCellInput,
  GridCellSelect,
  Notice,
  Panel,
  type LengthUnit,
} from "@loft/design";
import { Fragment, useEffect, useId, useRef, useState } from "react";

import type { ParameterUnit } from "../api/parameters";
import {
  type DraftRow,
  formatParameterValue,
  type ParameterField,
  type RowError,
  unitOptions,
  valuePending,
} from "../features/parameters";

export interface ParametersPanelProps {
  /** The working table; undefined while the first read is in flight. */
  rows: readonly DraftRow[] | undefined;
  /** The stored rows by id: which values are the server's word for the text. */
  stored: ReadonlyMap<string, DraftRow>;
  documentUnit: LengthUnit;
  /** The table could not be read, in a sentence. */
  loadError: string | null;
  /** The last refusal, on its row (or on the table when `rowId` is null). */
  error: RowError | null;
  /** A write lost a race; the table now shows the latest with the edits on top. */
  stale: boolean;
  saving: boolean;
  /** When set, the table is read-only and says why. */
  blockedReason?: string;
  /** The row Add just created; its Name cell takes focus. */
  focusRowId: string | null;
  onCommitCell: (id: string, field: ParameterField, text: string) => void;
  onUnitChange: (id: string, unit: ParameterUnit) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
  onRetry: () => void;
  onClose: () => void;
}

const HEAD =
  "px-1.5 py-1 text-left font-display text-2xs font-normal uppercase tracking-[0.14em] text-gauge";

export function ParametersPanel({
  rows,
  stored,
  documentUnit,
  loadError,
  error,
  stale,
  saving,
  blockedReason,
  focusRowId,
  onCommitCell,
  onUnitChange,
  onAdd,
  onDelete,
  onRetry,
  onClose,
}: ParametersPanelProps) {
  const errorId = useId();
  const locked = blockedReason !== undefined;
  const empty = rows !== undefined && rows.length === 0;
  const options = unitOptions(documentUnit);

  return (
    <Panel
      aria-label="Parameters"
      data-testid="parameters-panel"
      aria-busy={saving || undefined}
      className="border-0"
    >
      {/* `pr-8` clears the rail panel's collapse tab in the top-right corner. */}
      <header className="flex min-h-target-dense items-center gap-2 border-b border-hairline py-1 pl-3 pr-8">
        <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Parameters
        </h2>
        <span className="grow" />
        {saving ? (
          <span
            role="status"
            data-testid="parameters-saving"
            className="font-body text-2xs text-gauge"
          >
            Saving…
          </span>
        ) : null}
        {rows !== undefined && !empty ? (
          <Button
            onClick={onAdd}
            disabled={locked}
            data-testid="parameters-add"
            className="px-2 py-0.5 text-xs"
          >
            Add
          </Button>
        ) : null}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close parameters"
          data-testid="parameters-close"
          className="inline-flex min-h-target-dense items-center rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none transition-colors duration-fast hover:text-brass focus-visible:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
        >
          Close
        </button>
      </header>

      {locked ? (
        <p
          data-testid="parameters-blocked"
          className="border-b border-hairline px-3 py-1.5 font-body text-xs text-gauge"
        >
          {blockedReason}
        </p>
      ) : null}

      {stale ? (
        <Notice
          role="status"
          tone="gauge"
          label="Changed"
          layout="stacked"
          data-testid="parameters-stale"
          action={{
            label: "Retry",
            onClick: onRetry,
            testId: "parameters-retry",
          }}
        >
          The part changed while you were editing. The table shows its latest
          values with your edit on top; review it, then retry.
        </Notice>
      ) : null}

      {error !== null && error.rowId === null ? (
        <p
          role="alert"
          data-testid="parameters-error"
          className="border-b border-hairline px-3 py-1.5 font-body text-xs text-flag"
        >
          {error.message}
        </p>
      ) : null}

      {loadError !== null ? (
        <p
          role="alert"
          data-testid="parameters-load-error"
          className="px-3 py-3 font-body text-xs text-flag"
        >
          {loadError}
        </p>
      ) : rows === undefined ? (
        <p
          data-testid="parameters-loading"
          aria-live="polite"
          className="px-3 py-3 font-body text-xs text-gauge"
        >
          Reading the parameters…
        </p>
      ) : empty ? (
        <div
          data-testid="parameters-empty"
          className="flex items-center gap-3 px-3 py-3"
        >
          <p className="min-w-0 grow font-body text-xs text-gauge">
            Name a value once and use it in any dimension; change it here and
            every feature that uses it follows.
          </p>
          <Button
            variant="solid"
            onClick={onAdd}
            disabled={locked}
            data-testid="parameters-add"
            className="shrink-0"
          >
            Add
          </Button>
        </div>
      ) : (
        <table
          data-testid="parameters-table"
          className="w-full table-fixed border-collapse"
        >
          <colgroup>
            <col className="w-[18%]" />
            <col className="w-[13%]" />
            <col className="w-[26%]" />
            <col className="w-[16%]" />
            <col />
            <col className="w-6" />
          </colgroup>
          <thead>
            <tr className="border-b border-hairline">
              <th scope="col" className={HEAD}>
                Name
              </th>
              <th scope="col" className={HEAD}>
                Unit
              </th>
              <th scope="col" className={HEAD}>
                Expression
              </th>
              <th scope="col" className={`${HEAD} text-right`}>
                Value
              </th>
              <th scope="col" className={HEAD}>
                Comment
              </th>
              <th scope="col">
                <span className="sr-only">Delete</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const rowError = error?.rowId === row.id ? error : null;
              const who = row.name === "" ? `Row ${index + 1}` : row.name;
              const pending = valuePending(row, stored);
              const describedBy =
                rowError === null ? undefined : `${errorId}-${row.id}`;
              return (
                <Fragment key={row.id}>
                  <tr
                    data-testid="parameter-row"
                    data-row-id={row.id}
                    data-name={row.name}
                    data-invalid={rowError === null ? undefined : "true"}
                    className={
                      rowError === null
                        ? "border-b border-hairline/60"
                        : "border-l-2 border-l-flag"
                    }
                  >
                    <td>
                      <CommitCell
                        aria-label={`${who} name`}
                        data-testid="parameter-name"
                        value={row.name}
                        placeholder="Name"
                        invalid={rowError?.field === "name"}
                        aria-describedby={
                          rowError?.field === "name" ? describedBy : undefined
                        }
                        disabled={locked}
                        autoFocus={row.id === focusRowId}
                        onCommit={(text) => onCommitCell(row.id, "name", text)}
                      />
                    </td>
                    <td>
                      <GridCellSelect
                        aria-label={`${who} unit`}
                        data-testid="parameter-unit"
                        value={row.unit}
                        options={options}
                        disabled={locked}
                        onChange={(event) =>
                          onUnitChange(
                            row.id,
                            event.target.value as ParameterUnit,
                          )
                        }
                      />
                    </td>
                    <td>
                      <CommitCell
                        aria-label={`${who} expression`}
                        data-testid="parameter-expression"
                        value={row.expression}
                        placeholder="e.g. 40"
                        invalid={rowError?.field === "expression"}
                        aria-describedby={
                          rowError?.field === "expression"
                            ? describedBy
                            : undefined
                        }
                        disabled={locked}
                        onCommit={(text) =>
                          onCommitCell(row.id, "expression", text)
                        }
                      />
                    </td>
                    <td
                      data-testid="parameter-value"
                      title={
                        pending
                          ? "Evaluated when the table is saved"
                          : undefined
                      }
                      className={
                        "truncate px-1.5 py-1 text-right font-data text-xs tabular-nums " +
                        (pending ? "text-gauge" : "text-brass")
                      }
                    >
                      {pending
                        ? "—"
                        : formatParameterValue(
                            row.value,
                            row.unit,
                            documentUnit,
                          )}
                    </td>
                    <td>
                      <CommitCell
                        aria-label={`${who} comment`}
                        data-testid="parameter-comment"
                        value={row.comment}
                        disabled={locked}
                        onCommit={(text) =>
                          onCommitCell(row.id, "comment", text)
                        }
                      />
                    </td>
                    <td className="text-center">
                      <button
                        type="button"
                        onClick={() => onDelete(row.id)}
                        disabled={locked}
                        aria-label={`Delete ${who}`}
                        data-testid="parameter-delete"
                        className="inline-flex h-6 w-6 items-center justify-center font-data text-xs text-gauge outline-none transition-colors duration-fast hover:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:opacity-50"
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                  {rowError !== null ? (
                    <tr
                      data-testid="parameter-row-error"
                      className="border-b border-l-2 border-hairline/60 border-l-flag"
                    >
                      <td
                        colSpan={6}
                        id={describedBy}
                        role="alert"
                        className="px-1.5 pb-1.5 font-body text-xs text-flag"
                      >
                        {rowError.message}
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

/**
 * One editable cell: holds the text while it is being typed, commits it on
 * Enter or when focus leaves (only if it changed), and puts it back on Escape.
 * Enter always commits, so pressing it on an unchanged cell retries a table
 * the server refused or a write that lost a race.
 */
function CommitCell({
  value,
  onCommit,
  autoFocus,
  ...rest
}: {
  value: string;
  onCommit: (text: string) => void;
  "aria-label": string;
  "data-testid": string;
  "aria-describedby"?: string | undefined;
  placeholder?: string;
  invalid?: boolean;
  disabled?: boolean;
  autoFocus?: boolean;
}) {
  const [text, setText] = useState(value);
  const editing = useRef(false);
  /** The blur that follows Enter or Escape has already been handled. */
  const handled = useRef(false);
  const input = useRef<HTMLInputElement>(null);

  // Follow the table while the cell is not being typed in: a commit, an undo
  // or a refetch changes `value` under it.
  useEffect(() => {
    if (!editing.current) setText(value);
  }, [value]);

  useEffect(() => {
    if (autoFocus) input.current?.focus();
  }, [autoFocus]);

  return (
    <GridCellInput
      ref={input}
      value={text}
      onFocus={() => {
        editing.current = true;
        handled.current = false;
      }}
      onChange={(event) => setText(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          editing.current = false;
          handled.current = true;
          onCommit(text);
          event.currentTarget.blur();
        } else if (event.key === "Escape") {
          // The cell's own step back: nothing behind it (an open command, the
          // measure tool) may take this Escape too.
          event.preventDefault();
          event.stopPropagation();
          editing.current = false;
          handled.current = true;
          setText(value);
          event.currentTarget.blur();
        }
      }}
      onBlur={() => {
        editing.current = false;
        if (handled.current) {
          handled.current = false;
          return;
        }
        if (text !== value) onCommit(text);
      }}
      {...rest}
    />
  );
}
