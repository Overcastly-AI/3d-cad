import { Button, Kbd, type LengthUnit, TextField } from "@loft/design";
import {
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { documentActivity } from "../lib/activity";
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
 *
 * Not shown, deliberately: "has a body", "has drawings", "is broken". None are
 * on the wire for a LIST; getting them would mean an evaluate per row. A
 * register that guesses is worse than one that reports.
 *
 * FORM. The identity comes from the language the rest of the product already
 * speaks — no new look was invented. The sheet number moves out of the ruled
 * body into a scribed left GUTTER on the carbide ground, the way a drawing's
 * zone indices are printed in its margin; the addressed row takes a brass
 * scribe on that gutter's edge (the only accent, and it marks position across a
 * wide row rather than decorating); the name is the one thing set in body type
 * at reading size while every other cell is quiet tracked data. The create
 * control is no longer a form bolted above a table — it is the NEXT LINE of the
 * register, carrying the next sheet number, because that is what filing a new
 * part is, and its `N` accelerator is finally shown rather than hidden. Below
 * it the drawer's remaining ruled lines run to the bottom of the frame, which
 * is what kills the old "small card adrift in a void" read.
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
            openLink={openLink}
            onDelete={onDelete}
          />
          <ScribeLine
            idSingular={idSingular}
            copy={copy}
            nextSheetNo={sheetNo(documents.length + 1)}
            onCreate={onCreate}
          />
          <RuledRemainder />
        </div>
      )}
    </section>
  );
}

/** Filing identity: "001". Stable, and the gutter's whole reason to exist. */
function sheetNo(index: number): string {
  return String(index).padStart(3, "0");
}

/** Shared gutter width — the table's first column and the scribe line agree. */
const COLUMN = {
  /** Scribed margin carrying the sheet number — the table and the scribe line
   *  below it share this width so the log's left edge is one straight rule. */
  gutter: "w-[3.5rem]",
  units: "w-[4.5rem]",
  activity: "w-[9rem]",
  filed: "w-[7rem]",
  action: "w-[5.5rem]",
} as const;

function RegisterTable<T extends RegisterDocument>({
  idPlural,
  idSingular,
  copy,
  documents,
  showUnits,
  openLink,
  onDelete,
}: {
  idPlural: string;
  idSingular: string;
  copy: RegisterCopy;
  documents: T[];
  showUnits: boolean;
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
          <Th className={`${COLUMN.gutter} bg-carbide text-right`}>№</Th>
          <Th>Name</Th>
          {showUnits ? <Th className={COLUMN.units}>Units</Th> : null}
          <Th className={COLUMN.activity}>Last worked</Th>
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
            sheet={sheetNo(index + 1)}
            showUnits={showUnits}
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
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`px-3 py-2 text-left font-display text-2xs uppercase tracking-[0.16em] text-gauge ${
        className ?? ""
      }`}
    >
      {children}
    </th>
  );
}

/** One filed sheet: gutter number, name, activity, units, filing date, delete. */
function RegisterRow<T extends RegisterDocument>({
  idSingular,
  copy,
  entry,
  sheet,
  showUnits,
  openLink,
  onDelete,
}: {
  idSingular: string;
  copy: RegisterCopy;
  entry: T;
  sheet: string;
  showUnits: boolean;
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
        <Gutter sheet={sheet} addressed />
        <td colSpan={showUnits ? 3 : 2} className="px-3 py-2">
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
      <Gutter sheet={sheet} />
      <td className="truncate px-3 py-2 align-middle">
        {openLink(entry, {
          className:
            "rounded-sm font-body text-md text-mist underline-offset-4 outline-none hover:text-brass hover:underline focus-visible:text-brass focus-visible:underline",
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
      <td className="hidden px-3 py-2 align-middle font-data text-xs tabular-nums text-gauge md:table-cell">
        {filed}
      </td>
      <td className="px-3 py-2 text-right align-middle">
        <button
          type="button"
          onClick={() => setConfirming(true)}
          data-testid={`${idSingular}-delete`}
          aria-label={`Delete ${entry.name}`}
          className="rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none transition-colors duration-fast hover:text-flag focus-visible:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
        >
          Delete
        </button>
      </td>
    </tr>
  );
}

/**
 * The scribed margin: the sheet number on the carbide ground, ruled off the
 * register body. Its left edge carries the brass scribe for the ADDRESSED row
 * (hover / keyboard focus anywhere in it) — the row marker, at the left edge
 * where the eye starts, so a wide row never loses its place.
 */
function Gutter({ sheet, addressed }: { sheet: string; addressed?: boolean }) {
  return (
    <td
      className={`h-10 border-l-2 bg-carbide px-3 py-2 text-right align-middle font-data text-xs tabular-nums text-gauge ${
        addressed
          ? "border-brass"
          : "border-transparent group-hover:border-brass group-focus-within:border-brass"
      }`}
    >
      {sheet}
    </td>
  );
}

/**
 * The next line of the register — where a new sheet gets scribed. It carries
 * the next sheet number in the same gutter, so filing reads as continuing the
 * log rather than operating a form. `N` focuses it from anywhere on the page
 * (previously true but never shown; the chip teaches it).
 */
function ScribeLine({
  idSingular,
  copy,
  nextSheetNo,
  onCreate,
}: {
  idSingular: string;
  copy: RegisterCopy;
  nextSheetNo: string;
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
        {nextSheetNo}
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
