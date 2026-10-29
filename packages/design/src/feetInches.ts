/**
 * Architectural feet-inch lengths to 1/16 in (HOUSE-DRAWINGS): `24'-0"`,
 * `8'-1 1/8"`, `6'-10 1/2"`, and a length under a foot as inches alone
 * (`5 1/2"`, `3/4"`). Rounded half up to the nearest sixteenth, the fraction
 * in lowest terms. The twin of `loft_wire.feet_inches.feet_inches`, which
 * prints the same text on the composed sheet, pinned to the same cases.
 */

const MM_PER_INCH = 25.4;

function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b);
}

/** Canonical millimetres as architectural feet-inch (1/`denominator` in). */
export function formatFeetInches(mm: number, denominator = 16): string {
  const exact = (mm / MM_PER_INCH) * denominator;
  const steps = Math.floor(Math.abs(exact) + 0.5);
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
  return exact < 0 && steps > 0 ? `-${text}` : text;
}
