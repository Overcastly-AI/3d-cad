/**
 * The 2D authoring layer inside the WebGL viewport. Every color/opacity/size
 * comes from `@loft/design` `sketch` tokens; line materials render unlit and
 * un-tonemapped so the canvas shows the EXACT token hex — one palette, two
 * renderers (verified by the e2e pixel probe).
 */
import {
  DimensionTag,
  DimensionTagCell,
  formatLength,
  lengthUnitLabel,
  PerpendicularIcon,
  SnapCenterIcon,
  SnapEndpointIcon,
  SnapIntersectionIcon,
  SnapMidpointIcon,
  SnapOriginIcon,
  SnapXAxisIcon,
  SnapYAxisIcon,
  TangentIcon,
  HorizontalIcon,
  VerticalIcon,
  type IconProps,
} from "@loft/design";
import { sketch, viewport } from "@loft/design/tokens";
import { Html, useCursor } from "@react-three/drei";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactElement,
} from "react";
import {
  BufferGeometry,
  Float32BufferAttribute,
  Matrix4,
  Quaternion,
  Vector3,
  type Camera,
  type LineSegments,
} from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";

import { isTypingTarget } from "../lib/isTypingTarget";
import { useReducedMotion } from "../lib/useReducedMotion";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { parsePositiveLengthMm } from "../units/length";
import {
  definingPointPositions,
  entitySegmentPositions,
  pickedPointPositions,
} from "../sketch/geometry";
import {
  dimensionWitness,
  drawDimensionFields,
  drawShapeOf,
  type DrawDimensionField,
  type DrawDimensionKey,
  type DrawDimensionValues,
} from "../sketch/drawDimensions";
import {
  ORIGIN_AXIS_FRACTION,
  ORIGIN_DASH_FRACTION,
  ORIGIN_GAP_FRACTION,
  ORIGIN_RING_FRACTION,
  originAxisSpans,
  originIdentity,
  originRingSegments,
  SKETCH_CAMERA_DISTANCE_MM,
  SKETCH_CAMERA_FOV_DEG,
} from "../sketch/origin";
import {
  DATUM_LABELS,
  DATUM_PICKS,
  DATUM_X_AXIS_ID,
  DATUM_Y_AXIS_ID,
  DATUM_ORIGIN_ID,
  datumFrame,
  datumPickState,
  pickWithDatums,
  withoutDatums,
  type DatumKind,
  type DatumPickState,
} from "../sketch/datum";
import { pickCandidates, samePick, PICK_TOLERANCE_PX } from "../sketch/pick";
import {
  DATUM_PLANES,
  sceneOriginBasis,
  planeCameraPose,
  planeToWorld,
  resolveSpecBasis,
  worldToPlane,
  type CameraPose,
  type DatumPlaneName,
  type PlaneBasis,
  type Point2D,
  type SketchPlaneSpec,
} from "../sketch/plane";
import { axisLinePoints, reflectEntity } from "../sketch/mirror";
import { isClick, type PointerGesture } from "../sketch/clickIntent";
import { SNAP_LABELS, SNAP_TOLERANCE_PX, type SnapKind } from "../sketch/snap";
import { useSketchStore, type DrawDimensionDraft } from "../sketch/store";
import {
  dragDraws,
  placesPoints,
  previewEntities,
  type SketchEntity,
} from "../sketch/tools";
import { AdaptiveGrid } from "./AdaptiveGrid";
import { bluingRadiusMm, bluingWash } from "./bluingWash";
import { ConstraintGlyphs } from "./ConstraintGlyphs";
import { sketchIsDrawn, usePartViewStore } from "./partView";

/**
 * DEPTH POLICY OF THE SKETCHER (founder defect, 2026-08-01: *"I had an
 * extruded face then was trying to add a sketch and … I couldn't see it"*).
 *
 * A sketch seated on a face is COPLANAR with that face by construction, so
 * every mark it makes lands in the same depth slot as the solid under it.
 * Measured on the real stack before this landed: a rectangle drawn on the top
 * face of a 20 mm cube produced **0** pixels of `sketch.scribe` ink and a grid
 * that appeared over roughly half the face in speckled patches. Not "hard to
 * see" — gone.
 *
 * Three classes of mark, three different answers, because they do three
 * different jobs:
 *
 * 1. **The ACTIVE sketch's ink** (entities, preview, points, crosshair) draws
 *    ON TOP: `depthTest: false` + an explicit `renderOrder`. Justification for
 *    picking always-on-top over a depth bias: (a) WebGL has no polygon offset
 *    for lines or points — `POLYGON_OFFSET_FILL` is the only capability GLES2
 *    exposes, so `material.polygonOffset` moves nothing on a `lineSegments` or
 *    a `points`; the only alternative is lifting the geometry along the normal,
 *    which is scale- and angle-dependent (big enough to win the depth fight at
 *    one zoom reads as ink floating off the face at a grazing one). (b) Even if
 *    it worked, honest occlusion is the WRONG rule for the layer you are
 *    authoring: a boss standing in front of the plane would hide the line you
 *    are currently dragging, which is the founder's complaint with extra steps.
 *    Every tool worth copying (Fusion, Onshape, Plasticity) draws the active
 *    sketch over the model. It must also be `transparent`, not merely
 *    depth-testless: three renders the whole opaque queue before ANY transparent
 *    object, so an opaque line — whatever its renderOrder — would still be
 *    painted over by the (transparent) grid and plane cards.
 * 2. **The sheet meshes** (datum cards, the bluing patch, the grid) keep depth
 *    TESTING and take {@link COPLANAR_DECAL} instead. They are meshes, so
 *    polygon offset genuinely applies to them, and it is the right tool: a
 *    substrate must still be occluded by geometry actually in front of it, or
 *    an infinite grid washes the whole model.
 * 3. **Committed/solved sketches** ({@link SolvedLayer}) change NOTHING. A
 *    sketch you are not editing sits behind the model it made, exactly as
 *    before — the alternative is a viewport of stacked ghost profiles.
 *
 * Constraint glyphs, the snap mark and the spline handles need no entry here:
 * they are DOM-in-canvas (drei `Html`), so they already float over the scene.
 */
const ACTIVE_INK_RENDER_ORDER = 900;
/** Defining-point dots ride one step above their own lines. */
const ACTIVE_POINT_RENDER_ORDER = 901;
/**
 * The plane's own frame (origin + axes) draws over the solid like the rest of
 * the active layer, but one step UNDER the ink: it is the paper, not what is
 * written on it, so a line drawn along the X axis must cover the axis.
 */
const PLANE_FRAME_RENDER_ORDER = 899;

/**
 * Coplanar-decal depth bias for the sketcher's sheet meshes. Polygon offset is
 * expressed in DEPTH-BUFFER units and is slope-scaled, so unlike a world-mm
 * lift it holds at any zoom and any viewing angle — which is precisely the job
 * it was invented for.
 */
const COPLANAR_DECAL = {
  polygonOffset: true,
  polygonOffsetFactor: -2,
  polygonOffsetUnits: -2,
} as const;

/** Datum sheet half-extent feels like stock on the table (mm). */
const PLANE_SIZE_MM = 90;
/* Normal-on authoring distance (mm) — an A6-ish sheet fills the view. It lives
   in `sketch/origin.ts` with the fov and the frame fractions that scale off it,
   because `sketch/datum.ts` derives the frame's PICK region from the same
   framing and cannot import this file. */
/** Plane-pick vantage: the studio iso the shell opens with, re-centred. */
const PICK_CAMERA_DISTANCE_MM = 230;
/**
 * Press timing for the click/drag discriminator. r3f's `e.delta` reports the
 * travel but not the duration, and duration is half of what separates a
 * trackpad wobble from a deliberate flick-pan (see `sketch/clickIntent.ts`), so
 * the press time is recorded here and read back on the click.
 *
 * A module-level ref rather than component state on purpose: a pointer press is
 * a global, singular thing, both call sites below need it, and re-rendering the
 * scene on pointerdown would cost a frame in the middle of a gesture.
 */
const pressedAt = { current: null as number | null };

/** Remember when this press started (any button, any target in the scene). */
function notePressStart(event: { nativeEvent: { timeStamp: number } }): void {
  pressedAt.current = event.nativeEvent.timeStamp;
}

/**
 * Did the press that is still down OPEN a placement sequence? Set by the
 * pointer-down that placed a first point; read by the release to decide whether
 * a drag should COMPLETE the shape (FB-15). Module-level for the same reason as
 * {@link pressedAt}: a press is one global thing, and re-rendering the scene
 * mid-gesture would cost a frame exactly when the rubber band is moving.
 */
const strokeOpen = { current: false };

/** The gesture this click event completes — travel plus press duration. */
function gestureOf(event: {
  delta: number;
  nativeEvent: { timeStamp: number };
}): PointerGesture {
  const start = pressedAt.current;
  return {
    travelPx: event.delta,
    durationMs: start === null ? null : event.nativeEvent.timeStamp - start,
  };
}

/** One solved sketch feature, ready to render (on its resolved plane basis). */
export interface SolvedSketchLayer {
  featureId: string;
  basis: PlaneBasis;
  entities: SketchEntity[];
}

