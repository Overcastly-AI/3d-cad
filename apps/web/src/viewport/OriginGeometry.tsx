/**
 * The ORIGIN — the three principal planes and the three axes, drawn in the
 * scene (UI-W2, part half). Founder-raised: *"what about the ability to enable
 * planes, sketches and bodies? Similar to fusion?"*
 *
 * Until now the origin datums existed only as a picker step: three sheets that
 * appeared while you chose a sketch plane and vanished the moment you did. Once
 * a body was on screen there was NOTHING in the viewport telling you where XY
 * was, which way +Z ran, or where the part sat relative to world zero — so
 * every datum decision (an offset plane, a mirror, a section) was made against
 * geometry you could not see. That is the gap this closes.
 *
 * ## The drawing, and why it looks like this
 *
 * No new palette, no new idea. A shown origin plane is the SAME quiet steel
 * sheet the plane picker draws (`sketch.planeFill` / `planeEdge` /
 * `planeFillOpacity`), because a datum plane should look like a datum plane
 * whether you are picking it or merely referencing it — one datum language, one
 * token source. Boldness for this wave is spent on the timeline, not here; the
 * mandate calls these surfaces quiet precision instruments and the origin is
 * about as quiet as an instrument gets.
 *
 * The one piece of drawing that carries information rather than decoration: an
 * axis is SOLID on its positive half and PHANTOM (dashed) on its negative half.
 * Dashed-means-absent is already this product's language (hidden edges on a
 * drawing sheet, the ghost eye, the isolate glyph), so the line itself says
 * which way is +X without a legend, and the engraved letter at the positive end
 * confirms it. Structure encoding truth, not a decorative tick.
 *
 * ## The frame these are drawn in (FB-21)
 *
 * ONE convention, stated here because this is the module that annotates it for
 * the user: **everything in the viewport is drawn in the SCENE frame (three.js,
 * Y-up), and every kernel quantity crosses into it exactly once, through
 * `sketch/plane.ts`'s `occtToSceneTuple`.** The GLB bakes that same Z-up→Y-up
 * rotation, which is why the body needs no transform of its own.
 *
 * The user-visible consequences, which now all agree because they are all the
 * same vector rather than four constants kept in step:
 *
 *   kernel +Z (a part's height, an XY sketch's extrude direction)
 *     = scene +Y = the Z axis glyph = the ViewCube's TOP = `VIEW_DIRECTIONS.top`
 *   kernel +Y = scene −Z = the ViewCube's BACK (so FRONT looks along kernel +Y,
 *     the drafting convention)
 *   kernel +X = scene +X = the X axis glyph = the ViewCube's RIGHT
 *
 * ## Sizing
 *
 * Fixed-size datum geometry is useless at both ends of the range — a 90 mm
 * sheet is invisible under a 2 m weldment and swamps a 6 mm dowel — so the
 * extent tracks the framed subject's diagonal, with a floor for an empty part.
 * Origin geometry deliberately does NOT feed the camera fit: it is sized FROM
 * the bounds, so letting it back into them would be a feedback loop that zooms
 * out a little further every refit.
 */
import { sketch, viewport } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useEffect, useMemo } from "react";
import {
  BufferGeometry,
  Float32BufferAttribute,
  Matrix4,
  Quaternion,
  Vector3,
  type Box3,
} from "three";

import {
  occtToSceneTuple,
  sceneOriginBasis,
  planeToWorld,
  type DatumPlaneName,
  type PlaneBasis,
  type Vec3Tuple,
} from "../sketch/plane";
import {
  entityIsDrawn,
  ORIGIN_AXES,
  ORIGIN_PLANES,
  originAxisKey,
  originPlaneKey,
  usePartViewStore,
  type OriginAxisName,
} from "./partView";

/** Full sheet size (mm) when the part is empty — the picker's resting size. */
const EMPTY_EXTENT_MM = 90;
/**
 * Sheet size as a fraction of the subject's bounding diagonal. Sized ABOVE 1 on
 * purpose: a datum sheet exactly the size of the part is hidden by the part
 * (XY in particular passes through the base face of anything sitting on the
 * bench), and a plane you cannot see is not a plane you can reason about. At
 * 1.6× the sheet reads as stock laid out AROUND the model, which is how Fusion
 * and Plasticity draw theirs.
 */
