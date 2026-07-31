import {
  Button,
  Kbd,
  type LengthUnit,
  SortAscIcon,
  SortDescIcon,
  TextField,
} from "@loft/design";
import {
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type {
  PartEvalScope,
  PartEvalState,
  PartLastEvalStatus,
} from "../api/parts";
import { validatePartName } from "../lib/partName";
import { DocumentRegisterRow } from "./DocumentRegisterRow";

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
 * ─────────────────────────────────────────────────────────────────────────────
 * WORKSPACE MANAGEMENT (2026-07-31) — the row you hit on your TENTH document.
 *
 * Create-and-open was the whole surface; a drawer you cannot search, rename or
 * copy stops being a place you keep work. Three additions, and one deliberate
 * omission:
 *
 *   - FILTER, in the header rule rather than floating above the drawer as a
 *     rounded search pill with a magnifier (the template answer, and it would be
 *     the only round-cornered object on the screen). It is a title-block field:
 *     a tracked FILTER label and a ruled cell, on the header's own line. `/`
 *     focuses it from anywhere, shown as a chip the way `N` already is.
 *   - The COUNT becomes a FRACTION when the filter is on: "4 OF 12 PARTS",
 *     which is a sheet counter's own grammar and — the point — the one readout
 *     that makes an empty result legible instead of alarming. It is derived
 *     from the two array lengths on screen, so it cannot disagree with them.
 *   - SORT is the column headers themselves. NAME / LAST WORKED / FILED are
 *     buttons carrying `aria-sort` and a scribed direction chevron; clicking
 *     the active one reverses it. No new chrome at all — the design mandate's
 *     "a control that only decorates is a defect" answered by adding no
 *     control. The default is FILED ascending, which IS the server's order, so
 *     the unsorted state is a real state rather than a label over an arbitrary
 *     one.
 *
 * FOLDERS ARE NOT HERE, and the surface does not pretend otherwise: there is no
 * folder rail, no "unfiled" group and no drag target. A folder tree is a
 * documents-service change (a parent column, a move endpoint, cycle rules,
 * per-folder name uniqueness) and shipping the UI in front of nothing would be
 * the exact defect class this register is being held to. Filed in BACKLOG.
 * ─────────────────────────────────────────────────────────────────────────────
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
   * HOW MUCH of the tree that verdict covers — the second, orthogonal axis
   * (`whole` / `rolled_back` / null). Read WITH `eval_state`, never instead of
   * it, and never read null as `whole` (see `registerHealthReadout`).
   */
  eval_scope?: PartEvalScope;
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
  /** Fallback when a rename fails. */
  renameError: string;
  /** Fallback when a duplicate fails. */
  duplicateError: string;
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

/** Which column the drawer is ordered by. */
export type RegisterSortKey = "name" | "activity" | "filed";

export interface RegisterSort {
  key: RegisterSortKey;
  direction: "asc" | "desc";
}

/**
 * FILED ascending — which is the order the server already returns (oldest
 * first), so the register's initial state is a true description of what is on
 * screen rather than a label applied to an arbitrary order.
 */
export const DEFAULT_SORT: RegisterSort = { key: "filed", direction: "asc" };

/**
 * Name-substring filter, case- and accent-insensitive, applied to the list the
 * server returned.
 *
 * Client-side on purpose, and honestly so: the list endpoint returns the
 * caller's WHOLE drawer in one response (no pagination on the wire), so the
 * browser is filtering the complete set — the count can therefore say "4 of 12"
 * and mean it. If that list ever becomes a page, the filter has to move to the
 * server in the same change, because "4 of 12" would silently start meaning
 * "4 of the 12 I happen to be holding".
 */
export function filterDocuments<T extends RegisterDocument>(
  documents: T[],
  query: string,
): T[] {
  const needle = query.trim().toLocaleLowerCase();
  if (needle === "") return documents;
  return documents.filter((entry) =>
    entry.name.toLocaleLowerCase().includes(needle),
  );
}

/**
 * Order the drawer.
 *
 * NAME uses a numeric collator so "Rib 2" sorts before "Rib 10" — a register
 * full of numbered parts sorted lexically is a register nobody trusts.
 *
 * TIES ARE NOT BROKEN, deliberately: `Array.prototype.sort` is stable, so equal
 * rows keep the order the SERVER sent them in (documents lists by
 * `created_at, id`). Inventing a client-side tiebreak — collating the uuids, say
 * — would order two same-millisecond documents differently from every other
 * surface that shows them, for no gain; borrowing the server's order costs
 * nothing and cannot disagree with it.
 */
export function sortDocuments<T extends RegisterDocument>(
  documents: T[],
  sort: RegisterSort,
): T[] {
  const collator = new Intl.Collator(undefined, {
    numeric: true,
    sensitivity: "base",
  });
  const sign = sort.direction === "asc" ? 1 : -1;
  const compare = (a: T, b: T): number => {
    if (sort.key === "name") return collator.compare(a.name, b.name);
    const key = sort.key === "activity" ? "updated_at" : "created_at";
    return Date.parse(a[key]) - Date.parse(b[key]);
  };
  return [...documents].sort((a, b) => sign * compare(a, b));
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
  /**
   * Rename + invalidate. The page supplies the document's concurrency version
   * (parts carry `tree_version`, assemblies and drawings `doc_version`), which
   * is why the register does not read it off the row itself. Rejects so the
   * message lands under the field that was typed in.
   */
  onRename: (document: T, name: string) => Promise<void>;
  /** Duplicate + invalidate. Never told what the copy will be called. */
  onDuplicate: (document: T) => Promise<void>;
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
  onRename,
  onDuplicate,
  onDelete,
}: DocumentRegisterProps<T>) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<RegisterSort>(DEFAULT_SORT);

  const shown = useMemo(
    () => sortDocuments(filterDocuments(documents, query), sort),
    [documents, query, sort],
  );
  const filtering = query.trim() !== "";
  const empty = !isLoading && !isError && documents.length === 0;
  const showUnits = documents.some((d) => d.length_unit !== undefined);
  const showHealth = documents.some((d) => d.eval_state !== undefined);

  return (
    <section
      className="mt-4 flex min-h-0 grow flex-col border border-hairline bg-anvil text-mist"
      data-testid={`${idPlural}-register`}
    >
      <header className="flex shrink-0 flex-wrap items-baseline gap-x-4 gap-y-2 border-b border-hairline px-3 py-3">
        <h2 className="font-display text-2xs uppercase tracking-[0.2em] text-gauge">
          {copy.title}
        </h2>
        {empty || isLoading || isError ? null : (
          <FilterField
            idPlural={idPlural}
            copy={copy}
            query={query}
            onChange={setQuery}
          />
        )}
        <span className="grow" />
        {isError ? null : (
          <span
            className="font-data text-xs tabular-nums text-gauge"
            data-testid={`${idPlural}-count`}
          >
            {isLoading
              ? "—"
              : countLabel(shown.length, documents.length, filtering, copy)}
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
            documents={shown}
            showUnits={showUnits}
            showHealth={showHealth}
            sort={sort}
            onSort={setSort}
            openLink={openLink}
            onRename={onRename}
            onDuplicate={onDuplicate}
            onDelete={onDelete}
          />
          {shown.length === 0 ? (
            <NoMatches
              idPlural={idPlural}
              copy={copy}
              query={query.trim()}
              onClear={() => setQuery("")}
            />
          ) : (
            <ScribeLine
              idSingular={idSingular}
              copy={copy}
              // While a filter is on, the rows above are numbered 1..n WITHIN
              // the filtered view, so printing "6" under a row 2 would put two
              // different counting systems in one column. The gutter goes blank
              // rather than assert a position the view cannot support; filing
              // still appends to the whole register.
              nextOrdinal={filtering ? null : documents.length + 1}
              onCreate={onCreate}
            />
          )}
          <RuledRemainder />
        </div>
      )}
    </section>
  );
}