/** Quaternion orienting local XY (+Z normal) onto the plane basis. */
function planeQuaternion(basis: PlaneBasis): Quaternion {
  const { u, v, normal } = basis;
  const matrix = new Matrix4().makeBasis(
    new Vector3(...u),
    new Vector3(...v),
    new Vector3(...normal),
  );
  return new Quaternion().setFromRotationMatrix(matrix);
}

/** Quaternion orienting drei's Grid (local XZ, +Y normal) onto the plane. */
function gridQuaternion(basis: PlaneBasis): Quaternion {
  const { u, normal } = basis;
  const x = new Vector3(...u);
  const y = new Vector3(...normal);
  const z = x.clone().cross(y);
  return new Quaternion().setFromRotationMatrix(
    new Matrix4().makeBasis(x, y, z),
  );
}

/**
 * The scene camera's vertical field of view, with the orthographic fallback the
 * three call sites here all need (an ortho camera frames by zoom, not fov).
 */
function cameraFov(camera: Camera): number {
  return "fov" in camera && typeof camera.fov === "number"
    ? camera.fov
    : SKETCH_CAMERA_FOV_DEG;
}

/** Plane-mm segment pairs → a world-space positions buffer on this basis. */
function segmentPositions(
  basis: PlaneBasis,
  segments: ReadonlyArray<readonly [Point2D, Point2D]>,
): Float32Array {
  const out = new Float32Array(segments.length * 6);
  segments.forEach(([a, b], i) => {
    out.set(planeToWorld(basis, a), i * 6);
    out.set(planeToWorld(basis, b), i * 6 + 3);
  });
  return out;
}

/** Shared geometry plumbing: a positions buffer with disposal. */
function usePositionsGeometry(positions: Float32Array): BufferGeometry {
  const geometry = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute("position", new Float32BufferAttribute(positions, 3));
    return g;
  }, [positions]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return geometry;
}

interface InkSegmentsProps {
  positions: Float32Array;
  color: string;
  dashed?: boolean;
  /** Dash geometry (world mm); defaults to the rubber-band preview pattern. */
  dashSize?: number;
  gapSize?: number;
  /**
   * This is the ACTIVE sketch — draw it over the solid (policy note above).
   * Off by default so committed/solved ink keeps ordinary occlusion.
   */
  onTop?: boolean;
  /** Order WITHIN the on-top layer; defaults to the ink's own step. */
  order?: number;
}

/** One layer of sketch ink — a single LineSegments draw call. */
function InkSegments({
  positions,
  color,
  dashed = false,
  dashSize = sketch.previewDashMm,
  gapSize = sketch.previewGapMm,
  onTop = false,
  order = ACTIVE_INK_RENDER_ORDER,
}: InkSegmentsProps) {
  const ref = useRef<LineSegments>(null);
  const geometry = usePositionsGeometry(positions);
  // LineDashedMaterial needs per-vertex line distances.
  useEffect(() => {
    if (dashed) ref.current?.computeLineDistances();
  }, [geometry, dashed]);
  if (positions.length === 0) return null;
  // Alpha stays 1: `transparent` is here to put the ink in the queue that
  // renders LAST, not to fade it, so the token hex still lands exactly (the
  // e2e pixel probe reads it).
  const depth = onTop
    ? { depthTest: false, depthWrite: false, transparent: true }
    : {};
  return (
    <lineSegments
      ref={ref}
      geometry={geometry}
      frustumCulled={false}
      renderOrder={onTop ? order : 0}
    >
      {dashed ? (
        <lineDashedMaterial
          color={color}
          dashSize={dashSize}
          gapSize={gapSize}
          toneMapped={false}
          {...depth}
        />
      ) : (
        <lineBasicMaterial color={color} toneMapped={false} {...depth} />
      )}
    </lineSegments>
  );
}

/** Split entities into profile (solid scribe) and construction (dashed) sets. */
function partitionConstruction(entities: readonly SketchEntity[]): {
  profile: SketchEntity[];
  construction: SketchEntity[];
} {
  const profile: SketchEntity[] = [];
  const construction: SketchEntity[] = [];
  for (const entity of entities) {
    (entity.construction ? construction : profile).push(entity);
  }
  return { profile, construction };
}

/** Defining points (endpoints, centers) — screen-space brass dots. */
function InkPoints({
  positions,
  color,
  sizePx = sketch.pointSizePx,
  onTop = false,
}: {
  positions: Float32Array;
  color: string;
  sizePx?: number;
  /** Active-sketch handles draw over the solid (policy note above). */
  onTop?: boolean;
}) {
  const geometry = usePositionsGeometry(positions);
  if (positions.length === 0) return null;
  return (
    <points
      geometry={geometry}
      frustumCulled={false}
      renderOrder={onTop ? ACTIVE_POINT_RENDER_ORDER : 0}
    >
      <pointsMaterial
        color={color}
        size={sizePx}
        sizeAttenuation={false}
        toneMapped={false}
        {...(onTop
          ? { depthTest: false, depthWrite: false, transparent: true }
          : {})}
      />
    </points>
  );
}

/** One selectable datum sheet (plane-pick step). */
function DatumSheet({ plane }: { plane: DatumPlaneName }) {
  const hoveredPlane = useSketchStore((state) => state.hoveredPlane);
  const setHoveredPlane = useSketchStore((state) => state.setHoveredPlane);
  const choosePlane = useSketchStore((state) => state.choosePlane);
  const invalidate = useThree((state) => state.invalidate);
  const [pointerOver, setPointerOver] = useState(false);
  useCursor(pointerOver);
  const hovered = hoveredPlane === plane;

  const basis = useMemo(() => sceneOriginBasis(plane), [plane]);
  const quaternion = useMemo(() => planeQuaternion(basis), [basis]);
  const edgePositions = useMemo(() => {
    const s = PLANE_SIZE_MM / 2;
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
  }, [basis]);
  const edgeGeometry = usePositionsGeometry(edgePositions);

  // Hover state changes must draw a frame under frameloop="demand".
  useEffect(() => {
    invalidate();
  }, [hovered, invalidate]);

  return (
    <group>
      <mesh
        quaternion={quaternion}
        onPointerOver={(e) => {
          e.stopPropagation();
          setPointerOver(true);
          setHoveredPlane(plane);
        }}
        onPointerOut={() => {
          setPointerOver(false);
          setHoveredPlane(null);
        }}
        onPointerDown={notePressStart}
        onClick={(e) => {
          e.stopPropagation();
          // Same discriminator as the drawing surface below — the two used to
          // carry the same inline magic number and could drift apart.
          if (isClick(gestureOf(e))) choosePlane(plane);
        }}
      >
        <planeGeometry args={[PLANE_SIZE_MM, PLANE_SIZE_MM]} />
        <meshBasicMaterial
          color={sketch.planeFill}
          transparent
          opacity={
            hovered ? sketch.planeHoverFillOpacity : sketch.planeFillOpacity
          }
          depthWrite={false}
          side={2 /* DoubleSide */}
          {...COPLANAR_DECAL}
        />
      </mesh>
      <lineSegments geometry={edgeGeometry} frustumCulled={false}>
        <lineBasicMaterial
          color={hovered ? sketch.planeHoverEdge : sketch.planeEdge}
          toneMapped={false}
        />
      </lineSegments>
    </group>
  );
}

/**
 * Invisible raycast target: pointer position + click-to-place (drawing
 * tools) or click-to-pick (select tool), in plane mm. Picking uses the RAW
 * pointer point (snap would jump off fine targets) with a screen-pixel
 * tolerance converted to plane mm at the event's camera distance.
 */
