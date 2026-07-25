/**
 * ISO metric screw threads — the CLIENT half of a tapped hole.
 *
 * A tapped hole's thread is COSMETIC (the kernel decision, recorded in
 * `services/geometry/src/geometry/kernel/threads.py`): the geometry service cuts
 * the tap-drill bore and nothing else, and the `/evaluate` response for a tapped
 * hole is byte-identical — mesh id included — to the same hole untapped. So the
 * UI is the ONLY place a tapped hole is visibly tapped, which makes this module
 * load-bearing rather than cosmetic in the other sense: it owns the designation
 * notation (`M10x1.5`), the derived tap drill, and the tappable-bore band.
 *
 * DUPLICATION, DELIBERATE AND GUARDED. {@link ISO_METRIC_PITCHES} mirrors the
 * kernel's table of the same name. Nothing on the wire exposes it (the contract
 * carries a *designation*, not the catalogue), and a designation picker cannot
 * exist without the catalogue, so the table is duplicated here — and
 * `thread.test.ts` PARSES the kernel module and asserts the two are equal, so
 * drift is a red test rather than a UI that offers a thread the server rejects.
 * Everything else is closed-form arithmetic over that table, identical
 * expressions to the kernel's (IEEE-754 doubles both sides), never a second
 * rounded constant.
 *
 * The server stays the authority. These helpers exist so the everyday path never
 * reaches a rebuild error (`hole_thread_unsupported` / `hole_thread_mismatch`),
 * not to replace the check — a designation the client cannot honour is shown as
 * a field error, and the bore stays editable because a shop's rounded stock
 * drill (6.8 for M8x1.25, where `D - P` is 6.75) is a legitimate tap drill.
 */

/**
 * Basic internal-thread MINOR diameter factor: `D1 = D - 2*(5/8)*H` with the
 * ISO 68-1 fundamental triangle height `H = (sqrt(3)/2)*P`, i.e. `D - 1.0825*P`.
 * Written as the exact expression, not the rounded 1.0825 — the SAME expression
 * the kernel's `_MINOR_DIAMETER_FACTOR` uses, so the accepted band's floor is
 * bit-identical on both sides.
 */
const MINOR_DIAMETER_FACTOR = (1.25 * Math.sqrt(3)) / 2;

/**
 * Match tolerance (mm) when looking an authored `(nominal, pitch)` pair up in
 * the table — the kernel's `_DESIGNATION_TOL`. Real designations differ by
 * >= 0.05 mm in pitch and >= 0.4 mm in nominal diameter, so this can only ever
 * absorb float representation noise, never merge two designations.
 */
const DESIGNATION_TOL = 1e-9;

/**
 * ISO 261 metric screw-thread series: nominal diameter (mm) -> the pitches (mm)
 * the kernel accepts, COARSE first then the fine pitches in descending order.
 * A MIRROR of `geometry.kernel.threads.ISO_METRIC_PITCHES` (M1.6 through M64),
 * kept honest by the drift test in `thread.test.ts`.
 */
export const ISO_METRIC_PITCHES: Readonly<Record<string, readonly number[]>> = {
  "1.6": [0.35, 0.2],
  "2": [0.4, 0.25],
  "2.5": [0.45, 0.35],
  "3": [0.5, 0.35],
  "3.5": [0.6, 0.35],
  "4": [0.7, 0.5],
  "5": [0.8, 0.5],
  "6": [1, 0.75],
  "8": [1.25, 1, 0.75],
  "10": [1.5, 1.25, 1, 0.75],
  "12": [1.75, 1.5, 1.25, 1],
  "14": [2, 1.5, 1],
  "16": [2, 1.5, 1],
  "18": [2.5, 2, 1.5, 1],
  "20": [2.5, 2, 1.5, 1],
  "22": [2.5, 2, 1.5, 1],
  "24": [3, 2, 1.5],
  "27": [3, 2, 1.5],
  "30": [3.5, 3, 2, 1.5],
  "33": [3.5, 3, 2, 1.5],
  "36": [4, 3, 2, 1.5],
  "39": [4, 3, 2, 1.5],
  "42": [4.5, 4, 3, 2, 1.5],
  "45": [4.5, 4, 3, 2, 1.5],
  "48": [5, 4, 3, 2, 1.5],
  "52": [5, 4, 3, 2, 1.5],
  "56": [5.5, 4, 3, 2, 1.5],
  "60": [5.5, 4, 3, 2, 1.5],
  "64": [6, 4, 3, 2, 1.5],
} as const;

