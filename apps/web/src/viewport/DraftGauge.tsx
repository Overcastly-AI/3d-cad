/**
 * THE DRAFT TAPER GAUGE — the mould-release angle, as an instrument (CRAFT-10).
 *
 * The revolve gauge's twin, and deliberately the same three drawn things in the
 * same order, because they answer the same three questions about a different
 * verb:
 *
 *   1. **the pivot** — *about what?* The line where the tapered face meets the
 *      neutral (parting) plane, drawn as the identical brass chain line the
 *      revolve axis uses. A draft's neutral plane was, like the revolve axis
 *      before this item, a control with nothing on screen answering to it.
 *   2. **the arc** — *how far?* A graduated protractor from the face's current
 *      plane round to the tapered one.
 *   3. **the tapered edge** — *what will that give me?* The face seen edge-on
 *      from the pivot, drawn dashed where it is now and solid where the taper
 *      puts it. That pair of lines with an angle between them IS how a draft is
 *      dimensioned on a drawing, so the preview is not a stand-in for the
 *      result; it is the drawing of it.
 *
 * ## Why a 3-degree default still shows a ladder
 *
 * `angularTrack`'s own stop set floors at 5 degrees, so a draft at its everyday
 * default came back with no rungs at all and the instrument lost its signature
 * element exactly where it is used most. `angularStops` adds the 1-degree
 * subdivision the direction pass specifies; see `axisAnchorGauge.ts` for why
 * that is composed here rather than edited into the design package.
 *
 * ## The sign stays on the field
 *
 * The track's value is the taper's MAGNITUDE and its sign rides on the axis
 * direction, so the arc always sweeps away from the face and the drag can never
 * walk through zero — the one value the form rejects. The readout still says
 * `−3°`. `draftGaugeTrack` carries the full reasoning.
 *
 * ## The anchor is a PROP
 *
 * The picked face and the neutral plane arrive as props; this component reads
 * no pick store. W4's selection store changes where `PartPage` gets the face
 * FROM, not this file.
 */
import { useMemo } from "react";

import { sketch, viewport } from "@loft/design/tokens";
import type { Vec3 } from "@loft/design";

import type { PlanarFaceSignature } from "../api/parts";
import {
  occtToSceneTuple,
  sceneOriginBasis,
  type DatumPlaneName,
} from "../sketch/plane";
import {
  axisRadial,
  axisReach,
  draftAxisAnchor,
  type AxisAnchor,
} from "./axisAnchor";
import {
  arcPoint,
  draftGaugeTrack,
  MAX_DRAFT_DEG,
  MIN_DRAFT_DEG,
  rotateAboutAxis,
  type ArcSeat,
} from "./axisAnchorGauge";
import { Segments } from "./overlaySegments";
import { ParametricGauge } from "./ParametricGauge";
import { RevolveAxisLine } from "./RevolveAxisLine";

/** The neutral (parting) plane, exactly as the draft form holds it. */
export interface DraftNeutral {
  base: DatumPlaneName;
  /** Signed offset along the base normal, mm. */
  offsetMm: number;
  /** Reverse the pull — the other mould half. */
  flip: boolean;
}

export interface DraftGaugeProps {
  /**
   * The face the gauge stands on. A PROP: `PartPage` reads the pick store and
   * passes ONE signature, so W4's selection store is a re-wiring there rather
   * than a rewrite here.
   */
  face: PlanarFaceSignature;
  neutral: DraftNeutral;
  /** The editor's current taper, SIGNED degrees. */
  angleDeg: number;
  /** Report a new taper, signed (the editor owns the value). */
  onAngleChange: (deg: number) => void;
}

/** Arc clearance outside the face's own reach from the pivot — the revolve's. */
const ARC_CLEARANCE_FRAC = 0.2;

/** Shortest arc radius the gauge will seat at, scene mm. */
const MIN_ARC_RADIUS_MM = 0.5;

/**
 * How far past the face's centroid the drawn taper line runs, as a fraction of
 * the pivot-to-centroid distance.
 *
 * A dimension line overruns what it measures — that is what makes it read as a
 * measurement rather than as an edge of the part. A tenth is the draughting
 * habit and it is enough to clear the silhouette at every angle in range.
 */
const TAPER_LINE_OVERRUN_FRAC = 0.1;

/** Dash cycle of the REFERENCE line, as a fraction of its own length. */
const REFERENCE_DASH_FRAC = 0.08;

/** Push one segment pair onto a flat buffer. */
function pushSegment(out: number[], a: Vec3, b: Vec3): void {
  out.push(a[0], a[1], a[2], b[0], b[1], b[2]);
}

/**
 * The face's undrafted edge, dashed — where the face is NOW.
 *
 * Dashed rather than solid because it is a reference, not a result: the same
 * distinction the sketcher already draws between construction ink and scribe,
 * applied to the one line on screen that is about to stop being true.
 */
function referenceDashes(from: Vec3, to: Vec3): number[] {
  const out: number[] = [];
  const cycles = Math.max(3, Math.round(1 / REFERENCE_DASH_FRAC));
  for (let i = 0; i < cycles; i += 1) {
    // Half on, half off: the coarse dash of a construction line, and it keeps
    // the pair legible where the two lines converge at a small angle.
    const t0 = i / cycles;
    const t1 = (i + 0.5) / cycles;
    pushSegment(
      out,
      [
        from[0] + (to[0] - from[0]) * t0,
        from[1] + (to[1] - from[1]) * t0,
        from[2] + (to[2] - from[2]) * t0,
      ],
      [
        from[0] + (to[0] - from[0]) * t1,
        from[1] + (to[1] - from[1]) * t1,
        from[2] + (to[2] - from[2]) * t1,
      ],
    );
  }
  return out;
}

