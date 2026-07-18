/**
 * The document-unit selector — the editor-chrome instrument that sets how every
 * dimension in this part/assembly is typed and read (docs/design/units.md §U2).
 *
 * It is DISPLAY metadata only: changing it never re-solves or migrates a stored
 * value. The canonical mm the API carries is untouched; the whole viewport of
 * dimension cells + readouts simply re-formats into the new unit. The page owns
 * the persistence (a document PATCH under its OCC token) and passes the loaded
 * unit down; this component is a controlled, keyboard-first select.
 */
import {
  InlineSelect,
  LENGTH_UNITS,
  type LengthUnit,
  lengthUnitLabel,
} from "@loft/design";

const OPTIONS = LENGTH_UNITS.map((u) => ({
  value: u,
  label: lengthUnitLabel(u),
}));

export interface DocumentUnitSelectProps {
  /** The document's current display unit. */
  value: LengthUnit;
  /** Persist a new display unit (the page PATCHes the document). */
  onChange: (unit: LengthUnit) => void;
  /** True while the unit PATCH is in flight — the control is briefly disabled. */
  busy?: boolean;
}

export function DocumentUnitSelect({
  value,
  onChange,
  busy = false,
}: DocumentUnitSelectProps) {
  return (
    <InlineSelect
      eyebrow="Units"
      aria-label="Document length unit"
      data-testid="document-unit-select"
      value={value}
      disabled={busy}
      onChange={(event) => onChange(event.target.value as LengthUnit)}
      options={OPTIONS}
    />
  );
}