/** The nominal diameters (mm) of the series, ascending — the size picker's list. */
export const THREAD_NOMINALS: readonly number[] = Object.keys(
  ISO_METRIC_PITCHES,
)
  .map(Number)
  .sort((a, b) => a - b);

/**
 * The default new-tap designation: M6x1 — the everyday fastener, and the same
 * nominal size the untapped hole form already defaults to (Ø6), so ticking
 * Tapped changes the bore by the pitch, not by a whole size.
 */
export const DEFAULT_THREAD_NOMINAL_MM = 6;
export const DEFAULT_THREAD_PITCH_MM = 1;

/**
 * A designation number without trailing zeros (`10` / `1.5` / `0.35`) — the
 * kernel's `_num` (`f"{value:g}"`). Every table value is a short decimal well
 * inside 6 significant digits, so `String` and `%g` agree exactly. Exported
 * because the size/pitch pickers label their options with it: one spelling of a
 * thread number across the editor, the callout, and the tree.
 */
export function formatThreadNumber(value: number): string {
  return String(value);
}

/**
 * `M<nominal>x<pitch>` — `M6x1`, `M10x1.5`, `M3x0.5`. ASCII `x` and an always-
 * spelled-out pitch, matching the kernel's `format_designation` character for
 * character: the callout the UI stamps is the callout the drawing/BOM will
 * derive, so there is one notation, not a display variant.
 */
export function formatDesignation(
  nominalDiameterMm: number,
  pitchMm: number,
): string {
  return `M${formatThreadNumber(nominalDiameterMm)}x${formatThreadNumber(pitchMm)}`;
}

/** The standard pitches for a nominal diameter, coarse first; empty if unknown. */
export function pitchesFor(nominalDiameterMm: number): readonly number[] {
  const key = Object.keys(ISO_METRIC_PITCHES).find(
    (k) => Math.abs(Number(k) - nominalDiameterMm) <= DESIGNATION_TOL,
  );
  return key === undefined ? [] : (ISO_METRIC_PITCHES[key] ?? []);
}

/**
 * The COARSE pitch of a nominal diameter (the table's first entry) — what a
 * designation defaults to when the size changes, because coarse is what a shop
 * taps unless a drawing says otherwise. `null` for a size off the series.
 */
export function coarsePitchFor(nominalDiameterMm: number): number | null {
  return pitchesFor(nominalDiameterMm)[0] ?? null;
}

/** True when `(nominal, pitch)` is a real ISO 261 combination the kernel knows. */
export function isSupportedDesignation(
  nominalDiameterMm: number,
  pitchMm: number,
): boolean {
  return pitchesFor(nominalDiameterMm).some(
    (pitch) => Math.abs(pitch - pitchMm) <= DESIGNATION_TOL,
  );
}

/**
 * The ISO recommended tap drill `D - P` (mm) — 5.0 for M6x1, 8.5 for M10x1.5,
 * 6.75 for M8x1.25, matching the published metric tap-drill tables (and the
 * kernel's `ResolvedThread.tap_drill_diameter_mm`, same expression, same
 * doubles). This is the value the editor derives into the bore field.
 */
export function tapDrillMm(nominalDiameterMm: number, pitchMm: number): number {
  return nominalDiameterMm - pitchMm;
}

/**
 * Basic internal minor diameter `D - 1.0825*P` (mm) — 100% thread depth, the
 * SMALLEST hole the tap can enter and the floor of the accepted bore band.
 */
export function minorDiameterMm(
  nominalDiameterMm: number,
  pitchMm: number,
): number {
  return nominalDiameterMm - MINOR_DIAMETER_FACTOR * pitchMm;
}

/**
 * True when `boreMm` is a hole this designation can actually be tapped in — the
 * kernel's `check_tap_drill_bore` band `[minor, nominal)`, same predicate and
 * same tolerance. Wide enough to accept a shop table's rounded stock drill
 * (6.8 for M8x1.25), narrow enough that a wrong designation cannot pass.
 */
export function boreFitsThread(
  nominalDiameterMm: number,
  pitchMm: number,
  boreMm: number,
): boolean {
  return (
    boreMm >= minorDiameterMm(nominalDiameterMm, pitchMm) - DESIGNATION_TOL &&
    boreMm < nominalDiameterMm
  );
}
