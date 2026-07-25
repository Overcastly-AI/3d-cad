/**
 * Assembly title-block readouts — the pure projection the {@link
 * AssemblyInspector} renders, kept out of the component so the unit conversion
 * is testable without a DOM (the same split the extrude form uses).
 *
 * FINDINGS burn-down 2026-07-25 #7: the assembly panel had been left behind by
 * FINDINGS #17 (unit-aware readouts) — it printed raw mm³/mm²/mm while the
 * identical part panel honoured the document unit, so one product spoke two
 * conventions. Storage is canonical mm forever; the conversion happens here, at
 * the display boundary, through the SAME `lib/format` seam the part inspector
 * uses.
 */
import {
  areaUnitLabel,
  type LengthUnit,
  lengthUnitLabel,
  volumeUnitLabel,
} from "@loft/design";

import type { EvaluateAssemblyResult } from "../api/assemblies";
import {
  formatArea,
  formatExtents,
  formatVec3,
  formatVolume,
} from "../lib/format";

/** Shown wherever the solve has not produced a number yet. */
export const EM_DASH = "—";

/** Every combined-mass / bounding-box cell of the assembly title block. */
export interface AssemblyReadout {
  volume: string;
  volumeUnit: string;
  area: string;
  areaUnit: string;
  centroid: string;
  extents: string;
  /** Label for the length-valued cells (centroid, extents). */
  lengthUnit: string;
}

/** Project an evaluation (or nothing yet) into display strings in `unit`. */
export function assemblyReadout(
  evaluation: EvaluateAssemblyResult | undefined,
  unit: LengthUnit,
): AssemblyReadout {
  const props = evaluation?.properties ?? null;
  const bbox = evaluation?.bounding_box ?? null;
  return {
    volume: props ? formatVolume(props.volume, unit) : EM_DASH,
    volumeUnit: volumeUnitLabel(unit),
    area: props ? formatArea(props.surface_area, unit) : EM_DASH,
    areaUnit: areaUnitLabel(unit),
    centroid: props ? formatVec3(props.centroid, unit) : EM_DASH,
    extents: bbox ? formatExtents(bbox.min, bbox.max, unit) : EM_DASH,
    lengthUnit: lengthUnitLabel(unit),
  };
}
