import { Button, formatChord, Kbd } from "@loft/design";
import { useCallback, useEffect, useRef, useState } from "react";

import type { PartVersion } from "../api/versions";
import { relativeAge } from "../lib/activity";
import { formatDate } from "../lib/format";
import { useModalLayer } from "../lib/modalGate";
import { containFocus, isSaveChord } from "./dialogKeys";

export interface VersionsPanelProps {
  partName: string;
  /** The part's versions (any order; drawn newest first). Undefined = loading. */
  versions: readonly PartVersion[] | undefined;
  /** The list could not be loaded, in a sentence. */
  loadError: string | null;
  /** Which version is being restored, or null. */
  restoringSeq: number | null;
  /** Why the last restore failed, in a sentence; null when it did not. */
  restoreError: string | null;
  /**
   * When set, Restore is inert and says this (an open command owns the tree,
   * or another tree write is in flight).
   */
  restoreBlockedReason?: string;
  onRestore: (seq: number) => void;
  /** Open the Save version dialog over this panel. */
  onSaveVersion: () => void;
  onClose: () => void;
  /** The clock, for the relative times (tests pin it). */
  now?: number;
}

/** "3 min ago" for a recent version, its ISO date for an older one. */
export function versionAge(iso: string, now: number): string {
  const time = Date.parse(iso);
  if (Number.isNaN(time)) return "—";
  return relativeAge(Math.max(0, now - time)) ?? formatDate(iso);
}

/**
 * VERSIONS: the part's named versions, newest first, each restorable (Onshape
 * "Versions and history", Fusion's version list). A row reads its number, its
 * name, when, and who; Restore asks once, inline, and says the step can be
 * undone, because it can: a restore is ONE undoable edit.
 *
 * Modal through `lib/modalGate`: the panel holds the keyboard while it is
 * open, so Escape backs out of the confirm first and then closes the panel,
 * and the workspace's own shortcuts never fire behind it.
 */
