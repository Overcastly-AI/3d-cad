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
  EvaluateAssemblyResult,
  InstanceResponse,
  MateResponse,
} from "../api/assemblies";
import { assemblyDiagnosisReadout } from "../assembly/diagnosis";
import { assemblyMassState, combinedEyebrow } from "../assembly/mass";
import { mateNamesById } from "../assembly/mates";
import { assemblyReadout } from "../assembly/readout";
import {
  assemblySolveLabel,
  assemblySolveTone,
  type AssemblySolve,
} from "../features/assemblySolve";
import { missingMaterialNotice } from "../features/materials";
import { formatCount, formatVec3 } from "../lib/format";
import { useDocumentLengthUnit } from "../units/documentUnit";

export interface AssemblyInspectorProps {
  evaluation: EvaluateAssemblyResult | undefined;
  /**
   * WHAT MAY BE CLAIMED about the evaluation above — one derived object, not a
   * `status` beside an `evaluating` boolean.
   *
   * The two used to be separate and they disagreed for the length of every
   * write: `evaluating` was the evaluate query's own `isFetching`, which is
   * FALSE for most of a rebuild (the part-docs key moves first, disabling the
   * query), so the status cell read the retained previous solve as a settled
   * verdict while the viewport still drew the previous pose. Taking the whole
   * `AssemblySolve` means this panel cannot render a verdict that does not
   * exist — `deriveAssemblySolve` nulls it while stale.
   */
  solve: AssemblySolve;
  /**
   * The graph's instances — the NAMES behind the roll-up's instance ids. An
   * absent list only costs the notice its names, never its honesty.
   */
  instances?: readonly InstanceResponse[];
  /**
   * The graph's mates, in panel order — the NAMES behind the diagnosis's mate
   * ids (MATEUI-1). Same list, same order as the tree panel's rows, so `M2` in
   * the message and `M2` on a row are the same object by construction.
   */
  mates?: readonly MateResponse[];
  /**
   * Act on the diagnosis where it is read: remove a named offender without
   * hunting for its row. Omitted (or `busy`) leaves the message as a message.
   */
  onDeleteMate?: (mate: MateResponse) => void;
  /** A graph write is in flight — the remove actions are inert until it lands. */
  busy?: boolean;
}

export function AssemblyInspector({
  evaluation,
  solve,
  instances = [],
  mates = [],
  onDeleteMate,
  busy = false,
}: AssemblyInspectorProps) {
  const em = "—";
  // Both cells read the SAME derivation. Reading `evaluation.diagnosis`
  // directly here is what let FREE DOF keep reporting the previous solve's 6
  // under a status cell that had already moved on — the two-cells-disagreeing
  // half of QA-R4, at this address.
  const diagnosis = solve.diagnosis;
  const status = solve.status;
  // MATEUI-1: the paragraph is COMPOSED from the typed diagnosis, never from
  // `diagnosis.message`/`suggested_fix` — those are the server's own prose and
  // they carry a Python `repr` of a UUID list. `mateNamesById` is the tree
  // panel's own numbering, so every mate the message names is findable.
  const diagnosisReadout = assemblyDiagnosisReadout(
    diagnosis,
    mateNamesById(mates),
  );
  const mateById = new Map(mates.map((mate) => [mate.id, mate]));
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
              className={`font-display text-sm uppercase tracking-[0.12em] text-right grow ${assemblySolveTone(
                solve,
              )}`}
              data-testid="assembly-solve-status"
              data-solve-stale={solve.stale ? "true" : "false"}
              aria-live="polite"
            >
              {assemblySolveLabel(solve)}
            </span>
          </div>
          <PanelRow label="Free DOF" data-testid="assembly-dof">
            {diagnosis
              ? formatCount(diagnosis.remaining_dof)
              : status
                ? "0"
                : em}
          </PanelRow>
          {diagnosisReadout !== null ? (
            <div className="px-3 pt-1 pb-2">
              <p
                data-testid="assembly-diagnosis"
                className="font-body text-xs text-gauge"
              >
                {diagnosisReadout.text}
              </p>
              {/* The named offenders, actionable where they are read. An error
                  that names an object and leaves you to hunt for it is a dead
                  end with extra steps (flow rule: no dead ends) — and the row
                  is still there for anyone who wants the context. Same verb as
                  the tree's own control, so the vocabulary holds.

                  The chip spends the TAG only; the sentence directly above has
                  just said "M1 Coincident", and repeating the kind on the
                  button said nothing twice and stacked the chips onto two rows,
                  pushing the bounding box below the fold at 1280. The
                  accessible name keeps the full form (it CONTAINS the visible
                  text, so speech input still matches — WCAG 2.5.3). */}
              {onDeleteMate !== undefined &&
              diagnosisReadout.subjects.length > 0 ? (
                <div
                  className="mt-1.5 flex flex-wrap gap-1.5"
                  data-testid="assembly-diagnosis-actions"
                >
                  {diagnosisReadout.subjects.map((subject) => {
                    const mate = mateById.get(subject.mateId);
                    if (mate === undefined) return null;
                    return (
                      <button
                        key={subject.mateId}
                        type="button"
                        onClick={() => onDeleteMate(mate)}
                        disabled={busy}
                        aria-label={`Remove ${subject.name}`}
                        data-testid={`diagnosis-remove-${subject.mateId}`}
                        className="rounded-sm border border-etch px-1.5 py-0.5 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none transition-colors duration-fast hover:border-flag hover:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50"
                      >
                        Remove {subject.tag}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>
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
