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
  DraftIcon,
  ExtrudeIcon,
  FilletIcon,
  ImportStepIcon,
  LoftIcon,
  MeasureIcon,
  PatternIcon,
  RevolveIcon,
  ShellIcon,
  SketchIcon,
  SweepIcon,
  ToolButton,
  ToolGroup,
} from "@loft/design";
import { useRef } from "react";

export interface CreateStripProps {
  /** The feature tree has loaded (buttons stay disabled until it has). */
  treeReady: boolean;
  /** Enter sketch mode — pick a plane, then L / R / C / A. */
  onNewSketch: () => void;
  /**
   * True when a STEP file may be imported: the part has no body yet. Import is
   * a BASE feature — the first body-affecting one — so it disables (with a
   * legible tooltip reason) once any body exists, like Extrude greys until a
   * sketch solves.
   */
  canImportStep?: boolean;
  /** An import is in flight (button disabled, its status shown in the viewport). */
  importingStep?: boolean;
  /** Bring an external solid in as the base body from a chosen `.step`/`.stp`. */
  onImportStep?: (file: File) => void;
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
   * True when ≥2 sketch features exist to blend through as a loft's ordered
   * sections (a loft references a LIST of earlier sketches, not the implicit
   * one) — the same two-sketch gate as sweep.
   */
  canLoft: boolean;
  onNewLoft: () => void;
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
  /** Hollow the current body to a uniform wall, opening picked faces (H). */
  onShell?: () => void;
  /** Taper picked faces for mold release about a neutral plane (D). */
  onDraft?: () => void;
  /** A solid body exists to inspect — the Measure tool lights up. */
  canMeasure?: boolean;
  /** The Measure tool is armed (picking targets in the viewport). */
  measuring?: boolean;
  /** Toggle the Measure tool (M). */
  onToggleMeasure?: () => void;
  /**
   * The command currently open in an editor (e.g. "Fillet"), or null. While a
   * command is open the whole band LOCKS: every tool disables with a "Finish X
   * first" reason so switching tools can never silently discard the open
   * command's picks (UI-REVIEW 2026-07-16, Track C P1 — the fillet→extrude
   * pick-loss). Cancel/OK on the editor is the way out.
   */
  activeCommand?: string | null;
}

