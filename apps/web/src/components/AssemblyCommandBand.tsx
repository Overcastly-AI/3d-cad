/**
 * The assembly command band — the full-width surface under the brand bar (the
 * sibling of the part editor's CreateStrip). History leads (the same shared
 * group, same position as the part band — muscle memory transfers), then one
 * Component action (add a part instance) and the v1 mate tools, icon-forward
 * and keyboard-hinted. A mate tool is a TOGGLE (the brass scribe marks the
 * armed one) and stays honestly disabled until two instances exist — you
 * cannot mate one part to itself. Chrome recedes; the viewport is the hero.
 */
import {
  AddIcon,
  AngleIcon,
  CoincidentIcon,
  ConcentricIcon,
  DistanceIcon,
  DuplicateIcon,
  FixedIcon,
  Flyout,
  formatChord,
  JointIcon,
  MeasureIcon,
  MoreIcon,
  MoveIcon,
  ToolButton,
  ToolGroup,
} from "@loft/design";
import type { ReactNode } from "react";

import type { ExportedFile, ExportFormat } from "../api/exportPart";
import type { AssemblyExportGate } from "../features/assemblyExport";
import type { MateTool } from "../assembly/mateStore";
import { CHORD_COPY_INSTANCE } from "../shortcuts/registry";
import type { HistoryStep } from "../lib/undoRedoShortcut";
import { ExportToolGroup } from "./ExportToolGroup";
import { HistoryGroup } from "./HistoryGroup";

export interface AssemblyCommandBandProps {
  /** The graph has loaded (History stays disabled until it has). */
  historyReady: boolean;
  /** An earlier graph snapshot exists (the graph GET's `can_undo`, UR3). */
  canUndo: boolean;
  /** A later graph snapshot exists (`can_redo` — the mirror gate). */
  canRedo: boolean;
  /** The history step in flight (drives the honest hold caption), or null. */
  historyHold: HistoryStep | null;
  /** A graph mutation is in flight — History holds with this caption. */
  historyHoldReason?: string | null;
  /** The workspace state that owns Ctrl+Z (armed mate tool / open picker). */
  historyLockReason?: string;
  /** Undo one assembly edit (Ctrl/⌘+Z). */
  onUndo: () => void;
  /** Redo one assembly edit (Ctrl/⌘+Shift+Z, Ctrl+Y). */
  onRedo: () => void;
  canAddPart: boolean;
  onAddPart: () => void;
  /** A Move session is open (the button reads armed; a press ends it). */
  moveActive: boolean;
  /** Why Move is unavailable (nothing selected / grounded), or null. */
  moveBlocker: string | null;
  onMove: () => void;
  /**
   * Why Copy is unavailable (nothing selected / a write in flight), or null.
   * A grounded component CAN be copied: the copy is never grounded.
   */
  copyBlocker: string | null;
  /** Copy the selected component, then open Move on the copy (Ctrl+D). */
  onCopy: () => void;
  /** A mate needs two instances; the tools stay disabled until then. */
  canMate: boolean;
  activeTool: MateTool | null;
  onToggleTool: (tool: MateTool) => void;
  /** Interference needs two parts; the check stays disabled until then. */
  canCheckInterference: boolean;
  /** A check is in flight (the tool holds with a "Scanning…" caption). */
  interferenceBusy: boolean;
  onCheckInterference: () => void;
  /**
   * Write the solved assembly as one file. Omit it and the EXPORT group is not
   * rendered at all.
   *
   * The assembly repeated the part workspace's defect at a second address: its
   * `ExportRow` sat inside the Inspect panel, under a Solve / Parts / Clash
   * segmented control, so the only way to a file went away with the panel
   * (EXPORT-1). The strip stays; this is the copy that survives a collapse.
   */
  exporter?: (format: ExportFormat) => Promise<ExportedFile>;
  /** Why export is inert (no assembly / no body), or undefined when ready. */
  exportDisabledReason?: string;
  /**
   * The solve did not honour every mate (QA 2026-10-10): the cells say the file
   * would be partial and a click asks once before writing.
   */
  exportGate?: AssemblyExportGate;
}

/** The relation mates under More, in their band order and with their keys. */
const LEGACY_MATES: readonly {
  tool: Exclude<MateTool, "joint">;
  label: string;
  shortcut: string;
  icon: ReactNode;
}[] = [
  {
    tool: "coincident",
    label: "Coincident",
    shortcut: "F",
    icon: <CoincidentIcon />,
  },
  {
    tool: "concentric",
    label: "Concentric",
    shortcut: "N",
    icon: <ConcentricIcon />,
  },
  {
    tool: "distance",
    label: "Distance",
    shortcut: "D",
    icon: <DistanceIcon />,
  },
  { tool: "angle", label: "Angle", shortcut: "G", icon: <AngleIcon /> },
  { tool: "lock", label: "Lock", shortcut: "K", icon: <FixedIcon /> },
];

