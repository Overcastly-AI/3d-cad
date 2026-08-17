import {
  Button,
  CloseIcon,
  type ContextMenuSection,
  DividerTabIcon,
  DuplicateIcon,
  OverflowMenu,
  RenameIcon,
  SelectField,
  Stamp,
  TextField,
  truncatedProps,
} from "@loft/design";
import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  type FolderResponse,
  folderPathLabel,
  UNFILED_LABEL,
} from "../api/folders";
import {
  DocumentHasDependentsError,
  type DocumentDependent,
} from "../api/parts";
import { registerHealthReadout } from "../features/partBuild";
import { documentActivity, relativeAge } from "../lib/activity";
import { formatDate } from "../lib/format";
import { validatePartName } from "../lib/partName";
import type {
  DocumentRegisterProps,
  RegisterCopy,
  RegisterDocument,
} from "./DocumentRegister";

/**
 * ONE FILED ROW, and the three verbs a drawer needs on its tenth document:
 * rename, duplicate, delete.
 *
 * Split out of `DocumentRegister` when the row grew states. The register frame
 * decides WHICH rows are shown (filter + sort); this file owns what one row can
 * do and — the part that matters — what it is allowed to SAY while doing it.
 *
 * The rule every state here obeys: **the row reports the server's answer, never
 * its own optimism.** Concretely:
 *
 *  - RENAME does not paint the typed name into the cell and move on. The write
 *    goes out under the document's optimistic-concurrency version, the register
 *    refetches, and the cell renders whatever the list came back with. A row
 *    that showed the new name while the server still held the old one is the
 *    "stale name after a rename" defect stated in the brief, arrived at from the
 *    other direction.
 *  - DUPLICATE does not guess the copy's name. The server assigns it ("Bracket
 *    copy", then "Bracket copy 2") and the new row appears with the name it
 *    actually got.
 *  - DELETE, refused because other documents reference this one, prints THOSE
 *    DOCUMENTS BY NAME from the 409's typed `dependents` payload. It does not
 *    say "in use" and it does not summarise a count: the user's next action is
 *    to go open those documents, so the refusal has to name them.
 *
 * FORM. Rename edits IN the name cell, leaving units, activity and rebuild
 * health on screen, because you rename a part while looking at which part it is.
 * Delete takes the row over, because a confirmation that shares a line with
 * other data is a confirmation people click through.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * THE VERBS MOVED INTO ONE MARK (REGISTER-1, 2026-08-17). They used to be four
 * words printed on every row, and that was defended here as discoverability. The
 * measurement retired the argument: at 1280 the four verbs held 256 px of 957
 * (27 %) against the NAME column's 173 px (18 %), so the widest column in a file
 * browser was row verbs at 1.5x the only column that tells two parts apart — and
 * NAME, starved, clipped mid-glyph. The verbs are now an `OverflowMenu` (the
 * shared `ContextMenu` card behind one punch-mark trigger), the column is 3.5 rem
 * — the gutter's width, so the drawer has two equal margins — and every pixel
 * freed went to NAME.
 *
 * What the old argument was right about is kept: the verbs are still reachable
 * by keyboard (one tab stop per row instead of four, then arrows), DELETE still
 * costs a confirmation, and nothing is hover-only — the trigger is always
 * rendered, not revealed on pointer.
 */

export interface DocumentRegisterRowProps<T extends RegisterDocument> {
  idSingular: string;
  copy: RegisterCopy;
  entry: T;
  ordinal: number;
  showUnits: boolean;
  showHealth: boolean;
  openLink: DocumentRegisterProps<T>["openLink"];
  onRename: (document: T, name: string) => Promise<void>;
  onDuplicate: (document: T) => Promise<void>;
  onDelete: (document: T) => Promise<void>;
  /** The drawer's whole folder tree — the move picker's options and the
   *  location label's names. Empty when the drawer has no folders. */
  folders?: readonly FolderResponse[];
  /** Print WHERE this document lives beside its name (only while filtering —
   *  see the call site: at rest the breadcrumb already says it). */
  showLocation?: boolean;
  /** File it, or un-file it with null. Absent = this drawer has no folders,
   *  and the MOVE verb is not offered rather than offered and inert. */
  onMove?: (document: T, folderId: string | null) => Promise<void>;
}