function PointerCatcher({ basis }: { basis: PlaneBasis }) {
  const setCursor = useSketchStore((state) => state.setCursor);
  const aim = useSketchStore((state) => state.aim);
  const placeAt = useSketchStore((state) => state.placeAt);
  const selectAt = useSketchStore((state) => state.selectAt);
  const setHoverPick = useSketchStore((state) => state.setHoverPick);
  const invalidate = useThree((state) => state.invalidate);
  const camera = useThree((state) => state.camera);
  const heightPx = useThree((state) => state.size.height);
  const quaternion = useMemo(() => planeQuaternion(basis), [basis]);

  const rawPlanePoint = (
    e: ThreeEvent<PointerEvent> | ThreeEvent<MouseEvent>,
  ) => worldToPlane(basis, [e.point.x, e.point.y, e.point.z]);

  /** One screen pixel in plane mm at this event's depth (perspective camera). */
  const worldPerPx = (e: ThreeEvent<PointerEvent> | ThreeEvent<MouseEvent>) =>
    (2 * e.distance * Math.tan((cameraFov(camera) * Math.PI) / 360)) / heightPx;
  const toleranceMm = (e: ThreeEvent<PointerEvent> | ThreeEvent<MouseEvent>) =>
    PICK_TOLERANCE_PX * worldPerPx(e);
  /** The snap magnet is a hair wider than the pick tolerance (see snap.ts). */
  const snapToleranceMm = (
    e: ThreeEvent<PointerEvent> | ThreeEvent<MouseEvent>,
  ) => SNAP_TOLERANCE_PX * worldPerPx(e);
  /**
   * Modifier state read from the EVENT — authoritative at the instant of the
   * click, where a keyboard-tracked flag can be one repaint stale. Ctrl/Cmd
   * suppresses every snap; Shift locks the aim to an axis.
   *
   * Alt is NOT a sketch modifier and must never become one: it belongs to the
   * camera (VP-1a — Alt+left-drag orbits, the only orbit gesture a trackpad can
   * produce while the sketcher owns LEFT). The press and click handlers below
   * therefore ignore alt-modified events outright.
   */
  const modifiers = (e: ThreeEvent<PointerEvent> | ThreeEvent<MouseEvent>) => ({
    suppressed: e.nativeEvent.ctrlKey || e.nativeEvent.metaKey,
    axisLock: e.nativeEvent.shiftKey,
  });

  return (
    <mesh
      position={[basis.origin[0], basis.origin[1], basis.origin[2]]}
      quaternion={quaternion}
      onPointerMove={(e) => {
        const raw = rawPlanePoint(e);
        // ONE aim path (store.aim): it resolves the entity snap / axis lock /
        // grid AND records which one it took, so the mark the user reads and
        // the point a click places are the same number by construction.
        aim(raw, snapToleranceMm(e), modifiers(e));
        // Read the tool at EVENT time: the render-subscribed value is a
        // stale closure for the frame right after a keyboard tool switch
        // (zustand commit → React render → r3f handler swap), which loses
        // the first click of a fast key-then-click sequence.
        const aimTool = useSketchStore.getState().tool;
        if (!placesPoints(aimTool)) {
          const state = useSketchStore.getState();
          // Select hovers the frame too (SKETCH-2) — the same candidate list
          // `selectAt` clicks, so the highlight can never promise a pick the
          // click does not make. The whole-curve tools (trim/extend/offset/
          // mirror/corner) address DRAWN geometry only: the frame is not
          // theirs to cut, reflect or fillet.
          const all =
            aimTool === "select"
              ? pickWithDatums(
                  state.entities,
                  raw,
                  toleranceMm(e),
                  datumFrame(state.datumFrameHalfMm),
                  "replace",
                  // The selection is an INPUT to picking now: over the frame
                  // with something held, a plain click clears instead of
                  // selecting, so the frame must not light up as if it were
                  // about to be picked. Same arguments as `selectAt`, or the
                  // highlight promises a pick the click does not make.
                  state.selection,
                )
              : pickCandidates(
                  withoutDatums(state.entities),
                  raw,
                  toleranceMm(e),
                );
          // Trim/extend/offset/mirror address a whole curve — the aim affordance
          // highlights the hovered target only (points are irrelevant to them);
          // select keeps its finer point-first grain. In the mirror axis phase
          // the hovered line drives the live reflection ghost (DrawLayer).
          const candidate =
            (aimTool === "select"
              ? all[0]
              : all.find((pick) => pick.kind === "entity")) ?? null;
          const previous = useSketchStore.getState().hoverPick;
          if (
            (candidate === null) !== (previous === null) ||
            (candidate !== null &&
              previous !== null &&
              !samePick(candidate, previous))
          ) {
            setHoverPick(candidate);
          }
        }
        invalidate();
      }}
      onPointerOut={() => {
        setCursor(null);
        setHoverPick(null);
        invalidate();
      }}
      onPointerDown={(e) => {
        notePressStart(e);
        strokeOpen.current = false;
        const store = useSketchStore.getState();
        // PRESS-DRAG-RELEASE (FB-15). The press places the first point, so the
        // rubber band follows the held pointer through the SAME `pending`
        // sequence the two-click path uses — one state machine, two gestures,
        // and nothing to keep in sync. The release below completes the shape
        // only if the pointer actually travelled (`isClick`, the FB-12
        // discriminator — no second threshold), so a press-and-release in place
        // leaves the sequence open and click-then-click carries on unchanged.
        //
        // Mouse and pen only. On touch, the finger that would drag is also the
        // finger that pans, and a two-finger pan delivers a primary
        // pointer-down of its own — placing on THAT would scatter points every
        // time somebody moved the view. Touch keeps tap-then-tap, which is the
        // better touch gesture anyway.
        //
        // Alt held means the camera has this drag (VP-1a): the same press is
        // orbiting, and placing a point from it would draw a stray entity every
        // time the modeller looked around.
        if (
          e.nativeEvent.button !== 0 ||
          e.nativeEvent.altKey ||
          e.nativeEvent.pointerType === "touch" ||
          !dragDraws(store.tool)
        ) {
          return;
        }
        store.placeAt(
          store.aim(rawPlanePoint(e), snapToleranceMm(e), modifiers(e)),
        );
        strokeOpen.current = useSketchStore.getState().pending.length > 0;
        invalidate();
      }}
      onClick={(e) => {
        // The release that ends an Alt-orbit (VP-1a) is the camera's, not the
        // sketcher's: it places nothing and picks nothing. `strokeOpen` is
        // cleared so a press that began un-modified and released under Alt
        // cannot leave a stale "a drag is in flight" flag for the next click.
        if (e.nativeEvent.altKey) {
          strokeOpen.current = false;
          return;
        }
        const store = useSketchStore.getState();
        const clickTool = store.tool;
        if (dragDraws(clickTool)) {
          const wasOpen = strokeOpen.current;
          strokeOpen.current = false;
          // The press already placed; a RELEASE only finishes the shape when
          // the gesture was a drag. `pending` is re-read live rather than
          // trusted from the press: Escape mid-drag cancels the placement, and
          // the release that follows must not resurrect it.
          if (
            wasOpen &&
            !isClick(gestureOf(e)) &&
            useSketchStore.getState().pending.length > 0
          ) {
            store.placeAt(
              store.aim(rawPlanePoint(e), snapToleranceMm(e), modifiers(e)),
            );
            invalidate();
          }
          return;
        }
        if (!isClick(gestureOf(e))) return; // the camera moved, not the model
        if (clickTool === "select") {
          selectAt(rawPlanePoint(e), toleranceMm(e));
        } else if (clickTool === "trim" || clickTool === "extend") {
          // Trim/extend send the RAW pick (unsnapped): the backend uses it to
          // choose the segment/end, and snapping would jump off a fine target.
          const raw = rawPlanePoint(e);
          const target =
            pickCandidates(
              withoutDatums(store.entities),
              raw,
              toleranceMm(e),
            ).find((pick) => pick.kind === "entity") ?? null;
          store.requestEdit(
            clickTool,
            target !== null && target.kind === "entity" ? target.id : null,
            raw,
          );
        } else if (clickTool === "offset") {
          // Offset picks a whole curve (raw pick, like trim/extend) and opens
          // the inline signed-distance editor; the offset fires on confirm.
          const raw = rawPlanePoint(e);
          const target =
            pickCandidates(
              withoutDatums(store.entities),
              raw,
              toleranceMm(e),
            ).find((pick) => pick.kind === "entity") ?? null;
          store.beginOffset(
            target !== null && target.kind === "entity" ? target.id : null,
          );
        } else if (clickTool === "mirror") {
          // Two-phase: click entities to build the target set, then (axis
          // phase) click a line to reflect them about it.
          const raw = rawPlanePoint(e);
          const target =
            pickCandidates(
              withoutDatums(store.entities),
              raw,
              toleranceMm(e),
            ).find((pick) => pick.kind === "entity") ?? null;
          const id = target?.kind === "entity" ? target.id : null;
          if (store.mirror?.phase === "axis") store.pickMirrorAxis(id);
          else store.toggleMirrorTarget(id);
        } else if (clickTool === "fillet" || clickTool === "chamfer") {
          // Corner tools collect two line legs (raw pick, like trim/offset);
          // the value editor opens once both are held.
          const raw = rawPlanePoint(e);
          const target =
            pickCandidates(
              withoutDatums(store.entities),
              raw,
              toleranceMm(e),
            ).find((pick) => pick.kind === "entity") ?? null;
          store.pickCornerLine(
            target !== null && target.kind === "entity" ? target.id : null,
          );
        } else {
          placeAt(
            store.aim(rawPlanePoint(e), snapToleranceMm(e), modifiers(e)),
          );
        }
        invalidate();
      }}
      onDoubleClick={(e) => {
        // Double-click finishes an open placement sequence (the spline's fit
        // points). The two down-events already placed the trailing point (the
        // second is rejected as coincident), so committing the pending set is
        // exactly right.
        if (useSketchStore.getState().tool !== "spline") return;
        e.stopPropagation();
        useSketchStore.getState().finishPlacement();
        invalidate();
      }}
    >
      <planeGeometry args={[100000, 100000]} />
      <meshBasicMaterial transparent opacity={0} depthWrite={false} />
    </mesh>
  );
}

/**
 * Snap-cursor crosshair (brass, world-mm arms) — the aim indicator for a FREE
 * or grid-snapped point. It stands down while a snap mark is up: the mark is
 * then the aim indicator, and measured on the captured shots the crosshair's
 * arms poked through every form and turned the centre mark (a circled cross)
 * into two crosses. One aim, one indicator — Chanel's "remove one accessory",
 * applied where it was actually costing legibility.
 */
