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

import { childFolders, folderPath, type FolderResponse } from "../api/folders";
import type {
  PartEvalScope,
  PartEvalState,
  PartLastEvalStatus,
} from "../api/parts";
import { validatePartName } from "../lib/partName";
import { KEY_FILTER, KEY_NEW_DOCUMENT } from "../shortcuts/registry";
import { DocumentRegisterRow } from "./DocumentRegisterRow";
import { RegisterFolderRow } from "./RegisterFolderRow";

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
 * ─────────────────────────────────────────────────────────────────────────────
 * FOLDERS (#WS2, 2026-08-01) — now backed by a real documents-side tree
 * (`py_kit/schemas/folders.py` states the four decisions; the register is a
 * client of them). What the surface does, and what it refuses to do:
 *
 *   - A FOLDER IS A DIVIDER, not a sidebar. The register is a log book, and the
 *     thing that divides a log book is a card divider with a raised tab. Folder
 *     rows are ruled at the same rhythm as filed rows, on the carbide gutter
 *     ground, carrying a `DividerTabIcon` where a filed row carries its ordinal
 *     (a folder has no position in the document sequence, so printing one would
 *     be the ordinal-as-identity mistake at a second address). No rail was
 *     added: a rail would duplicate the navigation the dividers and the
 *     breadcrumb already give, and a second place saying the same word is the
 *     defect this register keeps deleting.
 *   - THE BREADCRUMB IS THE TITLE. "Parts register › Gearbox › Housings" — the
 *     eyebrow that was already there, extended. It costs no line and nothing
 *     new.
 *   - EVERY COUNT ON A FOLDER ROW CAME FROM THE SERVER (`document_count`,
 *     `child_folder_count`), and both are DIRECT. The register cannot compute
 *     them: at the root it is holding only the *unfiled* documents, so anything
 *     it counted itself would be a number about a different set.
 *   - A FILTER SEARCHES THE WHOLE DRAWER, not the folder you are standing in,
 *     and each hit says where it lives. This is the reachability guarantee: a
 *     document you filed and forgot is always findable, and the "4 of 12"
 *     fraction keeps meaning what it meant before folders existed. While
 *     filtering the drawer is FLAT — dividers are suppressed, because a filter
 *     is a way of looking and not a place to stand.
 *   - MOVE IS A VERB IN THE ROW, not a drag. Dragging is offered as well (rows
 *     are draggable onto dividers), but the verb is the primary path: a filing
 *     gesture only reachable by pointer would put the one destructive-ish
 *     rearrangement in the product out of reach of the keyboard.
 *   - DELETING A FOLDER THAT HOLDS THINGS IS REFUSED, and the refusal names
 *     them — the same 409-with-contents grammar the document delete uses, so a
 *     user meets one refusal, not two.
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
  /**
   * Where it is FILED — a folder id, or null for unfiled (#WS2). Absent on a
   * caller that has not adopted filing; `undefined` and `null` are treated
   * alike here (both mean "at the root"), which is safe because a document the
   * server filed always carries a real id.
   */
  folder_id?: string | null;
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

/**
 * The filing half of a register (#WS2) — supplied by the page, which owns the
 * queries and the invalidations. Absent means this drawer has no folders and
 * the register draws none: a register cannot invent a tree, and one drawn in
 * front of nothing is the over-claim this whole surface is held to.
 *
 * `T` rides through so `onMoveDocument` receives the page's own document type
 * (a part carries `tree_version`, a drawing `doc_version`), the same reason
 * `onRename` is the page's.
 */
export interface RegisterFiling<T extends RegisterDocument> {
  /** The WHOLE tree for this drawer — ancestors for the breadcrumb, all of it
   *  for the move picker. One request, never one per level. */
  folders: FolderResponse[];
  /** True while that request is in flight; the rail stays quiet rather than
   *  briefly claiming the drawer has no folders. */
  isLoading: boolean;
  /** Create a folder inside the folder currently being viewed. */
  onCreateFolder: (name: string, parentId: string | null) => Promise<void>;
  onRenameFolder: (folder: FolderResponse, name: string) => Promise<void>;
  /** Delete it; rejects with `FolderNotEmptyError` when it still holds things. */
  onDeleteFolder: (folder: FolderResponse) => Promise<void>;
  /** File a document, or un-file it with `folderId: null`. */
  onMoveDocument: (document: T, folderId: string | null) => Promise<void>;
}

/** Which column the drawer is ordered by. */
export type RegisterSortKey = "name" | "activity" | "filed";

export interface RegisterSort {
  key: RegisterSortKey;
  direction: "asc" | "desc";
}

/**
 * LAST WORKED, newest first (REGISTER-2, UI-REVIEW 2026-08-17 P1-3).
 *
 * It used to be FILED ascending, defended as "the order the server already
 * returns, so the initial state is a true description rather than a label over
 * an arbitrary order". That is a good argument about HONESTY and the wrong
 * answer to the question the surface is asked. A returning engineer opens this
 * page to get back into the thing they were doing; oldest-first put that at the
 * BOTTOM — measured at row 120 of 120 — so the register's first screen was the
 * work they had finished with. Fusion's Data Panel and Onshape both default to
 * recently-modified-first for the same reason.
 *
 * The honesty argument survives intact: this order is SORTED, `aria-sort` says
 * so on the LAST WORKED header from the first paint, and the caption says it in
 * words. Nothing is unlabelled.
 */
export const DEFAULT_SORT: RegisterSort = {
  key: "activity",
  direction: "desc",
};

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
  /**
   * The row's link into its workspace — routes are typed per document kind.
   *
   * The props are SPREAD onto the anchor, all of them: `title` carries the full
   * name so a clipped one is still readable (REGISTER-1), and it arrives here
   * rather than being stamped by each page because a page that forgot it would
   * reintroduce exactly the defect the primitive closes.
   */
  openLink: (
    document: T,
    props: { className: string; title: string; "data-testid": string },
  ) => ReactNode;
  /**
   * Create + invalidate (+ navigate, for parts). Rejects with a field error.
   * `folderId` is the folder the register is standing in, so a document named
   * inside a folder is FILED there in the one create call — a create-then-move
   * pair could fail between the two and leave it somewhere the user did not
   * put it.
   */
  onCreate: (name: string, folderId: string | null) => Promise<void>;
  /** Folders, when this drawer has them (see `RegisterFiling`). */
  filing?: RegisterFiling<T>;
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
  /**
   * A SECOND WAY TO GET A DOCUMENT INTO THIS DRAWER — today the assemblies
   * register's STEP import, tomorrow whatever else arrives already made.
   *
   * The register places it; the page draws it. That split is the whole reason
   * this prop exists rather than the page simply rendering the control under
   * the drawer, which is what shipped in `f4c590b` and what UI-REVIEW
   * 2026-08-27 P1-A measured: the empty state's own copy proposed the import
   * and the layout put it **422 px lower at 1280x800 and 622 px lower at
   * 1600x1000** — the gap GROWS with the screen, because nine ruled rows that
   * exist to make a full drawer read as a log book were between them. Only the
   * register knows whether it is empty, so only the register can decide where
   * the second way in belongs.
   *
   * Omit it and NOTHING changes: no wrapper, no divider, no eyebrow — the
   * parts and drawings registers emit byte-identical markup, pinned by a test.
   */
  offer?: RegisterOffer;
}