export function VersionsPanel({
  partName,
  versions,
  loadError,
  restoringSeq,
  restoreError,
  restoreBlockedReason,
  onRestore,
  onSaveVersion,
  onClose,
  now = Date.now(),
}: VersionsPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const returnFocusTo = useRef<Element | null>(null);
  /** The row whose Restore is asking for confirmation. */
  const [confirming, setConfirming] = useState<number | null>(null);

  useEffect(() => {
    returnFocusTo.current = document.activeElement;
    panelRef.current?.focus();
    return () => {
      const target = returnFocusTo.current;
      if (target instanceof HTMLElement && target.isConnected) target.focus();
    };
  }, []);

  // The confirm's own Restore takes focus, so Enter confirms and Escape backs
  // out; backing out returns focus to the row's Restore.
  useEffect(() => {
    const panel = panelRef.current;
    if (panel === null) return;
    const selector =
      confirming === null
        ? null
        : `[data-testid="version-restore-confirm"][data-seq="${confirming}"]`;
    if (selector !== null) {
      panel.querySelector<HTMLElement>(selector)?.focus();
    }
  }, [confirming]);

  const cancelConfirm = useCallback(() => {
    const seq = confirming;
    setConfirming(null);
    if (seq === null) return;
    requestAnimationFrame(() => {
      panelRef.current
        ?.querySelector<HTMLElement>(
          `[data-testid="version-restore"][data-seq="${seq}"]`,
        )
        ?.focus();
    });
  }, [confirming]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent, insidePanel: boolean) => {
      if (event.key === "Escape") {
        event.preventDefault();
        if (confirming !== null) cancelConfirm();
        else onClose();
        return;
      }
      // The workspace's Ctrl+S is shielded while this is open; it means the
      // same thing here.
      if (isSaveChord(event)) {
        event.preventDefault();
        if (restoringSeq === null) onSaveVersion();
        return;
      }
      containFocus(panelRef.current, event, insidePanel);
    },
    [confirming, cancelConfirm, onClose, onSaveVersion, restoringSeq],
  );
  useModalLayer("versions", panelRef, onKeyDown);

  const rows =
    versions === undefined
      ? undefined
      : [...versions].sort((a, b) => b.seq - a.seq);
  const busy = restoringSeq !== null;
  const undoChord = formatChord("Ctrl+Z");

  return (
    <div
      data-testid="versions-backdrop"
      onClick={onClose}
      className="fixed inset-0 z-menu flex items-start justify-center overflow-y-auto bg-carbide/85 p-4 sm:pt-[12vh]"
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="versions-title"
        tabIndex={-1}
        data-testid="versions-panel"
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-xl border border-etch bg-anvil text-mist shadow-float outline-none"
      >
        <header className="flex items-center gap-x-4 border-b border-hairline bg-carbide px-4 py-2.5">
          <h2
            id="versions-title"
            className="font-display text-2xs uppercase tracking-[0.2em] text-gauge"
          >
            Versions
          </h2>
          <span className="min-w-0 truncate font-data text-xs text-brass">
            {partName}
          </span>
          <span className="grow" />
          <Button
            variant="solid"
            onClick={onSaveVersion}
            disabled={busy}
            data-testid="versions-save"
          >
            Save version…
          </Button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close versions"
            data-testid="versions-close"
            className="inline-flex min-h-target-dense items-center gap-2 rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none transition-colors duration-fast hover:text-brass focus-visible:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
          >
            Close
            <Kbd aria-hidden="true">Esc</Kbd>
          </button>
        </header>

        {restoreBlockedReason !== undefined ? (
          <p
            className="border-b border-hairline px-4 py-2 font-body text-xs text-gauge"
            data-testid="versions-blocked"
          >
            {restoreBlockedReason}
          </p>
        ) : null}

        {loadError !== null ? (
          <p
            role="alert"
            data-testid="versions-load-error"
            className="m-4 border border-flag px-3 py-2 font-body text-xs text-flag"
          >
            {loadError}
          </p>
        ) : rows === undefined ? (
          <p
            className="px-4 py-4 font-body text-xs text-gauge"
            data-testid="versions-loading"
          >
            Loading versions…
          </p>
        ) : rows.length === 0 ? (
          <p
            className="px-4 py-4 font-body text-sm text-gauge"
            data-testid="versions-empty"
          >
            No versions yet. Save one to keep the tree as it is now; you can
            come back to it at any time.
          </p>
        ) : (
          <ol
            aria-label="Saved versions, newest first"
            className="max-h-[56vh] overflow-y-auto"
          >
            {rows.map((version) => (
              <VersionRow
                key={version.seq}
                version={version}
                age={versionAge(version.created_at, now)}
                confirming={confirming === version.seq}
                restoring={restoringSeq === version.seq}
                disabled={busy || restoreBlockedReason !== undefined}
                undoChord={undoChord}
                onAsk={() => setConfirming(version.seq)}
                onCancel={cancelConfirm}
                onConfirm={() => onRestore(version.seq)}
              />
            ))}
          </ol>
        )}

        {restoreError !== null ? (
          <p
            role="alert"
            data-testid="versions-restore-error"
            className="mx-4 mb-3 mt-1 border border-flag px-3 py-2 font-body text-xs text-flag"
          >
            {restoreError}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function VersionRow({
  version,
  age,
  confirming,
  restoring,
  disabled,
  undoChord,
  onAsk,
  onCancel,
  onConfirm,
}: {
  version: PartVersion;
  age: string;
  confirming: boolean;
  restoring: boolean;
  disabled: boolean;
  undoChord: string;
  onAsk: () => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const label = `V${version.seq}`;
  return (
    <li
      data-testid="version-row"
      data-seq={version.seq}
      className="border-b border-hairline px-4 py-2.5 last:border-b-0"
    >
      <div className="flex items-baseline gap-3">
        <span
          className="w-10 shrink-0 font-data text-xs text-brass"
          data-testid="version-seq"
        >
          {label}
        </span>
        <div className="min-w-0 grow">
          <div className="flex items-baseline gap-2">
            <span
              className="min-w-0 truncate font-body text-sm text-mist"
              data-testid="version-name"
              title={version.name}
            >
              {version.name}
            </span>
          </div>
          {version.message !== "" ? (
            <p
              className="mt-0.5 line-clamp-2 font-body text-xs text-gauge"
              data-testid="version-message"
            >
              {version.message}
            </p>
          ) : null}
          <p className="mt-0.5 font-data text-2xs text-gauge">
            <time
              dateTime={version.created_at}
              title={version.created_at}
              data-testid="version-age"
            >
              {age}
            </time>
            {version.author !== null ? (
              <>
                <span aria-hidden className="px-1.5 text-etch">
                  ·
                </span>
                <span data-testid="version-author">{version.author}</span>
              </>
            ) : null}
          </p>
        </div>
        {confirming ? null : (
          <Button
            onClick={onAsk}
            disabled={disabled}
            aria-label={`Restore ${label}, ${version.name}`}
            data-testid="version-restore"
            data-seq={version.seq}
            className="shrink-0"
          >
            {restoring ? "Restoring…" : "Restore"}
          </Button>
        )}
      </div>
      {confirming ? (
        <div
          role="group"
          aria-label={`Confirm restoring ${label}`}
          className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 border-l-2 border-brass pl-3"
          data-testid="version-confirm"
        >
          <p className="min-w-0 grow font-body text-xs text-mist">
            Replace the current tree with{" "}
            <span className="font-data text-brass">{label}</span>? Later
            versions are kept, and Undo (
            <Kbd aria-hidden="true">{undoChord}</Kbd>
            <span className="sr-only">{undoChord}</span>) brings the current
            tree back.
          </p>
          <Button onClick={onCancel} data-testid="version-restore-cancel">
            Cancel
          </Button>
          <Button
            variant="solid"
            onClick={onConfirm}
            disabled={restoring}
            aria-busy={restoring}
            data-testid="version-restore-confirm"
            data-seq={version.seq}
          >
            {restoring ? "Restoring…" : `Restore ${label}`}
          </Button>
        </div>
      ) : null}
    </li>
  );
}
