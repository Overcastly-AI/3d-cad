/**
 * The 2D authoring layer inside the WebGL viewport. Every color/opacity/size
 * comes from `@loft/design` `sketch` tokens; line materials render unlit and
 * un-tonemapped so the canvas shows the EXACT token hex — one palette, two
 * renderers (verified by the e2e pixel probe).
 */
import { sketch, viewport } from "@loft/design/tokens";
import { Grid, useCursor } from "@react-three/drei";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  BufferGeometry,
  Float32BufferAttribute,
  Matrix4,
  Quaternion,
  Vector3,
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
  PLANE_BASES,
  planeCameraPose,
  planeToWorld,
  worldToPlane,
  type CameraPose,
  type DatumPlaneName,
} from "../sketch/plane";
import { useSketchStore } from "../sketch/store";
import { previewEntities, type SketchEntity } from "../sketch/tools";
import { ConstraintGlyphs } from "./ConstraintGlyphs";

/** Datum sheet half-extent feels like stock on the table (mm). */
const PLANE_SIZE_MM = 90;
/** Normal-on authoring distance (mm) — an A6-ish sheet fills the view. */
const SKETCH_CAMERA_DISTANCE_MM = 170;
/** Plane-pick vantage: the studio iso the shell opens with, re-centred. */
const PICK_CAMERA_DISTANCE_MM = 230;
/** r3f click filter: pointer travel above this (px) is a drag, not a click. */
const CLICK_SLOP_PX = 4;

/** One solved sketch feature, ready to render. */
export interface SolvedSketchLayer {
  featureId: string;
  plane: DatumPlaneName;
  entities: SketchEntity[];
}

/** Quaternion orienting local XY (+Z normal) onto the datum plane basis. */
function planeQuaternion(plane: DatumPlaneName): Quaternion {
  const { u, v, normal } = PLANE_BASES[plane];
  const matrix = new Matrix4().makeBasis(
    new Vector3(...u),
    new Vector3(...v),
    new Vector3(...normal),
  );
  return new Quaternion().setFromRotationMatrix(matrix);
}

/** Quaternion orienting drei's Grid (local XZ, +Y normal) onto the plane. */
function gridQuaternion(plane: DatumPlaneName): Quaternion {
  const { u, normal } = PLANE_BASES[plane];
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
}

