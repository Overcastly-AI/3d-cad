/**
 * The assembly title block — the solve state (the DRO/solve-diagnostic idiom,
 * mirrored from the sketcher) plus the combined mass properties the geometry
 * service rolled up over instances. The status + DOF + offending-mate ids are
 * read from the TYPED `AssemblySolveDiagnosis`, never a parsed message, so an
 * under/over/conflicting assembly reads legibly. Reuses the design primitives +
 * the same readout formatters as the body inspector — one number language.
 *
 * THE TITLE IS A CLAIM (materials.md §6.1). This panel's second section was
 * headed **COMBINED MASS** while reporting Volume / Area / Centroid and no mass
 * — the exact defect #57b closed on the part inspector, at a second address.
 * The words are now earned: while the roll-up's `mass_g` is null the section is
 * COMBINED PROPERTIES, there is no mass row at all (never `0 g`), and the panel
 * NAMES the instance that has no material, because the roll-up goes null unless
 * every contributor has one — a partial sum would under-report while looking
 * complete.
 */
import {
  formatMass,
  massUnitFor,
  Panel,
  PanelRow,
  PanelSection,
} from "@loft/design";

import type {
  AssemblyStatus,
  EvaluateAssemblyResult,
  InstanceResponse,
} from "../api/assemblies";
import { assemblyMassState, combinedEyebrow } from "../assembly/mass";
import { assemblyReadout } from "../assembly/readout";
import { missingMaterialNotice } from "../features/materials";
import { formatCount, formatVec3 } from "../lib/format";
import { useDocumentLengthUnit } from "../units/documentUnit";

export interface AssemblyInspectorProps {
  evaluation: EvaluateAssemblyResult | undefined;
  evaluating: boolean;
  /**
   * The graph's instances — the NAMES behind the roll-up's instance ids. An
   * absent list only costs the notice its names, never its honesty.
   */
  instances?: readonly InstanceResponse[];
}

const STATUS_LABEL: Record<AssemblyStatus, string> = {
  well_constrained: "Well constrained",
  under_constrained: "Under constrained",
  over_constrained: "Over constrained",
  conflicting: "Conflicting",
  not_converged: "Not converged",
};

/** A sick solve reads flag; a healthy or merely-under one stays quiet. */
function statusTone(status: AssemblyStatus): string {
  return status === "well_constrained" || status === "under_constrained"
    ? "text-mist"
    : "text-flag";
}

export function AssemblyInspector({
  evaluation,
  evaluating,
  instances = [],
}: AssemblyInspectorProps) {
  const em = "—";
  const diagnosis = evaluation?.diagnosis ?? null;
  const status = evaluation?.status ?? null;
  // Combined-mass / bbox readouts honor the document unit (FINDINGS burn-down
  // 2026-07-25 #7) — the same display-boundary conversion the part inspector
  // does, so an inch assembly and its inch parts speak one convention.
  const unit = useDocumentLengthUnit();
  const readout = assemblyReadout(evaluation, unit);
  // Mass rides the SAME units seam as the part panel: the wire is canonical
  // grams and the mass unit derives from the document length unit (§5).
  const mass = assemblyMassState(evaluation, instances);
  const centreOfMass = evaluation?.properties?.center_of_mass ?? null;
  const massNotice =
    mass.kind === "partial"
      ? missingMaterialNotice(mass.missing, "assembly")
      : mass.kind === "unassigned"
        ? "No component has a material, so this assembly has no total mass. Assign one in each part to weigh it."
        : null;

  return (
    <aside
      className="flex w-full flex-col gap-3"
      aria-label="Assembly inspector"
      data-testid="assembly-inspector"
    >
      <Panel>
        <PanelSection eyebrow="Solve state">
          <div className="flex items-baseline gap-2 px-3 py-1">
            <span className="font-body text-xs text-gauge min-w-12 shrink-0">
              Status
            </span>
            <span
              className={`font-display text-sm uppercase tracking-[0.12em] text-right grow ${
                status ? statusTone(status) : "text-gauge"
              }`}
              data-testid="assembly-solve-status"
              aria-live="polite"
            >
              {evaluating ? "Solving…" : status ? STATUS_LABEL[status] : em}
            </span>
          </div>
          <PanelRow label="Free DOF" data-testid="assembly-dof">
            {diagnosis
              ? formatCount(diagnosis.remaining_dof)
              : status
                ? "0"
                : em}
          </PanelRow>
          {diagnosis && diagnosis.message ? (
            <p
              data-testid="assembly-diagnosis"
              className="px-3 pt-1 pb-2 font-body text-xs text-gauge"
            >
              {diagnosis.message}
              {diagnosis.suggested_fix ? ` ${diagnosis.suggested_fix}` : ""}
            </p>
          ) : null}
        </PanelSection>

        <PanelSection eyebrow={combinedEyebrow(mass)}>
          {mass.kind === "known" ? (
            <PanelRow
              label="Mass"
              unit={massUnitFor(unit, mass.massG)}
              data-testid="assembly-mass"
            >
              {formatMass(mass.massG, unit, { unitSuffix: false })}
            </PanelRow>
          ) : null}
          <PanelRow
            label="Volume"
            unit={readout.volumeUnit}
            data-testid="assembly-volume"
          >
            {readout.volume}
          </PanelRow>
          <PanelRow label="Area" unit={readout.areaUnit}>
            {readout.area}
          </PanelRow>
          {/* Two DIFFERENT points, named apart because they differ (§3): the
              centre of MASS is mass-weighted and null until every component has
              a material; the centroid is the volume centre. This roll-up used
              to CALL its volume weighting mass-weighted. */}
          {centreOfMass !== null ? (
            <PanelRow
              label="Centre of mass"
              unit={readout.lengthUnit}
              data-testid="assembly-center-of-mass"
            >
              {formatVec3(centreOfMass, unit)}
            </PanelRow>
          ) : null}
          <PanelRow
            label="Centroid"
            unit={readout.lengthUnit}
            data-testid="assembly-centroid"
          >
            {readout.centroid}
          </PanelRow>
          {/* Absence, said out loud and pointed at its cause — never `0 g`, and
              never a silent dash while the wire is holding the name. */}
          {massNotice !== null ? (
            <p
              data-testid="assembly-mass-notice"
              className="px-3 pt-1 pb-2 font-body text-xs text-gauge"
            >
              {massNotice}
            </p>
          ) : null}
        </PanelSection>

        <PanelSection eyebrow="Bounding box">
          <PanelRow
            label="Extents"
            unit={readout.lengthUnit}
            data-testid="assembly-extents"
          >
            {readout.extents}
          </PanelRow>
        </PanelSection>
        {/* The decorative footer is gone (UI-REVIEW 2026-07-16, Track B):
            UNITS (no unit system) and SOLVER "Loft" (the product's own name
            dressed as a solver readout) carried nothing; INSTANCES folds into
            the tree's COMPONENTS eyebrow. Solve state / DOF above are the live
            instruments. */}
      </Panel>
    </aside>
  );
}
