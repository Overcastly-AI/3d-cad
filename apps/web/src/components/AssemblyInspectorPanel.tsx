/**
 * The assembly's right-hand instrument: one floating panel, two views toggled
 * by a quiet segmented control — SOLVE (the DRO/solve title block + combined
 * mass) and PARTS (the bill-of-materials schedule). Both are title-block
 * instruments cut from the same primitives; the toggle keeps the viewport the
 * hero (no third floating panel crowding the frame). The BOM read is fetched
 * by the workspace and passed down, so switching views never refetches.
 */
import { SegmentedControl } from "@loft/design";

import type { AssemblyBomResponse } from "../api/bom";
import type { EvaluateAssemblyResult } from "../api/assemblies";
import { AssemblyBomPanel } from "./AssemblyBomPanel";
import { AssemblyInspector } from "./AssemblyInspector";

export type InspectorView = "solve" | "bom";

export interface AssemblyInspectorPanelProps {
  view: InspectorView;
  onViewChange: (view: InspectorView) => void;
  evaluation: EvaluateAssemblyResult | undefined;
  evaluating: boolean;
  bom: AssemblyBomResponse | undefined;
  bomLoading: boolean;
  bomError: Error | null;
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
];

export function AssemblyInspectorPanel({
  view,
  onViewChange,
  evaluation,
  evaluating,
  bom,
  bomLoading,
  bomError,
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
        <AssemblyInspector evaluation={evaluation} evaluating={evaluating} />
      ) : (
        <AssemblyBomPanel bom={bom} loading={bomLoading} error={bomError} />
      )}
    </div>
  );
}
