/**
 * THE HOLE GAUGES — Ø and depth, pulled on the part (CRAFT-9c).
 *
 * Both instruments are {@link ParametricGauge}, unchanged; where they stand is
 * `holeAnchor.ts`. What is here is the only part that is about HOLE: that both
 * values are lengths in the document's unit, that a hole has one number you
 * can always pull (the bore) and one you can pull only when there is a bottom
 * to pull (a blind pocket's depth), and what the drag is a picture of.
 *
 * ## ONE TAG, TWO CELLS — the only `companion` gauge in the product
 *
 * Two tags twenty millimetres apart carrying two numbers is the "two dialects
 * drawn on screen" failure literally (direction §6.4). So the Ø instrument
 * speaks for the pair — `Ø 8 · D 12 mm` in one drafting strip — and the depth
 * instrument carries `tag: "none"`.
 *
 * Ø is the speaker and not depth for the same reason the pattern's spacing is
 * (see `PatternGaugeLayer`): it is the number that is ALWAYS there. A
 * through-all hole has no depth to state, and a speaker that disappeared when
 * you switched the depth mode would take the Ø readout with it. It is also the
 * editor's own primary field (`emphasis="primary"`), so the one number the tag
 * can never lose is the one the card already calls THE parametric handle.
 *
 * `tag: "none"` also switches off the depth gauge's global digit capture, and
 * that is the point rather than a side effect: only one instrument may own the
 * digits, and typing `10` while a hole is open means the BORE, from the Ø cell.
 * The depth keeps two routes of its own — `Tab` from the Ø cell lands in the
 * `D` cell beside it, and the rail's `hole-blind-depth` field is untouched.
 *
 * ## THE PREVIEW IS ROUTE (b) — the bore circle and the depth plane (§8.4)
 *
 * On every value: the MOUTH at the live Ø, drawn in the instrument's own
 * active brass because it is the thing the Ø arrow is pulling; and, for a blind
 * hole, the DEPTH PLANE — the bottom ring framed by a square sheet — with four
 * wall generators tying the two rings into one cylinder, in the preview ink
 * every other pending result uses. All x-ray (`depthTest: false`): the pocket
 * is INSIDE the material, which is the extrude ghost's reason and the cut
 * preview's.
 *
 * Both are stamped on the viewport from the DRAWN buffers — the ring's own
 * vertex radius and the plane's own distance down the axis — so a picture that
 * stopped following the drag reports where it was left, never the number that
 * should have moved it.
 *
 * ## The anchor arrives as a PROP
 *
 * CRAFT-12's selection store will re-source it; a component that read the hole
 * pick session here would be rewritten then instead of re-wired (§11).
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
import { useEffect, useMemo } from "react";

import { useDocumentLengthUnit } from "../units/documentUnit";
import {
  COARSE_STEP_FACTOR,
  DEPTH_EPSILON_MM,
  keyStepMm,
  SNAP_MM,
} from "./extrudeHandle";
import { drawnAdvance } from "./faceAnchor";
import {
  boreCircle,
  boreWalls,
  depthPlane,
  depthSeat,
  DIAMETER_UNITS_PER_VALUE,
  diameterSeat,
  drawnDiameter,
  MAX_HOLE_MM,
  MIN_HOLE_MM,
  type HoleAnchor,
} from "./holeAnchor";
import { Segments } from "./overlaySegments";
import { ParametricGauge } from "./ParametricGauge";
import { useViewportPickStamp } from "./pickStamp";

export interface HoleGaugeProps {
  /** Where the hole stands — a value, never a store read. */
  anchor: HoleAnchor;
  /** The editor's live bore diameter, canonical mm. */
  diameterMm: number;
  /**
   * The editor's live blind depth, canonical mm — or `null` for a through-all
   * hole (or a depth field that does not parse), which mounts no depth gauge
   * and draws no depth plane.
   */
  depthMm: number | null;
  /** Ask the editor for a new diameter, canonical mm (contract β: it echoes). */
  onDiameterChange: (mm: number) => void;
  /** Ask the editor for a new blind depth, canonical mm. */
  onDepthChange: (mm: number) => void;
}

/**
 * A hole length along a seat — the extrude's grammar, imported rather than
 * re-picked: one length snap per document unit across every gauge in the
 * product, or the same gesture means two things two commands apart.
 */
function holeTrack(
  seat: GaugeSeat,
  unit: LengthUnit,
  unitsPerValue = 1,
): GaugeTrack {
  return linearTrack(seat, {
    min: MIN_HOLE_MM,
    max: MAX_HOLE_MM,
    snap: SNAP_MM[unit],
    keyStep: keyStepMm(unit),
    coarseFactor: COARSE_STEP_FACTOR,
    epsilon: DEPTH_EPSILON_MM,
    format: (mm, opts) => formatLength(mm, unit, opts ?? {}),
    unitsPerValue,
  });
}

