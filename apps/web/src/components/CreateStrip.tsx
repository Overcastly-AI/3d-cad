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
import { BandActionCell, ToolButton, ToolGroup, VerbGlyph } from "@loft/design";
import { useRef } from "react";

import type { ExportedFile, ExportFormat } from "../api/exportPart";
import { useCommandActionStore } from "../features/commandActions";
import { verbHint, verbLabel } from "../features/patternScope";
import { ExportToolGroup } from "./ExportToolGroup";
import { HistoryGroup } from "./HistoryGroup";

/**
 * Which groups keep their words when the band runs out of room (higher holds
 * on longer — `CommandBand` guarantee #3). Ordered by INFORMATION PER PIXEL,
 * measured on this band at the icon tier vs the labeled one:
 *
 *   Export       +160px   format CODES — "STEP" / "STL" / "3MF" / "GLB". Three
 *                         of the four glyphs are the same mesh strip with one
 *                         differentiating mark, and no picture can spell a
 *                         format name. These labels are the only ones here
 *                         carrying information the icon cannot, and export is
 *                         the verb EXPORT-1 exists to keep findable.
 *   Inspect       +37px   the cheapest words on the band, and its one tool is
 *                         a MODE you toggle rather than a feature you add — a
 *                         distinction the caliper glyph does not draw.
 *   Create       +407px   the family a newcomer reaches for before the icons
 *                         are learned, so it is the first VERB group to earn
 *                         its width.
 *   Modify       +475px   same class as Create, reached once the tool set is
 *                         already familiar.
 *   Sheet metal  +524px   the widest labels on the band for a family that is
 *                         inert on every part that is not sheet metal — last
 *                         to earn 524px.
 *
 * History is icon-only by construction (frontend-qa 07-17 P2), so it has no
 * words to shed and sits at the default.
 */
const LABEL_PRIORITY = {
  export: 40,
  inspect: 30,
  create: 20,
  modify: 10,
  sheetMetal: 0,
} as const;

