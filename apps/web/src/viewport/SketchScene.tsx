/**
 * The 2D authoring layer inside the WebGL viewport. Every color/opacity/size
 * comes from `@loft/design` `sketch` tokens; line materials render unlit and
 * un-tonemapped so the canvas shows the EXACT token hex — one palette, two
 * renderers (verified by the e2e pixel probe).
 */
import {
  PerpendicularIcon,
  SnapCenterIcon,
  SnapEndpointIcon,
  SnapIntersectionIcon,
  SnapMidpointIcon,
  TangentIcon,
  HorizontalIcon,
  VerticalIcon,
  type IconProps,
} from "@loft/design";
import { sketch, viewport } from "@loft/design/tokens";
import { Html, useCursor } from "@react-three/drei";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState, type ReactElement } from "react";
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

import { useReducedMotion } from "../lib/useReducedMotion";
import {
  definingPointPositions,
  entitySegmentPositions,
  pickedPointPositions,
} from "../sketch/geometry";
import { pickCandidates, samePick, PICK_TOLERANCE_PX } from "../sketch/pick";
import {
  DATUM_PLANES,
  originBasis,
  planeCameraPose,
  planeToWorld,
  resolveSpecBasis,
  worldToPlane,
  type CameraPose,
  type DatumPlaneName,
  type PlaneBasis,
  type SketchPlaneSpec,
} from "../sketch/plane";
import { axisLinePoints, reflectEntity } from "../sketch/mirror";
import { isClick, type PointerGesture } from "../sketch/clickIntent";
import { SNAP_LABELS, SNAP_TOLERANCE_PX, type SnapKind } from "../sketch/snap";
import { useSketchStore } from "../sketch/store";
import {
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
/** Normal-on authoring distance (mm) — an A6-ish sheet fills the view. */
const SKETCH_CAMERA_DISTANCE_MM = 170;
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
}

/** One layer of sketch ink — a single LineSegments draw call. */
function InkSegments({
  positions,
  color,
  dashed = false,
  dashSize = sketch.previewDashMm,
  gapSize = sketch.previewGapMm,
  onTop = false,
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
      renderOrder={onTop ? ACTIVE_INK_RENDER_ORDER : 0}
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

  const basis = useMemo(() => originBasis(plane), [plane]);
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
  const worldPerPx = (e: ThreeEvent<PointerEvent> | ThreeEvent<MouseEvent>) => {
    const fov =
      "fov" in camera && typeof camera.fov === "number" ? camera.fov : 40;
    return (2 * e.distance * Math.tan((fov * Math.PI) / 360)) / heightPx;
  };
  const toleranceMm = (e: ThreeEvent<PointerEvent> | ThreeEvent<MouseEvent>) =>
    PICK_TOLERANCE_PX * worldPerPx(e);
  /** The snap magnet is a hair wider than the pick tolerance (see snap.ts). */
  const snapToleranceMm = (
    e: ThreeEvent<PointerEvent> | ThreeEvent<MouseEvent>,
  ) => SNAP_TOLERANCE_PX * worldPerPx(e);
  /**
   * Modifier state read from the EVENT — authoritative at the instant of the
   * click, where a keyboard-tracked flag can be one repaint stale. Ctrl/Cmd
   * suppresses every snap; Shift locks the aim to an axis. Alt is deliberately
   * unused: window managers and browser menus fight for Alt+drag.
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
          const all = pickCandidates(
            useSketchStore.getState().entities,
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
      onPointerDown={notePressStart}
      onClick={(e) => {
        if (!isClick(gestureOf(e))) return; // the camera moved, not the model
        const store = useSketchStore.getState();
        const clickTool = store.tool;
        if (clickTool === "select") {
          selectAt(rawPlanePoint(e), toleranceMm(e));
        } else if (clickTool === "trim" || clickTool === "extend") {
          // Trim/extend send the RAW pick (unsnapped): the backend uses it to
          // choose the segment/end, and snapping would jump off a fine target.
          const raw = rawPlanePoint(e);
          const target =
            pickCandidates(store.entities, raw, toleranceMm(e)).find(
              (pick) => pick.kind === "entity",
            ) ?? null;
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
            pickCandidates(store.entities, raw, toleranceMm(e)).find(
              (pick) => pick.kind === "entity",
            ) ?? null;
          store.beginOffset(
            target !== null && target.kind === "entity" ? target.id : null,
          );
        } else if (clickTool === "mirror") {
          // Two-phase: click entities to build the target set, then (axis
          // phase) click a line to reflect them about it.
          const raw = rawPlanePoint(e);
          const target =
            pickCandidates(store.entities, raw, toleranceMm(e)).find(
              (pick) => pick.kind === "entity",
            ) ?? null;
          const id = target?.kind === "entity" ? target.id : null;
          if (store.mirror?.phase === "axis") store.pickMirrorAxis(id);
          else store.toggleMirrorTarget(id);
        } else if (clickTool === "fillet" || clickTool === "chamfer") {
          // Corner tools collect two line legs (raw pick, like trim/offset);
          // the value editor opens once both are held.
          const raw = rawPlanePoint(e);
          const target =
            pickCandidates(store.entities, raw, toleranceMm(e)).find(
              (pick) => pick.kind === "entity",
            ) ?? null;
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
  if (candidate === null) return null;
  const Mark = SNAP_MARKS[candidate.kind];
  const label = SNAP_LABELS[candidate.kind];
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
        aria-label={`Snapping to ${label.toLowerCase()}`}
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
 * The live sketch: buffered entities (solved positions once persisted), the
 * rubber band, selection/hover ink (brass — the viewport selection tokens),
 * and the constraint annotation layer.
 */
function DrawLayer({ basis }: { basis: PlaneBasis }) {
  const entities = useSketchStore((state) => state.entities);
  const pending = useSketchStore((state) => state.pending);
  const tool = useSketchStore((state) => state.tool);
  const cursor = useSketchStore((state) => state.cursor);
  const selection = useSketchStore((state) => state.selection);
  const hoverPick = useSketchStore((state) => state.hoverPick);
  const mirror = useSketchStore((state) => state.mirror);
  const corner = useSketchStore((state) => state.corner);

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
      <Crosshair basis={basis} />
      <SnapMarker basis={basis} />
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
  const parts = useMemo(() => partitionConstruction(layer.entities), [layer]);
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
  const fov =
    "fov" in camera && typeof camera.fov === "number" ? camera.fov : 40;
  const distance =
    (span * FACE_FRAME_MARGIN) / 2 / Math.tan((fov * Math.PI) / 360);
  return Math.max(MIN_FACE_CAMERA_MM, distance);
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
  const basis = useMemo(
    () => (plane === null ? null : resolveSpecBasis(plane)),
    [plane],
  );
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
          <PointerCatcher basis={basis} />
          <DrawLayer basis={basis} />
        </group>
      ) : null}
      <SketchCameraRig />
    </group>
  );
}