const EXTENT_OF_DIAGONAL = 1.6;
/** Axes overrun the sheets so the triad reads as a frame, not a box. */
const AXIS_OVERRUN = 0.75;
/** Phantom-half dash pattern (world mm at a 90 mm sheet), scaled with extent. */
const DASH_FRACTION = 0.03;
const GAP_FRACTION = 0.022;
/** Keep the axis letters under the HUD strips, like the constraint glyphs. */
const LABEL_Z_RANGE: [number, number] = [20, 0];

/**
 * SCENE direction of each KERNEL principal axis (FB-21).
 *
 * A glyph labelled Z has to point where the part's Z actually goes, and the
 * part is drawn in the SCENE frame: the GLB bakes build123d's Z-up→Y-up
 * rotation, so kernel +Z arrives at scene +Y and kernel +Y at scene −Z
 * (`occtToSceneTuple` — the one rotation, `sketch/plane.ts`).
 *
 * These used to be the identity — `Z: [0, 0, 1]` — under a comment asserting
 * that scene and kernel axes coincide. They do not, and the sheets drawn three
 * functions below already knew it: `OriginPlane` builds from
 * `sceneOriginBasis`, which IS rotated. So one component drew its planes in
 * scene space and its axes in kernel space, and the glyph reading Z pointed
 * along the kernel's −Y while the part's height ran along the glyph reading Y —
 * exactly the founder's "turn on the axis and compare them to the view cube".
 *
 * DERIVED, not transcribed. `occtToSceneTuple([0,0,1])` is the same expression
 * the mesh, the sketch ink and the extrude ghost pass through, so the triad
 * cannot drift from the body it annotates the way a hand-written triple can.
 * The camera needs no change: `VIEW_DIRECTIONS.top` is scene +Y, which is now
 * the Z glyph's own direction — the ViewCube's TOP and the Z axis agree because
 * they are the same vector, not because two constants were kept in step.
 */
export const AXIS_DIRECTION: Record<OriginAxisName, Vec3Tuple> = {
  X: occtToSceneTuple([1, 0, 0]),
  Y: occtToSceneTuple([0, 1, 0]),
  Z: occtToSceneTuple([0, 0, 1]),
};

/** Quaternion orienting local XY (+Z normal) onto a plane basis. */
function planeQuaternion(basis: PlaneBasis): Quaternion {
  const { u, v, normal } = basis;
  return new Quaternion().setFromRotationMatrix(
    new Matrix4().makeBasis(
      new Vector3(...u),
      new Vector3(...v),
      new Vector3(...normal),
    ),
  );
}

/** A positions buffer that disposes with the component. */
function usePositions(positions: Float32Array): BufferGeometry {
  const geometry = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute("position", new Float32BufferAttribute(positions, 3));
    return g;
  }, [positions]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return geometry;
}

/** One principal plane as a translucent steel sheet with a scribed border. */
function OriginPlane({
  plane,
  extentMm,
}: {
  plane: DatumPlaneName;
  extentMm: number;
}) {
  const basis = useMemo(() => sceneOriginBasis(plane), [plane]);
  const quaternion = useMemo(() => planeQuaternion(basis), [basis]);
  const border = useMemo(() => {
    const s = extentMm / 2;
    const corners = [
      { x: -s, y: -s },
      { x: s, y: -s },
      { x: s, y: s },
      { x: -s, y: s },
    ];
    const positions = new Float32Array(4 * 6);
    corners.forEach((corner, i) => {
      const next = corners[(i + 1) % 4] ?? corner;
      positions.set(planeToWorld(basis, corner), i * 6);
      positions.set(planeToWorld(basis, next), i * 6 + 3);
    });
    return positions;
  }, [basis, extentMm]);
  const borderGeometry = usePositions(border);
  return (
    <group>
      <mesh quaternion={quaternion} raycast={() => null}>
        <planeGeometry args={[extentMm, extentMm]} />
        <meshBasicMaterial
          color={sketch.planeFill}
          transparent
          opacity={sketch.planeFillOpacity}
          depthWrite={false}
          toneMapped={false}
          side={2 /* DoubleSide */}
        />
      </mesh>
      <lineSegments
        geometry={borderGeometry}
        frustumCulled={false}
        raycast={() => null}
      >
        <lineBasicMaterial color={sketch.planeEdge} toneMapped={false} />
      </lineSegments>
    </group>
  );
}

