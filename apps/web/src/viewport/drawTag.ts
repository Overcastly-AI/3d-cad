/**
 * What the sketcher's draw-time boxes share (`DrawDimensionTag`, `PointEntry`):
 * where they stack, how a size reads, and the names a formula typed into one
 * of them may use (QA-RECT-BOX-NAMES).
 */
import { formatLength } from "@loft/design";
import { useMemo } from "react";

import {
  type ScopeDimension,
  scopeQuantities,
  useParameterScopeStore,
} from "../features/fieldFormulas";
import type { Quantity } from "../features/expr";
import { sketchDimensionScope, solvedReadouts } from "../sketch/readouts";
import { useSketchStore } from "../sketch/store";

/** The tag rail rides with the snap mark, under the HUD strips. */
export const DIMENSION_TAG_Z_RANGE: [number, number] = [21, 0];

/** Display precision for a size cell — a size, not a coordinate readout. */
export const sizeText = (
  mm: number,
  unit: Parameters<typeof formatLength>[1],
): string =>
  formatLength(mm, unit, { unitSuffix: false, maxFractionDigits: 2 });

/**
 * Put keys typed before a cell existed into it (FLOW-A1's replay) AS TYPING:
 * the native setter plus an `input` event, so the cell's own `onChange` sees
 * the text (its `fx` mark, its hint, its list) exactly as if it had been
 * typed there, and no second write races the keys that follow.
 */
export function replayText(
  node: HTMLInputElement,
  text: string,
  focus: boolean,
): void {
  // Written now, so a key that lands before the microtask meets the text, and
  // through the NATIVE setter: React's own (instance) setter would record the
  // text as already seen, and the `input` below would then be no change.
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )?.set;
  if (setter === undefined) node.value = text;
  else setter.call(node, text);
  if (focus) {
    node.focus();
    // Caret at the end: the user is mid-value.
    node.setSelectionRange(text.length, text.length);
  }
  // Announced after the commit this runs in (an event dispatched mid-commit
  // is lost to React), but before any queued key: a microtask. A key typed
  // since has announced the text itself.
  queueMicrotask(() => {
    if (text === "" || node.value !== text) return;
    node.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

export interface DrawNames {
  /** This sketch's named driving dimensions, offered by the autocomplete. */
  dimensions: ScopeDimension[];
  /** Everything a formula may read: the part's parameters, then those. */
  names: ReadonlyMap<string, Quantity>;
}

/**
 * The names in scope for a draw-time box: the part's parameters and this
 * sketch's own named dimensions, the same scope the dimension box reads
 * (PART-PARAMETERS step 8). A table not read yet counts as empty, so a name
 * it would have defined is reported, not silently dropped.
 */
export function useDrawNames(): DrawNames {
  const constraints = useSketchStore((state) => state.constraints);
  const solvedDimensions = useSketchStore((state) => state.solvedDimensions);
  const solvedAngles = useSketchStore((state) => state.solvedAngles);
  const parameters = useParameterScopeStore((state) => state.parameters);
  return useMemo(() => {
    const solved = solvedReadouts(solvedDimensions, solvedAngles);
    const dimensions = sketchDimensionScope(constraints, solved, null);
    return {
      dimensions,
      names: scopeQuantities(parameters ?? [], dimensions) ?? new Map(),
    };
  }, [constraints, solvedDimensions, solvedAngles, parameters]);
}
