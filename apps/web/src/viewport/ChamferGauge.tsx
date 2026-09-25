/**
 * THE CHAMFER DISTANCE GAUGE — and the bevel band it draws (CRAFT-9a).
 *
 * The fillet gauge's twin, and deliberately its twin rather than its
 * generalisation: the two verbs share a TRACK (`edgeGaugeTrack` — a length from
 * the edge along the face bisector, in the document's unit) and they do not
 * share a PREVIEW, because a round and a bevel are different drawings of
 * different results. One component with a `kind` prop would have been a
 * component that branches on what it is, which is the thing
 * {@link ParametricGauge} was extracted specifically to stop doing.
 *
 * ## Route (b), as direction §8.4 asks it to be stated
 *
 * A GEOMETRIC LINE-WORK PREVIEW, not a translucent result ghost. On every
 * picked edge, at the live distance: the two **offset lines** the cut reaches
 * to on each face — which is exactly how much of each face the chamfer eats —
 * closed into a **band** by the bevel's own cross-section at both ends of the
 * edge and at its middle, where the instrument stands.
 *
 * Drag the arrow and the band redraws in the same frame as the number, from
 * the number. No kernel round-trip.
 *
 * ## The anchor arrives as a PROP
 *
 * See `FilletGauge.tsx`: CRAFT-12 moves where anchors come from, and a
 * component that read the pick store would be rewritten rather than re-wired.
 */
import { type LengthUnit } from "@loft/design";
import { viewport } from "@loft/design/tokens";
import { useMemo } from "react";

import {
  chamferPreview,
  edgeGaugeTrack,
  MAX_EDGE_VALUE_MM,
  MIN_EDGE_VALUE_MM,
  type EdgeAnchor,
} from "./edgeAnchor";
import { Segments } from "./overlaySegments";
import { ParametricGauge } from "./ParametricGauge";

export interface ChamferGaugeProps {
  /** The picked edges, seated. Pick order, so the last is the newest. */
  anchors: readonly EdgeAnchor[];
  /** The editor's current distance, canonical mm. */
  distanceMm: number;
  /** Document length unit — drives the snap increment and the readout. */
  unit: LengthUnit;
  /** Report a new distance in canonical mm (the editor owns the value). */
  onDistanceChange: (mm: number) => void;
}

export function ChamferGauge({
  anchors,
  distanceMm,
  unit,
  onDistanceChange,
}: ChamferGaugeProps) {
  const seat = anchors.at(-1) ?? null;
  const track = useMemo(
    () => (seat === null ? null : edgeGaugeTrack(seat, unit)),
    [seat, unit],
  );
  const previews = useMemo(
    () => anchors.map((anchor) => chamferPreview(anchor, distanceMm)),
    [anchors, distanceMm],
  );

  if (seat === null || track === null || !(distanceMm > 0)) return null;

  return (
    <group name="chamfer-gauge">
      {/* NAMED — see `FilletGauge`: a spec measures THIS subtree's world box to
          prove the band redrew, because the arrow's own length moves with the
          value and would mask a preview frozen at the opening distance. */}
      <group name="chamfer-preview">
        {previews.map((preview, i) => (
          <group key={anchors[i]?.key ?? i}>
            <Segments
              positions={preview.offsets}
              color={viewport.manipulator.axis}
              opacity={viewport.manipulator.ladderMajorOpacity}
              depthTest={false}
              renderOrder={12}
            />
            <Segments
              positions={preview.bevels}
              color={viewport.manipulator.active}
              opacity={viewport.manipulator.axisOpacity}
              depthTest={false}
              renderOrder={12}
            />
          </group>
        ))}
      </group>
      <ParametricGauge
        label="Chamfer distance"
        tagLabel="C"
        gaugeId="chamfer-distance"
        value={distanceMm}
        onChange={onDistanceChange}
        track={track}
        min={MIN_EDGE_VALUE_MM}
        max={MAX_EDGE_VALUE_MM}
        tagUnit={unit}
      />
    </group>
  );
}