function Crosshair({ basis }: { basis: PlaneBasis }) {
  const cursor = useSketchStore((state) => state.cursor);
  const marked = useSketchStore((state) => state.snapCandidate !== null);
  const positions = useMemo(() => {
    if (cursor === null || marked) return new Float32Array(0);
    const a = sketch.cursorArmMm;
    const arms = [
      [
        { x: cursor.x - a, y: cursor.y },
        { x: cursor.x + a, y: cursor.y },
      ],
      [
        { x: cursor.x, y: cursor.y - a },
        { x: cursor.x, y: cursor.y + a },
      ],
    ];
    const out = new Float32Array(12);
    arms.forEach((arm, i) => {
      out.set(planeToWorld(basis, arm[0] ?? { x: 0, y: 0 }), i * 6);
      out.set(planeToWorld(basis, arm[1] ?? { x: 0, y: 0 }), i * 6 + 3);
    });
    return out;
  }, [cursor, marked, basis]);
  return <InkSegments positions={positions} color={sketch.cursor} onTop />;
}

/** Keep the snap mark under the HUD strips, like the constraint glyphs. */
const SNAP_Z_RANGE: [number, number] = [20, 0];

/**
 * Snap mark size (px). 24 rather than the toolbar's 16: measured on the
 * captured frames, a 16px form sat inside the entity's own brass point dot and
 * the four shapes stopped being tellable apart at a glance — which is the one
 * thing this mark exists to do.
 */
const SNAP_MARK_PX = 24;

/**
 * One mark per snap kind. Tangent and perpendicular reuse the CONSTRAINT
 * glyphs of the same names — the snap and the constraint mean the same
 * relation, so they get the same mark (one glyph, one source).
 */
const SNAP_MARKS: Record<SnapKind, (props: IconProps) => ReactElement> = {
  endpoint: SnapEndpointIcon,
  midpoint: SnapMidpointIcon,
  center: SnapCenterIcon,
  intersection: SnapIntersectionIcon,
  tangent: TangentIcon,
  perpendicular: PerpendicularIcon,
  origin: SnapOriginIcon,
  "x-axis": SnapXAxisIcon,
  "y-axis": SnapYAxisIcon,
  "axis-h": HorizontalIcon,
  "axis-v": VerticalIcon,
};

/**
 * THE honesty cue (UI-W5): a mark at the candidate NAMING which snap this
 * click will take, before it is taken. A snap that silently grabs the wrong
 * thing is worse than no snap — the sketch ends up subtly wrong and nothing on
 * screen ever said so — so the mark carries both a distinct form and the WORD.
 * Competitors show the symbol alone; the word is the deliberate extra, because
 * a symbol only informs someone who already learned it.
 *
 * Measured contrast on the carbide viewport ground (#0F141A): the mark in
 * `brass-hover` reads 11.80:1, and 5.49:1 in the worst case of sitting on a
 * major grid line (#3E4D61) — both clear of WCAG-AA. The word sits on the
 * anvil chip ground (#161D27) in `mist` at 13.21:1. Ratios are stated because
 * a "redundant" cue in this codebase once measured 1.54:1 while its comment
 * claimed otherwise; eyeballing a dark-on-dark pair does not work.
 *
 * Pointer-inert: the mark floats over the pointer catcher and must never eat
 * the click it is describing.
 */
function SnapMarker({ basis }: { basis: PlaneBasis }) {
  const candidate = useSketchStore((state) => state.snapCandidate);
  const plane = useSketchStore((state) => state.plane);
  if (candidate === null) return null;
  const Mark = SNAP_MARKS[candidate.kind];
  // The candidate's OWN word wins where it carries one: the origin's honest
  // name depends on what this plane's zero is (`sketch/origin.ts`).
  const label = candidate.label ?? SNAP_LABELS[candidate.kind];
  // …and where that zero can MOVE — a seated face's area centroid — the caveat
  // rides the accessible name, so the one surface that states it is the one the
  // user is reading at the moment they take it.
  const note = candidate.kind === "origin" ? originIdentity(plane).note : null;
  return (
    <Html
      position={planeToWorld(basis, candidate.at)}
      center
      zIndexRange={SNAP_Z_RANGE}
      style={{ pointerEvents: "none" }}
    >
      <div
        className="relative"
        data-testid="snap-marker"
        data-snap-kind={candidate.kind}
        data-snap-entities={
          candidate.entities.length > 0
            ? candidate.entities.join(" ")
            : undefined
        }
        role="img"
        aria-label={
          note === null
            ? `Snapping to ${label.toLowerCase()}`
            : `Snapping to ${label.toLowerCase()} — ${note}`
        }
      >
        <Mark size={SNAP_MARK_PX} className="block text-brass-hover" />
        {/* The word is a callout, offset clear of the mark's own strokes —
            derived from the mark size so the two can never grow into each
            other (the first cut had the chip corner sitting ON the square). */}
        <span
          className="absolute whitespace-nowrap border border-hairline bg-anvil px-1.5 py-px font-display text-2xs uppercase tracking-[0.16em] text-mist"
          style={{ left: SNAP_MARK_PX + 4, bottom: SNAP_MARK_PX + 4 }}
        >
          {label}
        </span>
      </div>
    </Html>
  );
}

/** The tag rail rides with the snap mark, under the HUD strips. */
const DIMENSION_TAG_Z_RANGE: [number, number] = [21, 0];

/** Display precision for a size cell — a size, not a coordinate readout. */
const sizeText = (mm: number, unit: Parameters<typeof formatLength>[1]) =>
  formatLength(mm, unit, { unitSuffix: false, maxFractionDigits: 2 });

/** Keys that start a value: digits, a decimal point, a leading minus. */
const STARTS_A_VALUE = /^[0-9.]$/;

/**
 * WHICH CORNER THE TAG HANGS FROM. The rail is anchored at the gesture's second
 * point — where the cursor is, which is what the founder asked for — and pushed
 * into the quadrant the drag was heading, so it hangs OFF the shape rather than
 * over it. The snap mark owns the cursor itself and puts its word up-and-right
 * (`SnapMarker`), so the rail never occupies the same pixels: it is offset by a
 * gap and flipped by direction, not stacked on the same spot
 * (docs/design/pre-selection.md §2 — one aim, one indicator).
 */
function tagTransform(from: Point2D, to: Point2D): string {
  const gap = 10;
  // Plane +y is up on screen, so a drag in +y hangs the rail upward.
  const x = to.x >= from.x ? `${gap}px` : `calc(-100% - ${gap}px)`;
  const y = to.y >= from.y ? `calc(-100% - ${gap}px)` : `${gap}px`;
  return `translate(${x}, ${y})`;
}

interface TagState {
  from: Point2D;
  to: Point2D;
  fields: DrawDimensionField[];
  /** Armed = the shape is drawn and the cells take typing. */
  armed: boolean;
}

/**
 * DIMENSION WHILE YOU DRAW (FB-16) — the size cells hung on the shape being
 * made. Two states, deliberately continuous:
 *
 *  · **live**, while the pointer still owns the size: a read-only strip showing
 *    the width/height (or length, or radius) the rubber band currently has. The
 *    DRO already reports WHERE the cursor is; nothing reported how BIG the
 *    thing you are dragging is, which is the number you actually care about.
 *    Pointer-inert, so it can never eat the click that finishes the shape.
 *  · **armed**, the moment the shape commits: the same numbers in the same
 *    place become cells you type into. Tab walks them (and wraps — a dimension
 *    pair is a loop, and tabbing out of the viewport mid-value is a dead end),
 *    Enter applies, Escape hands the canvas back with the shape kept.
 *
 * You do not have to click into a cell first: with the strip armed, typing a
 * DIGIT anywhere puts it in the first cell and focuses it — the tool proposes,
 * the user disposes (CLAUDE.md flow rule). Every other key still reaches the
 * canvas, so `r`, `l`, `Escape` behave exactly as they do without a strip up.
 *
 * WHY VALUES APPLY ON ENTER, NOT PER KEYSTROKE: each applied value is a
 * revision — a solve and a debounced save. Applying per keystroke would rebuild
 * the sketch at "5" on the way to "50", and would make Escape unable to
 * abandon anything, because the model would already have moved.
 */
