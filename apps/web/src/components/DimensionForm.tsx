import { Button, NumberField } from "@loft/design";
import { useState } from "react";

import type { BoxParams } from "../api/tessellate";
import {
  AXES,
  validateDimensions,
  type DimensionDraft,
  type DimensionErrors,
} from "../lib/dimensions";

export interface DimensionFormProps {
  initial: BoxParams;
  /** Called with validated dimensions (mm) — triggers re-tessellation. */
  onApply: (params: BoxParams) => void;
}

/**
 * Keyboard-first parametric entry: type, Enter (or Apply) re-tessellates.
 * Draft state is local; only validated values reach the store.
 */
export function DimensionForm({ initial, onApply }: DimensionFormProps) {
  const [draft, setDraft] = useState<DimensionDraft>({
    x: String(initial.x),
    y: String(initial.y),
    z: String(initial.z),
  });
  const [errors, setErrors] = useState<DimensionErrors>({});

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const result = validateDimensions(draft);
    if (result.ok) {
      setErrors({});
      onApply(result.values);
    } else {
      setErrors(result.errors);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="px-3"
      data-testid="dimension-form"
      noValidate
    >
      <div className="grid grid-cols-3 gap-2">
        {AXES.map((axis) => (
          <NumberField
            key={axis}
            label={axis.toUpperCase()}
            unit="mm"
            value={draft[axis]}
            error={errors[axis] ?? null}
            data-testid={`dim-${axis}`}
            aria-label={`${axis.toUpperCase()} dimension in millimetres`}
            onChange={(event) => {
              const value = event.currentTarget.value;
              setDraft((prev) => ({ ...prev, [axis]: value }));
              setErrors((prev) =>
                prev[axis] ? { ...prev, [axis]: undefined } : prev,
              );
            }}
          />
        ))}
      </div>
      <div className="flex justify-end pt-2">
        <Button type="submit" variant="solid" data-testid="dim-apply">
          Apply
        </Button>
      </div>
    </form>
  );
}
