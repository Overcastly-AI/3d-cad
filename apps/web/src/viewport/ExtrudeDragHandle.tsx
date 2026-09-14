/**
 * THE EXTRUDE DEPTH GAUGE — the call site (T-23, re-expressed by CRAFT-8).
 *
 * Everything that used to be here is now in two places: the arithmetic in
 * {@link extrudeTrack} (built on `@loft/design`'s pure `linearTrack`), and the
 * state, the grip, the tag and the keyboard in {@link ParametricGauge}. What is
 * left is the only part that is genuinely about EXTRUDE — which profile the
 * gauge stands on, which way the sweep goes, and that a depth is a length in
 * the document's unit.
 *
 * That is the shape every other verb's gauge now takes: a seat, a track, and a
 * mount. The reason the extraction was worth doing on its own, before any of
 * them: the optimistic ask-queue in the shell was written after a
 * load-dependent lost update, and six copies of that fix — whose symptom is an
 * occasional wrong number — is the worst thing this wave could have shipped.
 *
 * WHY THE GAUGE AND NOT THE GHOST DRAWS THE DEPTH. The gauge works in scene
 * coordinates (that is the frame a pointer ray arrives in) and is driven by the
 * LIVE distance rather than the debounced one, so the arrow stays under the
 * cursor while the swept mesh catches up a frame later.
 */
import { type LengthUnit } from "@loft/design";
import { useMemo } from "react";

import type { ExtrudeDirection } from "../features/extrude";
import type { PlaneBasis } from "../sketch/plane";
import {
  extrudeTrack,
  handleAxis,
  MAX_DEPTH_MM,
  MIN_DEPTH_MM,
} from "./extrudeHandle";
import { ParametricGauge } from "./ParametricGauge";
import type { ProfileRegion } from "./profileLoops";

export interface ExtrudeDragHandleProps {
  /** The sketch plane, in SCENE coordinates (see `extrudeHandle`'s frame note). */
  basis: PlaneBasis;
  /** The solved profile loops the gauge stands on. */
  regions: readonly ProfileRegion[];
  /** The editor's current distance, canonical mm. */
  depthMm: number;
  direction: ExtrudeDirection;
  /** Document length unit — drives the snap increment and the readout. */
  unit: LengthUnit;
  /** Report a new distance in canonical mm (the editor owns the value). */
  onDepthChange: (mm: number) => void;
}

export function ExtrudeDragHandle({
  basis,
  regions,
  depthMm,
  direction,
  unit,
  onDepthChange,
}: ExtrudeDragHandleProps) {
  const axis = useMemo(
    () => handleAxis(basis, direction, regions),
    [basis, direction, regions],
  );
  // MEMOISED, and it is load-bearing rather than tidy: the gauge's stop set and
  // its drawn form are derived from the track, so a track rebuilt on every
  // render would rebuild both on every frame of a drag — which is the
  // allocation in the render loop the viewport rules forbid.
  const track = useMemo(
    () => extrudeTrack(axis, basis, unit),
    [axis, basis, unit],
  );

  if (regions.length === 0 || depthMm <= 0) return null;

  return (
    <ParametricGauge
      label="Extrude depth"
      tagLabel="D"
      gaugeId="extrude-depth"
      value={depthMm}
      onChange={onDepthChange}
      track={track}
      min={MIN_DEPTH_MM}
      max={MAX_DEPTH_MM}
      tagUnit={unit}
      // The leader is CRAFT-7's, together with the proportion clamps and the
      // hit sleeve: CRAFT-8 must not move a pixel, and the pixel-match against
      // `w3-before-extrude-{1280,1600}.png` is the only cheap evidence the
      // extraction was faithful. `GaugeTag` already renders the leader; this
      // call site simply has not switched it on yet, which is a one-prop change
      // rather than a component change.
      tagClassName="pointer-events-none -translate-y-8 translate-x-4"
    />
  );
}
