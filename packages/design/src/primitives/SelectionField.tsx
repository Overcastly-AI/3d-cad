import { cx } from "../cx";
import { CloseIcon } from "./icons";

export interface SelectionOption {
  /** What the pick stores (a sketch line id). */
  value: string;
  /** What the modeller reads ("Front", "Right 1"). */
  label: string;
  selected: boolean;
}

export interface SelectionFieldProps {
  /** Visible label, e.g. "Defines slope". */
  label: string;
  /**
   * The viewport is picking for THIS field. Fusion and Onshape show the one
   * live selection field in the accent; a click in the model fills it.
   */
  armed: boolean;
  /** Make this the live field (a click on its cell). */
  onArm: () => void;
  /** The picks, named, in pick order. Empty: the placeholder. */
  picked: readonly string[];
  /** Shown in the cell while nothing is picked. */
  placeholder?: string;
  /** Drop every pick. Absent: no clear control. */
  onClear?: () => void;
  /** Everything the field may pick, toggled in place (the keyboard route). */
  options: readonly SelectionOption[];
  onToggle: (value: string) => void;
  /** Shown instead of the options when there is nothing to pick yet. */
  emptyHint?: string;
  /** Validation message; flags the cell when present. */
  error?: string | null;
  "data-testid"?: string;
}

/**
 * A SELECTION FIELD: the picks a command takes from the model, as Fusion's
 * "Select" cells and Onshape's query boxes hold them. The cell reads what is
 * picked by name and, when it is the live field, wears the brass accent: a
 * click in the viewport fills the live field. Under it every option is a
 * toggle, so the same picks are reachable without the viewport (keyboard,
 * screen reader, or an option the camera hides).
 *
 * Same title-block anatomy as `SelectField`: label over a carbide inset cell,
 * brass when live or focused, flag on error, every target at least the 24px
 * dense floor.
 */
export function SelectionField({
  label,
  armed,
  onArm,
  picked,
  placeholder = "Select",
  onClear,
  options,
  onToggle,
  emptyHint,
  error,
  "data-testid": testId,
}: SelectionFieldProps) {
  const invalid = Boolean(error);
  const summary = picked.length > 0 ? picked.join(", ") : placeholder;
  return (
    <fieldset
      className="flex min-w-0 flex-col gap-0.5"
      data-testid={testId}
      data-armed={armed ? "true" : "false"}
      aria-invalid={invalid || undefined}
    >
      <legend className="pb-0.5 font-body text-xs text-gauge">{label}</legend>
      <div
        className={cx(
          "flex w-full items-center rounded-sm border bg-carbide",
          invalid
            ? "border-flag"
            : armed
              ? "border-brass outline outline-1 outline-brass/40"
              : "border-etch",
        )}
      >
        <button
          type="button"
          aria-pressed={armed}
          aria-label={`${label}: ${summary}`}
          data-testid={testId === undefined ? undefined : `${testId}-arm`}
          onClick={onArm}
          className={cx(
            "flex min-h-target-dense min-w-0 grow items-center gap-2 px-2 text-left",
            "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brass",
          )}
        >
          <span
            aria-hidden
            className={cx(
              "h-2 w-2 shrink-0 rotate-45 border",
              armed ? "border-brass bg-brass/40" : "border-gauge",
            )}
          />
          <span
            className={cx(
              "truncate font-data text-md",
              picked.length > 0 ? "text-mist" : "text-gauge",
            )}
          >
            {summary}
          </span>
        </button>
        {onClear !== undefined && picked.length > 0 ? (
          <button
            type="button"
            aria-label={`Clear ${label}`}
            data-testid={testId === undefined ? undefined : `${testId}-clear`}
            onClick={onClear}
            className="flex min-h-target-dense w-6 shrink-0 items-center justify-center text-gauge hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
          >
            <CloseIcon size={12} />
          </button>
        ) : null}
      </div>
      {options.length > 0 ? (
        <div className="flex flex-wrap gap-1 pt-0.5">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={option.selected}
              data-testid={
                testId === undefined
                  ? undefined
                  : `${testId}-option-${option.value}`
              }
              onClick={() => onToggle(option.value)}
              className={cx(
                "min-h-target-dense rounded-sm border px-2 font-body text-xs transition-colors duration-fast",
                "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brass",
                option.selected
                  ? "border-brass bg-brass/15 text-brass"
                  : "border-etch bg-carbide text-mist hover:border-gauge",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : emptyHint !== undefined ? (
        <p className="font-body text-2xs text-gauge">{emptyHint}</p>
      ) : null}
      {invalid ? (
        <p className="font-body text-xs text-flag" role="alert">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}