/**
 * The count, which is the readout that decides whether an empty filter result
 * reads as "nothing matched" or as "my work is gone".
 *
 * Unfiltered it is the plain tally. Filtered it becomes a FRACTION — "4 of 12
 * parts" — the grammar a sheet counter uses, and both numbers are the lengths
 * of arrays this same render is drawing from, so the readout cannot drift from
 * what is on screen.
 */
function countLabel(
  shown: number,
  total: number,
  filtering: boolean,
  copy: RegisterCopy,
): string {
  const noun = total === 1 ? copy.noun : copy.nounPlural;
  return filtering ? `${shown} of ${total} ${noun}` : `${total} ${noun}`;
}

/**
 * FILTER — a title-block field on the header rule, not a search pill.
 *
 * Filters as you type (no submit, no debounce: the whole drawer is already in
 * memory, so a keystroke costs an array pass). `/` focuses it from anywhere on
 * the page and the chip teaches that, mirroring how `N` is taught on the scribe
 * line — one accelerator convention, learned once.
 */
function FilterField({
  idPlural,
  copy,
  query,
  onChange,
}: {
  idPlural: string;
  copy: RegisterCopy;
  query: string;
  onChange: (value: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

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
      if (event.key === "/") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="flex items-center gap-2">
      <label
        className="font-display text-2xs uppercase tracking-[0.16em] text-gauge"
        htmlFor={`${idPlural}-filter`}
      >
        Filter
      </label>
      <input
        ref={inputRef}
        id={`${idPlural}-filter`}
        // `text`, not `search`: Chromium paints its own blue round clear glyph
        // on a search input, which would be the only round object and the only
        // foreign colour on the screen. The clear control below is the same
        // quiet verb the rows use.
        type="text"
        value={query}
        autoComplete="off"
        spellCheck={false}
        placeholder="Name contains…"
        data-testid={`${idPlural}-filter`}
        aria-label={`Filter ${copy.nounPlural} by name`}
        onChange={(event) => onChange(event.currentTarget.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onChange("");
          }
        }}
        // The ruled cell of a title-block field: no box, one hairline under the
        // value, brass when it has focus. Deliberately NOT the rounded, boxed,
        // magnifier-prefixed search control every web app ships.
        className="w-[10rem] border-b border-etch bg-transparent pb-0.5 font-data text-xs text-mist outline-none placeholder:text-gauge focus:border-brass sm:w-[14rem]"
      />
      {query === "" ? (
        <>
          <span className="sr-only">Press slash to jump to this field.</span>
          <Kbd aria-hidden="true">/</Kbd>
        </>
      ) : (
        // Only while there is something to clear — a dead control is chrome.
        <button
          type="button"
          onClick={() => onChange("")}
          data-testid={`${idPlural}-filter-clear`}
          className="inline-flex min-h-target-dense items-center rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none transition-colors duration-fast hover:text-brass focus-visible:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
        >
          Clear
        </button>
      )}
    </div>
  );
}

