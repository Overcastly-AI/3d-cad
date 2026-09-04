/**
 * The MATERIAL cell of the title block — what the part is made of, and the way
 * to say so (docs/design/materials.md §6).
 *
 * A real drawing's title block carries MATERIAL beside the mass, so this is
 * where it goes: the same ruled section family as the readouts, no new visual
 * idiom. It is the affordance half of the honesty rule — a panel that refuses
 * to claim a mass owes the user the way to get one, otherwise "no mass" is just
 * a dead end.
 *
 * Densities are NEVER typed here. The library arrives from
 * `GET /api/v1/materials` (a physical constant has one home); when it cannot be
 * loaded the cell says so and disables itself rather than guessing.
 */
import { PanelRow, SelectField } from "@loft/design";

import type {
  Material,
  MaterialAssignment,
  MaterialKey,
} from "../api/materials";
import {
  type BodyMaterialRow,
  isUnassigned,
  type MassState,
  soleMaterial,
  unassignedNotice,
} from "../features/materials";

/** What the workspace supplies: the library, the assignment, and the writes. */
export interface MaterialControls {
  /** The served library, in display order; empty while it loads or fails. */
  library: readonly Material[];
  /** Why the library is unavailable, in the server's own words; null if fine. */
  libraryError: string | null;
  /** The part's current assignment (always an object — a stored NULL reads empty). */
  assignment: MaterialAssignment;
  /** One row per body of the tree, joined to the evaluation's resolved material. */
  rows: readonly BodyMaterialRow[];
  /** True while an assignment PATCH is in flight. */
  busy: boolean;
  /** Why the last assignment failed, in the server's own words; null if fine. */
  error: string | null;
  /** Set the document default (null clears it). */
  onAssignDefault: (material: MaterialKey | null) => void;
  /** Set ONE body's override (null falls back to the document default). */
  onAssignBody: (baseFeatureId: string, material: MaterialKey | null) => void;
}

export interface MaterialSectionProps extends MaterialControls {
  /** What the panel is entitled to say about mass (shared with the readouts). */
  state: MassState;
  /** Formats a body's mass in the document's derived mass unit. */
  formatBodyMass: (grams: number) => string;
}

const NONE = "";

/**
 * A body row is a fixed-width instrument (name · picker · mass), so a long
 * user-given name is clipped with an ellipsis rather than allowed to push the
 * mass out of the panel. The full name stays reachable — `title` on hover, and
 * the select's accessible name — and the unassigned notice always spells it
 * out in full.
 */
function shortName(name: string): string {
  return name.length > 16 ? `${name.slice(0, 15)}…` : name;
}

/** Section body only — the caller wraps it in the panel's ruled section. */
export function MaterialSection({
  library,
  libraryError,
  assignment,
  rows,
  busy,
  error,
  state,
  formatBodyMass,
  onAssignDefault,
  onAssignBody,
}: MaterialSectionProps) {
  const unavailable = libraryError !== null || library.length === 0;
  const defaultMaterial = assignment.default_material ?? null;
  const multiBody = rows.length > 1;
  const sole = soleMaterial(assignment, rows);
  const density =
    sole === null
      ? null
      : (library.find((m) => m.key === sole)?.density_kg_m3 ?? null);
  const notice = unassignedNotice(rows);

  const options = [
    { value: NONE, label: "No material" },
    ...library.map((material) => ({
      value: material.key,
      label: material.name,
    })),
  ];
  // A body's own cell offers "the document's material" as its first choice.
  // It reads "Default" rather than "Default · Aluminium 6061": the cell
  // DIRECTLY above shows what the default is, and the long form overflowed the
  // row into the mass readout at 1440 (measured, not guessed).
  const bodyOptions = [
    {
      value: NONE,
      label: defaultMaterial === null ? "No material" : "Default",
    },
    ...library.map((material) => ({
      value: material.key,
      label: material.name,
    })),
  ];

  return (
    <div data-testid="material-controls">
      {/*
        INLINE, not stacked (founder, 2026-08-28: the material selector "is not
        in any form compact like the header"). A stacked field spends a whole
        line of leading on a caption before the control even starts — 49px for
        one picker — and that is the anatomy of a settings dialog, which is
        exactly what the founder was looking at.

        `layout="inline"` is not new work: FB-19 built the dense caption-beside-
        control cell (`FieldRow`) for the feature editors and the panels never
        adopted it. Reaching for the primitive's existing dense mode is the
        whole fix here; hand-tuning padding in this file would have produced a
        second density language and left the next panel to be born wrong.
      */}
      <SelectField
        // The cell is already under a MATERIAL eyebrow, so the field's own
        // label says what it APPLIES TO rather than repeating the word:
        // "Whole part" when there is one body, "Default" when per-body rows
        // sit under it and may override it.
        label={multiBody ? "Default" : "Whole part"}
        layout="inline"
        data-testid="material-default-select"
        value={defaultMaterial ?? NONE}
        disabled={busy || unavailable}
        options={options}
        error={error}
        onChange={(event) =>
          onAssignDefault(
            event.target.value === NONE
              ? null
              : (event.target.value as MaterialKey),
          )
        }
      />

      {density !== null ? (
        <PanelRow label="Density" unit="kg/m³" data-testid="material-density">
          {density.toLocaleString("en-US")}
        </PanelRow>
      ) : null}

      {/*
        A body row is the SAME cell as the default picker above it — caption,
        control, reading — rather than a bordered pill in a hand-rolled flex.
        Two anatomies for "pick a material" was the reason this section read as
        a form: the eye has to re-learn the row on the way down the panel.
      */}
      {multiBody
        ? rows.map((row) => (
            <SelectField
              key={row.baseFeatureId}
              label={shortName(row.name)}
              layout="inline"
              title={row.name}
              aria-label={`Material for ${row.name}`}
              data-testid={`material-body-select-${row.ordinal}`}
              className="min-w-0"
              value={row.override ?? NONE}
              disabled={busy || unavailable}
              options={bodyOptions}
              trailing={
                <span data-testid={`material-body-mass-${row.ordinal}`}>
                  {row.massG !== null ? formatBodyMass(row.massG) : "—"}
                </span>
              }
              onChange={(event) =>
                onAssignBody(
                  row.baseFeatureId,
                  event.target.value === NONE
                    ? null
                    : (event.target.value as MaterialKey),
                )
              }
            />
          ))
        : null}

      {/* Absence, said out loud — and never as `0 g`. A part nobody has
          assigned anything to gets the invitation; a part where SOME bodies are
          assigned gets the name of the one that is not (§6.4), because we know
          it and "unknown" would be the vague half of the same defect. */}
      {state.kind === "partial" && notice !== null ? (
        <p
          className="px-3 pt-1 pb-1 font-body text-xs text-gauge"
          data-testid="material-unassigned"
        >
          {notice}
        </p>
      ) : state.kind === "unassigned" && isUnassigned(assignment) ? (
        <p
          className="px-3 pt-1 pb-1 font-body text-xs text-gauge"
          data-testid="material-hint"
        >
          Assign a material to get a mass.
        </p>
      ) : null}

      {libraryError !== null ? (
        <p
          role="alert"
          className="px-3 pt-1 pb-1 font-body text-xs text-flag"
          data-testid="material-library-error"
        >
          {libraryError}
        </p>
      ) : null}
    </div>
  );
}
