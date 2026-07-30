import { Button, Kbd, type LengthUnit, Stamp, TextField } from "@loft/design";
import {
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import type { PartEvalState, PartLastEvalStatus } from "../api/parts";
import { documentActivity, relativeAge } from "../lib/activity";
import { formatDate } from "../lib/format";
import { validatePartName } from "../lib/partName";

/**
 * THE REGISTER — the index surface behind /, /assemblies and /drawings
 * (frontend-design pass, 2026-07-25; UI-REVIEW 2026-07-24 P2 "the registers
 * read as templated web tables").
 *
 * The brief the audit set was not "make the table prettier": it was that the
 * first screen after sign-in must belong to the same instrument as the
 * workspaces. Two things were wrong, and only one of them was visual.
 *
 * INFORMATION. The old register spent its two widest columns on CREATED and
 * UPDATED rendered as identical ISO dates — for a drawer of same-day work that
 * is two columns of the same string, so the surface answered nothing a modeler
 * asks. What a modeler asks of a parts drawer, in order, is: *where was I*,
 * *which of these did I name and never start*, and *what units is it in*. All
 * three are answerable from the list payload and are now the columns:
 *
 *   - LAST WORKED — the relative age of the last edit ("20 min ago"), because
 *     `updated_at` is bumped by every tree write. Recency is the one thing a
 *     returning engineer scans for, and a relative age is scannable where a
 *     date is not. The exact stamp stays in the cell's `title`.
 *   - …and, in that same column, NOT STARTED for a document never edited since
 *     it was created (see `lib/activity.ts`): the empty stub, flagged as an
 *     exception instead of badging every row. One column, one job.
 *   - UNITS — real per-document metadata (`length_unit`), the thing a title
 *     block carries and a generic list does not. Drawings have none, so they
 *     do not render the column rather than render a blank one.
 *   - REBUILD — the drawer's health, once the record existed to report it (see
 *     `HealthCell` for the four states and why it is its own column).
 *
 * Still not shown, deliberately: "has a body", "has drawings". Neither is on
 * the wire for a LIST, and a modeler does not scan a register for them. A
 * register that guesses is worse than one that reports — which is exactly why
 * REBUILD reports the SERVER'S verdict (`eval_state`) rather than deriving one
 * from the two timestamps it happens to have.
 *
 * FORM. The identity comes from the language the rest of the product already
 * speaks — no new look was invented. The row ordinal sits in a scribed left
 * GUTTER on the carbide ground, the way a drawing's zone indices are printed in
 * its margin (and it is an ordinal, presented as one — see `Gutter`); the
 * addressed row takes a brass scribe on that gutter's edge (the only accent, and
 * it marks position across a wide row rather than decorating); the name is the
 * one thing set in body type at reading size while every other cell is quiet
 * tracked data. The create control is no longer a form bolted above a table — it
 * is the NEXT LINE of the register, carrying the next ordinal, because that is
 * what filing a new part is, and its `N` accelerator is shown rather than
 * hidden. Below it the drawer's remaining ruled lines run to the bottom of the
 * frame, which is what kills the old "small card adrift in a void" read.
 *
 * DRY: one component, three thin configs. The three pages were ~410 lines of
 * near-identical code (UI-REVIEW 2026-07-16 flagged the near-dup); a divergence
 * between the parts and drawings registers is now impossible by construction.
 */

/** The shape every register row needs; `length_unit` only where it exists. */
export interface RegisterDocument {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  length_unit?: LengthUnit;
  /**
   * Rebuild health — the SERVER'S verdict, already folded against the part's
   * current tree version. Absent on document kinds that have no feature tree
   * (assemblies, drawings), which drop the column rather than render a blank
   * one. Read this; never re-derive it (see `PartEvalState`).
   */
  eval_state?: PartEvalState;
  /**
   * The raw recorded outcome, which the STALE state spends to say "was broken"
   * instead of a bare "unknown". Never read without `eval_state`.
   */
  last_eval_status?: PartLastEvalStatus;
  /** When that record was written — the relative age in the cell's title. */
  last_eval_at?: string | null;
  /**
   * `last_eval_tree_version` is deliberately NOT taken: a version number is
   * only meaningful next to the part's CURRENT version, which a register row
   * does not carry, and printing one alone would be chrome that measures
   * nothing. The staleness it encodes already reached us as `eval_state`.
   */
}

/** Every word this register says. Copy is per-document-kind, structure is not. */
export interface RegisterCopy {
  /** Header eyebrow, e.g. "Parts register". */
  title: string;
  /** Screen-reader table caption. */
  caption: string;
  /** Count readout singular/plural nouns, e.g. "part" / "parts". */
  noun: string;
  nounPlural: string;
  /** Loading line, e.g. "Loading parts…". */
  loading: string;
  /** Fallback when the list request fails. */
  loadError: string;
  /** Fallback when a delete fails. */
  deleteError: string;
  /** Fallback when a create fails. */
  createError: string;
  /** Empty-state headline + invitation. */
  emptyHeadline: string;
  emptyBody: string;
  /** Create field label + placeholder + the two submit labels. */
  fieldLabel: string;
  placeholder: string;
  createLabel: string;
  createFirstLabel: string;
}

export interface DocumentRegisterProps<T extends RegisterDocument> {
  /** Test-id stem for list-level hooks: "parts" | "assemblies" | "drawings". */
  idPlural: string;
  /** Test-id stem for row-level hooks: "part" | "assembly" | "drawing". */
  idSingular: string;
  copy: RegisterCopy;
  documents: T[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  /** The row's link into its workspace — routes are typed per document kind. */
  openLink: (
    document: T,
    props: { className: string; "data-testid": string },
  ) => ReactNode;
  /** Create + invalidate (+ navigate, for parts). Rejects with a field error. */
  onCreate: (name: string) => Promise<void>;
  /** Delete + invalidate. Rejects to pin the message beside the confirm. */
  onDelete: (document: T) => Promise<void>;
}

export function DocumentRegister<T extends RegisterDocument>({
  idPlural,
  idSingular,
  copy,
  documents,
  isLoading,
  isError,
  error,
  openLink,
  onCreate,
  onDelete,
}: DocumentRegisterProps<T>) {
  const empty = !isLoading && !isError && documents.length === 0;
  const showUnits = documents.some((d) => d.length_unit !== undefined);
  const showHealth = documents.some((d) => d.eval_state !== undefined);

  return (
    <section
      className="mt-4 flex min-h-0 grow flex-col border border-hairline bg-anvil text-mist"
      data-testid={`${idPlural}-register`}
    >
      <header className="flex shrink-0 items-baseline gap-3 border-b border-hairline px-3 py-3">
        <h2 className="font-display text-2xs uppercase tracking-[0.2em] text-gauge">
          {copy.title}
        </h2>
        <span className="grow" />
        {isError ? null : (
          <span
            className="font-data text-xs tabular-nums text-gauge"
            data-testid={`${idPlural}-count`}
          >
            {isLoading
              ? "—"
              : `${documents.length} ${
                  documents.length === 1 ? copy.noun : copy.nounPlural
                }`}
          </span>
        )}
      </header>

      {isError ? (
        <p
          role="alert"
          data-testid={`${idPlural}-error`}
          className="px-3 py-6 font-body text-sm text-flag"
        >
          {error instanceof Error ? error.message : copy.loadError}
        </p>
      ) : isLoading ? (
        <p
          role="status"
          data-testid={`${idPlural}-loading`}
          className="px-3 py-6 font-data text-xs text-gauge"
        >
          {copy.loading}
        </p>
      ) : empty ? (
        <EmptyRegister
          idPlural={idPlural}
          copy={copy}
          onCreate={onCreate}
          idSingular={idSingular}
        />
      ) : (
        <div className="flex min-h-0 grow flex-col">
          <RegisterTable
            idPlural={idPlural}
            idSingular={idSingular}
            copy={copy}
            documents={documents}
            showUnits={showUnits}
            showHealth={showHealth}
            openLink={openLink}
            onDelete={onDelete}
          />
          <ScribeLine
            idSingular={idSingular}
            copy={copy}
            nextOrdinal={documents.length + 1}
            onCreate={onCreate}
          />
          <RuledRemainder />
        </div>
      )}
    </section>
  );
}

/** Shared gutter width — the table's first column and the scribe line agree. */
const COLUMN = {
  /** Scribed margin carrying the row ordinal — the table and the scribe line
   *  below it share this width so the log's left edge is one straight rule. */
  gutter: "w-[3.5rem]",
  units: "w-[4.5rem]",
  activity: "w-[9rem]",
  health: "w-[7.5rem]",
  filed: "w-[7rem]",
  action: "w-[5.5rem]",
} as const;

function RegisterTable<T extends RegisterDocument>({
  idPlural,
  idSingular,
  copy,
  documents,
  showUnits,
  showHealth,
  openLink,
  onDelete,
}: {
  idPlural: string;
  idSingular: string;
  copy: RegisterCopy;
  documents: T[];
  showUnits: boolean;
  showHealth: boolean;
  openLink: DocumentRegisterProps<T>["openLink"];
  onDelete: (document: T) => Promise<void>;
}) {
  return (
    <table
      className="w-full table-fixed border-collapse"
      data-testid={`${idPlural}-table`}
    >
      <caption className="sr-only">{copy.caption}</caption>
      <thead>
        <tr className="border-b border-hairline">
          {/* A POSITION, not a name for the part in it — see `Gutter`. The
              glyph alone announced as "numero sign"; the word is what a screen
              reader gets. */}
          <Th
            className={`${COLUMN.gutter} bg-carbide text-right`}
            data-testid={`${idPlural}-ordinal-header`}
          >
            <span aria-hidden>#</span>
            <span className="sr-only">Row</span>
          </Th>
          <Th>Name</Th>
          {showUnits ? <Th className={COLUMN.units}>Units</Th> : null}
          <Th className={COLUMN.activity}>Last worked</Th>
          {showHealth ? <Th className={COLUMN.health}>Rebuild</Th> : null}
          <Th className={`hidden md:table-cell ${COLUMN.filed}`}>Filed</Th>
          <th className={COLUMN.action}>
            <span className="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {documents.map((entry, index) => (
          <RegisterRow
            key={entry.id}
            idSingular={idSingular}
            copy={copy}
            entry={entry}
            ordinal={index + 1}
            showUnits={showUnits}
            showHealth={showHealth}
            openLink={openLink}
            onDelete={onDelete}
          />
        ))}
      </tbody>
    </table>
  );
}