/**
 * The filter matched nothing. An empty screen is an invitation to act, so this
 * says what was searched (quoting it, so a stray space is visible), states that
 * the drawer is intact, and offers the one control that fixes it. It replaces
 * the scribe line rather than sitting beside it: filing a new document is not
 * the answer to "your filter is too narrow".
 */
function NoMatches({
  idPlural,
  copy,
  query,
  onClear,
}: {
  idPlural: string;
  copy: RegisterCopy;
  query: string;
  onClear: () => void;
}) {
  return (
    <div
      className="flex shrink-0 items-stretch border-b border-hairline"
      data-testid={`${idPlural}-no-matches`}
    >
      <div
        className={`${COLUMN.gutter} shrink-0 border-l-2 border-transparent bg-carbide`}
        aria-hidden="true"
      />
      <div className="flex min-w-0 grow flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-4">
        <p className="font-body text-sm text-mist" role="status">
          No {copy.nounPlural} match{" "}
          <span className="font-data text-mist">“{query}”</span>.
        </p>
        <Button onClick={onClear} data-testid={`${idPlural}-no-matches-clear`}>
          Clear filter
        </Button>
      </div>
    </div>
  );
}

/** Shared gutter width — the table's first column and the scribe line agree. */
const COLUMN = {
  /** Scribed margin carrying the row ordinal — the table and the scribe line
   *  below it share this width so the log's left edge is one straight rule. */
  gutter: "w-[3.5rem]",
  units: "w-[4.5rem]",
  activity: "w-[9rem]",
  /** Wide enough for the longest stamped verdict ("Clean to stop") unwrapped. */
  health: "w-[9rem]",
  filed: "w-[7rem]",
  /** Three verbs, always visible — see `DocumentRegisterRow`. */
  action: "w-[13rem]",
} as const;

