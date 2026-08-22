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
import { useId } from "react";
import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  MouseEvent,
  ReactNode,
} from "react";

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
  /**
   * Show the `label` text beside the icon. Inside a `CommandBand`, labels are
   * a MEASURED tier, not a constant: the band probes the row's natural width
   * and sheds labels a `ToolGroup.labelPriority` level at a time until what
   * remains fits, writing `data-labels` on each group. This label collapses
   * via ancestor-attribute CSS when its own group is shed (icon + group
   * eyebrow + tooltip carry the name), so the no-wrap band can never clip or
   * hide a tool group at any width, including when future groups land. No
   * viewport-breakpoint arithmetic to go stale (the 2026-07-24 audit P0 was
   * exactly that staleness). Outside a band the label simply shows.
   */
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
 *
 * A gated tool uses `aria-disabled`, NOT the native `disabled` attribute, so a
 * disabled tool still HOVERS and FOCUSES — and therefore still shows its
 * tooltip + reason `caption` ("Solve a sketch first") to both mouse and
 * keyboard (UI-REVIEW 2026-07-16, Track C P1). It's inert on activation:
 * clicks and Enter/Space are swallowed. Playwright's `toBeDisabled()` /
 * `toBeEnabled()` honor `aria-disabled`, so existing gate assertions still hold.
 *
 * The gate reason also reaches SCREEN READERS: while disabled, the button's
 * `aria-describedby` points at the caption node (which is always in the DOM —
 * the tooltip hides by opacity, not unmount), so `aria-disabled` announces WITH
 * its why. Directly-referenced nodes are exempt from `aria-hidden` in the
 * accessible name/description computation, so the visual tooltip behavior is
 * untouched (BACKLOG P2, UR2 QA pass 2026-07-17).
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
  disabled,
  onClick,
  "aria-describedby": describedByProp,
  ...rest
}: ToolButtonProps) {
  const accessibleName =
    rest["aria-label"] ?? (shortcut ? `${label} — ${shortcut}` : label);
  const isDisabled = disabled === true;
  // Gate-reason description (see the doc comment above): while disabled, the
  // caption node describes the button. A consumer-provided `aria-describedby`
  // is preserved alongside it, never clobbered.
  const reasonId = useId();
  // Truthiness deliberately mirrors the caption render condition below, so the
  // id is only referenced when the caption node actually exists in the DOM.
  const hasGateReason = isDisabled && Boolean(caption);
  const describedBy =
    [describedByProp, hasGateReason ? reasonId : undefined]
      .filter(Boolean)
      .join(" ") || undefined;
  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    if (isDisabled) {
      event.preventDefault();
      return;
    }
    onClick?.(event);
  };

  return (
    <button
      type={type ?? "button"}
      aria-pressed={active}
      aria-disabled={isDisabled || undefined}
      aria-describedby={describedBy}
      aria-label={accessibleName}
      onClick={handleClick}
      className={cx(
        "group/tt relative inline-flex select-none items-center rounded-sm py-1.5",
        // Padding + gap follow the label tier: icon-only spacing when the
        // enclosing CommandBand has measured itself into the icon tier. EVERY
        // tool gets the same comfortable ≥32px target (`min-h-8`), labelled or
        // not, so one band row has one hover geometry; icon-only tools are
        // square (`min-w-8`). This promise was made in 2026-07 and unmet until
        // 2026-07-30, when `py-1.5` turned out to be a class the closed spacing
        // scale never emitted, leaving every band tool 16px tall.
        "min-h-8",
        // The enclosing group's `data-labels` is the ONE mechanism that hides
        // a label. There used to be a second, keyed on the band's own
        // `data-band-tier=icon` — with graduated shedding that selector is
        // actively harmful, not merely redundant: the band passes THROUGH the
        // icon tier while it buys labels back, so a band-level rule would keep
        // every label hidden during the probe, report that each tranche
        // "fits", and then show all of them at once when the final tier lands.
        // Measured exactly that on the part band: 2650.88px of row in a 1280px
        // frame, tier reported "mixed", every group labeled.
        showLabel
          ? "gap-2 px-3 [[data-labels=off]_&]:px-2"
          : "min-w-8 justify-center px-2",
        "transition-colors duration-fast",
        "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
        isDisabled ? "cursor-not-allowed opacity-40" : "hover:bg-carbide",
        active ? "text-brass" : "text-mist",
        className,
      )}
      {...rest}
    >
      <span className="flex shrink-0 items-center">{icon}</span>
      {showLabel ? (
        <span className="block min-w-0 truncate text-left font-display text-2xs uppercase tracking-[0.12em] [[data-labels=off]_&]:hidden">
          {label}
        </span>
      ) : null}

      {/* Active scribe — the accent is a line, never a fill. */}
      {active ? (
        <span
          aria-hidden
          // QA hook: the signature accent is a LINE, so its size is the
          // assertion. It measured 0x0 for months because the `inset-x-1.5` /
          // `h-px` steps were missing from the closed spacing scale, and a 0x0
          // element is invisible in a screenshot review (UI-REVIEW 2026-07-30).
          data-scribe
          className="pointer-events-none absolute inset-x-1.5 bottom-0.5 h-px bg-brass"
        />
      ) : null}

      {/* Tooltip: an anvil stamp with the accelerator engraved, and the quiet
          caption (count / reason) folded onto a second line so the resting
          button stays a single icon-thin row. The z-30 is LOCAL to the
          enclosing stacking context; page-level ordering (band above panels,
          so this stamp never hides behind the feature tree) comes from the
          `zLayer` scale on the band itself. `data-tooltip` is the QA hook for
          z-order/occlusion asserts. */}
      <span
        aria-hidden
        data-tooltip
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
          <span id={reasonId} className="font-data text-2xs text-gauge">
            {caption}
          </span>
        ) : null}
      </span>
    </button>
  );
}

export interface ToolGroupProps extends HTMLAttributes<HTMLDivElement> {
  /** Tracked-caps cluster name (encodes the real taxonomy, not decoration). */
  eyebrow?: string;
  /**
   * How hard this group holds on to its labels when the band runs out of room
   * — HIGHER keeps its words longer (`CommandBand` guarantee #3). Groups that
   * share a value are shed together, so peers are never half-dressed.
   *
   * The scale is per-band and means nothing on its own; what it encodes is
   * INFORMATION PER PIXEL. A label earns its width when the glyph cannot carry
   * the identity — a format code like "3MF" is an identifier no picture can
   * spell, while "Extrude" merely repeats a glyph the eyebrow and tooltip
   * already name. Rank accordingly, and say why at the call site.
   *
   * Left at the default, every group on a surface shares one level and the
   * band flips as a unit — the two-tier behaviour that predates this.
   */
  labelPriority?: number;
}

/**
 * A labeled cluster of tools — the Fusion-style "group" rendered in
 * Plasticity density. The eyebrow names the family (Geometric / Dimensional /
 * Relational / Create); the members sit in a tight row beneath it.
 *
 * `data-labels` is written by the enclosing `CommandBand` after it measures,
 * never rendered here: React would fight the imperative probe for it, and a
 * group that has not been measured yet must default to showing its labels so
 * the band's first measurement sees the widest configuration.
 */
export function ToolGroup({
  eyebrow,
  labelPriority = 0,
  className,
  children,
  ...rest
}: ToolGroupProps) {
  return (
    <div
      role="group"
      aria-label={eyebrow}
      data-label-priority={labelPriority}
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
