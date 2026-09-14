/**
 * THE DATUM OFFSET GAUGE — the same instrument, standing on a plane instead of
 * a face (CRAFT-9b).
 *
 * A datum plane is the one feature in the product that produces no body at all,
 * so before this it was the feature with the least to look at while you set it:
 * a dropdown, a number, and a viewport that showed nothing until Save. The
 * gauge and its preview turn it into the thing it always was — a sheet you slide
 * along a normal.
 *
 * ## THE PREVIEW IS ROUTE (b) — the offset plane, drawn (direction §8.4)
 *
 * A square sheet OUTLINE in the base plane's own axes, at the current distance.
 * Outline and not a filled quad, deliberately: the sketcher draws COMMITTED
 * datum planes as filled sheets, so a filled preview would say "this exists"
 * about a plane that has not been saved. Line-work says "about to be", which is
 * what every other preview in this app says, and it is what separates idiom D's
 * vocabulary from the committed model's.
 *
 * ## WHY THE GAUGE DRIVES A MAGNITUDE AND THE ANCHOR CARRIES THE SIGN
 *
 * A datum offset is signed; `linearTrack` is not, and the failure is not a
 * refusal — it is a DEGRADATION exactly where the user is looking hardest.
 * `arrowLength` bounds the head by `max(0, shaft) * 0.45`, so a negative value
 * draws a rod with no point; `ladderStops` returns no stops for a non-positive
 * span, so it also loses its scale. The instrument would quietly stop being an
 * instrument on one side of zero.
 *
 * So the gauge drives the DISTANCE and the seat carries the direction — which
 * is how a drafting dimension has always worked, and it keeps the arrow, the
 * ladder and the tag well-formed on both sides. The rail field keeps the sign
 * and remains the exact path; the tag reads the distance the arrow is drawn
 * along, so the two never disagree about the picture.
 */
import {
  formatLength,
  linearTrack,
  type GaugeSeat,
  type GaugeTrack,
  type LengthUnit,
} from "@loft/design";
import { viewport } from "@loft/design/tokens";
import { useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo } from "react";

import { useDocumentLengthUnit } from "../units/documentUnit";
import {
  COARSE_STEP_FACTOR,
  DEPTH_EPSILON_MM,
  keyStepMm,
  SNAP_MM,
} from "./extrudeHandle";
import {
  datumOutline,
  drawnAdvance,
  MAX_OFFSET_MM,
  MIN_OFFSET_MM,
  type DatumAnchor,
} from "./faceAnchor";
import { Segments } from "./overlaySegments";
import { ParametricGauge } from "./ParametricGauge";
import { useViewportPickStamp } from "./pickStamp";

export interface DatumGaugeProps {
  /** Where the instrument stands — a value, never a store read. */
  anchor: DatumAnchor;
  /** The editor's current offset, canonical mm, SIGNED as the form holds it. */
  offsetMm: number;
  /** Report a new SIGNED offset in canonical mm (the editor owns the value). */
  onChange: (mm: number) => void;
}

/**
 * The datum gauge's arithmetic: a distance along the base plane's normal.
 *
 * `min` is the extrude's own floor rather than zero, for the extrude's own
 * reason — a drag that can park exactly on the base plane would flip the seat's
 * direction under the pointer the instant the sign is recomputed, so the arrow
 * would turn over mid-gesture. Typing 0 is still allowed and still valid; it is
 * the DRAG that stops a tenth short, and the instrument simply draws itself
 * down to nothing there.
 */
export function datumTrack(seat: GaugeSeat, unit: LengthUnit): GaugeTrack {
  return linearTrack(seat, {
    min: MIN_OFFSET_MM,
    max: MAX_OFFSET_MM,
    snap: SNAP_MM[unit],
    keyStep: keyStepMm(unit),
    coarseFactor: COARSE_STEP_FACTOR,
    epsilon: DEPTH_EPSILON_MM,
    format: (mm, opts) => formatLength(mm, unit, opts ?? {}),
  });
}

export function DatumGauge({ anchor, offsetMm, onChange }: DatumGaugeProps) {
  const unit = useDocumentLengthUnit();
  const invalidate = useThree((state) => state.invalidate);

  const track = useMemo(
    () => datumTrack(anchor.seat, unit),
    [anchor.seat, unit],
  );
  const outline = useMemo(
    () => datumOutline(anchor, offsetMm),
    [anchor, offsetMm],
  );
  const { sign } = anchor;
  const setOffset = useCallback(
    (distance: number) => onChange(sign * distance),
    [onChange, sign],
  );

  useEffect(() => {
    invalidate();
  }, [outline, invalidate]);

  /**
   * Stamped from the DRAWN sheet's own vertices — where the picture stands, not
   * where the form says it should. The perimeter that witnesses the shell
   * preview would be useless here: a square translating rigidly has a constant
   * perimeter, so it would report a frozen plane as a moving one.
   */
  useViewportPickStamp(
    "datumPreviewOffsetMm",
    Math.round(drawnAdvance(outline, anchor.seat.base, anchor.seat.dir) * 100) /
      100,
  );

  return (
    <>
      {/* `datum-offset-sheet`, not `-plane`: `datum-offset-plane` is already a
          DOM test id on the plane chip, and two different things answering to
          one name is how a probe ends up measuring the wrong one. */}
      <group name="datum-offset-sheet">
        <Segments
          positions={outline}
          color={viewport.preview.edge}
          opacity={viewport.preview.edgeOpacity}
          depthTest={false}
          renderOrder={11}
        />
      </group>
      <ParametricGauge
        label="Datum offset"
        tagLabel="D"
        gaugeId="datum-offset"
        value={Math.abs(offsetMm)}
        onChange={setOffset}
        track={track}
        min={MIN_OFFSET_MM}
        max={MAX_OFFSET_MM}
        tagUnit={unit}
      />
    </>
  );
}
