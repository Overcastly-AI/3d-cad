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
import { InlineSelect, PanelRow, SelectField } from "@loft/design";

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
      <div className="px-3 pb-1">
        <SelectField
          // The cell is already under a MATERIAL eyebrow, so the field's own
          // label says what it APPLIES TO rather than repeating the word:
          // "Whole part" when there is one body, "Default" when per-body rows
          // sit under it and may override it.
          label={multiBody ? "Default" : "Whole part"}
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
      </div>

      {density !== null ? (
        <PanelRow label="Density" unit="kg/m³" data-testid="material-density">
          {density.toLocaleString("en-US")}
        </PanelRow>
      ) : null}

      {multiBody
        ? rows.map((row) => (
            <div
              key={row.baseFeatureId}
              className="flex items-center gap-2 px-3 py-1"
              data-testid={`material-body-${row.ordinal}`}
            >
              <InlineSelect
                eyebrow={shortName(row.name)}
                title={row.name}
                aria-label={`Material for ${row.name}`}
                data-testid={`material-body-select-${row.ordinal}`}
                className="min-w-0 grow"
                value={row.override ?? NONE}
                disabled={busy || unavailable}
                options={bodyOptions}
                onChange={(event) =>
                  onAssignBody(
                    row.baseFeatureId,
                    event.target.value === NONE
                      ? null
                      : (event.target.value as MaterialKey),
                  )
                }
              />
              <span
                className="shrink-0 font-data text-xs text-mist tabular-nums"
                data-testid={`material-body-mass-${row.ordinal}`}
              >
                {row.massG !== null ? formatBodyMass(row.massG) : "—"}
              </span>
            </div>
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