export function AssemblyCommandBand({
  historyReady,
  canUndo,
  canRedo,
  historyHold,
  historyHoldReason = null,
  historyLockReason,
  onUndo,
  onRedo,
  canAddPart,
  onAddPart,
  moveActive,
  moveBlocker,
  onMove,
  copyBlocker,
  onCopy,
  canMate,
  activeTool,
  onToggleTool,
  canCheckInterference,
  interferenceBusy,
  onCheckInterference,
  exporter,
  exportDisabledReason,
  exportGate,
}: AssemblyCommandBandProps) {
  const mateReason = canMate ? undefined : "Add two parts first";
  return (
    <div className="flex items-stretch divide-x divide-hairline">
      <HistoryGroup
        ready={historyReady}
        canUndo={canUndo}
        canRedo={canRedo}
        hold={historyHold}
        holdReason={historyHoldReason}
        lockReason={historyLockReason}
        onUndo={onUndo}
        onRedo={onRedo}
      />
      <ToolGroup eyebrow="Component">
        <ToolButton
          icon={<AddIcon />}
          label="Add part"
          showLabel
          disabled={!canAddPart}
          data-testid="add-instance"
          onClick={onAddPart}
        />
        <ToolButton
          icon={<MoveIcon />}
          label="Move"
          showLabel
          shortcut="M"
          active={moveActive}
          disabled={!moveActive && moveBlocker !== null}
          caption={moveActive ? undefined : (moveBlocker ?? undefined)}
          data-testid="move-instance"
          onClick={onMove}
        />
        <ToolButton
          icon={<DuplicateIcon />}
          label="Copy"
          showLabel
          shortcut={formatChord(CHORD_COPY_INSTANCE)}
          disabled={copyBlocker !== null}
          caption={copyBlocker ?? undefined}
          data-testid="copy-instance"
          onClick={onCopy}
        />
      </ToolGroup>
      {/* Joint leads, as in Fusion's Assemble panel: one command that brings
          two origins together and names the motion left free. The five
          relation mates stay a keystroke away under More, shortcuts intact. */}
      <ToolGroup eyebrow="Mate">
        <ToolButton
          icon={<JointIcon />}
          label="Joint"
          showLabel
          shortcut="J"
          active={activeTool === "joint"}
          disabled={!canMate}
          caption={mateReason}
          data-testid="mate-joint"
          onClick={() => onToggleTool("joint")}
        />
        <Flyout
          label="More"
          icon={<MoreIcon />}
          eyebrow="Mates"
          active={activeTool !== null && activeTool !== "joint"}
          data-testid="mate-more"
          items={LEGACY_MATES.map((mate) => ({
            key: mate.tool,
            icon: mate.icon,
            label: mate.label,
            shortcut: mate.shortcut,
            disabled: !canMate,
            "data-testid": `mate-${mate.tool}`,
            onSelect: () => onToggleTool(mate.tool),
          }))}
        />
      </ToolGroup>
      <ToolGroup eyebrow="Inspect">
        <ToolButton
          icon={<MeasureIcon />}
          label="Check interference"
          showLabel
          shortcut="I"
          disabled={!canCheckInterference}
          aria-busy={interferenceBusy}
          caption={
            interferenceBusy
              ? "Scanning…"
              : canCheckInterference
                ? undefined
                : "Add two parts first"
          }
          data-testid="check-interference"
          onClick={onCheckInterference}
        />
      </ToolGroup>
      {/* The deliverable closes the band — same position, same primitive and
          same eyebrow as the part and drawing workspaces, so the verb is in one
          place across all three (EXPORT-1). */}
      {exporter !== undefined ? (
        <ExportToolGroup
          testIdPrefix="assembly-export-band"
          // Export outranks the verb groups here for the same reason it does
          // on the part band: "STEP" is an identifier no glyph can spell,
          // while a mate glyph IS the vocabulary this workspace teaches. The
          // other groups stay at the default and shed together — this band
          // still fits its labels, so ranking them further would be guessing.
          labelPriority={40}
          exporter={exporter}
          disabledReason={exportDisabledReason}
          partial={exportGate?.partial ?? false}
          partialQualifier={exportGate?.qualifier ?? undefined}
          confirmReason={exportGate?.confirmReason ?? null}
          state={exportGate?.state}
        />
      ) : null}
    </div>
  );
}
