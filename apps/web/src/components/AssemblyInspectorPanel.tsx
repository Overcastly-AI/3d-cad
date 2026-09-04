/**
 * The assembly's right-hand instrument: one floating panel, three views toggled
 * by a quiet segmented control — SOLVE (the DRO/solve title block + combined
 * mass), PARTS (the bill-of-materials schedule), and CLASH (the interference
 * report). Below the view sits the EXPORT strip, always present, so the whole
 * solved assembly writes to STEP/STL from the same title block a part exports
 * from (one export language). Every view is a title-block instrument cut from
 * the same primitives; the toggle keeps the viewport the hero (no stack of
 * floating panels crowding the frame). The BOM + clash reads are owned by the
 * workspace and passed down, so switching views never refetches.
 */
import { SegmentedControl } from "@loft/design";

import type { AssemblyBomResponse } from "../api/bom";
import type { AssemblySolve } from "../features/assemblySolve";
import type {
  EvaluateAssemblyResult,
  InstanceResponse,
  InterferenceResult,
  MateResponse,
} from "../api/assemblies";
import { AssemblyBomPanel } from "./AssemblyBomPanel";
import { AssemblyClashPanel } from "./AssemblyClashPanel";
import { AssemblyInspector } from "./AssemblyInspector";
import { ExportRow } from "./ExportRow";
import type { ExportedFile, ExportFormat } from "../api/exportPart";

export type InspectorView = "solve" | "bom" | "clash";

export interface AssemblyInspectorPanelProps {
  view: InspectorView;
  onViewChange: (view: InspectorView) => void;
  evaluation: EvaluateAssemblyResult | undefined;
  /** What may be CLAIMED about that evaluation — see `AssemblyInspectorProps`. */
  solve: AssemblySolve;
  bom: AssemblyBomResponse | undefined;
  bomLoading: boolean;
  bomError: Error | null;
  /**
   * The graph's instances — the clash view's balloon numbers + names, and the
   * SOLVE view's names for any component the mass roll-up could not weigh.
   */
  instances: readonly InstanceResponse[];
  /**
   * The graph's mates, in panel order — the SOLVE view names the offenders a
   * conflict/redundancy diagnosis reports by the tag the tree prints on the
   * row (MATEUI-1), and offers to remove them from where the message is read.
   */
  mates: readonly MateResponse[];
  /** Remove a mate the diagnosis named — the tree panel's own handler. */
  onDeleteMate: (mate: MateResponse) => void;
  /** A graph write is in flight; the diagnosis's remove actions are inert. */
  busy: boolean;
  /** The last interference check's result, or null before the first run. */
  clashResult: InterferenceResult | null;
  clashBusy: boolean;
  clashError: string | null;
  /** Export the solved assembly as one file; undefined disables the strip. */
  exporter: (format: ExportFormat) => Promise<ExportedFile>;
  /** Why export is inert (no body to write), or undefined when ready. */
  exportDisabledReason?: string;
}

const VIEW_OPTIONS = [
  {
    value: "solve" as const,
    label: "Solve",
    "data-testid": "inspector-view-solve",
  },
  {
    value: "bom" as const,
    label: "Parts",
    "data-testid": "inspector-view-bom",
  },
  {
    value: "clash" as const,
    label: "Clash",
    "data-testid": "inspector-view-clash",
  },
];

export function AssemblyInspectorPanel({
  view,
  onViewChange,
  evaluation,
  solve,
  bom,
  bomLoading,
  bomError,
  instances,
  mates,
  onDeleteMate,
  busy,
  clashResult,
  clashBusy,
  clashError,
  exporter,
  exportDisabledReason,
}: AssemblyInspectorPanelProps) {
  return (
    <div className="flex w-full flex-col gap-3">
      <SegmentedControl
        label="View"
        value={view}
        onChange={onViewChange}
        options={VIEW_OPTIONS}
        className="px-0.5"
      />
      {view === "solve" ? (
        <AssemblyInspector
          evaluation={evaluation}
          solve={solve}
          instances={instances}
          mates={mates}
          onDeleteMate={onDeleteMate}
          busy={busy}
        />
      ) : view === "bom" ? (
        <AssemblyBomPanel bom={bom} loading={bomLoading} error={bomError} />
      ) : (
        <AssemblyClashPanel
          instances={instances}
          result={clashResult}
          busy={clashBusy}
          error={clashError}
        />
      )}
      {/* The EXPORT strip is a STICKY footer: a long clash schedule (or BOM)
          scrolls under it inside the panel's overflow, but export stays pinned
          to the fold and always reachable. `-mt-3 pt-3` reclaims the flex gap as
          a bg-anvil buffer so scrolling rows never bleed through above it. */}
      <div className="sticky bottom-0 z-10 -mt-3 bg-anvil pt-3">
        <ExportRow
          testIdPrefix="assembly-export"
          exporter={exporter}
          disabledReason={exportDisabledReason}
        />
      </div>
    </div>
  );
}