/** The Ø instrument's arithmetic: a DIAMETER drawn as a radius. */
export function holeDiameterTrack(
  anchor: HoleAnchor,
  unit: LengthUnit,
): GaugeTrack {
  return holeTrack(diameterSeat(anchor), unit, DIAMETER_UNITS_PER_VALUE);
}

/** The depth instrument's arithmetic: a length down the bore wall. */
export function holeDepthTrack(
  anchor: HoleAnchor,
  diameterMm: number,
  unit: LengthUnit,
): GaugeTrack {
  return holeTrack(depthSeat(anchor, diameterMm), unit);
}

/** Two-decimal stamp, the precision every other preview stamp publishes. */
const stamp = (mm: number): number => Math.round(mm * 100) / 100;

export function HoleGauge({
  anchor,
  diameterMm,
  depthMm,
  onDiameterChange,
  onDepthChange,
}: HoleGaugeProps) {
  const unit = useDocumentLengthUnit();
  const invalidate = useThree((state) => state.invalidate);

  // MEMOISED on what each track is FOR, and the split is load-bearing. The Ø
  // track never depends on the depth, so a depth drag cannot rebuild the Ø
  // instrument's geometry or stop set; the depth track DOES depend on Ø (it
  // stands on the wall), which rebuilds it only while Ø is moving — once per
  // pointermove, never per frame.
  const diameterTrack = useMemo(
    () => holeDiameterTrack(anchor, unit),
    [anchor, unit],
  );
  const depthTrack = useMemo(
    () => holeDepthTrack(anchor, diameterMm, unit),
    [anchor, diameterMm, unit],
  );

  const mouth = useMemo(
    () => boreCircle(anchor, diameterMm),
    [anchor, diameterMm],
  );
  const bottom = useMemo(
    () =>
      depthMm === null
        ? new Float32Array(0)
        : depthPlane(anchor, diameterMm, depthMm),
    [anchor, diameterMm, depthMm],
  );
  const walls = useMemo(
    () =>
      depthMm === null
        ? new Float32Array(0)
        : boreWalls(anchor, diameterMm, depthMm),
    [anchor, diameterMm, depthMm],
  );

  // frameloop="demand": the preview only moves when a value does, so ask for
  // the frame that shows it.
  useEffect(() => {
    invalidate();
  }, [mouth, bottom, walls, invalidate]);

  useViewportPickStamp(
    "holeBoreDiameterMm",
    mouth.length === 0 ? null : stamp(drawnDiameter(mouth, anchor.centre)),
  );
  useViewportPickStamp(
    "holeDepthPlaneMm",
    bottom.length === 0
      ? null
      : stamp(drawnAdvance(bottom, anchor.centre, anchor.axis)),
  );

  const companion = useMemo(
    () =>
      depthMm === null
        ? undefined
        : {
            tagLabel: "D",
            value: depthMm,
            onChange: onDepthChange,
            track: depthTrack,
            min: MIN_HOLE_MM,
            max: MAX_HOLE_MM,
          },
    [depthMm, onDepthChange, depthTrack],
  );

  return (
    <group name="hole-gauge">
      {/* NAMED, and each name is a test hook as much as a label: a spec can
          measure the ring and the plane separately, which is the only way to
          prove a depth drag left the mouth alone. */}
      <group name="hole-bore-circle">
        <Segments
          positions={mouth}
          color={viewport.manipulator.active}
          opacity={viewport.manipulator.axisOpacity}
          depthTest={false}
          renderOrder={12}
        />
      </group>
      {depthMm === null ? null : (
        <group name="hole-depth-plane">
          <Segments
            positions={bottom}
            color={viewport.preview.edge}
            opacity={viewport.preview.edgeOpacity}
            depthTest={false}
            renderOrder={11}
          />
          <Segments
            positions={walls}
            color={viewport.manipulator.axis}
            opacity={viewport.manipulator.ladderMinorOpacity}
            depthTest={false}
            renderOrder={11}
          />
        </group>
      )}
      <ParametricGauge
        label="Hole diameter"
        tagLabel="Ø"
        gaugeId="hole-diameter-gauge"
        value={diameterMm}
        onChange={onDiameterChange}
        track={diameterTrack}
        min={MIN_HOLE_MM}
        max={MAX_HOLE_MM}
        tagUnit={unit}
        {...(companion === undefined ? {} : { companion })}
      />
      {depthMm === null ? null : (
        <ParametricGauge
          label="Hole depth"
          tagLabel="D"
          tag="none"
          gaugeId="hole-depth-gauge"
          value={depthMm}
          onChange={onDepthChange}
          track={depthTrack}
          min={MIN_HOLE_MM}
          max={MAX_HOLE_MM}
        />
      )}
    </group>
  );
}
