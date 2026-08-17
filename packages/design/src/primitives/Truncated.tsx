/**
 * TRUNCATION THAT TELLS THE TRUTH.
 *
 * A name that does not fit its cell must say so and stay recoverable. Tailwind's
 * `truncate` (`overflow:hidden; text-overflow:ellipsis; white-space:nowrap`)
 * only does that when it is on the box the TEXT lives in and that box is
 * block-level — and the register got neither: the class sat on the `<td>` while
 * the link inside was `inline-flex`, which is an atomic inline box. It clipped
 * mid-glyph with no ellipsis, no `title`, and no cue that anything was missing,
 * so "Motor mount adapter plate rev C" and "Motor mount adapter plate rev D"
 * rendered identically (UI-REVIEW 2026-08-17 P1-2, measured: computed
 * `text-overflow: clip`, `title: null`).
 *
 * Two shapes, because the element is not always ours to render:
 *
 *  - `Truncated` for text we own.
 *  - `truncatedProps` for text a CALLER renders (the register's `openLink` hands
 *    back the page's own `<Link>`): it returns the class and the `title` to
 *    spread, so the fix travels with the pattern instead of being retyped.
 *
 * Both stamp `title` unconditionally. Measuring the overflow first would let the
 * tooltip appear only when it is needed, but it costs a ResizeObserver per row
 * and gets the answer wrong on the frame where the column resizes; a tooltip
 * that repeats a fully-visible name is harmless, and a missing one is the defect
 * this exists to close. (Onshape's and Fusion's document lists do the same.)
 *
 * `min-h-target-dense` is carried here rather than left to the caller: the
 * previous class string used `inline-flex items-center` to reach the 24 px tap
 * target, and that inline-flex WAS the bug. `block` + a min height keeps the
 * target and lets the ellipsis work, and `leading-6` centres the text in it.
 */
import { cx } from "../cx";
import type { ReactNode } from "react";

/**
 * The truncating box itself. `min-w-0` so it can shrink inside a flex parent
 * (without it a flex item's automatic minimum size is its content, and the text
 * pushes the cell wide instead of ellipsising).
 */
export const TRUNCATED_CLASS =
  "block min-h-target-dense min-w-0 max-w-full truncate leading-6";

/**
 * Class + `title` for an element somebody else renders.
 *
 * @param text  the FULL string — what the title must carry, not the visible cut
 * @param className  the caller's own ink (colour, face, focus ring)
 */
export function truncatedProps(
  text: string,
  className?: string,
): { className: string; title: string } {
  return { className: cx(TRUNCATED_CLASS, className), title: text };
}

export interface TruncatedProps {
  /** The full string — rendered, and stamped on `title`. */
  text: string;
  /** Rendered instead of the bare text (e.g. marked-up), when supplied. */
  children?: ReactNode;
  className?: string;
  "data-testid"?: string;
}

/** One line of text that ellipsises and keeps the full string reachable. */
export function Truncated({
  text,
  children,
  className,
  "data-testid": testid,
}: TruncatedProps) {
  return (
    <span
      className={cx(TRUNCATED_CLASS, className)}
      title={text}
      data-testid={testid}
    >
      {children ?? text}
    </span>
  );
}