export function DocumentRegisterRow<T extends RegisterDocument>({
  idSingular,
  copy,
  entry,
  ordinal,
  showUnits,
  showHealth,
  openLink,
  onRename,
  onDuplicate,
  onDelete,
  folders = [],
  showLocation = false,
  onMove,
}: DocumentRegisterRowProps<T>) {
  const [mode, setMode] = useState<"idle" | "rename" | "confirm" | "move">(
    "idle",
  );
  const [pending, setPending] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);
  /** The referents a refused delete named — rendered, never summarised. */
  const [blockedBy, setBlockedBy] = useState<DocumentDependent[] | null>(null);

  const remove = async () => {
    setPending(true);
    setRowError(null);
    setBlockedBy(null);
    try {
      await onDelete(entry);
    } catch (caught) {
      setPending(false);
      if (caught instanceof DocumentHasDependentsError) {
        setBlockedBy(caught.dependents);
        return;
      }
      setRowError(caught instanceof Error ? caught.message : copy.deleteError);
    }
  };

  const duplicate = async () => {
    setPending(true);
    setRowError(null);
    try {
      await onDuplicate(entry);
      setPending(false);
    } catch (caught) {
      setPending(false);
      setRowError(
        caught instanceof Error ? caught.message : copy.duplicateError,
      );
    }
  };

  const filed = formatDate(entry.created_at);
  const activity = documentActivity(
    entry.created_at,
    entry.updated_at,
    formatDate(entry.updated_at),
  );
  /** Data cells between NAME and FILED — the takeover span has to follow them. */
  const dataSpan = 2 + (showUnits ? 1 : 0) + (showHealth ? 1 : 0);

  if (mode === "move" && onMove !== undefined) {
    return (
      <tr
        data-testid={`${idSingular}-row`}
        {...{ [`data-${idSingular}-id`]: entry.id }}
        data-moving="true"
        className="border-b border-hairline last:border-b-0 bg-carbide"
      >
        <Gutter ordinal={ordinal} idSingular={idSingular} addressed />
        <td colSpan={dataSpan + 2} className="px-3 py-2">
          <MoveField
            idSingular={idSingular}
            entry={entry}
            folders={folders}
            onCancel={() => setMode("idle")}
            onSubmit={async (folderId) => {
              await onMove(entry, folderId);
              setMode("idle");
            }}
          />
        </td>
      </tr>
    );
  }

  if (mode === "confirm") {
    return (
      <tr
        data-testid={`${idSingular}-row`}
        {...{ [`data-${idSingular}-id`]: entry.id }}
        data-confirming="true"
        className="border-b border-hairline last:border-b-0 bg-carbide"
      >
        <Gutter ordinal={ordinal} idSingular={idSingular} addressed />
        <td colSpan={dataSpan} className="px-3 py-2">
          {blockedBy === null ? (
            <span className="font-body text-sm text-mist">
              Delete <span className="font-data text-flag">{entry.name}</span>?
              This cannot be undone.
            </span>
          ) : (
            <BlockedByDependents
              idSingular={idSingular}
              name={entry.name}
              dependents={blockedBy}
            />
          )}
          {rowError !== null ? (
            <span
              role="alert"
              className="ml-2 font-body text-xs text-flag"
              data-testid={`${idSingular}-delete-error`}
            >
              {rowError}
            </span>
          ) : null}
        </td>
        <td className="px-3 py-2" colSpan={2}>
          <div className="flex items-center justify-end gap-2">
            <Button
              onClick={() => {
                setMode("idle");
                setBlockedBy(null);
                setRowError(null);
              }}
              disabled={pending}
              data-testid={`${idSingular}-delete-cancel`}
            >
              {blockedBy === null ? "Cancel" : "Close"}
            </Button>
            {blockedBy === null ? (
              <Button
                variant="danger"
                onClick={() => void remove()}
                disabled={pending}
                data-testid={`${idSingular}-delete-confirm`}
              >
                {pending ? "Deleting…" : "Delete"}
              </Button>
            ) : null}
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr
      data-testid={`${idSingular}-row`}
      {...{ [`data-${idSingular}-id`]: entry.id }}
      {...(mode === "rename" ? { "data-renaming": "true" } : {})}
      className="group border-b border-hairline last:border-b-0 hover:bg-carbide focus-within:bg-carbide"
    >
      <Gutter
        ordinal={ordinal}
        idSingular={idSingular}
        addressed={mode === "rename"}
      />
      <td className="truncate px-3 py-2 align-middle">
        {mode === "rename" ? (
          <RenameField
            idSingular={idSingular}
            entry={entry}
            copy={copy}
            onCancel={() => setMode("idle")}
            onSubmit={async (name) => {
              await onRename(entry, name);
              setMode("idle");
            }}
          />
        ) : (
          <span className="flex min-w-0 items-baseline gap-x-2">
            {openLink(entry, {
              // TRUNCATION IS THE PRIMITIVE'S JOB (`truncatedProps`): it carries
              // the ellipsis, the `title` with the full name, and the 24 px tap
              // target the old `inline-flex` was reaching for — and that
              // inline-flex was exactly why the name clipped raw instead of
              // ellipsising (UI-REVIEW P1-2).
              ...truncatedProps(
                entry.name,
                "rounded-sm font-body text-md text-mist underline-offset-4 outline-none hover:text-brass hover:underline focus-visible:text-brass focus-visible:underline",
              ),
              "data-testid": `${idSingular}-open`,
            })}
            {showLocation ? (
              <span
                className="shrink-0 font-display text-2xs uppercase tracking-[0.14em] text-gauge"
                data-testid={`${idSingular}-location`}
                title="Where this document is filed"
              >
                {folderPathLabel(folders, entry.folder_id ?? null)}
              </span>
            ) : null}
          </span>
        )}
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
      <td className="px-2 py-2 text-right align-middle">
        {mode === "rename" ? null : (
          <div className="flex items-center justify-end gap-1">
            {rowError !== null ? (
              <span
                role="alert"
                className="mr-1 font-body text-xs text-flag"
                data-testid={`${idSingular}-action-error`}
              >
                {rowError}
              </span>
            ) : null}
            <OverflowMenu
              label={`Actions for ${entry.name}`}
              data-testid={`${idSingular}-actions`}
              sections={rowVerbs({
                idSingular,
                entry,
                pending,
                canMove: onMove !== undefined,
                onRename: () => {
                  setRowError(null);
                  setMode("rename");
                },
                onDuplicate: () => void duplicate(),
                onMove: () => {
                  setRowError(null);
                  setMode("move");
                },
                onDelete: () => {
                  setRowError(null);
                  setMode("confirm");
                },
              })}
            />
          </div>
        )}
      </td>
    </tr>
  );
}