/** One layer of sketch ink — a single LineSegments draw call. */
function InkSegments({
  positions,
  color,
  dashed = false,
  dashSize = sketch.previewDashMm,
  gapSize = sketch.previewGapMm,
}: InkSegmentsProps) {
  const ref = useRef<LineSegments>(null);
  const geometry = usePositionsGeometry(positions);
  // LineDashedMaterial needs per-vertex line distances.
  useEffect(() => {
    if (dashed) ref.current?.computeLineDistances();
  }, [geometry, dashed]);
  if (positions.length === 0) return null;
  return (
    <lineSegments ref={ref} geometry={geometry} frustumCulled={false}>
      {dashed ? (
        <lineDashedMaterial
          color={color}
          dashSize={dashSize}
          gapSize={gapSize}
          toneMapped={false}
        />
      ) : (
        <lineBasicMaterial color={color} toneMapped={false} />
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
}: {
  positions: Float32Array;
  color: string;
  sizePx?: number;
}) {
  const geometry = usePositionsGeometry(positions);
  if (positions.length === 0) return null;
  return (
    <points geometry={geometry} frustumCulled={false}>
      <pointsMaterial
        color={color}
        size={sizePx}
        sizeAttenuation={false}
        toneMapped={false}
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

  const quaternion = useMemo(() => planeQuaternion(plane), [plane]);
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
      positions.set(planeToWorld(plane, corner), i * 6);
      positions.set(planeToWorld(plane, next), i * 6 + 3);
    });
    return positions;
  }, [plane]);
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
        onClick={(e) => {
          e.stopPropagation();
          if (e.delta <= CLICK_SLOP_PX) choosePlane(plane);
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
function PointerCatcher({ plane }: { plane: DatumPlaneName }) {
  const setCursor = useSketchStore((state) => state.setCursor);
  const snap = useSketchStore((state) => state.snap);
  const placeAt = useSketchStore((state) => state.placeAt);
  const selectAt = useSketchStore((state) => state.selectAt);
  const setHoverPick = useSketchStore((state) => state.setHoverPick);
  const invalidate = useThree((state) => state.invalidate);
  const camera = useThree((state) => state.camera);
  const heightPx = useThree((state) => state.size.height);
  const quaternion = useMemo(() => planeQuaternion(plane), [plane]);

  const rawPlanePoint = (
    e: ThreeEvent<PointerEvent> | ThreeEvent<MouseEvent>,
  ) => worldToPlane(plane, [e.point.x, e.point.y, e.point.z]);

  /** Screen px → plane mm at this event's depth (perspective camera). */
  const toleranceMm = (
    e: ThreeEvent<PointerEvent> | ThreeEvent<MouseEvent>,
  ) => {
    const fov =
      "fov" in camera && typeof camera.fov === "number" ? camera.fov : 40;
    const worldPerPx =
      (2 * e.distance * Math.tan((fov * Math.PI) / 360)) / heightPx;
    return PICK_TOLERANCE_PX * worldPerPx;
  };

  return (
    <mesh
      quaternion={quaternion}
      onPointerMove={(e) => {
        const raw = rawPlanePoint(e);
        setCursor(snap(raw));
        // Read the tool at EVENT time: the render-subscribed value is a
        // stale closure for the frame right after a keyboard tool switch
        // (zustand commit → React render → r3f handler swap), which loses
        // the first click of a fast key-then-click sequence.
        const aimTool = useSketchStore.getState().tool;
        if (
          aimTool === "select" ||
          aimTool === "trim" ||
          aimTool === "extend"
        ) {
          const all = pickCandidates(
            useSketchStore.getState().entities,
            raw,
            toleranceMm(e),
          );
          // Trim/extend address a whole curve — the aim affordance highlights
          // the hovered target only (points are irrelevant to them); select
          // keeps its finer point-first grain.
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
      onClick={(e) => {
        if (e.delta > CLICK_SLOP_PX) return; // a pan, not a placement
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
        } else {
          placeAt(snap(rawPlanePoint(e)));
        }
        invalidate();
      }}
    >
      <planeGeometry args={[100000, 100000]} />
      <meshBasicMaterial transparent opacity={0} depthWrite={false} />
    </mesh>
  );
}

/** Snap-cursor crosshair (brass, world-mm arms). */
function Crosshair({ plane }: { plane: DatumPlaneName }) {
  const cursor = useSketchStore((state) => state.cursor);
  const positions = useMemo(() => {
    if (cursor === null) return new Float32Array(0);
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
      out.set(planeToWorld(plane, arm[0] ?? { x: 0, y: 0 }), i * 6);
      out.set(planeToWorld(plane, arm[1] ?? { x: 0, y: 0 }), i * 6 + 3);
    });
    return out;
  }, [cursor, plane]);
  return <InkSegments positions={positions} color={sketch.cursor} />;
}

/** The mm grid on the active sketch plane (cell = the 1 mm snap step). */
function SketchGrid({ plane }: { plane: DatumPlaneName }) {
  const quaternion = useMemo(() => gridQuaternion(plane), [plane]);
  return (
    <Grid
      quaternion={quaternion}
      cellSize={1}
      sectionSize={10}
      cellColor={viewport.gridMinor}
      sectionColor={viewport.gridMajor}
      fadeDistance={340}
      fadeStrength={1.2}
      infiniteGrid
    />
  );
}

/**
 * The live sketch: buffered entities (solved positions once persisted), the
 * rubber band, selection/hover ink (brass — the viewport selection tokens),
 * and the constraint annotation layer.
 */
function DrawLayer({ plane }: { plane: DatumPlaneName }) {
  const entities = useSketchStore((state) => state.entities);
  const pending = useSketchStore((state) => state.pending);
  const tool = useSketchStore((state) => state.tool);
  const cursor = useSketchStore((state) => state.cursor);
  const selection = useSketchStore((state) => state.selection);
  const hoverPick = useSketchStore((state) => state.hoverPick);

  const selectedIds = useMemo(
    () =>
      new Set(
        selection.flatMap((pick) => (pick.kind === "entity" ? [pick.id] : [])),
      ),
    [selection],
  );
  const hoveredId =
    hoverPick?.kind === "entity" && !selectedIds.has(hoverPick.id)
      ? hoverPick.id
      : null;

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
    () => entitySegmentPositions(buffer.profile, plane),
    [buffer, plane],
  );
  const constructionPositions = useMemo(
    () => entitySegmentPositions(buffer.construction, plane),
    [buffer, plane],
  );
  const selectedPositions = useMemo(
    () =>
      entitySegmentPositions(
        entities.filter((e) => selectedIds.has(e.id)),
        plane,
      ),
    [entities, selectedIds, plane],
  );
  const hoveredPositions = useMemo(
    () =>
      entitySegmentPositions(
        entities.filter((e) => e.id === hoveredId),
        plane,
      ),
    [entities, hoveredId, plane],
  );
  const pointPositions = useMemo(() => {
    const anchors = definingPointPositions(entities, plane);
    if (pending.length === 0) return anchors;
    const merged = new Float32Array(anchors.length + pending.length * 3);
    merged.set(anchors, 0);
    pending.forEach((point, i) => {
      merged.set(planeToWorld(plane, point), anchors.length + i * 3);
    });
    return merged;
  }, [entities, pending, plane]);
  const selectedPointPositions = useMemo(
    () => pickedPointPositions(selection, entities, plane),
    [selection, entities, plane],
  );
  const hoveredPointPositions = useMemo(
    () =>
      hoverPick !== null && hoverPick.kind === "point"
        ? pickedPointPositions([hoverPick], entities, plane)
        : new Float32Array(0),
    [hoverPick, entities, plane],
  );
  const preview = useMemo(
    () =>
      cursor === null
        ? new Float32Array(0)
        : entitySegmentPositions(previewEntities(tool, pending, cursor), plane),
    [tool, pending, cursor, plane],
  );

  return (
    <group>
      <InkSegments positions={bufferPositions} color={sketch.scribe} />
      <InkSegments
        positions={constructionPositions}
        color={sketch.constructionInk}
        dashed
        dashSize={sketch.constructionDashMm}
        gapSize={sketch.constructionGapMm}
      />
      <InkSegments positions={hoveredPositions} color={sketch.hoverInk} />
      <InkSegments positions={selectedPositions} color={sketch.selectedInk} />
      <InkPoints positions={pointPositions} color={sketch.point} />
      <InkPoints
        positions={hoveredPointPositions}
        color={sketch.hoverInk}
        sizePx={sketch.pickedPointSizePx}
      />
      <InkPoints
        positions={selectedPointPositions}
        color={sketch.selectedInk}
        sizePx={sketch.pickedPointSizePx}
      />
      <InkSegments positions={preview} color={sketch.preview} dashed />
      <Crosshair plane={plane} />
      <ConstraintGlyphs plane={plane} />
    </group>
  );
}

/** Persisted sketches, rendered from the SOLVED evaluate payload. */
function SolvedLayer({ layer }: { layer: SolvedSketchLayer }) {
  const parts = useMemo(() => partitionConstruction(layer.entities), [layer]);
  const profilePositions = useMemo(
    () => entitySegmentPositions(parts.profile, layer.plane),
    [parts, layer.plane],
  );
  const constructionPositions = useMemo(
    () => entitySegmentPositions(parts.construction, layer.plane),
    [parts, layer.plane],
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
      pose = planeCameraPose(plane, SKETCH_CAMERA_DISTANCE_MM);
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
}

/** Everything sketch inside the Canvas: pick sheets, draw layer, solved ink. */
export function SketchScene({ solved }: SketchSceneProps) {
  const mode = useSketchStore((state) => state.mode);
  const plane = useSketchStore((state) => state.plane);
  return (
    <group>
      {solved.map((layer) => (
        <SolvedLayer key={layer.featureId} layer={layer} />
      ))}
      {mode === "plane"
        ? DATUM_PLANES.map((name) => <DatumSheet key={name} plane={name} />)
        : null}
      {mode === "draw" && plane !== null ? (
        <group>
          <SketchGrid plane={plane} />
          <PointerCatcher plane={plane} />
          <DrawLayer plane={plane} />
        </group>
      ) : null}
      <SketchCameraRig />
    </group>
  );
}
