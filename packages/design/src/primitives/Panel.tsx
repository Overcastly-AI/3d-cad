import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  MouseEvent,
  ReactNode,
} from "react";
import { useId } from "react";

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
  /**
   * Toggle-style cells (mode switches): the selected cell's label carries
   * brass and `aria-pressed` is set. Leave undefined for plain actions.
   */
  selected?: boolean;
  /**
   * Optional scribed glyph, rendered aria-hidden to the left of the
   * label/caption stack — ties title-block actions (export formats, the DRO
   * snap toggle) into the toolbar's icon language. Inherits the label's ink
   * (brass when selected), one palette.
   */
  icon?: ReactNode;
  /**
   * WHY this action is currently gated, in the user's words ("Pick a face
   * first"). Rendered in place of the caption while disabled AND wired as the
   * button's `aria-describedby`, so the reason reaches the eye, the pointer and
   * a screen reader at the same time. Omit it and the cell is still reachable —
   * it just has nothing to explain.
   */
  disabledReason?: string;
}

/**
 * An actionable cell of the title block — same ruled anatomy as the static
 * label/value cells, but pressable. The label carries primary ink (mist)
 * where static cell labels stay gauge: on this panel, mist caps = an action.
 * Hover insets to the carbide ground; the focus ring is drawn inset so it
 * survives the panel's ruled edges.
 *
 * A gated cell uses `aria-disabled`, NOT the native `disabled` attribute — the
 * treatment `ToolButton` has had since 2026-07-16. It was `disabled` +
 * `disabled:pointer-events-none` here until 2026-07-30, which made every editor
 * footer action and every export cell a DISABLED TRAP: a greyed Create could be
 * neither hovered nor focused, so the reason it was grey had nowhere to live and
 * the user's only recourse was guessing (UI-REVIEW 2026-07-30 P2 — this cell is
 * used by 12 editors, so it was the widest instance of the defect in the
 * product). Now it stays in the a11y tree, keeps hover and focus, explains
 * itself through `disabledReason`, and is inert on activation: clicks — and
 * therefore Enter/Space, which dispatch one — are swallowed. Playwright's
 * `toBeDisabled()`/`toBeEnabled()` honour `aria-disabled`, so gate assertions
 * still hold; jest-dom's `toBeDisabled` does not, so jsdom tests assert
 * `aria-disabled` (and that the handler never fires).
 */
export function PanelActionCell({
  label,
  caption,
  selected,
  icon,
  className,
  type,
  disabled,
  disabledReason,
  onClick,
  "aria-describedby": describedByProp,
  ...rest
}: PanelActionCellProps) {
  const isDisabled = disabled === true;
  const reasonId = useId();
  const hasReason = isDisabled && disabledReason !== undefined;
  const describedBy =
    [describedByProp, hasReason ? reasonId : undefined]
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
      aria-pressed={selected}
      aria-disabled={isDisabled || undefined}
      aria-describedby={describedBy}
      onClick={handleClick}
      className={cx(
        "block w-full px-3 py-2 text-left transition-colors duration-fast",
        "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
        isDisabled ? "cursor-not-allowed opacity-50" : "hover:bg-carbide",
        className,
      )}
      {...rest}
    >
      <span className="flex items-center gap-2">
        {icon ? (
          <span
            aria-hidden
            className={cx(
              "flex shrink-0 items-center",
              selected ? "text-brass" : "text-gauge",
            )}
          >
            {icon}
          </span>
        ) : null}
        <span className="min-w-0">
          <span
            className={cx(
              "block font-display text-2xs uppercase tracking-[0.14em]",
              selected ? "text-brass" : "text-mist",
            )}
          >
            {label}
          </span>
          {/* While gated, the REASON takes the caption's line: "Enter" is not
              the useful thing to say about an action that cannot be taken. */}
          {hasReason ? (
            <span
              id={reasonId}
              data-disabled-reason
              className="block font-data text-xs text-gauge"
            >
              {disabledReason}
            </span>
          ) : caption ? (
            <span className="block font-data text-xs text-gauge">
              {caption}
            </span>
          ) : null}
        </span>
      </span>
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