function DrawDimensionTag({ basis }: { basis: PlaneBasis }) {
  const draft = useSketchStore((state) => state.drawDimension);
  const tool = useSketchStore((state) => state.tool);
  const pending = useSketchStore((state) => state.pending);
  const cursor = useSketchStore((state) => state.cursor);
  const commit = useSketchStore((state) => state.commitDrawDimensions);
  const dismiss = useSketchStore((state) => state.dismissDrawDimensions);
  const focusCell = useSketchStore((state) => state.focusDrawDimension);
  const unit = useDocumentLengthUnit();
  const invalidate = useThree((state) => state.invalidate);
  const inputs = useRef(new Map<DrawDimensionKey, HTMLInputElement>());

  const state: TagState | null = useMemo(() => {
    if (draft !== null) {
      return {
        from: draft.from,
        to: draft.to,
        fields: draft.fields,
        armed: true,
      };
    }
    const shape = drawShapeOf(tool);
    const from = pending[0];
    if (shape === null || from === undefined || cursor === null) return null;
    if (pending.length !== 1) return null;
    const fields = drawDimensionFields(shape, from, cursor);
    // Nothing to say about a zero-size rubber band.
    if (fields.every((field) => field.measuredMm === 0)) return null;
    return { from, to: cursor, fields, armed: false };
  }, [draft, tool, pending, cursor]);

  const armed = state?.armed === true;
  const firstKey = state?.fields[0]?.key;
  // One identity per drawn shape: it re-keys the cells, so a new rectangle
  // never inherits the numbers typed into the last one.
  const draftKey = draft === null ? "live" : draft.ids.join(",");

  /**
   * THE CELLS ARE UNCONTROLLED, and that is a decision, not an oversight. A
   * controlled cell has to round-trip every keystroke through React state, and
   * between the two keystrokes of "50" it has not re-rendered yet — so the
   * second digit lands in a field the DOM still shows as empty and the first is
   * lost. Measured against the real browser: typing "50" yielded "0". Nothing
   * here needs to re-render as you type (the callout follows FOCUS, not value),
   * so the browser owns the text and {@link readValues} reads it at commit.
   */
  const readValues = useCallback((): DrawDimensionValues => {
    const parsed: DrawDimensionValues = {};
    for (const [key, input] of inputs.current) {
      const mm = parsePositiveLengthMm(input.value, unit);
      if (mm !== null) parsed[key] = mm;
    }
    return parsed;
  }, [unit]);

  const apply = useCallback(() => {
    commit(readValues());
    invalidate();
  }, [commit, readValues, invalidate]);

  // Type anywhere to start dimensioning: the first digit lands in the first
  // cell. Enter with nothing typed accepts the shape as drawn and closes.
  useEffect(() => {
    if (!armed || firstKey === undefined) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "Enter") {
        event.preventDefault();
        apply();
        return;
      }
      if (!STARTS_A_VALUE.test(event.key) && event.key !== "Tab") return;
      const input = inputs.current.get(firstKey);
      if (input === undefined) return;
      // Focus DURING keydown and let the BROWSER deliver the character to the
      // newly-focused cell. Inserting it by hand (preventDefault + setState)
      // is what loses it — see the note on `readValues`.
      if (event.key === "Tab") event.preventDefault();
      input.focus();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [armed, firstKey, apply]);

  if (state === null) return null;

  const { from, to, fields } = state;
  const onKeyDown = (
    event: ReactKeyboardEvent<HTMLInputElement>,
    index: number,
  ) => {
    if (event.key === "Escape") {
      // The field's own Escape: abandon the typing, keep the shape, hand the
      // canvas back with the tool still armed. It never reaches the sketch
      // cascade, so it cannot also drop the tool.
      event.stopPropagation();
      event.preventDefault();
      event.currentTarget.blur();
      dismiss();
      invalidate();
      return;
    }
    if (event.key === "Enter") {
      // Explicit, not an implicit form submission: a form with no submit
      // button only submits implicitly when it holds EXACTLY ONE field, so a
      // rectangle's two cells would have swallowed Enter while a circle's one
      // cell applied. Measured — the rectangle's Enter did nothing at all.
      event.preventDefault();
      apply();
      return;
    }
    if (event.key !== "Tab" || fields.length < 2) return;
    const step = event.shiftKey ? -1 : 1;
    const next = fields[(index + step + fields.length) % fields.length];
    if (next === undefined) return;
    event.preventDefault();
    inputs.current.get(next.key)?.focus();
  };
  return (
    <Html
      position={planeToWorld(basis, to)}
      zIndexRange={DIMENSION_TAG_Z_RANGE}
      style={{ pointerEvents: "none" }}
    >
      <div style={{ transform: tagTransform(from, to) }}>
        <div
          key={draftKey}
          role={armed ? "group" : undefined}
          data-testid="draw-dimensions"
          data-state={armed ? "armed" : "live"}
          style={{ pointerEvents: armed ? "auto" : "none" }}
          aria-label={armed ? "Size of the shape you just drew" : undefined}
        >
          <DimensionTag unit={lengthUnitLabel(unit)}>
            {fields.map((field, index) =>
              armed ? (
                <DimensionTagCell
                  key={field.key}
                  label={field.label}
                  width={6}
                  placeholder={sizeText(field.measuredMm, unit)}
                  aria-label={`${field.name} in ${lengthUnitLabel(unit)}`}
                  data-testid={`draw-dimension-${field.key}`}
                  ref={(node: HTMLInputElement | null) => {
                    if (node === null) inputs.current.delete(field.key);
                    else inputs.current.set(field.key, node);
                  }}
                  onFocus={() => focusCell(field.key)}
                  onBlur={() => focusCell(null)}
                  onKeyDown={(event) => onKeyDown(event, index)}
                />
              ) : (
                <DimensionTagCell
                  key={field.key}
                  label={field.label}
                  width={6}
                  readout={sizeText(field.measuredMm, unit)}
                />
              ),
            )}
          </DimensionTag>
          {armed ? (
            <p className="mt-1 font-body text-2xs text-gauge">
              {fields.length > 1
                ? "Type a size · Tab switches · Enter applies"
                : "Type a size · Enter applies"}
            </p>
          ) : null}
        </div>
      </div>
    </Html>
  );
}

/**
 * Live modifier state for the aim. The pointer handlers already read Ctrl /
 * Cmd / Shift off each event, but a modifier pressed with the mouse HELD STILL
 * would otherwise leave the mark asserting a snap the next click will not take
 * — so the keyboard drives a re-resolve of the last raw aim too.
 */
function useSnapModifiers(active: boolean) {
  const setSnapModifiers = useSketchStore((state) => state.setSnapModifiers);
  const invalidate = useThree((state) => state.invalidate);
  useEffect(() => {
    if (!active) return;
    const sync = (event: KeyboardEvent) => {
      setSnapModifiers({
        suppressed: event.ctrlKey || event.metaKey,
        axisLock: event.shiftKey,
      });
      invalidate();
    };
    const clear = () => {
      setSnapModifiers({ suppressed: false, axisLock: false });
      invalidate();
    };
    window.addEventListener("keydown", sync);
    window.addEventListener("keyup", sync);
    // A chord that takes focus away (⌘Tab) never delivers its keyup, which
    // would strand the aim in freehand until the next modifier press.
    window.addEventListener("blur", clear);
    return () => {
      window.removeEventListener("keydown", sync);
      window.removeEventListener("keyup", sync);
      window.removeEventListener("blur", clear);
    };
  }, [active, setSnapModifiers, invalidate]);
}

/**
 * The mm grid on the active sketch plane (cell = the 1 mm snap step).
 *
 * `coplanar` is not cosmetic here: this grid is laid ON whatever the sketch is
 * seated on, so on a model face (or an origin datum a body happens to sit on)
 * it lands in the same depth slot as the solid and speckles into patches —
 * measured before the fix, roughly half the face gridded and half not. It keeps
 * depth TESTING, so a boss standing in front of the plane still occludes it;
 * only the tie is broken (see the depth-policy note at the top of this file).
 */
function SketchGrid({ basis }: { basis: PlaneBasis }) {
  const quaternion = useMemo(() => gridQuaternion(basis), [basis]);
  return (
    <AdaptiveGrid
      position={basis.origin}
      quaternion={quaternion}
      cellSize={1}
      sectionSize={10}
      cellColor={viewport.gridMinor}
      sectionColor={viewport.gridMajor}
      coplanar
    />
  );
}

/** Keep the axis letters under the HUD strips, like the constraint glyphs. */
const AXIS_LABEL_Z_RANGE: [number, number] = [20, 0];

/**
 * THE ORIGIN OF THE SHEET — where (0,0) is, drawn.
 *
 * Founder, 2026-08-02: *"there isn't an origin to start a drawing from."* The
 * snap layer now offers it (`sketch/snap.ts`); this is the half you can SEE,
 * and the two are the same point by construction — plane (0,0), which
 * `planeToWorld` maps to the basis origin. Nothing here names a world axis, so
 * a change of world convention cannot rotate this mark off its own zero.
 *
 * The drawing, in one sentence: a centre-punch ring at zero with the plane's
 * two axes running out of it, solid on the positive half and phantom on the
 * negative, the letter engraved at the positive end. That axis encoding is not
 * invented here — `viewport/OriginGeometry` already draws the WORLD triad that
 * way, and dashed-means-absent is this product's language throughout — so the
 * sketcher and the world speak one axis dialect and the line itself says which
 * way +X runs, with no legend. The ring is the one addition: the axes already
 * cross at zero, so the composite reads as a drafting centre mark without a
 * second element being drawn, and the ring alone still marks the spot.
 *
 * Ink is `sketch.constructionInk` — the token that already means "reference
 * geometry, not profile", which is exactly what the plane's own frame is. It
 * sits deliberately between the grid (quiet) and the scribe (bright): the frame
 * must out-read the grid it lies on and must never compete with the ink you
 * draw. Brass is spent on the parametric handles and on the snap mark that
 * fires when you take this point — never on standing chrome.
 */