/**
 * Length of a RESTING axis mark, as a fraction of the enabled datum's length.
 * Short enough that the two states can never be mistaken for one another at a
 * glance, long enough to read as an axis rather than a tick.
 */
const REST_FRACTION = 0.42;
/**
 * Strength of a resting mark: `preview.edgeOpacity`, this product's existing
 * "a hair under solid so it reads as a preview" value for a LINE — referenced,
 * not re-picked.
 *
 * The obvious first choice was `preview.surfaceOpacity` (0.42), the ghost
 * translucency, and the frame said no. A mark at 0.42 composites to ~(46,56,68)
 * over the bench, which is DARKER than a major grid line at (62,77,97) — and
 * the triad lies on the grid's own section lines at world zero, so the quietest
 * plausible value made the thing invisible exactly where it lives. Dimmed has
 * to mean dimmer than the DATUM, not dimmer than the bench it is drawn on.
 * The distance from the enabled state is carried by length, by the missing
 * phantom half and by the missing engraved letter — three differences, none of
 * them a subtlety.
 */
const REST_OPACITY = viewport.preview.edgeOpacity;

/**
 * THE RESTING ORIGIN MARK (CRAFT-3).
 *
 * The audit's P1-1, second half: *"the origin triad is off by default (the
 * ORIGIN panel's six toggles all start hidden), so an axis-aligned view offers
 * no up, no origin and no scale."* Four of the five things missing from
 * `03-front-ortho-void.png` were the grid's job (CRAFT-2); this is the fifth.
 *
 * Two states, and the DIFFERENCE between them is the whole design, because the
 * ORIGIN rows are an existing control and an off-state that looks like its
 * on-state would break it:
 *
 *   at rest   the positive half only, 42 % as long, preview strength, no letter
 *   enabled   full length, full strength, the phantom negative half, engraved
 *
 * So the resting state says WHERE zero is and WHICH WAY IS UP — the two facts
 * an axis-aligned view cannot otherwise carry — and says nothing else. Asking
 * for the axis still buys you the whole datum: three changes at once (length,
 * strength, annotation), which is what makes the toggle feel like it did
 * something.
 *
 * Drawn in the datum ink (`sketch.planeEdge`) rather than a quieter one on
 * purpose: the triad lies ON the grid's own section lines at world zero, so a
 * mark dimmer than the grid would be a mark you cannot see. Quiet here is
 * spent on length and opacity, where the grid cannot swallow it.
 */
function OriginMark({
  axis,
  lengthMm,
}: {
  axis: OriginAxisName;
  lengthMm: number;
}) {
  const dir = AXIS_DIRECTION[axis];
  const positions = useMemo(
    () =>
      new Float32Array([
        0,
        0,
        0,
        dir[0] * lengthMm,
        dir[1] * lengthMm,
        dir[2] * lengthMm,
      ]),
    [dir, lengthMm],
  );
  const geometry = usePositions(positions);
  return (
    <lineSegments
      // Named for the scene probe: a spec asks the GRAPH whether the triad is
      // drawn at rest, which no pixel census can answer on a mark that sits on
      // the grid's own section lines.
      name={`origin-axis-${axis}`}
      geometry={geometry}
      frustumCulled={false}
      raycast={() => null}
      // DRAWN LAST, DELIBERATELY. A translucent object is sorted against the
      // other translucent objects by distance, and this mark sits at the world
      // origin — a near-tie with the camera-following ground grid. The tie
      // broke both ways between otherwise identical frames, and the mark's
      // composite (and so its measured colour) went with it: an ink census of
      // the same scene read 248 px in one run and 0 in the next. `renderOrder`
      // is consulted BEFORE distance, so pinning it puts the annotation over
      // the bench every frame. It writes no depth — a 1 px annotation should
      // not occlude anything — which is what makes drawing it last safe.
      renderOrder={1}
    >
      <lineBasicMaterial
        color={sketch.planeEdge}
        transparent
        opacity={REST_OPACITY}
        depthWrite={false}
        toneMapped={false}
      />
    </lineSegments>
  );
}