export interface CreateStripProps {
  /** The feature tree has loaded (buttons stay disabled until it has). */
  treeReady: boolean;
  /**
   * An earlier history snapshot exists to restore (the tree response's
   * `can_undo` — docs/design/undo-redo.md). At the ring's floor the button
   * disables with its honest reason, like every other gated tool.
   */
  canUndo?: boolean;
  /** A later history snapshot exists to restore (`can_redo` — the mirror gate). */
  canRedo?: boolean;
  /**
   * The tree write currently holding the History tools, or null. Both buttons
   * disable while ANY of these is in flight, and the tooltip names the TRUE
   * reason (an idle Redo held by a running undo says "Undoing…", never
   * "Redoing…"): an undo, a redo, or a rollback-bar move (history and the
   * rollback bar mutually exclude — both rewrite the tree under the OCC).
   */
  historyHold?: "undo" | "redo" | "rollback" | null;
  /** Undo one feature-tree edit (Ctrl/⌘+Z). */
  onUndo?: () => void;
  /** Redo one feature-tree edit (Ctrl/⌘+Shift+Z, Ctrl+Y). */
  onRedo?: () => void;
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
  /**
   * The feature the user selected in the tree, when a pattern/mirror can act on
   * it — the verbs then PROPOSE it by name ("Repeat Hole1") instead of offering
   * a generic array of the whole body (docs/design/pattern-scope.md §7.2; the
   * flow rule "the next step is visible from the current state"). Null when
   * nothing is selected: a toolbar that renamed itself on every tree change
   * would be noise, so only an explicit selection moves these words.
   */
  scopeSubject?: string | null;
  /** Hollow the current body to a uniform wall, opening picked faces (H). */
  onShell?: () => void;
  /** Taper picked faces for mold release about a neutral plane (D). */
  onDraft?: () => void;
  /** Drill a cylindrical hole into the current body at a point on a face (O). */
  onHole?: () => void;
  /** Reflect the current body about a plane and union the reflection in (I). */
  onMirror?: () => void;
  /**
   * A solved sketch exists to thicken into a sheet-metal base flange (the same
   * gate as Extrude — a base flange consumes a sketch profile).
   */
  canBaseFlange?: boolean;
  /** Thicken a sketch profile to gauge — the sheet-metal part's first body. */
  onNewBaseFlange?: () => void;
  /**
   * The part is sheet metal (a base flange exists), so an edge flange can fold
   * off one of its straight edges, and the flat pattern can be unfolded.
   */
  canEdgeFlange?: boolean;
  /** Fold a leg off a picked straight edge of the sheet body. */
  onNewEdgeFlange?: () => void;
  /**
   * The part is sheet metal (a base flange exists), so a closed hem can fold a
   * picked straight edge 180° back onto the sheet — the same gate as edge flange.
   */
  canHem?: boolean;
  /** Fold a picked straight edge 180° back onto the sheet (a closed hem). */
  onNewHem?: () => void;
  /**
   * The part has ≥2 edge flanges whose bends can meet at a corner, so a corner
   * relief can notch that corner. Below two edge flanges the tool disables.
   */
  canCornerRelief?: boolean;
  /** Notch the shared corner of two adjacent edge flanges (corner relief). */
  onNewCornerRelief?: () => void;
  /** The flat pattern can be unfolded (the part is sheet metal). */
  canFlatPattern?: boolean;
  /** A flat-pattern unfold is in flight (opening the drawing). */
  flatteningPattern?: boolean;
  /** Unfold the sheet body onto a flat-pattern drawing (the model→flatten loop). */
  onFlatPattern?: () => void;
  /** A profile-only flat-pattern DXF download is in flight. */
  exportingFlatDxf?: boolean;
  /**
   * Download the flat pattern as a profile-only DXF cut path — the file a
   * laser/turret vendor asks for by name (AUDIT-PRODUCT F-2a). Sits beside
   * "Flat pattern" rather than in the Export group because it is a SHEET-METAL
   * deliverable and shares that verb's gate: both need a sheet body, and the
   * next thing a user wants after seeing the blank is to send it out.
   */
  onExportFlatDxf?: () => void;
  /**
   * Two or more bodies exist to fuse (a `merge: false` add / an import started a
   * second body). Below two bodies the Combine tool disables with its reason.
   */
  canCombine?: boolean;
  /** Fuse two bodies into one via a boolean union (multi-body §MB-1). */
  onCombine?: () => void;
  /** A solid body exists to inspect — the Measure tool lights up. */
  canMeasure?: boolean;
  /** The Measure tool is armed (picking targets in the viewport). */
  measuring?: boolean;
  /** Toggle the Measure tool (M). */
  onToggleMeasure?: () => void;
  /**
   * The command currently open in an editor (e.g. "Fillet"), or null. While a
   * command is open the band RECEDES to an in-command bar — the active command
   * name + OK / Cancel — and the tool groups fall back (kept in the a11y tree,
   * still locked, but out of the visual band): the band reads "you are inside
   * Fillet", not "here is the whole toolbar, greyed" (UI-REVIEW 2026-07-16,
   * Batch 3 item 10 — Fusion/Plasticity in-command chrome). Switching tools can
   * still never discard the open command's picks (Track C P1, the
   * fillet→extrude pick-loss).
   */
  activeCommand?: string | null;
  /** Commit the open command (runs its validated submit via the action bus). */
  onCommandOk?: () => void;
  /** Cancel the open command (the workspace closes the editor). */
  onCommandCancel?: () => void;
  /**
   * Write the part's current evaluated body to a file — the band's terminal
   * verb. Omit it and the EXPORT group is not rendered at all.
   *
   * Export lives HERE, in document-level chrome, because it is an action and
   * not a readout: it used to exist only as the last cell of the Inspector's
   * readout stack, so collapsing that panel removed the only way to get a file
   * out of the product (EXPORT-1; founder, 2026-08-17). The Inspector keeps its
   * strip — that is the right place for the "this file would be partial"
   * notice — but the affordance the user reaches for survives a panel collapse.
   */
  onExport?: (format: ExportFormat) => Promise<ExportedFile>;
  /** Why export is inert (nothing built / unverified), or undefined when ready. */
  exportDisabledReason?: string;
  /** Allowed, but the file would be a prefix of the tree. */
  exportPartial?: boolean;
  /** What makes it a prefix, in a clause — `ExportGate.qualifier` (EXPORT-3). */
  exportPartialQualifier?: string;
  /** QA hook: the export gate state name the workspace derived. */
  exportState?: string;
}