/** {@link DocumentRegisterProps.offer} — one way in, drawn for two placements. */
export interface RegisterOffer {
  /**
   * Eyebrow over the fork's second arm in an EMPTY drawer, written to be
   * parallel with the first ("Start from a STEP file" against "Start from
   * scratch") so the two read as alternatives rather than as steps.
   */
  label: string;
  /**
   * The control itself.
   *
   * - `fork` — beside the create form in an empty drawer, as an equal
   *   proposition. It already sits inside the register's scribed margin, so it
   *   draws no gutter and no rule of its own.
   * - `line` — the drawer's last line, under the scribe line. It owns its
   *   gutter and its rule here (see `REGISTER_GUTTER`), because only the page
   *   knows when its own state — an armed drop target, say — should colour it.
   */
  render: (placement: "fork" | "line") => ReactNode;
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
  filing,
  offer,
}: DocumentRegisterProps<T>) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<RegisterSort>(DEFAULT_SORT);
  /** The folder being viewed; null is the drawer root (the unfiled set). */
  const [folderId, setFolderId] = useState<string | null>(null);

  const filtering = query.trim() !== "";
  const folders = filing?.folders ?? [];

  /**
   * The documents on screen.
   *
   * FILTERING SEARCHES THE WHOLE DRAWER — the reachability guarantee. Standing
   * in a folder and filtering there would make a document you filed and forgot
   * unfindable, which is the one thing folders must not cost. Not filtering,
   * the view is the folder you are standing in (at the root: the unfiled set).
   */
  const inScope = useMemo(
    () =>
      filtering || filing === undefined
        ? documents
        : documents.filter((entry) => (entry.folder_id ?? null) === folderId),
    [documents, filtering, filing, folderId],
  );
  const shown = useMemo(
    () => sortDocuments(filterDocuments(inScope, query), sort),
    [inScope, query, sort],
  );
  /** Dividers at this level; suppressed while filtering (the drawer goes flat). */
  const dividers = useMemo(
    () => (filtering ? [] : childFolders(folders, folderId)),
    [folders, folderId, filtering],
  );
  const path = useMemo(
    () => folderPath(folders, folderId),
    [folders, folderId],
  );

  /**
   * "Empty" is about the WHOLE drawer, not this view: the first-run invitation
   * belongs to a user who has filed nothing at all. A user standing in an empty
   * folder gets `NothingHere` instead, which offers the right next action.
   */
  const empty =
    !isLoading && !isError && documents.length === 0 && folders.length === 0;
  /**
   * WHICH UNITS THIS DRAWER SPEAKS — the whole drawer, not the view, so the
   * readout does not change meaning when a filter narrows the rows.
   *
   * One unit is a drawer-level fact and is stated once on the header rule; two
   * or more is a per-row fact and earns the column back. Nothing is hidden
   * either way (REGISTER-1: the old column spent 8 % of the table width on
   * `mm, mm, mm, mm`).
   */
  const unitsInDrawer = useMemo(() => {
    const seen = new Set<LengthUnit>();
    for (const entry of documents) {
      if (entry.length_unit !== undefined) seen.add(entry.length_unit);
    }
    return [...seen];
  }, [documents]);
  const showUnits = unitsInDrawer.length > 1;
  /**
   * REBUILD KEEPS ITS COLUMN, ALWAYS — and the reasoning is worth keeping
   * because the obvious "improvement" here is wrong and was shipped once
   * (cb2e43e, reverted the same night after it turned `workspace.spec.ts` red).
   *
   * The idea was to extend the rule `unitsInDrawer` above already states — "a
   * column of one repeated value is not a column" — to REBUILD, which on a real
   * five-part drawer showed the same em dash in every row. Measured, that is one
   * of six headings carrying nothing, so the motivation was real. It collapsed
   * to a single header readout whenever every document agreed.
   *
   * THE ANALOGY DOES NOT HOLD, for two reasons that only became visible once it
   * was running:
   *
   *  - A UNIT IS A STABLE ATTRIBUTE; A VERDICT IS VOLATILE. A drawer's unit is
   *    fixed at creation and essentially never changes, so hoisting it to the
   *    header is a permanent simplification. Health changes under the user's
   *    hands — evaluate ONE part and the drawer stops agreeing, so the column
   *    springs back into existence and every other column's width changes with
   *    it. A table whose SHAPE depends on volatile per-row data reflows while
   *    you are reading it, and it does so at the exact moment you most need to
   *    read it: when something has just broken.
   *  - IT IS A PER-ROW QUESTION. You scan this column to decide WHICH part to
   *    open. "Do they all agree?" is a different question from "which of these
   *    is broken?", and only the column answers the second one.
   *
   * It also, as a direct consequence, deleted `data-testid="part-health"`
   * whenever the drawer happened to be uniform — so no spec could rely on a
   * documented hook (design mandate 5: never break test hooks for looks). That
   * was the symptom that caught it. The two bullets above are the cause, and
   * they would have been just as true with the hook preserved.
   *
   * The width the collapse was chasing was largely bought anyway, by the page
   * moving to `max-w-sheet` in the same change.
   */
  const showHealth = documents.some((d) => d.eval_state !== undefined);

  return (
    <section
      className="mt-4 flex min-h-0 grow flex-col border border-hairline bg-anvil text-mist"
      data-testid={`${idPlural}-register`}
    >
      <header className="flex shrink-0 flex-wrap items-baseline gap-x-4 gap-y-2 border-b border-hairline px-3 py-3">
        <Breadcrumb
          idPlural={idPlural}
          title={copy.title}
          path={path}
          onOpen={setFolderId}
        />
        {empty || isLoading || isError ? null : (
          <FilterField
            idPlural={idPlural}
            copy={copy}
            query={query}
            onChange={setQuery}
          />
        )}
        <span className="grow" />
        {/* The drawer's unit, said once. Only when every document agrees on it
            — the moment two disagree the UNITS column comes back and this goes
            away, so there is never a second place saying the same word. */}
        {empty || isLoading || isError || unitsInDrawer.length !== 1 ? null : (
          <span
            className="font-display text-2xs uppercase tracking-[0.16em] text-gauge"
            data-testid={`${idPlural}-drawer-units`}
            title={`Every ${copy.noun} in this drawer is dimensioned in ${unitsInDrawer[0]}`}
          >
            {unitsInDrawer[0]}
          </span>
        )}
        {isError ? null : (
          <span
            className="font-data text-xs tabular-nums text-gauge"
            data-testid={`${idPlural}-count`}
            title={
              // The denominator is the whole drawer WHENEVER the view is a
              // subset of it — filtered or filed. One rule, so the readout
              // never has to be reinterpreted.
              shown.length === documents.length
                ? undefined
                : `${documents.length} in this drawer altogether`
            }
          >
            {isLoading ? "—" : countLabel(shown.length, documents.length, copy)}
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
          offer={offer}
        />
      ) : (
        <div className="flex min-h-0 grow flex-col">
          {/*
            THE ROWS SCROLL, THE DRAWER DOES NOT (REGISTER-2). Measured on a
            120-part drawer at 1280x800 before this change: `main.scrollHeight`
            5145 px against a 756 px frame, with the page as the scroller — so
            the header rule, the FILTER, the count, the sort controls AND the
            only create control all left the screen together. At row 104 the
            user had six columns of unlabelled data and a 4000 px scroll back
            to the controls.

            Only the ROWS belong in the scroller. Everything that addresses the
            drawer as a whole — the header above, the scribe line below, and the
            column headers, which ARE the sort controls and so are `sticky`
            inside it — stays on screen at any length.
          */}
          <div
            // `relative` is LOAD-BEARING, not tidiness. Measured at 120 parts in
            // Chromium: without it the table's scrollable overflow propagates
            // straight past this clipping box to the PAGE — `main.scrollHeight`
            // stays 5038 against a 756 px frame and `main.scrollTop = 9999`
            // still drags the filter 4160 px off-screen, so the drawer looks
            // pinned and is not. Positioning the scroll container makes its clip
            // authoritative for the ancestor's overflow: 5038 -> 756.
            // (`contain: paint` fixes it identically; `relative` is the cheaper
            // promise to make.)
            className="relative flex min-h-0 grow flex-col overflow-y-auto"
            data-testid={`${idPlural}-scroll`}
          >
            <RegisterTable
              idPlural={idPlural}
              idSingular={idSingular}
              copy={copy}
              documents={shown}
              dividers={dividers}
              folders={folders}
              filtering={filtering}
              showUnits={showUnits}
              showHealth={showHealth}
              sort={sort}
              onSort={setSort}
              openLink={openLink}
              onRename={onRename}
              onDuplicate={onDuplicate}
              onDelete={onDelete}
              onOpenFolder={setFolderId}
              filing={filing}
            />
            {shown.length === 0 && filtering ? (
              <NoMatches
                idPlural={idPlural}
                copy={copy}
                query={query.trim()}
                onClear={() => setQuery("")}
              />
            ) : shown.length === 0 && dividers.length === 0 ? (
              <NothingHere
                idPlural={idPlural}
                copy={copy}
                folderName={path[path.length - 1]?.name ?? null}
              />
            ) : null}
            <RuledRemainder />
          </div>
          {/* The next line of the register, now PINNED to the drawer's bottom
              rule. It is the same control it always was and it reads the same
              way — a log book's writing line is at the end of the entries — but
              at 120 parts "the end of the entries" was 5145 px down, i.e. the
              one thing you cannot reach when you have the most work filed.
              Suppressed only when a filter matched nothing, where `NoMatches`
              owns the line: filing a new document is not the answer to "your
              filter is too narrow". */}
          {shown.length === 0 && filtering ? null : (
            <ScribeLine
              idSingular={idSingular}
              idPlural={idPlural}
              copy={copy}
              // While a filter is on, the rows above are numbered 1..n WITHIN
              // the filtered view, so printing "6" under a row 2 would put two
              // different counting systems in one column. The gutter goes blank
              // rather than assert a position the view cannot support; filing
              // still appends to the whole register.
              nextOrdinal={filtering ? null : inScope.length + 1}
              folderId={folderId}
              onCreate={onCreate}
              filing={filing}
            />
          )}
          {/* The drawer's LAST line — after the scribe line, because a sheet
              that already exists is filed after the one you are about to
              write. Exactly where `f4c590b` put it, which the review praised;
              the register now owns the DECISION rather than the geometry. */}
          {offer?.render("line")}
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
function countLabel(shown: number, total: number, copy: RegisterCopy): string {
  const noun = total === 1 ? copy.noun : copy.nounPlural;
  // ONE rule since folders (#WS2): a fraction whenever the view is a SUBSET of
  // the drawer, for whatever reason — a filter, or standing in a folder. The
  // alternative (a plain tally that silently means "here") would have made "12
  // parts" mean two different things on two screens of the same register.
  return shown === total ? `${total} ${noun}` : `${shown} of ${total} ${noun}`;
}

/**
 * THE BREADCRUMB IS THE TITLE (#WS2).
 *
 * The header already carried a tracked eyebrow ("Parts register"); standing
 * inside a folder extends it — "Parts register › Gearbox › Housings" — rather
 * than adding a second navigation strip. Every segment before the last is a
 * button back to that level, so the way out is always one click and always in
 * the same place. The LAST segment is not a button: it is where you are, and a
 * control that does nothing is a defect (mandate 3a).
 */
function Breadcrumb({
  idPlural,
  title,
  path,
  onOpen,
}: {
  idPlural: string;
  title: string;
  path: readonly FolderResponse[];
  onOpen: (folderId: string | null) => void;
}) {
  return (
    <h2
      className="flex flex-wrap items-baseline gap-1.5 font-display text-2xs uppercase tracking-[0.2em] text-gauge"
      data-testid={`${idPlural}-breadcrumb`}
    >
      {path.length === 0 ? (
        title
      ) : (
        <button
          type="button"
          onClick={() => onOpen(null)}
          data-testid={`${idPlural}-breadcrumb-root`}
          className="rounded-sm uppercase tracking-[0.2em] outline-none transition-colors duration-fast hover:text-brass focus-visible:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
        >
          {title}
        </button>
      )}
      {path.map((folder, index) => {
        const here = index === path.length - 1;
        return (
          <span key={folder.id} className="flex items-baseline gap-1.5">
            <span aria-hidden="true" className="text-etch">
              ›
            </span>
            {here ? (
              <span className="text-mist" aria-current="page">
                {folder.name}
              </span>
            ) : (
              <button
                type="button"
                onClick={() => onOpen(folder.id)}
                data-testid={`${idPlural}-breadcrumb-step`}
                className="rounded-sm uppercase tracking-[0.2em] outline-none transition-colors duration-fast hover:text-brass focus-visible:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
              >
                {folder.name}
              </button>
            )}
          </span>
        );
      })}
    </h2>
  );
}

/**
 * You are standing somewhere with nothing in it. Distinct from `NoMatches`
 * (a filter found nothing) and from `EmptyRegister` (you have filed nothing at
 * all, ever): this one states WHERE it is empty and leaves the scribe line
 * below it, because filing something here is exactly the right next action.
 */
function NothingHere({
  idPlural,
  copy,
  folderName,
}: {
  idPlural: string;
  copy: RegisterCopy;
  folderName: string | null;
}) {
  return (
    <div
      className="flex shrink-0 items-stretch border-b border-hairline"
      data-testid={`${idPlural}-nothing-here`}
    >
      <div
        className={`${COLUMN.gutter} shrink-0 border-l-2 border-transparent bg-carbide`}
        aria-hidden="true"
      />
      <div className="min-w-0 grow px-3 py-4">
        <p className="font-body text-sm text-gauge" role="status">
          {folderName === null
            ? `No ${copy.nounPlural} are unfiled — everything is in a folder.`
            : `Nothing is filed in ${folderName} yet.`}
        </p>
      </div>
    </div>
  );
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
      if (event.key === KEY_FILTER) {
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
          <Kbd aria-hidden="true">{KEY_FILTER}</Kbd>
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

/**
 * THE WIDTH BUDGET (REGISTER-1, 2026-08-17).
 *
 * Every column here is FIXED and NAME takes what is left, because NAME is the
 * only column that tells two rows apart and it was the third-narrowest: 173 px
 * of 957 at 1280 (18 %), against 256 px of row verbs (27 %) and 72 px of a UNITS
 * column reading `mm, mm, mm, mm` (UI-REVIEW P1-2, measured in the running app).
 *
 * Two changes bought NAME 272 px:
 *  - the four verbs became one `OverflowMenu` mark, so ACTION is now the
 *    GUTTER'S width — the drawer reads with two equal scribed margins, an
 *    ordinal in the left one and the row's verbs in the right;
 *  - UNITS is no longer a per-row column when the drawer speaks one unit; it is
 *    stated once on the header rule, the way a title block states it (see
 *    `unitsInDrawer`). A column of one repeated value is not a column.
 *
 * FILED stayed, and that is a deliberate disagreement with the audit's "(c)
 * reclaim FILED": it is the only column carrying a document's ABSOLUTE date, it
 * is a live sort key, and its constancy in the audit's sample is an artifact of
 * a drawer seeded in one session, not a property of the column. It is already
 * dropped below `md`, where the width actually runs out.
 */
/**
 * THE SCRIBED MARGIN'S WIDTH, for anything drawn as a line OF this register
 * from outside it (a {@link RegisterOffer} in its `line` placement).
 *
 * Exported because `f4c590b` transcribed it as a literal `w-[3.5rem]` into
 * `AssembliesPage`, which is the DRY rule's "a number copied between two files
 * is a copy waiting to drift" in its most literal form: the drawer's left rule
 * runs unbroken only while the two agree, and nothing would have told us when
 * they stopped.
 */
export const REGISTER_GUTTER = "w-[3.5rem]";

const COLUMN = {
  /** Scribed margin carrying the row ordinal — the table and the scribe line
   *  below it share this width so the log's left edge is one straight rule. */
  gutter: REGISTER_GUTTER,
  units: "w-[4.5rem]",
  activity: "w-[9rem]",
  /** Wide enough for the longest stamped verdict ("Clean to stop") unwrapped. */
  health: "w-[9rem]",
  filed: "w-[7rem]",
  /** ONE mark, at the gutter's width — the drawer's right-hand margin. */
  action: "w-[3.5rem]",
} as const;

function RegisterTable<T extends RegisterDocument>({
  idPlural,
  idSingular,
  copy,
  documents,
  dividers,
  folders,
  filtering,
  showUnits,
  showHealth,
  sort,
  onSort,
  openLink,
  onRename,
  onDuplicate,
  onDelete,
  onOpenFolder,
  filing,
}: {
  idPlural: string;
  idSingular: string;
  copy: RegisterCopy;
  documents: T[];
  dividers: FolderResponse[];
  folders: FolderResponse[];
  filtering: boolean;
  showUnits: boolean;
  showHealth: boolean;
  sort: RegisterSort;
  onSort: (sort: RegisterSort) => void;
  openLink: DocumentRegisterProps<T>["openLink"];
  onRename: (document: T, name: string) => Promise<void>;
  onDuplicate: (document: T) => Promise<void>;
  onDelete: (document: T) => Promise<void>;
  onOpenFolder: (folderId: string | null) => void;
  filing?: RegisterFiling<T>;
}) {
  return (
    <table
      className="w-full table-fixed border-collapse"
      data-testid={`${idPlural}-table`}
    >
      <caption className="sr-only">{copy.caption}</caption>
      <thead>
        {/* No `border-b` on the row: a COLLAPSED table border does not travel
            with a sticky cell, so the rule is drawn by each `Th`'s own hairline
            (`STICKY_TH`) and stays under the headers wherever they are. */}
        <tr>
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
          <th className={`${STICKY_TH} ${COLUMN.action}`}>
            <span className="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {/* Dividers first, then filed rows — the order a drawer is read in.
            Suppressed entirely while filtering (the caller passes none). */}
        {dividers.map((folder) => (
          <RegisterFolderRow
            key={folder.id}
            idPlural={idPlural}
            copy={copy}
            folder={folder}
            columns={2 + (showUnits ? 1 : 0) + (showHealth ? 1 : 0)}
            onOpen={() => onOpenFolder(folder.id)}
            onRename={filing?.onRenameFolder}
            onDelete={filing?.onDeleteFolder}
          />
        ))}
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
            folders={folders}
            // WHERE IT LIVES, and only while filtering: the filter searches the
            // whole drawer, so a hit may be in a folder you are not standing
            // in, and a row that did not say so would be a result you could not
            // act on. At rest every row on screen is in the folder named by the
            // breadcrumb, so the label would be a column of the same string.
            showLocation={filtering && filing !== undefined}
            onMove={filing?.onMoveDocument}
          />
        ))}
      </tbody>
    </table>
  );
}

/**
 * A COLUMN HEADER THAT STAYS (REGISTER-2). It is `sticky` to the top of the
 * drawer's own scroller, because these headers are not labels — three of them
 * ARE the sort controls, and losing them at row 104 left the reader with six
 * columns of unlabelled data and no way to re-sort without scrolling back
 * 4000 px.
 *
 * The hairline is drawn by a pseudo-element rather than by a `border-b` on the
 * row: with `border-collapse: collapse` the collapsed rule belongs to the TABLE,
 * not to the sticky cell, so it stays behind at the top of the scroll while the
 * headers travel. `bg-anvil` is load-bearing too — a transparent sticky header
 * lets the rows read through it.
 */
const STICKY_TH =
  "sticky top-0 z-10 bg-anvil after:pointer-events-none after:absolute after:inset-x-0 after:bottom-0 after:h-px after:bg-hairline after:content-['']";

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
      className={`${STICKY_TH} px-3 py-2 text-left font-display text-2xs uppercase tracking-[0.16em] text-gauge ${
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
      className={`${STICKY_TH} px-3 py-2 text-left font-display text-2xs uppercase tracking-[0.16em] ${
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
  idPlural,
  copy,
  nextOrdinal,
  folderId,
  onCreate,
  filing,
}: {
  idSingular: string;
  idPlural: string;
  copy: RegisterCopy;
  /** Null while filtered — see the call site. */
  nextOrdinal: number | null;
  /** The folder being viewed — where a new document or divider is filed. */
  folderId: string | null;
  onCreate: (name: string, folderId: string | null) => Promise<void>;
  /** Only `onCreateFolder` is used here, and it mentions no document type —
   *  narrowed to that one callback so the scribe line stays non-generic. */
  filing?: Pick<RegisterFiling<RegisterDocument>, "onCreateFolder">;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const focus = useCallback(() => inputRef.current?.focus(), []);
  /**
   * ONE LINE, TWO MODES. Filing a divider is the same gesture as filing a
   * document — name it, scribe it — so it reuses this line rather than adding a
   * second control to the header. "New folder" swaps the field's label and
   * verb; Cancel swaps back.
   */
  const [scribing, setScribing] = useState<"document" | "folder">("document");

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
      if (event.key.toLowerCase() === KEY_NEW_DOCUMENT) {
        event.preventDefault();
        focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [focus]);

  return (
    // `border-t`, not `border-b`: the line is now pinned under the scrolling
    // rows (REGISTER-2), so its rule closes the drawer rather than separating
    // it from what used to follow.
    <div className="flex shrink-0 items-stretch border-t border-hairline bg-anvil">
      <div
        className={`${COLUMN.gutter} shrink-0 border-l-2 border-transparent bg-carbide px-3 pt-3 text-right font-data text-xs tabular-nums text-gauge`}
        aria-hidden="true"
      >
        {nextOrdinal ?? ""}
      </div>
      <div className="flex min-w-0 grow flex-wrap items-end gap-x-4 gap-y-2 px-3 py-3">
        {scribing === "folder" && filing !== undefined ? (
          <CreateForm
            key="folder"
            idSingular={`${idSingular}-folder`}
            copy={{
              ...copy,
              fieldLabel: "Folder name",
              placeholder: "e.g. Gearbox",
              createError: "The folder could not be created.",
            }}
            inputRef={inputRef}
            submitLabel="New folder"
            onCreate={async (name) => {
              await filing.onCreateFolder(name, folderId);
              // Back to the line's resting state. It has to go back: `N`
              // focuses this field and is taught as "name a new document", so
              // a line parked in folder mode would make the one accelerator
              // the register advertises do something else.
              setScribing("document");
            }}
          />
        ) : (
          <CreateForm
            key="document"
            idSingular={idSingular}
            copy={copy}
            inputRef={inputRef}
            submitLabel={copy.createLabel}
            onCreate={(name) => onCreate(name, folderId)}
            showChord
          />
        )}
        {filing === undefined ? null : (
          <button
            type="button"
            onClick={() =>
              setScribing(scribing === "folder" ? "document" : "folder")
            }
            data-testid={`${idPlural}-new-folder`}
            className="mb-2 inline-flex min-h-target-dense shrink-0 items-center rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none transition-colors duration-fast hover:text-brass focus-visible:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
          >
            {scribing === "folder" ? `New ${copy.noun}` : "New folder"}
          </button>
        )}
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
    // `basis-0 min-h-0`: the blank lines fill what the filed rows LEAVE and
    // nothing more. Before REGISTER-2 they were 24 real lines at the end of the
    // page scroll, so a full drawer paid ~960 px of empty ruling for a flourish
    // that only exists to keep a SHORT drawer from reading as a card in a void.
    <div
      className="flex min-h-0 shrink grow basis-0 overflow-hidden"
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

/**
 * The eyebrow over one arm of the empty drawer's fork.
 *
 * The same face as "Empty register" above it, because these labels are
 * STRUCTURE — they say "these two are alternatives, not steps" — and structure
 * in this register is drawn in the log book's own hand, never in a new one.
 *
 * `text-gauge`, NOT the one-rank-quieter `text-etch` the first draft used and
 * that the surrounding hierarchy argues for: etch on anvil measures **3.07:1**,
 * which is below AA for 10 px text (it was 3.35:1 even on carbide). The
 * hierarchy is carried by position and tracking instead. A rank of emphasis is
 * never worth a rank of legibility, and the register has no token between the
 * two — if it ever needs one, that is a token decision, not a per-site one.
 */
function ForkLabel({ children }: { children: ReactNode }) {
  return (
    <p className="font-display text-2xs uppercase tracking-[0.16em] text-gauge">
      {children}
    </p>
  );
}

/** First run: an invitation with the create control, not a blank drawer. */
function EmptyRegister({
  idPlural,
  idSingular,
  copy,
  onCreate,
  offer,
}: {
  idPlural: string;
  idSingular: string;
  copy: RegisterCopy;
  onCreate: (name: string, folderId: string | null) => Promise<void>;
  offer?: RegisterOffer;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => inputRef.current?.focus(), []);
  const createForm = (
    <CreateForm
      idSingular={idSingular}
      copy={copy}
      inputRef={inputRef}
      submitLabel={copy.createFirstLabel}
      // A drawer with nothing in it has no folders either, so the
      // first document is always filed at the root.
      onCreate={(name) => onCreate(name, null)}
    />
  );
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
          {offer === undefined ? (
            <div className="mt-5 max-w-md">{createForm}</div>
          ) : (
            /*
              THE DOUBLE-ENTRY FORK (UI-REVIEW 2026-08-27 P1-A).
              An empty log book has exactly two ways to gain an entry: write one
              in, or paste one in. So they are ruled as two columns of one
              ledger, at the same y, divided by the same hairline every other
              rule on this page is drawn in — not two cards, which would be a
              web page's answer to a question this drawer already knows how to
              ask. The ruled remainder below is the drawer's ground; the fork
              sits on it, so the register still reads as a log book and not as a
              form floating in a void.

              Below `sm` the rule turns horizontal and the arms stack: two
              columns of a control each cannot be read at 640 px, and a fork you
              cannot read is not a fork.
            */
            <div
              className="mt-6 grid max-w-3xl grid-cols-1 divide-y divide-hairline sm:grid-cols-2 sm:divide-x sm:divide-y-0"
              data-testid={`${idPlural}-empty-fork`}
            >
              <div className="min-w-0 pb-6 sm:pb-0 sm:pr-8">
                <ForkLabel>Start from scratch</ForkLabel>
                <div className="mt-3">{createForm}</div>
              </div>
              <div className="min-w-0 pt-6 sm:pl-8 sm:pt-0">
                <ForkLabel>{offer.label}</ForkLabel>
                <div className="mt-3">{offer.render("fork")}</div>
              </div>
            </div>
          )}
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
            {KEY_NEW_DOCUMENT.toUpperCase()}
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