function SketchOrigin({
  basis,
  plane,
  frameHalfHeightMm,
}: {
  basis: PlaneBasis;
  plane: SketchPlaneSpec;
  frameHalfHeightMm: number;
}) {
  const identity = originIdentity(plane);
  const axisLengthMm = frameHalfHeightMm * ORIGIN_AXIS_FRACTION;
  const spans = useMemo(() => originAxisSpans(axisLengthMm), [axisLengthMm]);
  const selection = useSketchStore((state) => state.selection);
  const hoverPick = useSketchStore((state) => state.hoverPick);
  const originState = datumPickState(DATUM_ORIGIN_ID, selection, hoverPick);
  const axisState: Record<"x" | "y", DatumPickState> = {
    x: datumPickState(DATUM_X_AXIS_ID, selection, hoverPick),
    y: datumPickState(DATUM_Y_AXIS_ID, selection, hoverPick),
  };

  const ring = useMemo(
    () =>
      segmentPositions(
        basis,
        originRingSegments(frameHalfHeightMm * ORIGIN_RING_FRACTION),
      ),
    [basis, frameHalfHeightMm],
  );
  const originDot = useMemo(
    () =>
      originState === "idle"
        ? new Float32Array(0)
        : new Float32Array(planeToWorld(basis, { x: 0, y: 0 })),
    [basis, originState],
  );
  const axisPositions = useMemo(
    () =>
      spans.map((span) => ({
        key: span.key,
        positive: segmentPositions(basis, [span.positive]),
        negative: segmentPositions(basis, [span.negative]),
      })),
    [basis, spans],
  );

  return (
    <group>
      {axisPositions.map((axis) => (
        <group key={axis.key}>
          <InkSegments
            positions={axis.positive}
            color={DATUM_INK[axisState[axis.key]]}
            onTop
            order={PLANE_FRAME_RENDER_ORDER}
          />
          <InkSegments
            positions={axis.negative}
            color={DATUM_INK[axisState[axis.key]]}
            dashed
            dashSize={axisLengthMm * ORIGIN_DASH_FRACTION}
            gapSize={axisLengthMm * ORIGIN_GAP_FRACTION}
            onTop
            order={PLANE_FRAME_RENDER_ORDER}
          />
        </group>
      ))}
      <InkSegments
        positions={ring}
        color={DATUM_INK[originState]}
        onTop
        order={PLANE_FRAME_RENDER_ORDER}
      />
      {/* Engaged, the ring wears the picked-point dot every other defining
          point wears — the frame joins the handle language rather than
          inventing a second one for itself. */}
      <InkPoints
        positions={originDot}
        color={DATUM_INK[originState]}
        sizePx={sketch.pickedPointSizePx}
        onTop
      />
      {spans.map((span) => (
        <Html
          key={span.key}
          position={planeToWorld(basis, span.tip)}
          center
          zIndexRange={AXIS_LABEL_Z_RANGE}
          style={{ pointerEvents: "none" }}
        >
          <span
            data-testid={`sketch-axis-label-${span.key}`}
            data-pick-state={axisState[span.key]}
            className={`font-data text-2xs tracking-[0.18em] ${
              axisState[span.key] === "idle" ? "text-gauge" : "text-brass"
            }`}
          >
            {span.label}
          </span>
        </Html>
      ))}
      {/* The frame's DOM: its name for anyone who cannot see it, the QA hook
          that says WHICH origin this plane has, and — since SKETCH-2 made the
          frame selectable — a keyboard path to select it.

          Every element here is pointer-INERT by design. The one click this must
          never eat is the click that places a point exactly at zero; the canvas
          owns pointer picking (`datumPickCandidates`), and these controls exist
          for the keyboard. Focus is visible in the VIEWPORT rather than on the
          control: focusing one hovers its datum, so the ring or the axis lights
          up in the scene — the ink is the focus ring, which is the only place a
          screen-reader-only control could honestly show one. */}
      <Html
        position={planeToWorld(basis, { x: 0, y: 0 })}
        center
        style={{ pointerEvents: "none" }}
      >
        <DatumHandle
          id={DATUM_ORIGIN_ID}
          testId="sketch-origin"
          state={originState}
          label={
            identity.note === null
              ? `Sketch origin — ${identity.label}`
              : `Sketch origin — ${identity.label}. ${identity.note}`
          }
          originLabel={identity.label}
        />
        <DatumHandle
          id={DATUM_X_AXIS_ID}
          testId="sketch-axis-x"
          state={axisState.x}
          label={`Sketch ${DATUM_LABELS[DATUM_X_AXIS_ID]}`}
        />
        <DatumHandle
          id={DATUM_Y_AXIS_ID}
          testId="sketch-axis-y"
          state={axisState.y}
          label={`Sketch ${DATUM_LABELS[DATUM_Y_AXIS_ID]}`}
        />
      </Html>
    </group>
  );
}

/**
 * The frame's ink, per pick state. Both renderers read one palette: `hoverInk`
 * and `selectedInk` are the SAME brass the drawn geometry uses, so the frame
 * answers a pick in the language the rest of the sketcher already speaks.
 */
const DATUM_INK: Readonly<Record<DatumPickState, string>> = {
  idle: sketch.constructionInk,
  hover: sketch.hoverInk,
  selected: sketch.selectedInk,
};

/**
 * One screen-reader-only, keyboard-reachable handle for a member of the sketch
 * frame. `aria-pressed` carries the selection, so a keyboard user hears what
 * they hold; `data-pick-state` is the same fact for QA. Pointer-inert (see the
 * caller) — activating it is a keyboard act, and hovering it is a focus act.
 */
function DatumHandle({
  id,
  testId,
  state,
  label,
  originLabel,
}: {
  id: DatumKind;
  testId: string;
  state: DatumPickState;
  label: string;
  originLabel?: string;
}) {
  const togglePick = useSketchStore((store) => store.togglePick);
  const setHoverPick = useSketchStore((store) => store.setHoverPick);
  return (
    <button
      type="button"
      className="sr-only"
      style={{ pointerEvents: "none" }}
      data-testid={testId}
      data-pick-state={state}
      {...(originLabel === undefined
        ? {}
        : { "data-origin-label": originLabel })}
      aria-pressed={state === "selected"}
      aria-label={label}
      onFocus={() => setHoverPick(DATUM_PICKS[id])}
      onBlur={() => setHoverPick(null)}
      onClick={() => togglePick(DATUM_PICKS[id])}
    />
  );
}

/** r3f wants a raycast function, and this sheet must never eat a click. */
const NO_RAYCAST = () => {};

/**
 * LAYOUT BLUING — the dark ground the scribe reads against, laid on the face
 * the active sketch is seated on. See `sketch.faceBluing` in the design tokens
 * for the measured contrast this exists to fix (1.32:1 → 5.9:1) and
 * `bluingWash.ts` for why the patch is feathered rather than a card; this
 * component is only its placement.
 *
 * It is drawn ONLY for an `on_face` sketch, which is the whole restraint: a
 * sketch in space already has the carbide ground and needs no wash, and you
 * blue STOCK, not air. It keeps depth testing (+ {@link COPLANAR_DECAL}) so
 * geometry genuinely in front of the plane still covers it — the wash is paint
 * on a surface, not an overlay on the frame.
 */
function FaceBluing({
  basis,
  areaMm2,
}: {
  basis: PlaneBasis;
  areaMm2: number;
}) {
  const quaternion = useMemo(() => planeQuaternion(basis), [basis]);
  const size = bluingRadiusMm(areaMm2) * 2;
  return (
    <mesh
      position={[basis.origin[0], basis.origin[1], basis.origin[2]]}
      quaternion={quaternion}
      raycast={NO_RAYCAST}
      // The wash and the plane grid are both transparent AND coplanar, so their
      // draw order would otherwise be decided by a tie-break. It is the ground:
      // it goes down first, explicitly.
      renderOrder={-1}
    >
      <planeGeometry args={[size, size]} />
      <meshBasicMaterial
        color={sketch.faceBluing}
        alphaMap={bluingWash()}
        transparent
        opacity={sketch.faceBluingOpacity}
        depthWrite={false}
        side={2 /* DoubleSide */}
        {...COPLANAR_DECAL}
      />
    </mesh>
  );
}

/**
 * The drafting callout for the size cell that has focus — extension lines and a
 * dimension line laid on the very edge the number drives. Without it a pair of
 * cells labelled W and H is a form floating over a picture; with it, typing in
 * a cell points at its own edge, which is how a drawing says the same thing.
 * Empty whenever no cell has focus.
 */
