/**
 * THE FILLET RADIUS GAUGE — and the rolling ball it draws (CRAFT-9a).
 *
 * The instrument itself is {@link ParametricGauge}, unchanged and unextended;
 * what is here is the only part that is about FILLET: which edge it stands on,
 * that a radius is a length in the document's unit, and — the part this item
 * exists for — **what the drag changes besides the number**.
 *
 * ## Route (b), stated in the terms direction §8.4 asks for
 *
 * This ships a GEOMETRIC LINE-WORK PREVIEW, not a translucent result ghost. On
 * every picked edge, at the live radius, the round's BAND:
 *
 *  · the two **tangency lines** — where the round meets each face, drawn along
 *    the whole edge, which is the fillet's actual footprint on the body;
 *  · the **arc** at both ends of the edge and at the seat — the cross-section
 *    the round replaces the sharp corner with.
 *
 * It is the same band the chamfer draws, and it differs in the one way the two
 * features differ: the rung is an arc rather than a chord. The rolling ball's
 * full circle is deliberately absent — see `edgeAnchor.ts`, where the captured
 * screenshot that removed it is written down.
 *
 * Drag the arrow and both redraw in the same frame as the number, because they
 * are computed from it. A ghost would have needed a kernel round-trip per
 * pointer move; this needs none, and it answers the question the drag poses —
 * *how big is that?*
 *
 * ## Why the preview is drawn on EVERY picked edge and the gauge on ONE
 *
 * A fillet applies to the whole selection, so a preview on one edge would
 * understate what Save is about to do. The instrument is singular for the
 * opposite reason: one value, one place to take hold of it. It sits on the edge
 * picked LAST, which is where the eye already is.
 *
 * ## The anchor arrives as a PROP
 *
 * Deliberately. CRAFT-12 replaces the fillet's own pick session with a
 * persistent selection store; a component that read the pick store here would
 * be rewritten then. `edgeAnchorSource.ts` owns that reading, and this file is
 * a pure function of its argument.
 */
import { type LengthUnit } from "@loft/design";
import { viewport } from "@loft/design/tokens";
import { useMemo } from "react";

import {
  edgeGaugeTrack,
  filletPreview,
  MAX_EDGE_VALUE_MM,
  MIN_EDGE_VALUE_MM,
  type EdgeAnchor,
} from "./edgeAnchor";
import { Segments } from "./overlaySegments";
import { ParametricGauge } from "./ParametricGauge";

export interface FilletGaugeProps {
  /** The picked edges, seated. Pick order, so the last is the newest. */
  anchors: readonly EdgeAnchor[];
  /** The editor's current radius, canonical mm. */
  radiusMm: number;
  /** Document length unit — drives the snap increment and the readout. */
  unit: LengthUnit;
  /** Report a new radius in canonical mm (the editor owns the value). */
  onRadiusChange: (mm: number) => void;
}

export function FilletGauge({
  anchors,
  radiusMm,
  unit,
  onRadiusChange,
}: FilletGaugeProps) {
  const seat = anchors.at(-1) ?? null;
  // MEMOISED on the seat and the unit, never on the radius: the track is the
  // gauge's geometry and arithmetic, and rebuilding it on every pointer move
  // would rebuild the drawn instrument and its stop set once per frame — the
  // render-loop allocation the viewport rules forbid, and the reason
  // `ExtrudeDragHandle` memoises its own.
  const track = useMemo(
    () => (seat === null ? null : edgeGaugeTrack(seat, unit)),
    [seat, unit],
  );
  // The preview DOES depend on the radius — that is the whole point of the
  // item. Keyed on the anchor list so a second pick redraws without touching
  // the instrument.
  const previews = useMemo(
    () => anchors.map((anchor) => filletPreview(anchor, radiusMm)),
    [anchors, radiusMm],
  );

  if (seat === null || track === null || !(radiusMm > 0)) return null;

  return (
    <group name="fillet-gauge">
      {/* NAMED, and the name is a test hook as much as a label: the world box
          of THIS subtree is how a spec proves the PREVIEW redrew rather than
          only the arrow. Measuring the whole gauge cannot tell them apart —
          the arrow's own length tracks the value too, so a preview frozen at
          the radius the editor opened with would pass that check. */}
      <group name="fillet-preview">
        {previews.map((preview, i) => (
          <group key={anchors[i]?.key ?? i}>
            <Segments
              positions={preview.tangencyLines}
              color={viewport.manipulator.axis}
              opacity={viewport.manipulator.ladderMajorOpacity}
              depthTest={false}
              renderOrder={12}
            />
            <Segments
              positions={preview.arcs}
              color={viewport.manipulator.active}
              opacity={viewport.manipulator.axisOpacity}
              depthTest={false}
              renderOrder={12}
            />
          </group>
        ))}
      </group>
      <ParametricGauge
        label="Fillet radius"
        tagLabel="R"
        gaugeId="fillet-radius"
        value={radiusMm}
        onChange={onRadiusChange}
        track={track}
        min={MIN_EDGE_VALUE_MM}
        max={MAX_EDGE_VALUE_MM}
        tagUnit={unit}
      />
    </group>
  );
}