function RegisterTable<T extends RegisterDocument>({
  idPlural,
  idSingular,
  copy,
  documents,
  showUnits,
  showHealth,
  sort,
  onSort,
  openLink,
  onRename,
  onDuplicate,
  onDelete,
}: {
  idPlural: string;
  idSingular: string;
  copy: RegisterCopy;
  documents: T[];
  showUnits: boolean;
  showHealth: boolean;
  sort: RegisterSort;
  onSort: (sort: RegisterSort) => void;
  openLink: DocumentRegisterProps<T>["openLink"];
  onRename: (document: T, name: string) => Promise<void>;
  onDuplicate: (document: T) => Promise<void>;
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
          <SortableTh
            idPlural={idPlural}
            sortKey="name"
            label="Name"
            sort={sort}
            onSort={onSort}
          />
          {showUnits ? <Th className={COLUMN.units}>Units</Th> : null}
          <SortableTh
            idPlural={idPlural}
            sortKey="activity"
            label="Last worked"
            className={COLUMN.activity}
            sort={sort}
            onSort={onSort}
          />
          {showHealth ? <Th className={COLUMN.health}>Rebuild</Th> : null}
          <SortableTh
            idPlural={idPlural}
            sortKey="filed"
            label="Filed"
            className={`hidden md:table-cell ${COLUMN.filed}`}
            sort={sort}
            onSort={onSort}
          />
          <th className={COLUMN.action}>
            <span className="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {documents.map((entry, index) => (
          <DocumentRegisterRow
            key={entry.id}
            idSingular={idSingular}
            copy={copy}
            entry={entry}
            ordinal={index + 1}
            showUnits={showUnits}
            showHealth={showHealth}
            openLink={openLink}
            onRename={onRename}
            onDuplicate={onDuplicate}
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

/**
 * A column header that IS the sort control.
 *
 * No sort dropdown was added, because the table already has three labels
 * naming exactly the three things you would sort by, and a separate control
 * would be a second place saying the same word. Clicking a quiet header sorts
 * by it (ascending — A→Z, oldest first, which is what these columns' natural
 * reading direction is); clicking the ACTIVE header reverses it. The direction
 * chevron only appears on the active column, so the header row stays a header
 * row rather than a strip of three widgets.
 *
 * `aria-sort` on the `th` is the real state for assistive tech, and the button's
 * `sr-only` sentence says what the next click will do — a bare chevron cannot.
 */
function SortableTh({
  idPlural,
  sortKey,
  label,
  className,
  sort,
  onSort,
}: {
  idPlural: string;
  sortKey: RegisterSortKey;
  label: string;
  className?: string;
  sort: RegisterSort;
  onSort: (sort: RegisterSort) => void;
}) {
  const active = sort.key === sortKey;
  const ascending = sort.direction === "asc";
  const next: RegisterSort = active
    ? { key: sortKey, direction: ascending ? "desc" : "asc" }
    : { key: sortKey, direction: "asc" };
  const Chevron = ascending ? SortAscIcon : SortDescIcon;

  return (
    <th
      className={`px-3 py-2 text-left font-display text-2xs uppercase tracking-[0.16em] ${
        className ?? ""
      }`}
      aria-sort={active ? (ascending ? "ascending" : "descending") : "none"}
      data-testid={`${idPlural}-sort-${sortKey}-header`}
    >
      <button
        type="button"
        onClick={() => onSort(next)}
        data-testid={`${idPlural}-sort-${sortKey}`}
        className={`inline-flex min-h-target-dense items-center gap-1 rounded-sm uppercase tracking-[0.16em] outline-none transition-colors duration-fast hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass ${
          active ? "text-brass" : "text-gauge"
        }`}
      >
        {label}
        {active ? <Chevron size={12} /> : null}
        <span className="sr-only">
          {active
            ? `Sorted ${ascending ? "ascending" : "descending"}; activate to reverse`
            : "Activate to sort by this column"}
        </span>
      </button>
    </th>
  );
}

/**
 * The next line of the register — where a new row gets scribed. It carries the
 * next ordinal in the same gutter, so filing reads as continuing the log rather
 * than operating a form. `N` focuses it from anywhere on the page (previously
 * true but never shown; the chip teaches it).
 *
 * The ordinal it shows counts the WHOLE drawer, not the filtered view: a new
 * document is filed at the end of the register, and a filter is a way of
 * looking, not a place things go.
 */
function ScribeLine({
  idSingular,
  copy,
  nextOrdinal,
  onCreate,
}: {
  idSingular: string;
  copy: RegisterCopy;
  /** Null while filtered — see the call site. */
  nextOrdinal: number | null;
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
        {nextOrdinal ?? ""}
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