/**
 * WHAT ONE ROW CAN DO, as menu sections.
 *
 * Two sections, and the split is the point: the three verbs that change a
 * document sit together, DELETE sits alone below the rule in the flag ink. The
 * old row printed all four at identical weight, which is how a destructive verb
 * ends up looking like a fourth way to file something.
 *
 * The `data-testid`s are the ones the row has always carried (`part-rename`,
 * `part-duplicate`, `part-move`, `part-delete`), so the suites that drive them
 * only have to open the menu first — the verbs did not change, their address on
 * screen did.
 */
function rowVerbs<T extends RegisterDocument>({
  idSingular,
  entry,
  pending,
  canMove,
  onRename,
  onDuplicate,
  onMove,
  onDelete,
}: {
  idSingular: string;
  entry: T;
  pending: boolean;
  canMove: boolean;
  onRename: () => void;
  onDuplicate: () => void;
  onMove: () => void;
  onDelete: () => void;
}): ContextMenuSection[] {
  return [
    {
      key: "edit",
      items: [
        {
          key: "rename",
          label: "Rename",
          icon: <RenameIcon />,
          onSelect: onRename,
          "data-testid": `${idSingular}-rename`,
          "aria-label": `Rename ${entry.name}`,
        },
        {
          key: "duplicate",
          label: pending ? "Copying…" : "Duplicate",
          icon: <DuplicateIcon />,
          disabled: pending,
          disabledReason: pending ? "A copy is already being made" : undefined,
          onSelect: onDuplicate,
          "data-testid": `${idSingular}-duplicate`,
          "aria-label": `Duplicate ${entry.name}`,
        },
        // Absent, not inert, when the drawer has no folders — the same rule the
        // row verb followed: a register cannot offer a filing gesture it has
        // nowhere to file into.
        ...(canMove
          ? [
              {
                key: "move",
                label: "Move to folder",
                icon: <DividerTabIcon />,
                onSelect: onMove,
                "data-testid": `${idSingular}-move`,
                "aria-label": `Move ${entry.name} to a folder`,
              },
            ]
          : []),
      ],
    },
    {
      key: "destroy",
      items: [
        {
          key: "delete",
          label: "Delete",
          icon: <CloseIcon />,
          danger: true,
          onSelect: onDelete,
          "data-testid": `${idSingular}-delete`,
          "aria-label": `Delete ${entry.name}`,
        },
      ],
    },
  ];
}

/**
 * The refusal, with the referents NAMED (409 `*_has_dependents`).
 *
 * This repo already refuses to delete a feature that another feature references
 * and lists them; the cross-document case is the same convention one level up,
 * so it reads the same way rather than inventing a second one. What it must not
 * do is degrade to "this part is in use" — the user's next action is to open
 * those documents and re-point or remove the reference, and a message that
 * withholds their names makes that a search.
 */