function witnessPositions(
  draft: DrawDimensionDraft | null,
  focus: DrawDimensionKey | null,
  entities: readonly SketchEntity[],
  basis: PlaneBasis,
): Float32Array {
  if (draft === null || focus === null) return new Float32Array(0);
  const field = draft.fields.find((f) => f.key === focus);
  if (field?.entity == null) return new Float32Array(0);
  const entity = entities.find((e) => e.id === field.entity);
  if (entity === undefined) return new Float32Array(0);
  const centre = {
    x: (draft.from.x + draft.to.x) / 2,
    y: (draft.from.y + draft.to.y) / 2,
  };
  const segments: Array<[Point2D, Point2D]> =
    entity.kind === "line"
      ? dimensionWitness(entity.start, entity.end, centre, sketch.glyphOffsetMm)
      : entity.kind === "circle"
        ? [
            [
              entity.center,
              { x: entity.center.x + entity.radius, y: entity.center.y },
            ],
          ]
        : [];
  if (segments.length === 0) return new Float32Array(0);
  const positions = new Float32Array(segments.length * 6);
  segments.forEach(([a, b], i) => {
    positions.set(planeToWorld(basis, a), i * 6);
    positions.set(planeToWorld(basis, b), i * 6 + 3);
  });
  return positions;
}

/**
 * The live sketch: buffered entities (solved positions once persisted), the
 * rubber band, selection/hover ink (brass — the viewport selection tokens),
 * and the constraint annotation layer.
 */
function DrawLayer({ basis }: { basis: PlaneBasis }) {
  const buffered = useSketchStore((state) => state.entities);
  // The sketch frame is drawn by `SketchOrigin`, at the size the camera parks
  // at — so once it has been materialised into the buffer (grounding a profile
  // to it), it must not ALSO be drawn here as ordinary construction geometry.
  // One owner for the frame's ink; one cross at zero, not two.
  const entities = useMemo(() => withoutDatums(buffered), [buffered]);
  const pending = useSketchStore((state) => state.pending);
  const tool = useSketchStore((state) => state.tool);
  const cursor = useSketchStore((state) => state.cursor);
  const selection = useSketchStore((state) => state.selection);
  const hoverPick = useSketchStore((state) => state.hoverPick);
  const mirror = useSketchStore((state) => state.mirror);
  const corner = useSketchStore((state) => state.corner);
  const drawDimension = useSketchStore((state) => state.drawDimension);
  const drawDimensionFocus = useSketchStore(
    (state) => state.drawDimensionFocus,
  );

  // Mirror targets and corner legs read as "picked" (brass), the same
  // affordance as a selection — merged so the idle buffer never double-draws
  // them.
  const selectedIds = useMemo(() => {
    const ids = new Set(
      selection.flatMap((pick) => (pick.kind === "entity" ? [pick.id] : [])),
    );
    for (const id of mirror?.targets ?? []) ids.add(id);
    for (const id of corner?.picks ?? []) ids.add(id);
    return ids;
  }, [selection, mirror, corner]);
  const hoveredId =
    hoverPick?.kind === "entity" && !selectedIds.has(hoverPick.id)
      ? hoverPick.id
      : null;

  // The live reflection ghost: while picking the axis, the hovered line drives
  // a local reflection of the target set so the user sees exactly where the
  // copies land before committing (the backend stays the source of truth).
  const ghostPositions = useMemo(() => {
    if (mirror?.phase !== "axis" || hoveredId === null) {
      return new Float32Array(0);
    }
    const axis = axisLinePoints(entities, hoveredId);
    if (axis === null) return new Float32Array(0); // hovered a non-line
    const targets = mirror.targets.flatMap((id) => {
      const entity = entities.find((e) => e.id === id);
      return entity ? [entity] : [];
    });
    const ghosts = targets.map((entity, i) =>
      reflectEntity(entity, axis.a, axis.b, `ghost-${i}`),
    );
    return entitySegmentPositions(ghosts, basis);
  }, [mirror, hoveredId, entities, basis]);

  // The idle buffer (not selected, not hovered) splits into profile ink
  // (solid scribe) and construction ink (muted, dashed) — selection/hover
  // brass wins over both while a pick is live.
  const buffer = useMemo(
    () =>
      partitionConstruction(
        entities.filter((e) => !selectedIds.has(e.id) && e.id !== hoveredId),
      ),
    [entities, selectedIds, hoveredId],
  );
  const bufferPositions = useMemo(
    () => entitySegmentPositions(buffer.profile, basis),
    [buffer, basis],
  );
  const constructionPositions = useMemo(
    () => entitySegmentPositions(buffer.construction, basis),
    [buffer, basis],
  );
  const selectedPositions = useMemo(
    () =>
      entitySegmentPositions(
        entities.filter((e) => selectedIds.has(e.id)),
        basis,
      ),
    [entities, selectedIds, basis],
  );
  const hoveredPositions = useMemo(
    () =>
      entitySegmentPositions(
        entities.filter((e) => e.id === hoveredId),
        basis,
      ),
    [entities, hoveredId, basis],
  );
  const pointPositions = useMemo(() => {
    const anchors = definingPointPositions(entities, basis);
    if (pending.length === 0) return anchors;
    const merged = new Float32Array(anchors.length + pending.length * 3);
    merged.set(anchors, 0);
    pending.forEach((point, i) => {
      merged.set(planeToWorld(basis, point), anchors.length + i * 3);
    });
    return merged;
  }, [entities, pending, basis]);
  const selectedPointPositions = useMemo(
    () => pickedPointPositions(selection, entities, basis),
    [selection, entities, basis],
  );
  const hoveredPointPositions = useMemo(
    () =>
      hoverPick !== null && hoverPick.kind === "point"
        ? pickedPointPositions([hoverPick], entities, basis)
        : new Float32Array(0),
    [hoverPick, entities, basis],
  );
  const preview = useMemo(
    () =>
      cursor === null
        ? new Float32Array(0)
        : entitySegmentPositions(previewEntities(tool, pending, cursor), basis),
    [tool, pending, cursor, basis],
  );
  const witness = useMemo(
    () => witnessPositions(drawDimension, drawDimensionFocus, entities, basis),
    [drawDimension, drawDimensionFocus, entities, basis],
  );

  return (
    <group>
      {/* Every layer here is the sketch you are AUTHORING, so every layer is
          `onTop` — a rule with no exceptions is one nobody has to remember.
          The one thing that would break is a mark you want occluded, and this
          group contains none. */}
      <InkSegments positions={bufferPositions} color={sketch.scribe} onTop />
      <InkSegments
        positions={constructionPositions}
        color={sketch.constructionInk}
        dashed
        dashSize={sketch.constructionDashMm}
        gapSize={sketch.constructionGapMm}
        onTop
      />
      <InkSegments positions={hoveredPositions} color={sketch.hoverInk} onTop />
      <InkSegments
        positions={selectedPositions}
        color={sketch.selectedInk}
        onTop
      />
      <InkPoints positions={pointPositions} color={sketch.point} onTop />
      <InkPoints
        positions={hoveredPointPositions}
        color={sketch.hoverInk}
        sizePx={sketch.pickedPointSizePx}
        onTop
      />
      <InkPoints
        positions={selectedPointPositions}
        color={sketch.selectedInk}
        sizePx={sketch.pickedPointSizePx}
        onTop
      />
      <InkSegments positions={preview} color={sketch.preview} dashed onTop />
      <InkSegments
        positions={ghostPositions}
        color={sketch.preview}
        dashed
        onTop
      />
      {/* The focused size cell's own dimension callout — brass, because a
          driving dimension IS the parametric handle (`sketch.glyphDimension`). */}
      <InkSegments positions={witness} color={sketch.glyphDimension} onTop />
      <Crosshair basis={basis} />
      <SnapMarker basis={basis} />
      <DrawDimensionTag basis={basis} />
      <ConstraintGlyphs basis={basis} />
    </group>
  );
}

/**
 * A quiet translucent datum sheet marking an OFFSET plane's position — the
 * "sketch at a height" cue. Bounded quad in the datum-plane tokens, drawn at
 * the plane's basis so it sits at the offset (origin datums draw at z=0 and
 * are already the world frame, so this only appears for offset planes).
 */
function DatumHintSheet({ basis }: { basis: PlaneBasis }) {
  const quaternion = useMemo(() => planeQuaternion(basis), [basis]);
  const edgePositions = useMemo(() => {
    const s = PLANE_SIZE_MM / 2;
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
  }, [basis]);
  const edgeGeometry = usePositionsGeometry(edgePositions);
  const position: [number, number, number] = [
    basis.origin[0],
    basis.origin[1],
    basis.origin[2],
  ];
  return (
    <group>
      <mesh position={position} quaternion={quaternion}>
        <planeGeometry args={[PLANE_SIZE_MM, PLANE_SIZE_MM]} />
        <meshBasicMaterial
          color={sketch.planeFill}
          transparent
          opacity={sketch.planeActiveFillOpacity}
          depthWrite={false}
          side={2 /* DoubleSide */}
          {...COPLANAR_DECAL}
        />
      </mesh>
      <lineSegments geometry={edgeGeometry} frustumCulled={false}>
        <lineBasicMaterial color={sketch.planeActiveEdge} toneMapped={false} />
      </lineSegments>
    </group>
  );
}

