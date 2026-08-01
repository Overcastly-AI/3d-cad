import { Button, DividerTabIcon, TextField } from "@loft/design";
import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  type FolderMember,
  type FolderResponse,
  FolderNotEmptyError,
} from "../api/folders";
import { validatePartName } from "../lib/partName";
import type { RegisterCopy } from "./DocumentRegister";

/**
 * ONE DIVIDER in the drawer (#WS2) — a folder, drawn as the thing that divides
 * a log book rather than as a sidebar entry.
 *
 * FORM. Ruled at the filed rows' rhythm, on the same carbide gutter ground, but
 * the gutter carries a `DividerTabIcon` where a filed row carries its ordinal:
 * a folder has no position in the document sequence, and printing one would be
 * the ordinal-as-identity mistake at a second address. The name is set in the
 * tracked display face rather than the body face the documents use, so a glance
 * separates structure from content without a second colour or a second rule.
 *
 * WHAT IT MAY SAY. The counts are the SERVER'S (`document_count`,
 * `child_folder_count`) and both are DIRECT — this folder's own children, not
 * its subtree. The row says "6 parts" and its title says the rest, because a
 * count that silently included six sub-folders' worth would be the same
 * over-claim as a health badge derived from fetch state. Nothing here adds the
 * two numbers together and nothing derives either from the rows on screen (at
 * the root those rows are the UNFILED documents — a different set entirely).
 *
 * DELETE. Refused while the folder holds anything, with the contents NAMED from
 * the 409's typed payload — the same grammar and the same row-takeover the
 * document delete uses, so a user meets one refusal, not two. A folder delete
 * can never delete a document; the server will not do it and the copy says so.
 */

/** Same ink as the document row's verbs — one action vocabulary in the drawer. */
const ACTION_BUTTON =
  "inline-flex min-h-target-dense items-center rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] outline-none transition-colors duration-fast focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass";