interface DraftPose {
  anchor: AxisAnchor;
  seat: ArcSeat;
  /** ＋1 or −1 — which way the taper leans. */
  sign: 1 | -1;
  /** Pivot-to-centroid distance, the drawn taper line's own length. */
  armMm: number;
}

export function DraftGauge({
  face,
  neutral,
  angleDeg,
  onAngleChange,
}: DraftGaugeProps) {
  const pose = useMemo<DraftPose | null>(() => {
    // The signature speaks the KERNEL's Z-up world; the scene is Y-up. One
    // rotation, applied once, at the boundary — `sketch/plane.ts`'s rule.
    const faceNormal = occtToSceneTuple([
      face.normal.x,
      face.normal.y,
      face.normal.z,
    ]);
    const faceCentroid = occtToSceneTuple([
      face.centroid.x,
      face.centroid.y,
      face.centroid.z,
    ]);
    const basis = sceneOriginBasis(neutral.base);
    const sense = neutral.flip ? -1 : 1;
    const neutralNormal: Vec3 = [
      basis.normal[0] * sense,
      basis.normal[1] * sense,
      basis.normal[2] * sense,
    ];
    const neutralPoint: Vec3 = [
      basis.origin[0] + basis.normal[0] * neutral.offsetMm,
      basis.origin[1] + basis.normal[1] * neutral.offsetMm,
      basis.origin[2] + basis.normal[2] * neutral.offsetMm,
    ];
    const anchor = draftAxisAnchor(
      faceNormal,
      faceCentroid,
      neutralNormal,
      neutralPoint,
    );
    // A face PARALLEL to the neutral plane has no pivot line and cannot be
    // drafted about it — a box's top face against XY is the everyday instance.
    // No gauge, and the face-pick and Neutral-plane controls say why.
    if (anchor === null) return null;
    const { foot, radial, distance } = axisRadial(anchor, faceCentroid);
    if (radial === null || !(distance > 0)) return null;
    const armMm = distance * (1 + TAPER_LINE_OVERRUN_FRAC);
    const sign: 1 | -1 = angleDeg < 0 ? -1 : 1;
    return {
      anchor,
      sign,
      armMm,
      seat: {
        centre: foot,
        axis: anchor.dir,
        reference: radial,
        arcRadiusMm: Math.max(
          MIN_ARC_RADIUS_MM,
          distance * (1 + ARC_CLEARANCE_FRAC),
        ),
        // The instrument's own scale is the face's reach from its pivot — for
        // a drafted side wall, its height. The arrowhead and the rung arms are
        // fractions of it, so the gauge suits the wall rather than the number.
        seatRadiusMm: Math.max(MIN_ARC_RADIUS_MM, distance),
      },
    };
  }, [face, neutral, angleDeg]);

  const track = useMemo(
    () => (pose === null ? null : draftGaugeTrack(pose.seat, pose.sign)),
    [pose],
  );

  /** The tapered edge: dashed where the face is, solid where the draft puts it. */
  const preview = useMemo(() => {
    if (pose === null)
      return { reference: new Float32Array(0), drafted: new Float32Array(0) };
    const { seat, armMm } = pose;
    const at0 = arcPoint(seat, 0, armMm);
    const drafted = rotateAboutAxis(seat, at0, Math.abs(angleDeg) * pose.sign);
    const out: number[] = [];
    pushSegment(out, seat.centre, drafted);
    return {
      reference: new Float32Array(referenceDashes(seat.centre, at0)),
      drafted: new Float32Array(out),
    };
  }, [pose, angleDeg]);

  if (pose === null || track === null) return null;

  const magnitude = Math.min(
    MAX_DRAFT_DEG,
    Math.max(MIN_DRAFT_DEG, Math.abs(angleDeg)),
  );

  return (
    <>
      <RevolveAxisLine
        anchor={pose.anchor}
        centre={pose.seat.centre}
        reachMm={axisReach(pose.armMm * 2, pose.seat.arcRadiusMm)}
      />
      {/* THE UNDRAFTED EDGE, in CONSTRUCTION ink rather than brass.
          Caught by looking at the founder capture, which is the only check that
          asks whether a thing is LEGIBLE rather than whether it is present and
          correctly computed. At the everyday 3-degree default the two lines are
          0.58 mm apart at the tip — `arm * sin(3°)` — so drawn in the same
          brass as the drafted edge they merged into ONE line and the pair
          stopped reading as an angle at all. Every assertion still passed;
          both lines were there, in the right places, at the right sizes.
          `sketch.constructionInk` is the token that already means exactly this
          ("reference, not profile") and it is a value contrast rather than a
          hue one, which is what survives two nearly-coincident lines. */}
      <Segments
        positions={preview.reference}
        color={sketch.constructionInk}
        opacity={0.7}
        depthTest={false}
        renderOrder={10}
      />
      <Segments
        positions={preview.drafted}
        color={viewport.preview.edge}
        opacity={viewport.preview.edgeOpacity}
        depthTest={false}
        renderOrder={10}
      />
      <ParametricGauge
        label="Draft angle"
        tagLabel="A"
        gaugeId="draft-angle"
        value={magnitude}
        // The track carries the MAGNITUDE; the sign belongs to the editor and
        // is put back here, in the one place that knows which way this gauge
        // was built to lean. A `Pull`/sign flip re-seats the whole instrument.
        onChange={(v) => onAngleChange(v * pose.sign)}
        track={track}
        min={MIN_DRAFT_DEG}
        max={MAX_DRAFT_DEG}
      />
    </>
  );
}
