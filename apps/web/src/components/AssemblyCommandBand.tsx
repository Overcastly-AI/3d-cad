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
  FixedIcon,
  MeasureIcon,
  ToolButton,
  ToolGroup,
} from "@loft/design";

import type { MateTool } from "../assembly/mateStore";
import type { HistoryStep } from "../lib/undoRedoShortcut";
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
  /** A mate needs two instances; the tools stay disabled until then. */
  canMate: boolean;
  activeTool: MateTool | null;
  onToggleTool: (tool: MateTool) => void;
  /** Interference needs two parts; the check stays disabled until then. */
  canCheckInterference: boolean;
  /** A check is in flight (the tool holds with a "Scanning…" caption). */
  interferenceBusy: boolean;
  onCheckInterference: () => void;
}

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
  canMate,
  activeTool,
  onToggleTool,
  canCheckInterference,
  interferenceBusy,
  onCheckInterference,
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
      </ToolGroup>
      <ToolGroup eyebrow="Mate">
        <ToolButton
          icon={<CoincidentIcon />}
          label="Coincident"
          showLabel
          shortcut="F"
          active={activeTool === "coincident"}
          disabled={!canMate}
          caption={mateReason}
          data-testid="mate-coincident"
          onClick={() => onToggleTool("coincident")}
        />
        <ToolButton
          icon={<ConcentricIcon />}
          label="Concentric"
          showLabel
          shortcut="N"
          active={activeTool === "concentric"}
          disabled={!canMate}
          caption={mateReason}
          data-testid="mate-concentric"
          onClick={() => onToggleTool("concentric")}
        />
        <ToolButton
          icon={<DistanceIcon />}
          label="Distance"
          showLabel
          shortcut="D"
          active={activeTool === "distance"}
          disabled={!canMate}
          caption={mateReason}
          data-testid="mate-distance"
          onClick={() => onToggleTool("distance")}
        />
        <ToolButton
          icon={<AngleIcon />}
          label="Angle"
          showLabel
          shortcut="G"
          active={activeTool === "angle"}
          disabled={!canMate}
          caption={mateReason}
          data-testid="mate-angle"
          onClick={() => onToggleTool("angle")}
        />
        <ToolButton
          icon={<FixedIcon />}
          label="Lock"
          showLabel
          shortcut="K"
          active={activeTool === "lock"}
          disabled={!canMate}
          caption={mateReason}
          data-testid="mate-lock"
          onClick={() => onToggleTool("lock")}
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
    </div>
  );
}