/** One principal axis: solid on +, phantom on −, engraved at the + end. */
function OriginAxis({
  axis,
  lengthMm,
}: {
  axis: OriginAxisName;
  lengthMm: number;
}) {
  const dir = AXIS_DIRECTION[axis];
  const positive = useMemo(
    () =>
      new Float32Array([
        0,
        0,
        0,
        dir[0] * lengthMm,
        dir[1] * lengthMm,
        dir[2] * lengthMm,
      ]),
    [dir, lengthMm],
  );
  const negative = useMemo(
    () =>
      new Float32Array([
        0,
        0,
        0,
        -dir[0] * lengthMm,
        -dir[1] * lengthMm,
        -dir[2] * lengthMm,
      ]),
    [dir, lengthMm],
  );
  const positiveGeometry = usePositions(positive);
  const negativeGeometry = usePositions(negative);
  return (
    <group name={`origin-axis-${axis}`}>
      <lineSegments
        geometry={positiveGeometry}
        frustumCulled={false}
        raycast={() => null}
      >
        <lineBasicMaterial color={sketch.planeEdge} toneMapped={false} />
      </lineSegments>
      {/* The phantom half. `computeLineDistances()` on the drawn object is what
          makes a dashed material dash at all — it is a ref effect, not a prop. */}
      <lineSegments
        geometry={negativeGeometry}
        frustumCulled={false}
        raycast={() => null}
        ref={(node) => node?.computeLineDistances()}
      >
        <lineDashedMaterial
          color={sketch.planeEdge}
          dashSize={lengthMm * DASH_FRACTION}
          gapSize={lengthMm * GAP_FRACTION}
          toneMapped={false}
        />
      </lineSegments>
      <Html
        position={[dir[0] * lengthMm, dir[1] * lengthMm, dir[2] * lengthMm]}
        center
        zIndexRange={LABEL_Z_RANGE}
        style={{ pointerEvents: "none" }}
      >
        <span
          data-testid={`origin-axis-label-${axis}`}
          className="font-data text-2xs tracking-[0.18em] text-gauge"
        >
          {axis}
        </span>
      </Html>
    </group>
  );
}

export interface OriginGeometryProps {
  /** The framed subject's bounds — sizes the sheets. Null/empty = resting size. */
  bounds: Box3 | null;
}

/**
 * The origin: the enabled datums, plus the RESTING MARK for every axis that is
 * not enabled (CRAFT-3).
 *
 * The planes still default to HIDDEN, as Fusion's do — a sheet is a working
 * surface and an unasked-for one is in the way. The three AXES no longer do:
 * an axis-aligned view with no grid horizon, no shadow and no letters told the
 * modeller nothing about where zero was or which way was up, and that is the
 * one question a squared-on view is least able to answer for itself. Each axis
 * draws exactly one of the two states, never both, so the toggle keeps a
 * visible job.
 */
export function OriginGeometry({ bounds }: OriginGeometryProps) {
  const view = usePartViewStore((state) => state.view);
  const extentMm = useMemo(() => {
    if (bounds === null || bounds.isEmpty()) return EMPTY_EXTENT_MM;
    const diagonal = bounds.getSize(new Vector3()).length();
    return Math.max(diagonal * EXTENT_OF_DIAGONAL, EMPTY_EXTENT_MM / 2);
  }, [bounds]);
  const planes = ORIGIN_PLANES.filter((plane) =>
    entityIsDrawn(view, originPlaneKey(plane)),
  );
  const axes = ORIGIN_AXES.filter((axis) =>
    entityIsDrawn(view, originAxisKey(axis)),
  );
  const resting = ORIGIN_AXES.filter((axis) => !axes.includes(axis));
  const axisLengthMm = (extentMm / 2) * (1 + AXIS_OVERRUN);
  return (
    <group>
      {planes.map((plane) => (
        <OriginPlane key={plane} plane={plane} extentMm={extentMm} />
      ))}
      {axes.map((axis) => (
        <OriginAxis key={axis} axis={axis} lengthMm={axisLengthMm} />
      ))}
      {resting.map((axis) => (
        <OriginMark
          key={axis}
          axis={axis}
          lengthMm={axisLengthMm * REST_FRACTION}
        />
      ))}
    </group>
  );
}
