/**
 * Architectural feet-inch lengths to 1/16 in (HOUSE-DRAWINGS): `24'-0"`,
 * `8'-1 1/8"`, `6'-10 1/2"`, and a length under a foot as inches alone
 * (`5 1/2"`, `3/4"`). Rounded half up to the nearest sixteenth, the fraction
 * in lowest terms.
 *
 * The twin of `loft_wire.feet_inches.feet_inches`, which prints the composed
 * sheet: the sheet and the screen must never print different numbers, so both
 * take the SAME IEEE-double steps (identical in Python and JavaScript). The
 * length in 32nds, `t = |mm| / 25.4 * 32`, within `SNAP_32NDS` of a whole 32nd
 * IS that 32nd (an odd one is a half-sixteenth, rounded up, in integers);
 * otherwise `floor(x * 16 + 0.5)`. `feetInches.vectors.json` (10,000 values)
 * pins both to the same text.
 */

const MM_PER_INCH = 25.4;

/** How close (in 32nds) a length must be to a whole 32nd to be it. */
const SNAP_32NDS = 1e-6;

function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b);
}

/** |mm| in whole sixteenths of an inch, rounded half up (the Python twin). */
export function sixteenths(mm: number): number {
  const x = Math.abs(mm) / MM_PER_INCH;
  const t = x * 32;
  const nearest = Math.floor(t + 0.5);
  if (Math.abs(t - nearest) <= SNAP_32NDS) {
    // Exact in integers: an odd 32nd is a half-sixteenth, and half goes up.
    return Math.floor((nearest + 1) / 2);
  }
  return Math.floor(x * 16 + 0.5);
}

/** Canonical millimetres as architectural feet-inch (1/16 in). */
export function formatFeetInches(mm: number): string {
  const denominator = 16;
  const steps = sixteenths(mm);
  const perFoot = 12 * denominator;
  const feet = Math.floor(steps / perFoot);
  const rest = steps % perFoot;
  const inches = Math.floor(rest / denominator);
  const part = rest % denominator;
  const divisor = part === 0 ? 1 : gcd(part, denominator);
  const frac = part === 0 ? "" : `${part / divisor}/${denominator / divisor}`;
  let text: string;
  if (feet > 0) {
    text = `${feet}'-${frac ? `${inches} ${frac}` : `${inches}`}"`;
  } else if (inches > 0) {
    text = frac ? `${inches} ${frac}"` : `${inches}"`;
  } else {
    text = frac ? `${frac}"` : `0"`;
  }
  return mm < 0 && steps > 0 ? `-${text}` : text;
}
