/**
 * Toolbar primitives — the grouped-icon layer that carries Loft's growing
 * tool count (frontend-design plan, docs/design/toolbar-system.md). Built ON
 * the existing machine-shop token system, not beside it: square corners,
 * hairline rules, scribed icons, and brass spent only on the active scribe —
 * never a filled button. Chrome recedes; the viewport keeps the pixels.
 *
 * Keyboard is still the primary surface (the global sketch key handler is
 * untouched); these buttons are the DISCOVERABLE surface, and each teaches its
 * accelerator through a `Kbd` chip in the tooltip — icons for the eye, letters
 * for the hands.
 */
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

import { cx } from "../cx";

/** A shortcut chip — a small stamped key, brass on the carbide ground. */
export function Kbd({ className, ...rest }: HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cx(
        "inline-flex min-w-4 items-center justify-center rounded-sm border border-hairline",
        "bg-carbide px-1 py-px font-data text-2xs not-italic leading-none text-brass",
        className,
      )}
      {...rest}
    />
  );
}

export interface ToolButtonProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "aria-label"
> {
  /** Scribed glyph (an icon component's element). Rendered aria-hidden. */
  icon: ReactNode;
  /** Human name — the tooltip title and the default accessible name. */
  label: string;
  /** Keyboard accelerator, shown as a `Kbd` chip in the tooltip. */
  shortcut?: string;
  /** Toggle/selected state — sets `aria-pressed` and the brass scribe. */
  active?: boolean;
  /** Show the `label` text beside the icon (the feature toolbar does). */
  showLabel?: boolean;
  /** Quiet supplement (count / reason) — engraved in the tooltip, not stacked. */
  caption?: ReactNode;
  /**
   * Where the tooltip hangs. Top-anchored strips drop it BELOW (default);
   * bottom-anchored surfaces (the viewport's view rail) raise it ABOVE so the
   * window edge never clips it.
   */
  tooltipSide?: "bottom" | "top";
  /** Override the computed accessible name (label + shortcut otherwise). */
  "aria-label"?: string;
}

/**
 * One tool. Icon-forward and dense; the label rides along only where the
 * surface has room (`showLabel`). The tooltip appears on hover AND keyboard
 * focus (a11y), sits BELOW the button so the top-anchored strip never clips
 * it, and is aria-hidden so the accessible name isn't announced twice.
 */
export function ToolButton({
  icon,
  label,
  shortcut,
  active,
  showLabel,
  caption,
  tooltipSide = "bottom",
  className,
  type,
  ...rest
}: ToolButtonProps) {
  const accessibleName =
    rest["aria-label"] ?? (shortcut ? `${label} — ${shortcut}` : label);

  return (
    <button
      type={type ?? "button"}
      aria-pressed={active}
      aria-label={accessibleName}
      className={cx(
        "group/tt relative inline-flex select-none items-center gap-2 rounded-sm",
        showLabel ? "px-3 py-1.5" : "px-2 py-1.5",
        "transition-colors duration-fast hover:bg-carbide",
        "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
        "disabled:opacity-40 disabled:pointer-events-none",
        active ? "text-brass" : "text-mist",
        className,
      )}
      {...rest}
    >
      <span className="flex shrink-0 items-center">{icon}</span>
      {showLabel ? (
        <span className="min-w-0 truncate text-left font-display text-2xs uppercase tracking-[0.12em]">
          {label}
        </span>
      ) : null}

      {/* Active scribe — the accent is a line, never a fill. */}
      {active ? (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-x-1.5 bottom-0.5 h-px bg-brass"
        />
      ) : null}

      {/* Tooltip: an anvil stamp with the accelerator engraved, and the quiet
          caption (count / reason) folded onto a second line so the resting
          button stays a single icon-thin row. */}
      <span
        aria-hidden
        className={cx(
          "pointer-events-none absolute left-1/2 z-30 -translate-x-1/2",
          tooltipSide === "bottom" ? "top-full mt-1.5" : "bottom-full mb-1.5",
          "flex flex-col gap-0.5 whitespace-nowrap border border-hairline bg-anvil px-2 py-1",
          "font-body text-2xs text-mist opacity-0",
          "group-hover/tt:opacity-100 group-focus-visible/tt:opacity-100",
          "motion-safe:transition-opacity motion-safe:duration-fast",
        )}
      >
        <span className="flex items-center gap-1.5">
          {label}
          {shortcut ? <Kbd>{shortcut}</Kbd> : null}
        </span>
        {caption ? (
          <span className="font-data text-2xs text-gauge">{caption}</span>
        ) : null}
      </span>
    </button>
  );
}

export interface ToolGroupProps extends HTMLAttributes<HTMLDivElement> {
  /** Tracked-caps cluster name (encodes the real taxonomy, not decoration). */
  eyebrow?: string;
}

/**
 * A labeled cluster of tools — the Fusion-style "group" rendered in
 * Plasticity density. The eyebrow names the family (Geometric / Dimensional /
 * Relational / Create); the members sit in a tight row beneath it.
 */
export function ToolGroup({
  eyebrow,
  className,
  children,
  ...rest
}: ToolGroupProps) {
  return (
    <div
      role="group"
      aria-label={eyebrow}
      className={cx("flex flex-col justify-center px-1.5 py-1", className)}
      {...rest}
    >
      {eyebrow ? (
        <span className="px-1 pb-0.5 font-display text-2xs uppercase tracking-[0.16em] text-gauge">
          {eyebrow}
        </span>
      ) : null}
      <div className="flex items-stretch gap-0.5">{children}</div>
    </div>
  );
}
