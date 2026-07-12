/**
 * The feature-create tools, rendered in the full-width top band when NOT
 * sketching (the mode-off half of the command surface). These are the same
 * scribed icon buttons that used to live in the feature-tree panel's CREATE
 * row — grouped like Fusion's Create — moved up so the top band is always the
 * command surface. Every test hook is preserved: `new-sketch`, `new-extrude`,
 * `new-revolve` keep their ids, labels, and disabled semantics.
 *
 * Fusion's Create / Modify split is the growth path: the sketch-consuming verbs
 * live in Create, the body-editing verbs (fillet, chamfer; sweep/shell to come)
 * in a sibling **Modify** group. A Modify tool needs a solid body AND a landed
 * kernel op — until both are true its button stays honestly disabled (the
 * accelerator is engraved in the tooltip so it teaches the keyboard the moment
 * it lights up), matching how Extrude greys out until a sketch is solved.
 */
import {
  ChamferIcon,
  DatumIcon,
  ExtrudeIcon,
  FilletIcon,
  MeasureIcon,
  PatternIcon,
  RevolveIcon,
  SketchIcon,
  SweepIcon,
  ToolButton,
  ToolGroup,
} from "@loft/design";

export interface CreateStripProps {
  /** The feature tree has loaded (buttons stay disabled until it has). */
  treeReady: boolean;
  /** Enter sketch mode — pick a plane, then L / R / C / A. */
  onNewSketch: () => void;
  /** Author a standalone datum (construction) plane the tree can reuse. */
  onNewDatum?: () => void;
  /** True when a solved sketch exists to extrude. */
  canExtrude: boolean;
  onNewExtrude: () => void;
  /** True when a solved sketch exists to revolve (same gate as extrude). */
  canRevolve: boolean;
  onNewRevolve: () => void;
  /**
   * True when ≥2 sketch features exist to designate as a sweep's profile and
   * path (a sweep references two earlier sketches, not the implicit one).
   */
  canSweep: boolean;
  onNewSweep: () => void;
  /**
   * A solid body exists to modify. When false — or when a Modify handler is
   * not yet wired (the kernel op hasn't landed) — that Modify tool is disabled.
   */
  canModify?: boolean;
  /** Round the selected edges (arrives with the geometry fillet op). */
  onFillet?: () => void;
  /** Bevel the selected edges (arrives with the geometry chamfer op). */
  onChamfer?: () => void;
  /** Repeat the current body into a linear/circular array (P). */
  onPattern?: () => void;
  /** A solid body exists to inspect — the Measure tool lights up. */
  canMeasure?: boolean;
  /** The Measure tool is armed (picking targets in the viewport). */
  measuring?: boolean;
  /** Toggle the Measure tool (M). */
  onToggleMeasure?: () => void;
}

export function CreateStrip({
  treeReady,
  onNewSketch,
  onNewDatum,
  canExtrude,
  onNewExtrude,
  canRevolve,
  onNewRevolve,
  canSweep,
  onNewSweep,
  canModify = false,
  onFillet,
  onChamfer,
  onPattern,
  canMeasure = false,
  measuring = false,
  onToggleMeasure,
}: CreateStripProps) {
  const filletReady = canModify && treeReady && onFillet !== undefined;
  const chamferReady = canModify && treeReady && onChamfer !== undefined;
  const patternReady = canModify && treeReady && onPattern !== undefined;

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
          icon={<DatumIcon />}
          showLabel
          label="Datum"
          data-testid="tool-datum"
          aria-label="Datum plane — a construction plane a sketch can sit on"
          disabled={!treeReady || onNewDatum === undefined}
          onClick={onNewDatum}
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
        <ToolButton
          icon={<SweepIcon />}
          showLabel
          label="Sweep"
          shortcut="S"
          data-testid="new-sweep"
          aria-label={
            canSweep
              ? "Sweep — carry a profile sketch along an open path sketch (S)"
              : "Sweep — draw a profile sketch and a path sketch first"
          }
          disabled={!canSweep || !treeReady}
          onClick={onNewSweep}
        />
      </ToolGroup>

      <ToolGroup aria-label="Modify">
        <ToolButton
          icon={<FilletIcon />}
          showLabel
          label="Fillet"
          data-testid="new-fillet"
          aria-label={
            filletReady
              ? "Fillet — round the selected edges"
              : "Fillet — select a body edge first"
          }
          disabled={!filletReady}
          onClick={onFillet}
        />
        <ToolButton
          icon={<ChamferIcon />}
          showLabel
          label="Chamfer"
          data-testid="new-chamfer"
          aria-label={
            chamferReady
              ? "Chamfer — bevel the selected edges"
              : "Chamfer — select a body edge first"
          }
          disabled={!chamferReady}
          onClick={onChamfer}
        />
        <ToolButton
          icon={<PatternIcon />}
          showLabel
          label="Pattern"
          shortcut="P"
          data-testid="new-pattern"
          aria-label={
            patternReady
              ? "Pattern — repeat the body in a linear or circular array (P)"
              : "Pattern — create a body first"
          }
          disabled={!patternReady}
          onClick={onPattern}
        />
      </ToolGroup>

      <ToolGroup aria-label="Inspect">
        <ToolButton
          icon={<MeasureIcon />}
          showLabel
          label="Measure"
          shortcut="M"
          active={measuring}
          data-testid="measure-tool"
          aria-label={
            canMeasure
              ? "Measure — pick two points or edges to read the distance (M)"
              : "Measure — create a body first"
          }
          disabled={!canMeasure || onToggleMeasure === undefined}
          onClick={onToggleMeasure}
        />
      </ToolGroup>
    </div>
  );
}
