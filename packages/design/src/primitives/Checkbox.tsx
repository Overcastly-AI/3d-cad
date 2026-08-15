import { cx } from "../cx";
import { CheckIcon } from "./icons";

export interface CheckboxProps {
  /** Visible label naming what the box turns on, e.g. "Merge result". */
  label: string;
  /** Current state. */
  checked: boolean;
  /** Called with the NEXT state on toggle. */
  onChange: (checked: boolean) => void;
  /** Optional quiet helper line under the label. */
  description?: string;
  disabled?: boolean;
  "data-testid"?: string;
  "aria-label"?: string;
}

/**
 * A ruled check cell — a scribed square that fills with brass + the house
 * `CheckIcon` when on, quiet carbide when off. Same title-block anatomy as the
 * field primitives (carbide inset, etch border, brass focus/accent) so a
 * boolean option reads as a member of the instrument panel, not a stock form
 * control. A `role="checkbox"` button carries native Space/Enter toggling and
 * an accessible `aria-checked`; app code never restyles a raw <input>.
 *
 * TARGET SIZE (FB-19). With no `description`, this control was exactly as tall
 * as its own 16px check square (`h-4`) — under the product's 24px floor
 * (`target.dense`, WCAG 2.2 SC 2.5.8), which the density pass would otherwise
 * have made worse rather than better. The floor is on the primitive so every
 * checkbox in the product gets it, and it is a MINIMUM: a row with a
 * description is still as tall as its content (measured on the extrude card's
 * old two-line merge cell: 32.3px).
 */
export function Checkbox({
  label,
  checked,
  onChange,
  description,
  disabled = false,
  ...rest
}: CheckboxProps) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx(
        "group flex min-h-target-dense gap-2 text-left",
        // Centred on a single-line label, top-aligned once a description turns
        // the cell into a paragraph (the box belongs beside the FIRST line).
        description === undefined ? "items-center" : "items-start",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass",
        disabled && "cursor-not-allowed opacity-40",
      )}
      {...rest}
    >
      <span
        aria-hidden
        className={cx(
          "mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border transition-colors duration-fast",
          checked
            ? "border-brass bg-brass/15 text-brass"
            : "border-etch bg-carbide text-transparent group-hover:border-gauge",
        )}
      >
        <CheckIcon size={12} />
      </span>
      <span className="flex flex-col gap-0.5">
        <span className="font-body text-xs text-mist">{label}</span>
        {description !== undefined ? (
          <span className="font-body text-2xs leading-snug text-gauge">
            {description}
          </span>
        ) : null}
      </span>
    </button>
  );
}