export function CreateStrip({
  treeReady,
  onNewSketch,
  canImportStep = false,
  importingStep = false,
  onImportStep,
  onNewDatum,
  canExtrude,
  onNewExtrude,
  canRevolve,
  onNewRevolve,
  canSweep,
  onNewSweep,
  canLoft,
  onNewLoft,
  canModify = false,
  onFillet,
  onChamfer,
  onPattern,
  onShell,
  onDraft,
  canMeasure = false,
  measuring = false,
  onToggleMeasure,
  activeCommand = null,
}: CreateStripProps) {
  const importInputRef = useRef<HTMLInputElement>(null);
  const importReady =
    treeReady && canImportStep && !importingStep && onImportStep !== undefined;

  const filletReady = canModify && treeReady && onFillet !== undefined;
  const chamferReady = canModify && treeReady && onChamfer !== undefined;
  const patternReady = canModify && treeReady && onPattern !== undefined;
  const shellReady = canModify && treeReady && onShell !== undefined;
  const draftReady = canModify && treeReady && onDraft !== undefined;

  // An open command scopes the whole band: every tool locks with one honest
  // reason, so no click can discard the open command's picks (Track C P1).
  const locked = activeCommand != null && activeCommand !== "";
  const lockReason = locked ? `Finish ${activeCommand} first` : undefined;
  /** The tooltip's second line: the lock reason wins, else the gate reason. */
  const captionFor = (ready: boolean, reason: string): string | undefined =>
    locked ? lockReason : ready ? undefined : reason;

  return (
    <div
      aria-label="Create"
      data-testid="create-strip"
      data-command={activeCommand ?? undefined}
      className="flex items-stretch divide-x divide-hairline"
    >
      {/* The native file picker — kept in the DOM (hidden, non-tabbable) and
          triggered by the Import button, so a `.step`/`.stp` choice streams
          straight to the import route. Resetting the value lets the same file
          be re-chosen after an error. */}
      <input
        ref={importInputRef}
        type="file"
        accept=".step,.stp"
        data-testid="import-step-input"
        className="hidden"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file !== undefined && onImportStep !== undefined) {
            onImportStep(file);
          }
        }}
      />

      <ToolGroup eyebrow="Create">
        <ToolButton
          icon={<ImportStepIcon />}
          showLabel
          label="Import"
          data-testid="import-step-button"
          aria-label={
            importReady || (canImportStep && importingStep)
              ? "Import STEP — bring an external solid in as the base body"
              : "Import STEP — only the first body can be imported; this part already has one"
          }
          caption={captionFor(
            importReady,
            canImportStep ? "Import unavailable" : "A body already exists",
          )}
          disabled={locked || !importReady}
          onClick={() => importInputRef.current?.click()}
        />
        <ToolButton
          icon={<SketchIcon />}
          showLabel
          label="Sketch"
          data-testid="new-sketch"
          aria-label="New sketch — pick a plane, then L / R / C / A"
          caption={captionFor(treeReady, "Loading the tree…")}
          disabled={locked || !treeReady}
          onClick={onNewSketch}
        />
        <ToolButton
          icon={<DatumIcon />}
          showLabel
          label="Datum"
          data-testid="tool-datum"
          aria-label="Datum plane — a construction plane a sketch can sit on"
          caption={captionFor(
            treeReady && onNewDatum !== undefined,
            "Loading the tree…",
          )}
          disabled={locked || !treeReady || onNewDatum === undefined}
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
          caption={captionFor(canExtrude && treeReady, "Solve a sketch first")}
          disabled={locked || !canExtrude || !treeReady}
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
          caption={captionFor(canRevolve && treeReady, "Solve a sketch first")}
          disabled={locked || !canRevolve || !treeReady}
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
          caption={captionFor(
            canSweep && treeReady,
            "Draw a profile and a path sketch",
          )}
          disabled={locked || !canSweep || !treeReady}
          onClick={onNewSweep}
        />
        <ToolButton
          icon={<LoftIcon />}
          showLabel
          label="Loft"
          shortcut="L"
          data-testid="new-loft"
          aria-label={
            canLoft
              ? "Loft — blend a solid through two or more ordered section sketches (L)"
              : "Loft — draw at least two section sketches first"
          }
          caption={captionFor(
            canLoft && treeReady,
            "Draw at least two section sketches",
          )}
          disabled={locked || !canLoft || !treeReady}
          onClick={onNewLoft}
        />
      </ToolGroup>

      <ToolGroup eyebrow="Modify">
        <ToolButton
          icon={<FilletIcon />}
          showLabel
          label="Fillet"
          data-testid="new-fillet"
          aria-label={
            filletReady
              ? "Fillet — round the selected edges"
              : "Fillet — create a body first"
          }
          caption={captionFor(filletReady, "Create a body first")}
          disabled={locked || !filletReady}
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
              : "Chamfer — create a body first"
          }
          caption={captionFor(chamferReady, "Create a body first")}
          disabled={locked || !chamferReady}
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
          caption={captionFor(patternReady, "Create a body first")}
          disabled={locked || !patternReady}
          onClick={onPattern}
        />
        <ToolButton
          icon={<ShellIcon />}
          showLabel
          label="Shell"
          shortcut="H"
          data-testid="new-shell"
          aria-label={
            shellReady
              ? "Shell — hollow the body to a uniform wall, opening picked faces (H)"
              : "Shell — create a body first"
          }
          caption={captionFor(shellReady, "Create a body first")}
          disabled={locked || !shellReady}
          onClick={onShell}
        />
        <ToolButton
          icon={<DraftIcon />}
          showLabel
          label="Draft"
          shortcut="D"
          data-testid="new-draft"
          aria-label={
            draftReady
              ? "Draft — taper picked faces for mold release about a neutral plane (D)"
              : "Draft — create a body first"
          }
          caption={captionFor(draftReady, "Create a body first")}
          disabled={locked || !draftReady}
          onClick={onDraft}
        />
      </ToolGroup>

      <ToolGroup eyebrow="Inspect">
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
          caption={captionFor(
            canMeasure && onToggleMeasure !== undefined,
            "Create a body first",
          )}
          disabled={locked || !canMeasure || onToggleMeasure === undefined}
          onClick={onToggleMeasure}
        />
      </ToolGroup>
    </div>
  );
}