export function CreateStrip({
  treeReady,
  canUndo = false,
  canRedo = false,
  historyHold = null,
  onUndo,
  onRedo,
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
  scopeSubject = null,
  onShell,
  onDraft,
  onHole,
  onMirror,
  canBaseFlange = false,
  onNewBaseFlange,
  canEdgeFlange = false,
  onNewEdgeFlange,
  canHem = false,
  onNewHem,
  canCornerRelief = false,
  onNewCornerRelief,
  canFlatPattern = false,
  flatteningPattern = false,
  onFlatPattern,
  exportingFlatDxf = false,
  onExportFlatDxf,
  canCombine = false,
  onCombine,
  canMeasure = false,
  measuring = false,
  onToggleMeasure,
  activeCommand = null,
  onCommandOk,
  onCommandCancel,
  onExport,
  exportDisabledReason,
  exportPartial = false,
  exportPartialQualifier,
  exportState,
}: CreateStripProps) {
  const importInputRef = useRef<HTMLInputElement>(null);
  const importReady =
    treeReady && canImportStep && !importingStep && onImportStep !== undefined;
  // The open editor publishes its submit gate here; the OK cell shows its true
  // (disabled) state on an invalid form instead of looking actionable but no-op.
  const okReady = useCommandActionStore((s) => s.okReady);

  const filletReady = canModify && treeReady && onFillet !== undefined;
  const chamferReady = canModify && treeReady && onChamfer !== undefined;
  const patternReady = canModify && treeReady && onPattern !== undefined;
  const shellReady = canModify && treeReady && onShell !== undefined;
  const draftReady = canModify && treeReady && onDraft !== undefined;
  const holeReady = canModify && treeReady && onHole !== undefined;
  const mirrorReady = canModify && treeReady && onMirror !== undefined;
  const combineReady = canCombine && treeReady && onCombine !== undefined;
  const baseFlangeReady =
    canBaseFlange && treeReady && onNewBaseFlange !== undefined;
  const edgeFlangeReady =
    canEdgeFlange && treeReady && onNewEdgeFlange !== undefined;
  const hemReady = canHem && treeReady && onNewHem !== undefined;
  const cornerReliefReady =
    canCornerRelief && treeReady && onNewCornerRelief !== undefined;
  const flatPatternReady =
    canFlatPattern &&
    treeReady &&
    !flatteningPattern &&
    onFlatPattern !== undefined;
  const flatDxfReady =
    canFlatPattern &&
    treeReady &&
    !exportingFlatDxf &&
    onExportFlatDxf !== undefined;

  // An open command scopes the whole band: every tool locks with one honest
  // reason, so no click can discard the open command's picks (Track C P1).
  const locked = activeCommand != null && activeCommand !== "";
  const lockReason = locked ? `Finish ${activeCommand} first` : undefined;
  /** The tooltip's second line: the lock reason wins, else the gate reason. */
  const captionFor = (ready: boolean, reason: string): string | undefined =>
    locked ? lockReason : ready ? undefined : reason;
  /**
   * The scope proposal's second channel, and it is load-bearing rather than
   * belt-and-braces. At the 1280x800 floor the band has MEASURED itself into
   * the icon tier for Create/Modify, so the renamed label ("Repeat Hole1") is
   * shed — and that is the width the quality floor names. `ToolButton`'s own
   * contract for the icon tier is that "icon + group eyebrow + tooltip carry
   * the name", so the proposal rides the caption, which is never shed and which
   * `aria-describedby` already routes to screen readers.
   *
   * Deliberately NOT fixed by promoting Modify's `labelPriority`: that scale is
   * a measured information-per-pixel ordering, and the group it would demote is
   * EXPORT, whose format codes EXPORT-1 exists to keep findable.
   */
  const scopeCaptionFor = (
    ready: boolean,
    reason: string,
  ): string | undefined => {
    const gate = captionFor(ready, reason);
    if (gate !== undefined || scopeSubject === null) return gate;
    return `Repeats ${scopeSubject}, not the whole body`;
  };

  return (
    <div
      aria-label="Create"
      data-testid="create-strip"
      data-command={activeCommand ?? undefined}
      className="flex items-stretch"
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

      {/* In-command state: the band recedes to the active command + OK/Cancel.
          The tool groups below stay in the DOM (a11y tree + still locked) but
          fall out of the visual band, so it reads "you are inside <command>". */}
      {locked ? (
        <div
          data-testid="in-command"
          className="flex grow items-stretch"
          role="group"
          aria-label={`In command: ${activeCommand}`}
        >
          <div className="flex flex-col justify-center gap-0.5 px-4">
            <span className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
              In command
            </span>
            <span
              data-testid="in-command-name"
              className="flex items-center gap-1.5 font-data text-sm leading-none text-brass"
            >
              <span aria-hidden className="text-brass">
                ▸
              </span>
              {activeCommand}
            </span>
          </div>
          <span aria-hidden className="my-2 w-px bg-hairline" />
          <div className="ml-auto flex items-stretch divide-x divide-hairline border-l border-hairline">
            <BandActionCell
              label="Cancel"
              caption="Esc"
              data-testid="in-command-cancel"
              onClick={onCommandCancel}
            />
            <BandActionCell
              label="OK"
              caption={okReady ? "Enter" : "Finish the form"}
              accent
              disabled={!okReady}
              data-testid="in-command-ok"
              onClick={onCommandOk}
            />
          </div>
        </div>
      ) : null}

      <div
        data-testid="tool-groups"
        className={
          locked ? "sr-only" : "flex items-stretch divide-x divide-hairline"
        }
      >
        {/* History leads the band (the Fusion position): every modeling edit
            is reversible from here. The group itself is the SHARED
            HistoryGroup (identical in the assembly band); this band's truths
            ride in as captions — the rollback-bar hold and the open-command
            lock. Icon-only keeps the no-wrap band inside the 1280×800 floor
            (frontend-qa 07-17 P2). */}
        <HistoryGroup
          ready={treeReady}
          canUndo={canUndo}
          canRedo={canRedo}
          hold={
            historyHold === "undo" || historyHold === "redo"
              ? historyHold
              : null
          }
          holdReason={
            historyHold === "rollback" ? "Moving the rollback bar…" : null
          }
          lockReason={lockReason}
          onUndo={onUndo}
          onRedo={onRedo}
        />

        <ToolGroup eyebrow="Create" labelPriority={LABEL_PRIORITY.create}>
          <ToolButton
            icon={<VerbGlyph verb="import_step" />}
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
            icon={<VerbGlyph verb="sketch" />}
            showLabel
            label="Sketch"
            data-testid="new-sketch"
            aria-label="New sketch — pick a plane, then L / R / C / A"
            caption={captionFor(treeReady, "Loading the tree…")}
            disabled={locked || !treeReady}
            onClick={onNewSketch}
          />
          <ToolButton
            icon={<VerbGlyph verb="datum" />}
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
            icon={<VerbGlyph verb="extrude" />}
            showLabel
            label="Extrude"
            data-testid="new-extrude"
            aria-label={
              canExtrude
                ? "Extrude — add or cut a sketch profile"
                : "Extrude — draw a sketch first"
            }
            caption={captionFor(
              canExtrude && treeReady,
              "Draw a sketch to extrude",
            )}
            disabled={locked || !canExtrude || !treeReady}
            onClick={onNewExtrude}
          />
          <ToolButton
            icon={<VerbGlyph verb="revolve" />}
            showLabel
            label="Revolve"
            data-testid="new-revolve"
            aria-label={
              canRevolve
                ? "Revolve — sweep a sketch profile about an axis"
                : "Revolve — draw a sketch first"
            }
            caption={captionFor(
              canRevolve && treeReady,
              "Draw a sketch to revolve",
            )}
            disabled={locked || !canRevolve || !treeReady}
            onClick={onNewRevolve}
          />
          <ToolButton
            icon={<VerbGlyph verb="sweep" />}
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
            icon={<VerbGlyph verb="loft" />}
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

        <ToolGroup eyebrow="Modify" labelPriority={LABEL_PRIORITY.modify}>
          <ToolButton
            icon={<VerbGlyph verb="fillet" />}
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
            icon={<VerbGlyph verb="chamfer" />}
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
            icon={<VerbGlyph verb="pattern" />}
            showLabel
            label={verbLabel("pattern", scopeSubject)}
            shortcut="P"
            data-testid="new-pattern"
            aria-label={
              patternReady
                ? verbHint("pattern", scopeSubject)
                : "Pattern — create a body first"
            }
            caption={scopeCaptionFor(patternReady, "Create a body first")}
            disabled={locked || !patternReady}
            onClick={onPattern}
          />
          <ToolButton
            icon={<VerbGlyph verb="shell" />}
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
            icon={<VerbGlyph verb="draft" />}
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
          <ToolButton
            icon={<VerbGlyph verb="hole" />}
            showLabel
            label="Hole"
            shortcut="O"
            data-testid="new-hole"
            aria-label={
              holeReady
                ? "Hole — drill a cylinder into the body at a point on a face (O)"
                : "Hole — create a body first"
            }
            caption={captionFor(holeReady, "Create a body first")}
            disabled={locked || !holeReady}
            onClick={onHole}
          />
          <ToolButton
            icon={<VerbGlyph verb="mirror" />}
            showLabel
            label={verbLabel("mirror", scopeSubject)}
            shortcut="I"
            data-testid="new-mirror"
            aria-label={
              mirrorReady
                ? verbHint("mirror", scopeSubject)
                : "Mirror — create a body first"
            }
            caption={scopeCaptionFor(mirrorReady, "Create a body first")}
            disabled={locked || !mirrorReady}
            onClick={onMirror}
          />
          <ToolButton
            icon={<VerbGlyph verb="boolean" />}
            showLabel
            label="Combine"
            data-testid="new-combine"
            aria-label={
              combineReady
                ? "Combine — fuse two bodies into one (boolean union)"
                : "Combine — needs two or more bodies"
            }
            caption={captionFor(combineReady, "Needs two bodies")}
            disabled={locked || !combineReady}
            onClick={onCombine}
          />
        </ToolGroup>

        <ToolGroup
          eyebrow="Sheet metal"
          labelPriority={LABEL_PRIORITY.sheetMetal}
        >
          <ToolButton
            icon={<VerbGlyph verb="sheet_metal_base_flange" />}
            showLabel
            label="Base flange"
            data-testid="new-base-flange"
            aria-label={
              baseFlangeReady
                ? "Base flange — thicken a sketch profile to gauge (the sheet's first body)"
                : "Base flange — draw a sketch first"
            }
            caption={captionFor(baseFlangeReady, "Draw a sketch first")}
            disabled={locked || !baseFlangeReady}
            onClick={onNewBaseFlange}
          />
          <ToolButton
            icon={<VerbGlyph verb="sheet_metal_edge_flange" />}
            showLabel
            label="Edge flange"
            data-testid="new-edge-flange"
            aria-label={
              edgeFlangeReady
                ? "Edge flange — fold a leg off a straight edge of the sheet"
                : "Edge flange — add a base flange first"
            }
            caption={captionFor(edgeFlangeReady, "Add a base flange first")}
            disabled={locked || !edgeFlangeReady}
            onClick={onNewEdgeFlange}
          />
          <ToolButton
            icon={<VerbGlyph verb="sheet_metal_hem" />}
            showLabel
            label="Hem"
            data-testid="new-hem"
            aria-label={
              hemReady
                ? "Hem — fold a straight edge of the sheet 180° back onto itself (a closed hem)"
                : "Hem — add a base flange first"
            }
            caption={captionFor(hemReady, "Add a base flange first")}
            disabled={locked || !hemReady}
            onClick={onNewHem}
          />
          <ToolButton
            icon={<VerbGlyph verb="sheet_metal_corner_relief" />}
            showLabel
            label="Corner relief"
            data-testid="new-corner-relief"
            aria-label={
              cornerReliefReady
                ? "Corner relief — notch the shared corner of two adjacent edge flanges"
                : "Corner relief — add two edge flanges that meet at a corner first"
            }
            caption={captionFor(cornerReliefReady, "Needs two edge flanges")}
            disabled={locked || !cornerReliefReady}
            onClick={onNewCornerRelief}
          />
          <ToolButton
            icon={<VerbGlyph verb="flat_pattern" />}
            showLabel
            label="Flat pattern"
            data-testid="new-flat-pattern"
            aria-label={
              canFlatPattern
                ? "Flat pattern — unfold the sheet body onto a drawing blank"
                : "Flat pattern — add a base flange first"
            }
            caption={captionFor(
              flatPatternReady,
              flatteningPattern ? "Unfolding…" : "Add a base flange first",
            )}
            disabled={locked || !flatPatternReady}
            onClick={onFlatPattern}
          />
          {/*
            The deliverable, next to the thing it delivers (AUDIT-PRODUCT F-2a).
            A flat pattern exists to be CUT, so the step after seeing the blank is
            sending it to a vendor — this writes the profile-only DXF cut path
            directly, instead of the old route of authoring a drawing, exporting
            it as DXF, and deleting the A4 border and title block by hand.

            Here rather than in the Export group because a flat pattern is a
            sheet-metal deliverable, not another format of the 3-D body: the
            Export cells all write the solid, and dropping a 2-D cut path among
            them would make that group mean two different things. It carries the
            flat-pattern glyph for the same reason it carries that gate — same
            subject, different verb, and the label says which.
          */}
          <ToolButton
            icon={<VerbGlyph verb="flat_pattern" />}
            showLabel
            label="Flat DXF"
            data-testid="export-flat-dxf"
            aria-label={
              canFlatPattern
                ? "Flat DXF — download the flat pattern as a 1:1 DXF cut path (outline and fold lines only)"
                : "Flat DXF — add a base flange first"
            }
            aria-busy={exportingFlatDxf}
            caption={captionFor(
              flatDxfReady,
              exportingFlatDxf ? "Writing…" : "Add a base flange first",
            )}
            disabled={locked || !flatDxfReady}
            onClick={onExportFlatDxf}
          />
        </ToolGroup>

        <ToolGroup eyebrow="Inspect" labelPriority={LABEL_PRIORITY.inspect}>
          <ToolButton
            icon={<VerbGlyph verb="measure" />}
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

        {/* EXPORT closes the band: the band reads left to right as the work —
            undo the last edit, create, modify, fold, inspect — and ends in the
            deliverable, the same order and the same `ToolGroup eyebrow="Export"`
            the drawing band already uses. It is the LAST group and not a
            document menu because there is no menu layer in this product, and a
            verb hidden behind one more click is the defect this ticket exists
            to fix, not a milder version of it. */}
        {onExport !== undefined ? (
          <ExportToolGroup
            testIdPrefix="part-export-band"
            labelPriority={LABEL_PRIORITY.export}
            exporter={onExport}
            // An open command owns the picks, so export holds with the SAME
            // one honest reason as every other tool in the locked band.
            disabledReason={locked ? lockReason : exportDisabledReason}
            partial={exportPartial}
            partialQualifier={exportPartialQualifier}
            state={exportState}
          />
        ) : null}
      </div>
    </div>
  );
}
