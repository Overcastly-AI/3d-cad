import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

import { cx } from "../cx";

/**
 * The title-block panel — Loft's signature element (frontend-design plan,
 * 2026-07-10). Composed like an engineering-drawing title block: an outer
 * ruled frame, hairline-divided sections with tracked eyebrow labels, and
 * label/value cells set in the data face. Cells are square-cornered on
 * purpose; the data is the ornament.
 */
export function Panel({ className, ...rest }: HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={cx(
        "border border-hairline bg-anvil text-mist rounded-none",
        className,
      )}
      {...rest}
    />
  );
}

export interface PanelSectionProps extends HTMLAttributes<HTMLDivElement> {
  /** Tracked-caps eyebrow, e.g. "MASS PROPERTIES". */
  eyebrow: string;
}

export function PanelSection({
  eyebrow,
  className,
  children,
  ...rest
}: PanelSectionProps) {
  return (
    <div
      className={cx("border-b border-hairline last:border-b-0", className)}
      role="group"
      aria-label={eyebrow}
      {...rest}
    >
      <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge px-3 pt-3 pb-1">
        {eyebrow}
      </h2>
      <div className="pb-2">{children}</div>
    </div>
  );
}

export interface PanelRowProps {
  label: string;
  /** Unit rendered after the value, quiet. */
  unit?: string;
  children: ReactNode;
  "data-testid"?: string;
}

export interface PanelActionCellProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** The action, tracked caps — e.g. "STEP". */
  label: string;
  /** Quiet one-line description under the label — e.g. "Exact B-rep". */
  caption?: string;
}

/**
 * An actionable cell of the title block — same ruled anatomy as the static
 * label/value cells, but pressable. The label carries primary ink (mist)
 * where static cell labels stay gauge: on this panel, mist caps = an action.
 * Hover insets to the carbide ground; the focus ring is drawn inset so it
 * survives the panel's ruled edges.
 */
export function PanelActionCell({
  label,
  caption,
  className,
  type,
  ...rest
}: PanelActionCellProps) {
  return (
    <button
      type={type ?? "button"}
      className={cx(
        "block w-full px-3 py-2 text-left transition-colors duration-fast",
        "hover:bg-carbide",
        "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
        "disabled:opacity-50 disabled:pointer-events-none",
        className,
      )}
      {...rest}
    >
      <span className="block font-display text-2xs uppercase tracking-[0.14em] text-mist">
        {label}
      </span>
      {caption ? (
        <span className="block font-data text-xs text-gauge">{caption}</span>
      ) : null}
    </button>
  );
}

/** One ruled label/value cell of the title block. */
export function PanelRow({ label, unit, children, ...rest }: PanelRowProps) {
  return (
    <div
      className="flex items-baseline gap-2 px-3 py-1"
      data-testid={rest["data-testid"]}
    >
      <span className="font-body text-xs text-gauge min-w-12 shrink-0">
        {label}
      </span>
      <span className="font-data text-base text-mist text-right grow tabular-nums break-all">
        {children}
      </span>
      {unit ? (
        <span className="font-body text-xs text-gauge shrink-0">{unit}</span>
      ) : null}
    </div>
  );
}
