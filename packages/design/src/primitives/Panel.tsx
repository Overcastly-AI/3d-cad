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
      {/*
        THE RULED CAPTION BAR — the density pass's one bold move (founder,
        2026-08-28: "not in any form compact like the header").

        The eyebrow used to float on `pt-3 pb-1` with the body carrying another
        `pb-2`: 39px of chrome per section before a single row of content, and
        an inspector with six sections spent 234px saying nothing. A drawing's
        schedule does not float its captions — it RULES them, and this file has
        claimed the title-block metaphor since day one without ever drawing that
        line. Ruling the caption is what lets the padding go: the rule does the
        separating that 12px of air was doing, so the section reads as MORE of a
        title block at 24px than it did at 39.

        Measured on the part workspace (`e2e/panel-density.spec.ts`, before vs
        after): section-to-section pitch 122.5px -> 101px, and the caption band
        itself is a 24px row like every other row in the panel.

        The accessible name is untouched (`aria-label={eyebrow}`) — several suites
        address these groups by name, and a density pass may not rename anything.
      */}
      <h2 className="flex min-h-target-dense items-center border-b border-hairline px-3 py-1 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
        {eyebrow}
      </h2>
      <div className="py-0.5">{children}</div>
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
        // `min-h-target` (32px, comfortable) rather than the 24px dense floor:
        // this is an ACTION, and the density pass is not licence to shrink the
        // things a modeller commits with. The 8px of vertical padding it used
        // to carry on top of that was slack, not target.
        "block min-h-target w-full px-3 py-1 text-left transition-colors duration-fast",
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
      // ONE 24px BAND per cell — the same target height the header's tool row
      // holds (`target.dense`, WCAG 2.2 SC 2.5.8), so a modeller reading the
      // inspector is reading the toolbar's rhythm. `py-1` + a 13px value made
      // this 27.5px, which is the pitch of a settings dialog, not an instrument.
      //
      // `items-center` rather than `items-baseline`: inside a min-height band a
      // baseline pins the text to the TOP and leaves the slack below, which is
      // what makes a nominally-dense row still photograph as loose. The
      // label/value size difference is 1px, so nothing reads as misaligned.
      className="flex min-h-target-dense items-center gap-2 px-3 py-0.5"
      // Density hook: `e2e/panel-density.spec.ts` measures the PITCH of this
      // row family against the header's tool row. Most cells are read-only
      // readouts that carry no testid because nothing drives them, so the
      // family needs a name of its own or the measurement has to guess
      // structurally — and a structural guess breaks the moment the markup does.
      data-panel-cell
      data-testid={rest["data-testid"]}
    >
      <span className="font-body text-xs text-gauge min-w-12 shrink-0">
        {label}
      </span>
      <span className="font-data text-sm text-mist text-right grow tabular-nums break-all">
        {children}
      </span>
      {unit ? (
        <span className="font-body text-xs text-gauge shrink-0">{unit}</span>
      ) : null}
    </div>
  );
}
