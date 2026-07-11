import type { ButtonHTMLAttributes } from "react";

import { cx } from "../cx";

export interface SketchGlyphProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /**
   * Annotation ink: `quiet` = geometric constraints (gauge), `accent` =
   * driving dimensions (brass — THE parametric handles), `flag` =
   * conflicting/redundant constraints.
   */
  tone?: "quiet" | "accent" | "flag";
  /** Selected glyph (pending Delete) — brass with a scribe underline. */
  selected?: boolean;
}

const tones = {
  quiet: "text-gauge hover:text-mist",
  accent: "text-brass hover:text-brass-hover",
  flag: "text-flag",
} as const;

/**
 * In-viewport constraint annotation — engineering-drawing notation, not a
 * badge: bare data-face text (H / V / C / FIX / 40 / R12.5) floating by the
 * geometry it governs. No background, no border, no radius; state is carried
 * by ink alone. Interactive (select / open the dimension editor), so it is
 * a real button with a visible focus ring.
 */
export function SketchGlyph({
  tone = "quiet",
  selected,
  className,
  type,
  ...rest
}: SketchGlyphProps) {
  return (
    <button
      type={type ?? "button"}
      aria-pressed={selected}
      className={cx(
        "select-none whitespace-nowrap bg-transparent p-0.5 font-data text-xs leading-none",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brass",
        selected
          ? "text-brass underline decoration-brass underline-offset-4"
          : tones[tone],
        className,
      )}
      {...rest}
    />
  );
}
