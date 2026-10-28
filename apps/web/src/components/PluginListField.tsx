/**
 * A plugin's LIST input in the generated form (CASEWORK): its rows as an add
 * and remove list, each row its fields (numbers in the document unit,
 * choices as selects), as Mozaik lists a run's cabinets. "Add" copies the
 * last row, so the next box starts like the one before. The text and its
 * checks are `features/pluginList`'s.
 */
import {
  Button,
  type LengthUnit,
  lengthUnitLabel,
  SelectField,
} from "@loft/design";

import {
  addRow,
  type ListInput,
  listRows,
  removeRow,
  setRowField,
} from "../features/pluginList";
import { ValueField } from "./ValueField";

export interface PluginListFieldProps {
  input: ListInput;
  /** The list's text: its rows as JSON. */
  value: string;
  unit: LengthUnit;
  /** Field errors by `<input>/<row>/<field>`, and the list's own. */
  errors: Readonly<Record<string, string>>;
  onChange: (text: string) => void;
  "data-testid": string;
}

export function PluginListField({
  input,
  value,
  unit,
  errors,
  onChange,
  "data-testid": testId,
}: PluginListFieldProps) {
  const rows = listRows(value);
  const item = input.item_label;
  const canRemove = rows.length > input.min_items;
  const canAdd = rows.length < input.max_items;
  return (
    <fieldset data-testid={testId} className="flex flex-col gap-1.5">
      <legend className="font-body text-xs text-gauge">
        {input.label} ({rows.length})
      </legend>
      {rows.map((row, index) => (
        <div
          // Rows have no identity of their own: their place is what they are.
          key={index}
          data-testid={`${testId}-row`}
          className="flex flex-col gap-1 border border-hairline bg-carbide/40 px-2 pb-2 pt-1"
        >
          <div className="flex items-center gap-2">
            <span className="grow font-display text-2xs uppercase tracking-[0.14em] text-gauge">
              {item} {index + 1}
            </span>
            <Button
              size="dense"
              data-testid={`${testId}-remove`}
              aria-label={`Remove ${item.toLowerCase()} ${index + 1}`}
              disabled={!canRemove}
              onClick={() => onChange(removeRow(value, index))}
            >
              Remove
            </Button>
          </div>
          <div className="grid grid-cols-2 gap-x-2 gap-y-1">
            {input.fields.map((field) => {
              const text = row[field.name] ?? "";
              const error =
                errors[`${input.name}/${index}/${field.name}`] ?? null;
              const id = `${testId}-${index}-${field.name}`;
              const set = (next: string) =>
                onChange(setRowField(value, index, field.name, next));
              if (field.kind === "choice") {
                return (
                  <SelectField
                    key={field.name}
                    label={field.label}
                    data-testid={id}
                    value={text}
                    error={error}
                    options={field.options.map((o) => ({
                      value: o.value,
                      label: o.label,
                    }))}
                    onChange={(e) => set(e.target.value)}
                  />
                );
              }
              return (
                <ValueField
                  key={field.name}
                  label={field.label}
                  unit={
                    field.kind === "length"
                      ? lengthUnitLabel(unit)
                      : field.kind === "angle"
                        ? "°"
                        : ""
                  }
                  kind={
                    field.kind === "length"
                      ? "length"
                      : field.kind === "angle"
                        ? "angle"
                        : "int"
                  }
                  inputMode="text"
                  data-testid={id}
                  value={text}
                  error={error}
                  onValueChange={set}
                  onFocus={(e) => e.currentTarget.select()}
                />
              );
            })}
          </div>
        </div>
      ))}
      <Button
        data-testid={`${testId}-add`}
        disabled={!canAdd}
        onClick={() => onChange(addRow(input, value, unit))}
      >
        Add {item.toLowerCase()}
      </Button>
    </fieldset>
  );
}
