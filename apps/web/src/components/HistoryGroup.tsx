/**
 * The History tool group — undo/redo, identical in BOTH command bands (part +
 * assembly) so muscle memory transfers between workspaces. One rendering, two
 * consumers (the DRY rule applied to chrome): icon-only at every width (Fusion
 * ships undo/redo unlabeled; the two most self-evident glyphs in software),
 * platform-aware chord chips, and honest aria-disabled gating from the
 * server's `can_undo`/`can_redo` — the buttons are wired state, never
 * decoration. The document-specific truths (what write is holding the tools,
 * what workspace state owns Ctrl+Z right now) arrive as captions.
 */
import {
  formatChord,
  RedoIcon,
  ToolButton,
  ToolGroup,
  UndoIcon,
} from "@loft/design";

import type { HistoryStep } from "../lib/undoRedoShortcut";

export interface HistoryGroupProps {
  /** The document has loaded (buttons stay disabled until it has). */
  ready: boolean;
  /**
   * An earlier history snapshot exists to restore (the document GET's
   * `can_undo` — docs/design/undo-redo.md). At the ring's floor the button
   * disables with its honest reason, like every other gated tool.
   */
  canUndo: boolean;
  /** A later history snapshot exists to restore (`can_redo` — the mirror gate). */
  canRedo: boolean;
  /**
   * The history step currently in flight, or null. Both buttons disable while
   * one runs, and the tooltip names the TRUE verb (an idle Redo held by a
   * running undo says "Undoing…", never "Redoing…").
   */
  hold: HistoryStep | null;
  /**
   * A NON-history document write holding the tools (the part page's
   * rollback-bar move, an assembly mutation), named honestly, or null —
   * history and any other document rewrite mutually exclude under the OCC.
   */
  holdReason?: string | null;
  /**
   * The workspace state that owns the band right now (an open command, an
   * armed mate tool, an open picker), or undefined. While set, both buttons
   * lock with THIS reason — it outranks every gate caption.
   */
  lockReason?: string;
  /** Undo one document edit (Ctrl/⌘+Z). */
  onUndo?: () => void;
  /** Redo one document edit (Ctrl/⌘+Shift+Z, Ctrl+Y). */
  onRedo?: () => void;
}

export function HistoryGroup({
  ready,
  canUndo,
  canRedo,
  hold,
  holdReason = null,
  lockReason,
  onUndo,
  onRedo,
}: HistoryGroupProps) {
  const locked = lockReason !== undefined && lockReason !== "";
  const busy = hold !== null || (holdReason !== null && holdReason !== "");
  const undoReady = ready && canUndo && !busy && onUndo !== undefined;
  const redoReady = ready && canRedo && !busy && onRedo !== undefined;
  /** The one true reason both buttons are holding, or undefined. */
  const holdCaption =
    hold === "undo"
      ? "Undoing…"
      : hold === "redo"
        ? "Redoing…"
        : (holdReason ?? undefined);
  /** The tooltip's second line: the lock reason wins, else the gate reason. */
  const captionFor = (
    stepReady: boolean,
    reason: string,
  ): string | undefined =>
    locked ? lockReason : stepReady ? undefined : (holdCaption ?? reason);

  return (
    <ToolGroup eyebrow="History">
      <ToolButton
        icon={<UndoIcon />}
        label="Undo"
        shortcut={formatChord("Ctrl+Z")}
        data-testid="undo-button"
        aria-label="Undo"
        caption={captionFor(
          undoReady,
          canUndo ? "One moment…" : "Nothing to undo",
        )}
        disabled={locked || !undoReady}
        onClick={onUndo}
      />
      <ToolButton
        icon={<RedoIcon />}
        label="Redo"
        shortcut={formatChord("Ctrl+Shift+Z")}
        data-testid="redo-button"
        aria-label="Redo"
        caption={captionFor(
          redoReady,
          canRedo ? "One moment…" : "Nothing to redo",
        )}
        disabled={locked || !redoReady}
        onClick={onRedo}
      />
    </ToolGroup>
  );
}
