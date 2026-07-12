/**
 * The feature-create tools, rendered in the full-width top band when NOT
 * sketching (the mode-off half of the command surface). These are the same
 * scribed icon buttons that used to live in the feature-tree panel's CREATE
 * row — grouped like Fusion's Create — moved up so the top band is always the
 * command surface. Every test hook is preserved: `new-sketch`, `new-extrude`,
 * `new-revolve` keep their ids, labels, and disabled semantics.
 */
import {
  ExtrudeIcon,
  RevolveIcon,
  SketchIcon,
  ToolButton,
  ToolGroup,
} from "@loft/design";

export interface CreateStripProps {
  /** The feature tree has loaded (buttons stay disabled until it has). */
  treeReady: boolean;
  /** Enter sketch mode — pick a plane, then L / R / C / A. */
  onNewSketch: () => void;
  /** True when a solved sketch exists to extrude. */
  canExtrude: boolean;
  onNewExtrude: () => void;
  /** True when a solved sketch exists to revolve (same gate as extrude). */
  canRevolve: boolean;
  onNewRevolve: () => void;
}

export function CreateStrip({
  treeReady,
  onNewSketch,
  canExtrude,
  onNewExtrude,
  canRevolve,
  onNewRevolve,
}: CreateStripProps) {
  return (
    <div
      aria-label="Create"
      data-testid="create-strip"
      className="flex items-stretch divide-x divide-hairline"
    >
      <ToolGroup aria-label="Create">
        <ToolButton
          icon={<SketchIcon />}
          showLabel
          label="Sketch"
          data-testid="new-sketch"
          aria-label="New sketch — pick a plane, then L / R / C / A"
          disabled={!treeReady}
          onClick={onNewSketch}
        />
        <ToolButton
          icon={<ExtrudeIcon />}
          showLabel
          label="Extrude"
          data-testid="new-extrude"
          aria-label={
            canExtrude
              ? "Extrude — add or cut a sketch profile"
              : "Extrude — solve a sketch first"
          }
          disabled={!canExtrude || !treeReady}
          onClick={onNewExtrude}
        />
        <ToolButton
          icon={<RevolveIcon />}
          showLabel
          label="Revolve"
          data-testid="new-revolve"
          aria-label={
            canRevolve
              ? "Revolve — sweep a sketch profile about an axis"
              : "Revolve — solve a sketch first"
          }
          disabled={!canRevolve || !treeReady}
          onClick={onNewRevolve}
        />
      </ToolGroup>
    </div>
  );
}