function BlockedByDependents({
  idSingular,
  name,
  dependents,
}: {
  idSingular: string;
  name: string;
  dependents: DocumentDependent[];
}) {
  return (
    <div role="alert" data-testid={`${idSingular}-blocked`}>
      <span className="font-body text-sm text-mist">
        <span className="font-data text-flag">{name}</span> is still used by{" "}
        {dependents.length === 1
          ? "one document"
          : `${dependents.length} documents`}
        . Remove the reference there first.
      </span>
      <ul className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
        {dependents.map((dependent) => (
          <li key={dependent.id} className="flex items-baseline gap-1.5">
            <span
              className="font-data text-xs text-mist"
              data-testid={`${idSingular}-dependent`}
              data-dependent-kind={dependent.kind}
            >
              {dependent.name}
            </span>
            <span className="font-display text-2xs uppercase tracking-[0.14em] text-gauge">
              {dependent.kind}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * MOVE — the keyboard-first filing gesture (#WS2).
 *
 * A SELECT of every folder in the drawer by full path, plus "Unfiled", rather
 * than a drag target. Dragging is a fine second way to file, but a move
 * reachable only by pointer would put the product's one rearrangement out of
 * reach of a keyboard, in an app whose own design docs call it keyboard-first —
 * so the select is the primary path and it is complete on its own.
 *
 * The takeover spans the row for the same reason DELETE does: filing is a
 * decision, and a control that shares a line with five other cells is a control
 * people operate by accident. The current folder is preselected and Save is
 * inert until it changes, so the common miss (opening it and pressing Enter)
 * costs nothing.
 *
 * On success the register REFETCHES and the row re-renders from the list the
 * server sent; nothing here paints the destination optimistically. A move that
 * reported success while the document was still in the old place is the exact
 * defect this row is being held to.
 */
function MoveField<T extends RegisterDocument>({
  idSingular,
  entry,
  folders,
  onSubmit,
  onCancel,
}: {
  idSingular: string;
  entry: T;
  folders: readonly FolderResponse[];
  onSubmit: (folderId: string | null) => Promise<void>;
  onCancel: () => void;
}) {
  /** "" is Unfiled — a select's value is a string, and null is not one. */
  const current = entry.folder_id ?? "";
  const [choice, setChoice] = useState(current);
  const [pending, setPending] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const selectRef = useRef<HTMLSelectElement>(null);

  useEffect(() => selectRef.current?.focus(), []);

  const options = [
    { value: "", label: UNFILED_LABEL },
    // Sorted by the path a human reads, so a nested folder sits under its
    // parent rather than wherever the server's name order happened to put it.
    ...[...folders]
      .map((folder) => ({
        value: folder.id,
        label: folderPathLabel(folders, folder.id),
      }))
      .sort((a, b) => a.label.localeCompare(b.label)),
  ];

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (choice === current) {
      onCancel();
      return;
    }
    setPending(true);
    try {
      await onSubmit(choice === "" ? null : choice);
    } catch (caught) {
      setPending(false);
      setFieldError(
        caught instanceof Error
          ? caught.message
          : "The document could not be moved.",
      );
    }
  };

  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(event) => void submit(event)}
      noValidate
      data-testid={`${idSingular}-move-form`}
    >
      <span className="mb-1 font-body text-sm text-mist">
        File <span className="font-data">{entry.name}</span> in
      </span>
      <SelectField
        ref={selectRef}
        label="Folder"
        hideLabel
        value={choice}
        options={options}
        error={fieldError}
        disabled={pending}
        data-testid={`${idSingular}-move-folder`}
        className="min-w-[12rem]"
        onChange={(event) => {
          setChoice(event.currentTarget.value);
          if (fieldError !== null) setFieldError(null);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onCancel();
          }
        }}
      />
      <Button
        type="submit"
        variant="solid"
        disabled={pending || choice === current}
        data-testid={`${idSingular}-move-save`}
        className="shrink-0"
      >
        {pending ? "Moving…" : "Move"}
      </Button>
      <Button
        type="button"
        onClick={onCancel}
        disabled={pending}
        data-testid={`${idSingular}-move-cancel`}
        className="shrink-0"
      >
        Cancel
      </Button>
    </form>
  );
}

/**
 * Rename in the name cell. Enter commits, Escape reverts — the two keys a
 * modeler already uses everywhere else in this product — and the field opens
 * with the current name selected, so the common case (retype it) is one action.
 *
 * The commit is a real write under the document's concurrency version, so a
 * name typed against a row someone else moved is REFUSED rather than silently
 * winning; that message lands under the field where the typing happened.
 */
function RenameField<T extends RegisterDocument>({
  idSingular,
  entry,
  copy,
  onSubmit,
  onCancel,
}: {
  idSingular: string;
  entry: T;
  copy: RegisterCopy;
  onSubmit: (name: string) => Promise<void>;
  onCancel: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(entry.name);
  const [pending, setPending] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const invalid = validatePartName(name);
    if (invalid !== null) {
      setFieldError(invalid);
      return;
    }
    if (name.trim() === entry.name) {
      // Nothing changed — don't spend a version bump saying so.
      onCancel();
      return;
    }
    setPending(true);
    try {
      await onSubmit(name.trim());
    } catch (caught) {
      setPending(false);
      setFieldError(
        caught instanceof Error ? caught.message : copy.renameError,
      );
    }
  };

  return (
    <form
      className="flex items-end gap-2"
      onSubmit={(event) => void submit(event)}
      noValidate
      data-testid={`${idSingular}-rename-form`}
    >
      <TextField
        ref={inputRef}
        label={`New name for ${entry.name}`}
        hideLabel
        value={name}
        error={fieldError}
        autoComplete="off"
        disabled={pending}
        data-testid={`${idSingular}-rename-name`}
        className="grow"
        onChange={(event) => {
          setName(event.currentTarget.value);
          if (fieldError !== null) setFieldError(null);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onCancel();
          }
        }}
      />
      <Button
        type="submit"
        variant="solid"
        disabled={pending}
        data-testid={`${idSingular}-rename-save`}
        className="shrink-0"
      >
        {pending ? "Saving…" : "Save"}
      </Button>
      <Button
        type="button"
        onClick={onCancel}
        disabled={pending}
        data-testid={`${idSingular}-rename-cancel`}
        className="shrink-0"
      >
        Cancel
      </Button>
    </form>
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
 * The cell is a RENDERER, not a decider: what it is entitled to say comes from
 * `registerHealthReadout` (`features/partBuild.ts`), the same module the open
 * part's STATUS/EXPORT cells read. A second place deciding register wording is
 * how two surfaces end up disagreeing about the same part (audit J2/J3).
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
 *
 * ...and, crossing all four, the SCOPE axis: an `ok` that covers only the
 * features before a travel stop is not "Clean", it is "Clean to stop" in the
 * same indeterminate ink, because the rest of the tree was never attempted.
 * `data-health` stays the STATE and `data-health-scope` carries the second
 * axis, so a QA hook reads the pair exactly as the wire sends it.
 */
function HealthCell<T extends RegisterDocument>({
  idSingular,
  entry,
}: {
  idSingular: string;
  entry: T;
}) {
  const readout = registerHealthReadout({
    state: entry.eval_state,
    scope: entry.eval_scope ?? null,
    lastStatus: entry.last_eval_status,
    age: rebuildAge(entry.last_eval_at),
  });
  const hooks = {
    "data-testid": `${idSingular}-health`,
    "data-health": readout.state,
    ...(readout.scope !== null && readout.scope !== undefined
      ? { "data-health-scope": readout.scope }
      : {}),
    title: readout.title,
  };
  const sr =
    readout.srSuffix === null ? null : (
      <span className="sr-only">{readout.srSuffix}</span>
    );

  if (readout.state === "never") {
    return (
      <span {...hooks} className="font-data text-xs text-gauge">
        <span aria-hidden>—</span>
        <span className="sr-only">{readout.label}</span>
      </span>
    );
  }

  if (readout.tone === "quiet") {
    return (
      <span
        {...hooks}
        className="font-display text-2xs uppercase tracking-[0.14em] text-gauge"
      >
        {readout.label}
        {sr}
      </span>
    );
  }

  return readout.tone === "flag" ? (
    <Stamp tone="flag" {...hooks}>
      {readout.label}
      {sr}
    </Stamp>
  ) : (
    <Stamp indeterminate {...hooks}>
      {readout.label}
      {sr}
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
 * "Row", and unpadded, because the padding was most of the lie. Sorting and
 * filtering make the point again from the other side: the ordinal counts the
 * rows AS SHOWN, so it renumbers when the register is re-ordered, which is
 * exactly what a position does and exactly what an identity must not.
 *
 * A REAL sheet number is a stored per-owner monotonic sequence on the document
 * row, i.e. a documents-service change, and it is filed as its own item rather
 * than faked here. The gutter's form (carbide ground, brass scribe,
 * right-aligned tabular data face) is unchanged — only what it asserts.
 */
export function Gutter({
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