export function RegisterFolderRow({
  idPlural,
  copy,
  folder,
  columns,
  onOpen,
  onRename,
  onDelete,
}: {
  idPlural: string;
  copy: RegisterCopy;
  folder: FolderResponse;
  /** Data cells between the name and FILED — the takeover span follows them. */
  columns: number;
  onOpen: () => void;
  onRename?: (folder: FolderResponse, name: string) => Promise<void>;
  onDelete?: (folder: FolderResponse) => Promise<void>;
}) {
  const [mode, setMode] = useState<"idle" | "rename" | "confirm">("idle");
  const [pending, setPending] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);
  /** What a refused delete named — rendered, never summarised. */
  const [blockedBy, setBlockedBy] = useState<FolderMember[] | null>(null);

  const remove = async () => {
    if (onDelete === undefined) return;
    setPending(true);
    setRowError(null);
    setBlockedBy(null);
    try {
      await onDelete(folder);
    } catch (caught) {
      setPending(false);
      if (caught instanceof FolderNotEmptyError) {
        setBlockedBy(caught.contents);
        return;
      }
      setRowError(
        caught instanceof Error
          ? caught.message
          : "The folder could not be deleted.",
      );
    }
  };

  if (mode === "confirm") {
    return (
      <tr
        data-testid={`${idPlural}-folder-row`}
        data-folder-id={folder.id}
        data-confirming="true"
        className="border-b border-hairline bg-carbide"
      >
        <FolderGutter addressed />
        <td colSpan={columns} className="px-3 py-2">
          {blockedBy === null ? (
            <span className="font-body text-sm text-mist">
              Delete the folder{" "}
              <span className="font-data text-flag">{folder.name}</span>? It is
              empty, so nothing else goes with it.
            </span>
          ) : (
            <BlockedByContents
              idPlural={idPlural}
              folder={folder}
              contents={blockedBy}
            />
          )}
          {rowError !== null ? (
            <span
              role="alert"
              className="ml-2 font-body text-xs text-flag"
              data-testid={`${idPlural}-folder-delete-error`}
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
              data-testid={`${idPlural}-folder-delete-cancel`}
            >
              {blockedBy === null ? "Cancel" : "Close"}
            </Button>
            {blockedBy === null ? (
              <Button
                variant="danger"
                onClick={() => void remove()}
                disabled={pending}
                data-testid={`${idPlural}-folder-delete-confirm`}
              >
                {pending ? "Deleting…" : "Delete folder"}
              </Button>
            ) : null}
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr
      data-testid={`${idPlural}-folder-row`}
      data-folder-id={folder.id}
      {...(mode === "rename" ? { "data-renaming": "true" } : {})}
      className="group border-b border-hairline hover:bg-carbide focus-within:bg-carbide"
    >
      <FolderGutter addressed={mode === "rename"} />
      <td className="truncate px-3 py-2 align-middle" colSpan={columns}>
        {mode === "rename" && onRename !== undefined ? (
          <RenameFolderField
            idPlural={idPlural}
            folder={folder}
            onCancel={() => setMode("idle")}
            onSubmit={async (name) => {
              await onRename(folder, name);
              setMode("idle");
            }}
          />
        ) : (
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <button
              type="button"
              onClick={onOpen}
              data-testid={`${idPlural}-folder-open`}
              className="inline-flex min-h-target-dense items-center rounded-sm font-display text-xs uppercase tracking-[0.14em] text-mist underline-offset-4 outline-none hover:text-brass hover:underline focus-visible:text-brass focus-visible:underline"
            >
              {folder.name}
            </button>
            <span
              className="font-data text-xs tabular-nums text-gauge"
              data-testid={`${idPlural}-folder-count`}
              // The counts are DIRECT; the title says so rather than letting a
              // reader assume the number covers the subtree.
              title="Directly in this folder — sub-folders are not counted"
            >
              {countLabel(folder, copy)}
            </span>
          </div>
        )}
      </td>
      <td className="hidden px-3 py-2 md:table-cell" />
      <td className="px-2 py-2 text-right align-middle">
        {mode === "rename" ? null : (
          <div className="flex items-center justify-end gap-1">
            {rowError !== null ? (
              <span
                role="alert"
                className="mr-1 font-body text-xs text-flag"
                data-testid={`${idPlural}-folder-action-error`}
              >
                {rowError}
              </span>
            ) : null}
            <button
              type="button"
              onClick={onOpen}
              data-testid={`${idPlural}-folder-open-verb`}
              aria-label={`Open the folder ${folder.name}`}
              className={`${ACTION_BUTTON} text-gauge hover:text-brass focus-visible:text-brass`}
            >
              Open
            </button>
            {onRename === undefined ? null : (
              <button
                type="button"
                onClick={() => {
                  setRowError(null);
                  setMode("rename");
                }}
                data-testid={`${idPlural}-folder-rename`}
                aria-label={`Rename the folder ${folder.name}`}
                className={`${ACTION_BUTTON} text-gauge hover:text-brass focus-visible:text-brass`}
              >
                Rename
              </button>
            )}
            {onDelete === undefined ? null : (
              <button
                type="button"
                onClick={() => {
                  setRowError(null);
                  setMode("confirm");
                }}
                data-testid={`${idPlural}-folder-delete`}
                aria-label={`Delete the folder ${folder.name}`}
                className={`${ACTION_BUTTON} text-gauge hover:text-flag focus-visible:text-flag`}
              >
                Delete
              </button>
            )}
          </div>
        )}
      </td>
    </tr>
  );
}

/**
 * "6 parts · 2 folders" — the server's two DIRECT counts, and only the ones
 * that are non-zero, so an empty folder reads "Empty" rather than "0 parts ·
 * 0 folders" (two readouts saying nothing, which is the chrome-that-measures-
 * nothing defect at small scale).
 */
function countLabel(folder: FolderResponse, copy: RegisterCopy): string {
  const parts: string[] = [];
  if (folder.document_count > 0) {
    parts.push(
      `${folder.document_count} ${
        folder.document_count === 1 ? copy.noun : copy.nounPlural
      }`,
    );
  }
  if (folder.child_folder_count > 0) {
    parts.push(
      `${folder.child_folder_count} ${
        folder.child_folder_count === 1 ? "folder" : "folders"
      }`,
    );
  }
  return parts.length === 0 ? "Empty" : parts.join(" · ");
}

/**
 * The refusal, with the contents NAMED (409 `folder_not_empty`).
 *
 * The same shape as the document delete's `BlockedByDependents`, deliberately:
 * the user's next action is the same kind of action (go and move those things),
 * so the message should not need re-learning. What it must not do is degrade to
 * "this folder is not empty" — that ends the conversation.
 */
function BlockedByContents({
  idPlural,
  folder,
  contents,
}: {
  idPlural: string;
  folder: FolderResponse;
  contents: FolderMember[];
}) {
  return (
    <div role="alert" data-testid={`${idPlural}-folder-blocked`}>
      <span className="font-body text-sm text-mist">
        <span className="font-data text-flag">{folder.name}</span> still holds{" "}
        {contents.length === 1 ? "one item" : `${contents.length} items`}. Move
        them out first — deleting a folder never deletes what is in it.
      </span>
      <ul className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
        {contents.map((member) => (
          <li key={member.id} className="flex items-baseline gap-1.5">
            <span
              className="font-data text-xs text-mist"
              data-testid={`${idPlural}-folder-content`}
              data-content-kind={member.kind}
            >
              {member.name}
            </span>
            <span className="font-display text-2xs uppercase tracking-[0.14em] text-gauge">
              {member.kind}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Rename in place — Enter commits, Escape abandons, exactly as a filed row. */
function RenameFolderField({
  idPlural,
  folder,
  onSubmit,
  onCancel,
}: {
  idPlural: string;
  folder: FolderResponse;
  onSubmit: (name: string) => Promise<void>;
  onCancel: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(folder.name);
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
    if (name.trim() === folder.name) {
      onCancel();
      return;
    }
    setPending(true);
    try {
      await onSubmit(name.trim());
    } catch (caught) {
      setPending(false);
      setFieldError(
        caught instanceof Error
          ? caught.message
          : "The folder could not be renamed.",
      );
    }
  };

  return (
    <form
      className="flex items-end gap-2"
      onSubmit={(event) => void submit(event)}
      noValidate
      data-testid={`${idPlural}-folder-rename-form`}
    >
      <TextField
        ref={inputRef}
        label={`New name for the folder ${folder.name}`}
        hideLabel
        value={name}
        error={fieldError}
        autoComplete="off"
        disabled={pending}
        data-testid={`${idPlural}-folder-rename-name`}
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
        data-testid={`${idPlural}-folder-rename-save`}
        className="shrink-0"
      >
        {pending ? "Saving…" : "Save"}
      </Button>
      <Button
        type="button"
        onClick={onCancel}
        disabled={pending}
        data-testid={`${idPlural}-folder-rename-cancel`}
        className="shrink-0"
      >
        Cancel
      </Button>
    </form>
  );
}

/**
 * The scribed margin, carrying the DIVIDER TAB instead of an ordinal — see the
 * component docstring for why a folder has no number. Same width, same ground,
 * same brass scribe on the addressed row, so the drawer's left edge stays one
 * straight rule.
 */
function FolderGutter({ addressed }: { addressed?: boolean }) {
  return (
    <td
      className={`h-10 border-l-2 bg-carbide px-3 py-2 text-right align-middle text-gauge ${
        addressed
          ? "border-brass"
          : "border-transparent group-hover:border-brass group-focus-within:border-brass"
      }`}
    >
      <DividerTabIcon size={14} className="ml-auto" />
    </td>
  );
}
