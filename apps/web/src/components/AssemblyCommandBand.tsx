/**
 * The assembly command band — the full-width surface under the brand bar (the
 * sibling of the part editor's CreateStrip). One Component action (add a part
 * instance) and the three v1 mate tools (Coincident / Concentric / Lock),
 * icon-forward and keyboard-hinted. A mate tool is a TOGGLE (the brass scribe
 * marks the armed one) and stays honestly disabled until two instances exist —
 * you cannot mate one part to itself. Chrome recedes; the viewport is the hero.
 */
import {
  AddIcon,
  CoincidentIcon,
  ConcentricIcon,
  FixedIcon,
  ToolButton,
  ToolGroup,
} from "@loft/design";

import type { MateTool } from "../assembly/mateStore";

export interface AssemblyCommandBandProps {
  canAddPart: boolean;
  onAddPart: () => void;
  /** A mate needs two instances; the tools stay disabled until then. */
  canMate: boolean;
  activeTool: MateTool | null;
  onToggleTool: (tool: MateTool) => void;
}

export function AssemblyCommandBand({
  canAddPart,
  onAddPart,
  canMate,
  activeTool,
  onToggleTool,
}: AssemblyCommandBandProps) {
  const mateReason = canMate ? undefined : "Add two parts first";
  return (
    <div className="flex items-stretch divide-x divide-hairline">
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
    </div>
  );
}