/** Persisted sketches, rendered from the SOLVED evaluate payload. */
function SolvedLayer({ layer }: { layer: SolvedSketchLayer }) {
  // A saved sketch carries its frame as construction entities once anything was
  // grounded to it (`sketch/datum.ts`). They are the plane's own datum, not ink
  // the user drew, so a solved layer never paints them — the world origin triad
  // already says where zero is out here.
  const parts = useMemo(
    () => partitionConstruction(withoutDatums(layer.entities)),
    [layer],
  );
  const profilePositions = useMemo(
    () => entitySegmentPositions(parts.profile, layer.basis),
    [parts, layer.basis],
  );
  const constructionPositions = useMemo(
    () => entitySegmentPositions(parts.construction, layer.basis),
    [parts, layer.basis],
  );
  return (
    <>
      <InkSegments positions={profilePositions} color={sketch.scribeSolved} />
      <InkSegments
        positions={constructionPositions}
        color={sketch.constructionInk}
        dashed
        dashSize={sketch.constructionDashMm}
        gapSize={sketch.constructionGapMm}
      />
    </>
  );
}

/**
 * How much MORE than the picked face the entry frame shows. 1.7 keeps the whole
 * face plus a band of its surroundings on screen, so the face's own outline —
 * and the body and bench beyond it — say where you are.
 *
 * The alternative, framing the profile you are about to draw, cannot work: on
 * entry there is no profile yet. Framing the whole BODY was the other candidate
 * and loses the point of a face sketch (a 5 mm boss on a 400 mm plate would be
 * a speck). The face is the subject; its neighbourhood is the context.
 */
const FACE_FRAME_MARGIN = 1.7;
/** Never closer than this (mm) — a tiny face must not put the eye inside the stock. */
const MIN_FACE_CAMERA_MM = 45;

/**
 * Distance (mm) the authoring camera parks at.
 *
 * A fixed {@link SKETCH_CAMERA_DISTANCE_MM} is right for a datum plane, whose
 * sheet is a fixed size — but it is meaningless on a MODEL FACE, whose size is
 * whatever the part is. Founder report, 2026-08-01: entering a sketch on a face
 * parked so close that the face filled the frame edge to edge as a featureless
 * slab, with no outline, no body and no horizon to say where you were. The face
 * carries its own area in its signature, so the frame is derived from it: fit
 * the equal-area square plus {@link FACE_FRAME_MARGIN} into the vertical field
 * of view. Big face, stand back; small boss, lean in.
 */
function sketchCameraDistanceMm(
  plane: SketchPlaneSpec,
  camera: Camera,
): number {
  if (plane.kind !== "on_face") return SKETCH_CAMERA_DISTANCE_MM;
  const span = Math.sqrt(Math.max(plane.signature.area_mm2, 0));
  if (!(span > 0)) return SKETCH_CAMERA_DISTANCE_MM;
  // Perspective only; an ortho sketch camera would frame by zoom, not distance.
  const distance =
    (span * FACE_FRAME_MARGIN) /
    2 /
    Math.tan((cameraFov(camera) * Math.PI) / 360);
  return Math.max(MIN_FACE_CAMERA_MM, distance);
}

/**
 * Half-height (mm) of the frame the sketch camera parks in — the plane's own
 * frame is sized from THIS, the same number the camera rig uses, so the axes
 * always span the view a sketch opens at whether that is a fixed datum sheet or
 * a 400 mm face. One derivation, two consumers.
 */
function sketchFrameHalfHeightMm(
  plane: SketchPlaneSpec,
  camera: Camera,
): number {
  return (
    sketchCameraDistanceMm(plane, camera) *
    Math.tan((cameraFov(camera) * Math.PI) / 360)
  );
}

/**
 * Camera rig: eases to the plane-pick iso or the normal-on authoring pose
 * (instant under prefers-reduced-motion), releases the camera otherwise.
 */
function SketchCameraRig() {
  const mode = useSketchStore((state) => state.mode);
  const plane = useSketchStore((state) => state.plane);
  const reducedMotion = useReducedMotion();
  const camera = useThree((state) => state.camera);
  const controls = useThree(
    (state) => state.controls,
  ) as OrbitControlsImpl | null;
  const invalidate = useThree((state) => state.invalidate);
  const goal = useRef<{
    position: Vector3;
    up: Vector3;
    target: Vector3;
  } | null>(null);

  useEffect(() => {
    let pose: CameraPose | null = null;
    if (mode === "draw" && plane !== null) {
      pose = planeCameraPose(
        resolveSpecBasis(plane),
        sketchCameraDistanceMm(plane, camera),
      );
    } else if (mode === "plane") {
      const direction = new Vector3(1, 0.68, 1.35)
        .normalize()
        .multiplyScalar(PICK_CAMERA_DISTANCE_MM);
      pose = {
        position: [direction.x, direction.y, direction.z],
        up: [0, 1, 0],
        target: [0, 0, 0],
      };
    } else {
      // Sketch over: give the camera back, restore the world up.
      goal.current = null;
      camera.up.set(0, 1, 0);
      controls?.update();
      invalidate();
      return;
    }
    const next = {
      position: new Vector3(...pose.position),
      up: new Vector3(...pose.up),
      target: new Vector3(...pose.target),
    };
    if (reducedMotion) {
      camera.position.copy(next.position);
      camera.up.copy(next.up);
      if (controls) {
        controls.target.copy(next.target);
        controls.update();
      } else {
        camera.lookAt(next.target);
      }
      goal.current = null;
    } else {
      goal.current = next;
    }
    invalidate();
  }, [mode, plane, reducedMotion, camera, controls, invalidate]);

  useFrame((_, delta) => {
    const g = goal.current;
    if (g === null) return;
    // Exponential ease — frame-rate independent, allocation-free.
    const k = 1 - Math.exp(-Math.min(delta, 0.1) * 10);
    camera.position.lerp(g.position, k);
    camera.up.lerp(g.up, k).normalize();
    if (controls) {
      controls.target.lerp(g.target, k);
      controls.update();
    } else {
      camera.lookAt(g.target);
    }
    if (camera.position.distanceTo(g.position) < 0.05) {
      camera.position.copy(g.position);
      camera.up.copy(g.up);
      controls?.update();
      goal.current = null;
    }
    invalidate();
  });

  return null;
}

export interface SketchSceneProps {
  solved: readonly SolvedSketchLayer[];
  /**
   * The "Pick a face" mode is armed: the body's planar faces are the
   * affordance (FacePickOverlay), so the origin datum sheets step back to keep
   * the pick target unambiguous.
   */
  facePicking?: boolean;
}

/** Everything sketch inside the Canvas: pick sheets, draw layer, solved ink. */
export function SketchScene({ solved, facePicking = false }: SketchSceneProps) {
  const mode = useSketchStore((state) => state.mode);
  const plane = useSketchStore((state) => state.plane);
  const partView = usePartViewStore((state) => state.view);
  const bodyPresent = usePartViewStore((state) => state.bodyPresent);
  const camera = useThree((state) => state.camera);
  const basis = useMemo(
    () => (plane === null ? null : resolveSpecBasis(plane)),
    [plane],
  );
  // Sized once per plane from the frame the camera parks in (see
  // `sketchFrameHalfHeightMm`) — not per frame: the mark is the sheet's own
  // datum, not a zoom-tracking HUD element.
  const frameHalfHeightMm = useMemo(
    () => (plane === null ? 0 : sketchFrameHalfHeightMm(plane, camera)),
    [plane, camera],
  );
  // The store picks the frame with the number that DRAWS it, so the region that
  // selects the origin and the axes is the ink the user is aiming at (SKETCH-2).
  const setDatumFrame = useSketchStore((state) => state.setDatumFrame);
  useEffect(() => {
    setDatumFrame(frameHalfHeightMm);
  }, [frameHalfHeightMm, setDatumFrame]);
  // WHICH solved sketches are drawn (UI-W2, part half). The rule used to be a
  // hard one-liner in the workspace — "a body exists, so draw no sketch ink at
  // all" — which is a reasonable DEFAULT (coincident scribe ink z-fights the
  // solid it made) and a bad LAW: it left a modeler no way to look at the
  // profile that drives the feature they are editing. It is now the default of
  // a per-sketch stop the browser can override in either direction, and the ROW
  // and the SCENE read the same derivation, so the eye can never disagree with
  // the pixels.
  const drawn = solved.filter((layer) =>
    sketchIsDrawn(partView, layer.featureId, bodyPresent),
  );
  useSnapModifiers(mode === "draw");
  return (
    <group>
      {drawn.map((layer) => (
        <SolvedLayer key={layer.featureId} layer={layer} />
      ))}
      {mode === "plane" && !facePicking
        ? DATUM_PLANES.map((name) => <DatumSheet key={name} plane={name} />)
        : null}
      {mode === "draw" && plane !== null && basis !== null ? (
        <group>
          {plane.kind === "offset" ? <DatumHintSheet basis={basis} /> : null}
          {plane.kind === "on_face" ? (
            <FaceBluing basis={basis} areaMm2={plane.signature.area_mm2} />
          ) : null}
          <SketchGrid basis={basis} />
          <SketchOrigin
            basis={basis}
            plane={plane}
            frameHalfHeightMm={frameHalfHeightMm}
          />
          <PointerCatcher basis={basis} />
          <DrawLayer basis={basis} />
        </group>
      ) : null}
      <SketchCameraRig />
    </group>
  );
}