function Th({
  children,
  className,
  ...rest
}: {
  children: ReactNode;
  className?: string;
  "data-testid"?: string;
}) {
  return (
    <th
      className={`px-3 py-2 text-left font-display text-2xs uppercase tracking-[0.16em] text-gauge ${
        className ?? ""
      }`}
      {...rest}
    >
      {children}
    </th>
  );
}

/** One filed row: ordinal, name, units, activity, health, filed, delete. */
function RegisterRow<T extends RegisterDocument>({
  idSingular,
  copy,
  entry,
  ordinal,
  showUnits,
  showHealth,
  openLink,
  onDelete,
}: {
  idSingular: string;
  copy: RegisterCopy;
  entry: T;
  ordinal: number;
  showUnits: boolean;
  showHealth: boolean;
  openLink: DocumentRegisterProps<T>["openLink"];
  onDelete: (document: T) => Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const remove = async () => {
    setPending(true);
    setDeleteError(null);
    try {
      await onDelete(entry);
    } catch (caught) {
      setPending(false);
      setDeleteError(
        caught instanceof Error ? caught.message : copy.deleteError,
      );
    }
  };

  const filed = formatDate(entry.created_at);
  const activity = documentActivity(
    entry.created_at,
    entry.updated_at,
    formatDate(entry.updated_at),
  );

  if (confirming) {
    return (
      <tr
        data-testid={`${idSingular}-row`}
        {...{ [`data-${idSingular}-id`]: entry.id }}
        data-confirming="true"
        className="border-b border-hairline last:border-b-0 bg-carbide"
      >
        <Gutter ordinal={ordinal} idSingular={idSingular} addressed />
        {/* Name + every data cell up to FILED: the confirm takes the row over,
            so the span has to follow whichever optional columns are showing. */}
        <td
          colSpan={2 + (showUnits ? 1 : 0) + (showHealth ? 1 : 0)}
          className="px-3 py-2"
        >
          <span className="font-body text-sm text-mist">
            Delete <span className="font-data text-flag">{entry.name}</span>?
            This cannot be undone.
          </span>
          {deleteError !== null ? (
            <span
              role="alert"
              className="ml-2 font-body text-xs text-flag"
              data-testid={`${idSingular}-delete-error`}
            >
              {deleteError}
            </span>
          ) : null}
        </td>
        <td className="px-3 py-2" colSpan={2}>
          <div className="flex items-center justify-end gap-2">
            <Button
              onClick={() => setConfirming(false)}
              disabled={pending}
              data-testid={`${idSingular}-delete-cancel`}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => void remove()}
              disabled={pending}
              data-testid={`${idSingular}-delete-confirm`}
            >
              {pending ? "Deleting…" : "Delete"}
            </Button>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr
      data-testid={`${idSingular}-row`}
      {...{ [`data-${idSingular}-id`]: entry.id }}
      className="group border-b border-hairline last:border-b-0 hover:bg-carbide focus-within:bg-carbide"
    >
      <Gutter ordinal={ordinal} idSingular={idSingular} />
      <td className="truncate px-3 py-2 align-middle">
        {openLink(entry, {
          className:
            // `min-h-target-dense`: the row stays dense, the TAP TARGET does not go
            // under the 24px floor (design `target` policy; it measured 84x18).
            "inline-flex min-h-target-dense items-center rounded-sm font-body text-md text-mist underline-offset-4 outline-none hover:text-brass hover:underline focus-visible:text-brass focus-visible:underline",
          "data-testid": `${idSingular}-open`,
        })}
      </td>
      {showUnits ? (
        <td className="px-3 py-2 align-middle font-data text-xs text-gauge">
          {entry.length_unit ?? "—"}
        </td>
      ) : null}
      <td className="px-3 py-2 align-middle">
        {activity.kind === "never" ? (
          <span
            className="font-display text-2xs uppercase tracking-[0.14em] text-gauge"
            title="No edits since it was created"
            data-testid={`${idSingular}-unstarted`}
          >
            Not started
          </span>
        ) : (
          <span
            className="font-data text-xs tabular-nums text-mist"
            title={
              activity.kind === "worked"
                ? `Last edited ${formatDate(entry.updated_at)}`
                : undefined
            }
          >
            {activity.kind === "worked" ? activity.label : "—"}
          </span>
        )}
      </td>
      {showHealth ? (
        <td className="px-3 py-2 align-middle">
          <HealthCell idSingular={idSingular} entry={entry} />
        </td>
      ) : null}
      <td className="hidden px-3 py-2 align-middle font-data text-xs tabular-nums text-gauge md:table-cell">
        {filed}
      </td>
      <td className="px-3 py-2 text-right align-middle">
        <button
          type="button"
          onClick={() => setConfirming(true)}
          data-testid={`${idSingular}-delete`}
          aria-label={`Delete ${entry.name}`}
          // 53x15 before the target policy — the one destructive verb in the
          // register was its smallest control.
          className="inline-flex min-h-target-dense items-center justify-end rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none transition-colors duration-fast hover:text-flag focus-visible:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
        >
          Delete
        </button>
      </td>
    </tr>
  );
}

/**
 * Relative age of the health record, as a title-clause (" 20 min ago"). Falls
 * back to the absolute date for anything older than the relative buckets, so
 * the phrasing matches the FILED column's format.
 */
function rebuildAge(iso: string | null | undefined): string {
  if (iso === undefined || iso === null) return "";
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return "";
  const label = relativeAge(Math.max(0, Date.now() - at));
  return label === null ? ` on ${formatDate(iso)}` : `, ${label}`;
}

/**
 * REBUILD — "would this part rebuild if I opened it?", the one question the
 * register could not answer until documents started keeping the record
 * (`c98c454`).
 *
 * WHY ITS OWN COLUMN, next to LAST WORKED rather than inside it. The two answer
 * different questions and are both worth saying at once: "20 min ago" is where
 * you were, "broken" is what you will walk into. Folding health into the
 * activity cell would force one of them to be suppressed exactly when both
 * matter, and it would quietly redefine LAST WORKED — which the backend
 * deliberately protected by NOT bumping `updated_at` when it records a rebuild,
 * so that column keeps meaning "someone worked on it" rather than "someone
 * looked at it". Two facts, two cells; the column sits adjacent so the pair
 * reads as one clause about the same sitting.
 *
 * The four states and their exact claims — this cell is the reason the derived
 * `eval_state` exists, so it never says more than the server did:
 *
 *  - **never** — nothing is known. A quiet dash, and the screen reader is told
 *    "not evaluated" rather than being left with an em-dash.
 *  - **ok** — NO FEATURE ERRORED when this tree was last rebuilt. Deliberately
 *    NOT a tick and deliberately not the word "good": `ok` says nothing about
 *    whether the part has a body, and the title says so in as many words. It is
 *    the quietest state on the surface because "it rebuilds" is the expectation.
 *  - **failed** — a feature errored, and that verdict still applies to the tree
 *    as it stands. The one loud state: a flag-inked stamp, because this is the
 *    expensive surprise the column was added for.
 *  - **stale** — evaluated, then the tree moved. Health is genuinely UNKNOWN, so
 *    it renders INDETERMINATE: the dashed phantom stamp the clash schedule uses
 *    for UNVERIFIED, never a tick and never a flag. The raw record is still
 *    spent — "was broken" / "was clean", past tense, quiet ink — because "the
 *    last rebuild errored and then you changed something" is more useful than
 *    "unknown", as long as the surface never dresses it up as current.
 */
function HealthCell<T extends RegisterDocument>({
  idSingular,
  entry,
}: {
  idSingular: string;
  entry: T;
}) {
  const state = entry.eval_state ?? "never";
  const age = rebuildAge(entry.last_eval_at);
  const testId = `${idSingular}-health`;

  if (state === "never") {
    return (
      <span
        data-testid={testId}
        data-health="never"
        title="This part has not been evaluated, so nothing is known about whether it rebuilds."
        className="font-data text-xs text-gauge"
      >
        <span aria-hidden>—</span>
        <span className="sr-only">Not evaluated</span>
      </span>
    );
  }

  if (state === "ok") {
    return (
      <span
        data-testid={testId}
        data-health="ok"
        title={`No feature errored when this part was last rebuilt${age}. That is not a claim that it has a body.`}
        className="font-display text-2xs uppercase tracking-[0.14em] text-gauge"
      >
        Clean
      </span>
    );
  }

  if (state === "failed") {
    return (
      <Stamp
        tone="flag"
        data-testid={testId}
        data-health="failed"
        title={`A feature errored when this part was last rebuilt${age}. Open it to see which.`}
      >
        Broken
      </Stamp>
    );
  }

  const wasBroken = entry.last_eval_status === "failed";
  return (
    <Stamp
      indeterminate
      data-testid={testId}
      data-health="stale"
      title={`The tree changed after the last rebuild${age}, so this part's health is unknown — it ${
        wasBroken ? "had a feature error" : "was clean"
      } then.`}
    >
      {wasBroken ? "Was broken" : "Was clean"}
      <span className="sr-only">
        {" "}
        — the tree changed since, so its current health is unknown
      </span>
    </Stamp>
  );
}

/**
 * The scribed margin: the ROW ORDINAL on the carbide ground, ruled off the
 * register body. Its left edge carries the brass scribe for the ADDRESSED row
 * (hover / keyboard focus anywhere in it) — the row marker, at the left edge
 * where the eye starts, so a wide row never loses its place.
 *
 * It used to render `001` and its own doc comment called that a "filing
 * identity: stable". It was `String(index + 1).padStart(3, "0")` — a POSITION in
 * a zero-padded costume, and positions move: file 001/002/003, delete 001, and
 * 001/002 now address different parts than they did a moment ago. A user who
 * wrote "sheet 002" in a change note or a message was holding a reference that
 * silently retargeted (UI-REVIEW 2026-07-30 P2 — the same lens as the false
 * clash badge, at lower stakes).
 *
 * The call: keep the number, drop the claim. A position is genuinely useful in a
 * dense list ("the third row"), so the column stays — as `#` with an `sr-only`
 * "Row", and unpadded, because the padding was most of the lie. A REAL sheet
 * number is a stored per-owner monotonic sequence on the document row, i.e. a
 * documents-service change, and it is filed as its own item rather than faked
 * here. The gutter's form (carbide ground, brass scribe, right-aligned tabular
 * data face) is unchanged — only what it asserts.
 */
function Gutter({
  ordinal,
  idSingular,
  addressed,
}: {
  ordinal: number;
  idSingular: string;
  addressed?: boolean;
}) {
  return (
    <td
      className={`h-10 border-l-2 bg-carbide px-3 py-2 text-right align-middle font-data text-xs tabular-nums text-gauge ${
        addressed
          ? "border-brass"
          : "border-transparent group-hover:border-brass group-focus-within:border-brass"
      }`}
    >
      <span data-testid={`${idSingular}-ordinal`}>{ordinal}</span>
    </td>
  );
}

/**
 * The next line of the register — where a new row gets scribed. It carries the
 * next ordinal in the same gutter, so filing reads as continuing the log rather
 * than operating a form. `N` focuses it from anywhere on the page (previously
 * true but never shown; the chip teaches it).
 */
function ScribeLine({
  idSingular,
  copy,
  nextOrdinal,
  onCreate,
}: {
  idSingular: string;
  copy: RegisterCopy;
  nextOrdinal: number;
  onCreate: (name: string) => Promise<void>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const focus = useCallback(() => inputRef.current?.focus(), []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      if (event.key.toLowerCase() === "n") {
        event.preventDefault();
        focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [focus]);

  return (
    <div className="flex shrink-0 items-stretch border-b border-hairline">
      <div
        className={`${COLUMN.gutter} shrink-0 border-l-2 border-transparent bg-carbide px-3 pt-3 text-right font-data text-xs tabular-nums text-gauge`}
        aria-hidden="true"
      >
        {nextOrdinal}
      </div>
      <div className="min-w-0 grow px-3 py-3">
        <CreateForm
          idSingular={idSingular}
          copy={copy}
          inputRef={inputRef}
          submitLabel={copy.createLabel}
          onCreate={onCreate}
          showChord
        />
      </div>
    </div>
  );
}

/**
 * The unfiled lines of the drawer, ruled at the row rhythm and running to the
 * bottom of the frame. A log book's blank lines: it is the register's ground,
 * not a control, so it is `aria-hidden` and never focusable — the same standing
 * the sheet grid behind the page has. It exists because a register that stops
 * a third of the way down the frame reads as a card on a web page, and one that
 * runs to the edge reads as the drawer it is.
 */
function RuledRemainder() {
  return (
    <div
      className="flex grow overflow-hidden"
      aria-hidden="true"
      data-testid="register-ruled-remainder"
    >
      {/* The scribed margin runs the whole height of the drawer, not just past
          the filed rows — one straight left rule from header to frame edge. */}
      <div
        className={`${COLUMN.gutter} shrink-0 border-l-2 border-transparent bg-carbide`}
      />
      <RuledLines />
    </div>
  );
}

/**
 * Enough blank lines to reach the bottom of a tall frame; the container clips
 * the rest, so this is a ceiling rather than a layout constant to keep in sync.
 */
const RULED_LINES = 24;

/** The blank lines themselves, at the filed rows' exact 41px rhythm. */
function RuledLines() {
  return (
    <div className="grow overflow-hidden" aria-hidden="true">
      {Array.from({ length: RULED_LINES }, (_, index) => (
        <div key={index} className="h-10 border-b border-hairline/40" />
      ))}
    </div>
  );
}

/** First run: an invitation with the create control, not a blank drawer. */
function EmptyRegister({
  idPlural,
  idSingular,
  copy,
  onCreate,
}: {
  idPlural: string;
  idSingular: string;
  copy: RegisterCopy;
  onCreate: (name: string) => Promise<void>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => inputRef.current?.focus(), []);
  return (
    <div
      className="flex min-h-0 grow items-stretch"
      data-testid={`${idPlural}-empty`}
    >
      {/* The scribed margin, unbroken even before the first sheet is filed. */}
      <div
        className={`${COLUMN.gutter} shrink-0 border-l-2 border-transparent bg-carbide`}
        aria-hidden="true"
      />
      <div className="flex min-h-0 grow flex-col">
        <div className="shrink-0 px-4 py-10 sm:px-6 sm:py-12">
          <p className="font-display text-2xs uppercase tracking-[0.2em] text-gauge">
            Empty register
          </p>
          <h3 className="mt-2 font-body text-lg text-mist">
            {copy.emptyHeadline}
          </h3>
          <p className="mt-1 max-w-md font-body text-sm text-gauge">
            {copy.emptyBody}
          </p>
          <div className="mt-5 max-w-md">
            <CreateForm
              idSingular={idSingular}
              copy={copy}
              inputRef={inputRef}
              submitLabel={copy.createFirstLabel}
              onCreate={onCreate}
            />
          </div>
        </div>
        <RuledLines />
      </div>
    </div>
  );
}

/** The shared create control — a name cell + the one brass action. */
function CreateForm({
  idSingular,
  copy,
  inputRef,
  submitLabel,
  onCreate,
  showChord,
}: {
  idSingular: string;
  copy: RegisterCopy;
  inputRef: React.RefObject<HTMLInputElement | null>;
  submitLabel: string;
  onCreate: (name: string) => Promise<void>;
  showChord?: boolean;
}) {
  const [name, setName] = useState("");
  const [pending, setPending] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const invalid = validatePartName(name);
    if (invalid !== null) {
      setFieldError(invalid);
      return;
    }
    setPending(true);
    try {
      await onCreate(name.trim());
      setName("");
      setFieldError(null);
      setPending(false);
      inputRef.current?.focus();
    } catch (caught) {
      setPending(false);
      setFieldError(
        caught instanceof Error ? caught.message : copy.createError,
      );
    }
  };

  return (
    <form
      className="flex items-end gap-3"
      onSubmit={(event) => void submit(event)}
      noValidate
      data-testid={`create-${idSingular}-form`}
    >
      <TextField
        ref={inputRef}
        label={copy.fieldLabel}
        value={name}
        error={fieldError}
        placeholder={copy.placeholder}
        autoComplete="off"
        disabled={pending}
        data-testid={`create-${idSingular}-name`}
        className="grow"
        onChange={(event) => {
          setName(event.currentTarget.value);
          if (fieldError !== null) setFieldError(null);
        }}
      />
      {showChord ? (
        <>
          {/* The `N` accelerator has always worked and was never shown. The
              chip teaches it; the sr-only sentence says what the bare glyph
              cannot. */}
          <span className="sr-only">Press N to jump to this field.</span>
          <Kbd className="mb-2 shrink-0" aria-hidden="true">
            N
          </Kbd>
        </>
      ) : null}
      <Button
        type="submit"
        variant="solid"
        disabled={pending}
        data-testid={`create-${idSingular}-submit`}
        className="mb-[1px] shrink-0"
      >
        {pending ? "Creating…" : submitLabel}
      </Button>
    </form>
  );
}
