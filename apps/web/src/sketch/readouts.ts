/**
 * The solver's per-dimension readouts, merged into one lookup (split out of
 * `constraints.ts`, which re-exports them; behaviour unchanged).
 */
import type { components } from "@loft/ts-client/gateway";

/**
 * One solved dimension readout, lined to its authored constraint by
 * `constraint_index`: for a DRIVING dim `value_mm` is the evaluated
 * expression/literal; for a DRIVEN dim it is measured from the solved geometry.
 */
export type SolvedDimension = components["schemas"]["SolvedDimension"];
/**
 * One solved ANGULAR readout, in degrees, on the same `constraint_index` space
 * as {@link SolvedDimension}. The contract keeps the two lists apart on purpose
 * — there is no honest millimetre value for an angle, and `value_mm` is a
 * required field every linear consumer reads unconditionally — so the merge
 * happens here, once, in {@link solvedReadouts}.
 */
export type SolvedAngle = components["schemas"]["SolvedAngle"];

/**
 * THE readout the sketcher shows for one dimension, whatever its unit — the
 * single merge point for `SolvedSketch.dimensions` + `SolvedSketch.angles`.
 *
 * QA-R2: the two wire lists were never merged, so `apps/web/src` read the
 * linear list alone and NOTHING read `angles`. An angle driven by an expression
 * therefore kept the placeholder degrees the client had guessed while the
 * solver moved the model: authored 30, re-driven `15*3`, the geometry went to
 * 45.000 and the glyph read `30°` forever. An annotation that contradicts the
 * geometry is worse than an absent one, because it looks authoritative.
 *
 * `value` is in the constraint's OWN unit and `unit` says which, so a consumer
 * cannot read degrees out of something named for millimetres — the property the
 * split existed to protect, kept without forcing every reader to merge lists.
 */
export interface SolvedReadout {
  constraint_index: number;
  driving: boolean;
  expression: string | null;
  name: string | null;
  /** The solved value in `unit`: evaluated if driving, measured if driven. */
  value: number;
  unit: "mm" | "deg";
}

/**
 * Merge the solver's two per-dimension lists into one lookup by
 * `constraint_index`. A constraint is linear or angular and never both, so an
 * index collision means the payload disagrees with itself; the LINEAR entry
 * wins and the angular one is dropped, but the unit rides along either way, so
 * the readers below still refuse a readout whose unit does not match the
 * constraint they are drawing. Silently showing the wrong unit is the failure
 * this whole split exists to prevent.
 */
export function solvedReadouts(
  dimensions: readonly SolvedDimension[],
  angles: readonly SolvedAngle[],
): Map<number, SolvedReadout> {
  const byIndex = new Map<number, SolvedReadout>();
  for (const angle of angles) {
    byIndex.set(angle.constraint_index, {
      constraint_index: angle.constraint_index,
      driving: angle.driving,
      expression: angle.expression ?? null,
      name: angle.name ?? null,
      value: angle.value_deg,
      unit: "deg",
    });
  }
  for (const dimension of dimensions) {
    byIndex.set(dimension.constraint_index, {
      constraint_index: dimension.constraint_index,
      driving: dimension.driving,
      expression: dimension.expression ?? null,
      name: dimension.name ?? null,
      value: dimension.value_mm,
      unit: "mm",
    });
  }
  return byIndex;
}

/**
 * The sketch's own named DRIVING dimensions a dimension formula may read
 * (PART-PARAMETERS step 8: the dimension box offers them as it does the part's
 * parameters), each at its number: the solver's reading when there is one,
 * else the authored value. `except` is the dimension being edited (a formula
 * may not read itself). A driven dimension is measured after the solve, so the
 * server refuses a reference to it, and it is not offered.
 */
export function sketchDimensionScope(
  constraints: readonly object[],
  solved: ReadonlyMap<number, SolvedReadout>,
  except: number | null,
): { name: string; value: number }[] {
  const out: { name: string; value: number }[] = [];
  constraints.forEach((constraint, index) => {
    if (index === except) return;
    const c = constraint as {
      name?: string | null;
      driving?: boolean;
      value_mm?: number;
      value_deg?: number;
    };
    if (typeof c.name !== "string" || c.name === "" || c.driving === false) {
      return;
    }
    const value = solved.get(index)?.value ?? c.value_mm ?? c.value_deg;
    if (typeof value === "number") out.push({ name: c.name, value });
  });
  return out;
}

/** The readout for `index`, or undefined unless its unit is the one asked for. */
export function readoutIn(
  solved: ReadonlyMap<number, SolvedReadout> | undefined,
  index: number | null | undefined,
  unit: "mm" | "deg",
): SolvedReadout | undefined {
  if (solved === undefined || index === null || index === undefined) {
    return undefined;
  }
  const readout = solved.get(index);
  return readout?.unit === unit ? readout : undefined;
}
