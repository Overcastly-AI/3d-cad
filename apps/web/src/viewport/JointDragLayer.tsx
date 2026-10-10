/**
 * The in-canvas half of driving a joint by hand (`useJointDrive`).
 *
 * A press — on the jointed part's own body (routed here by `AssemblyScene`)
 * or on the drive handle Move puts up — starts a drag whose every pointer
 * position is PROJECTED onto the joint's free motion (`assembly/jointDrag`):
 * the swept angle about the axis for a turn, the closest approach along it for
 * a slide, the hit on the plane normal to it for a planar joint's in-plane
 * slide. On the body, a plain drag turns and Shift+drag slides
 * (`driveModeFor`); on the handle, each part does one thing (the ring turns,
 * the arrow slides along, the square slides across). The camera's orbit is
 * held off for the length of the drag and handed back on release, even if the
 * layer unmounts mid-drag (the same hand-back `MoveTriad` makes).
 *
 * QA STAMP. The axis and the camera's view-projection are published on the
 * viewport as `data-joint-drag`, so a spec can project a point of the part to
 * the screen and make the real gesture.
 */
import { assembly as assemblyTokens } from "@loft/design/tokens";
import { perspectiveUnitsPerPixel } from "@loft/design";
import { Line } from "@react-three/drei";
import { type ThreeEvent, useFrame, useThree } from "@react-three/fiber";
import {
  type MutableRefObject,
  useCallback,
  useEffect,
  useMemo,
  useRef,
} from "react";
import {
  DoubleSide,
  type Group,
  Matrix4,
  Quaternion,
  Raycaster,
  Vector2,
  Vector3,
} from "three";

import {
  beginJointDrag,
  beginPlaneDrag,
  type DriveMode,
  driveModeFor,
  type Ray,
  sceneRayToKernel,
} from "../assembly/jointDrag";
import { occtPointToScene, scenePointToOcct } from "../assembly/placement";
import type {
  DriveAxis,
  DriveGesture,
  DriveTarget,
} from "../assembly/useJointDrive";

/**
 * Start a drag of `target` from this press; `fromBody` vs. the handle. A
 * handle part names its `mode`; a body press reads it from Shift.
 */
export type JointPress = (
  event: ThreeEvent<PointerEvent>,
  target: DriveTarget,
  fromBody: boolean,
  mode?: DriveMode,
) => void;

export interface JointDragLayerProps {
  /** The joint the selected part can be dragged along, or null. */
  target: DriveTarget | null;
  /** Draw the drive handle (Move on a jointed part). */
  showHandle: boolean;
  /** Filled with the press handler, for the body press `AssemblyScene` routes. */
  pressRef: MutableRefObject<JointPress | null>;
  onPreview: (target: DriveTarget, gesture: DriveGesture) => void;
  /**
   * The pointer came up: at `gesture`, or null when it never moved (a body
   * press that never moved is a click, and the page selects).
   */
  onRelease: (
    target: DriveTarget,
    gesture: DriveGesture | null,
    fromBody: boolean,
  ) => void;
}

const Z = new Vector3(0, 0, 1);
const VP = new Matrix4();
const DEFAULT_FOV_DEG = 45;
/** Pointer travel below which a press is a click (the OS drag threshold). */
const DRAG_THRESHOLD_PX = 3;

function sameGesture(a: DriveGesture | null, b: DriveGesture): boolean {
  if (a === null || a.mode !== b.mode) return false;
  if (a.mode === "plane" && b.mode === "plane") {
    return (
      a.shift.x === b.shift.x &&
      a.shift.y === b.shift.y &&
      a.shift.z === b.shift.z
    );
  }
  return a.mode !== "plane" && b.mode !== "plane" && a.value === b.value;
}

/** The axis a stamp reports: its value and the bounds the drag stops at. */
const stampAxis = (axis: DriveAxis | null) =>
  axis === null
    ? null
    : {
        value: axis.value,
        min: Number.isFinite(axis.min) ? axis.min : null,
        max: Number.isFinite(axis.max) ? axis.max : null,
      };

export function JointDragLayer({
  target,
  showHandle,
  pressRef,
  onPreview,
  onRelease,
}: JointDragLayerProps) {
  const camera = useThree((s) => s.camera);
  const canvas = useThree((s) => s.gl.domElement);
  const invalidate = useThree((s) => s.invalidate);
  const controls = useThree((s) => s.controls) as { enabled?: boolean } | null;

  const active = useRef<{
    read: (ray: Ray) => DriveGesture | null;
    target: DriveTarget;
    gesture: DriveGesture | null;
    cleanup: () => void;
  } | null>(null);

  const rayAt = useCallback(
    (clientX: number, clientY: number) => {
      const rect = canvas.getBoundingClientRect();
      const ndc = new Vector2(
        ((clientX - rect.left) / rect.width) * 2 - 1,
        -((clientY - rect.top) / rect.height) * 2 + 1,
      );
      const caster = new Raycaster();
      caster.setFromCamera(ndc, camera);
      const { origin, direction } = caster.ray;
      return sceneRayToKernel(
        [origin.x, origin.y, origin.z],
        [direction.x, direction.y, direction.z],
      );
    },
    [canvas, camera],
  );

  const press = useCallback<JointPress>(
    (event, target, fromBody, forced) => {
      if (active.current !== null) return;
      if (event.button !== 0) return;
      event.stopPropagation();
      const mode = forced ?? driveModeFor(target.motion, event.shiftKey);
      const ray = rayAt(event.clientX, event.clientY);
      const grab = scenePointToOcct([
        event.point.x,
        event.point.y,
        event.point.z,
      ]);
      let read: ((ray: Ray) => DriveGesture | null) | null = null;
      if (mode === "plane") {
        const drag = beginPlaneDrag({ axis: target.axis, ray, grab });
        if (drag !== null) {
          read = (r) => {
            const shift = drag.move(r);
            return shift === null ? null : { mode, shift };
          };
        }
      } else {
        const axis = mode === "turn" ? target.rot : target.lin;
        const drag =
          axis === null
            ? null
            : beginJointDrag({
                mode,
                axis: target.axis,
                value: axis.value,
                min: axis.min,
                max: axis.max,
                ray,
                grab,
              });
        if (drag !== null) {
          read = (r) => {
            const value = drag.move(r);
            return value === null ? null : { mode, value };
          };
        }
      }
      if (read === null) return;
      if (controls !== null) controls.enabled = false;
      const pressed = { x: event.clientX, y: event.clientY };
      let travelled = false;
      const onMove = (e: PointerEvent) => {
        const session = active.current;
        if (session === null) return;
        // A click that jitters is still a click, not an edit.
        travelled ||=
          Math.hypot(e.clientX - pressed.x, e.clientY - pressed.y) >
          DRAG_THRESHOLD_PX;
        if (!travelled) return;
        const gesture = session.read(rayAt(e.clientX, e.clientY));
        if (gesture === null || sameGesture(session.gesture, gesture)) return;
        session.gesture = gesture;
        onPreview(session.target, gesture);
        invalidate();
      };
      const onUp = () => {
        const session = active.current;
        if (session === null) return;
        session.cleanup();
        onRelease(session.target, session.gesture, fromBody);
      };
      const cleanup = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
        active.current = null;
        if (controls !== null) controls.enabled = true;
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
      active.current = { read, target, gesture: null, cleanup };
    },
    [rayAt, controls, onPreview, onRelease, invalidate],
  );

  useEffect(() => {
    pressRef.current = press;
    return () => {
      pressRef.current = null;
    };
  }, [press, pressRef]);
  // Unmounting mid-drag hands the camera back and writes nothing.
  useEffect(() => () => active.current?.cleanup(), []);

  // ——— where the handle hangs ——————————————————————————————————————————
  const frame = useMemo(() => {
    if (target === null) return null;
    const point = occtPointToScene(target.axis.point);
    const dir = new Vector3(...occtPointToScene(target.axis.dir)).normalize();
    const quaternion = new Quaternion().setFromUnitVectors(Z, dir);
    return { point, dir, quaternion };
  }, [target]);

  // ——— QA stamp + fixed on-screen size ————————————————————————————————
  const handleRef = useRef<Group>(null);
  const host = useMemo(
    () => canvas.closest<HTMLElement>('[data-testid="viewport"]'),
    [canvas],
  );
  const lastStamp = useRef("");
  useFrame((state) => {
    if (frame === null || target === null) return;
    const rect = canvas.getBoundingClientRect();
    const at = new Vector3(...frame.point);
    if (handleRef.current !== null) {
      const fov =
        (state.camera as { isPerspectiveCamera?: boolean })
          .isPerspectiveCamera === true
          ? (state.camera as unknown as { fov: number }).fov
          : DEFAULT_FOV_DEG;
      const s =
        perspectiveUnitsPerPixel(
          fov,
          state.camera.position.distanceTo(at),
          rect.height,
        ) * assemblyTokens.jointHandle.sizePx;
      handleRef.current.scale.setScalar(Math.max(s, 1e-6));
    }
    if (host === null) return;
    state.camera.updateMatrixWorld();
    VP.multiplyMatrices(
      state.camera.projectionMatrix,
      state.camera.matrixWorldInverse,
    );
    const primary = stampAxis(target.rot ?? target.lin);
    const stamp = JSON.stringify({
      canvas: [rect.left, rect.top, rect.width, rect.height].map(Math.round),
      viewProj: VP.elements.map((n) => Math.round(n * 1e6) / 1e6),
      mateId: target.mateId,
      motion: target.motion,
      instanceId: target.instanceId,
      // Scene frame (Y up), like the move triad's stamp.
      point: frame.point,
      dir: [frame.dir.x, frame.dir.y, frame.dir.z],
      // The plain drag's axis (the turn wherever there is one).
      value: primary?.value ?? null,
      min: primary?.min ?? null,
      max: primary?.max ?? null,
      rot: stampAxis(target.rot),
      lin: stampAxis(target.lin),
      atLimit: target.atLimit,
    });
    if (stamp !== lastStamp.current) {
      lastStamp.current = stamp;
      host.dataset.jointDrag = stamp;
    }
  });
  useEffect(() => {
    if (target !== null) return;
    if (host !== null) delete host.dataset.jointDrag;
    lastStamp.current = "";
  }, [target, host]);
  useEffect(
    () => () => {
      if (host !== null) delete host.dataset.jointDrag;
    },
    [host],
  );

  if (frame === null || target === null || !showHandle) return null;
  const tokens = assemblyTokens.jointHandle;
  const material = (
    <meshBasicMaterial
      color={tokens.color}
      depthTest={false}
      transparent
      toneMapped={false}
      side={DoubleSide}
    />
  );
  return (
    <group
      ref={handleRef}
      position={frame.point}
      quaternion={frame.quaternion}
      renderOrder={20}
    >
      <Line
        points={[
          [0, 0, -1.3],
          [0, 0, 1.3],
        ]}
        color={tokens.color}
        lineWidth={tokens.lineWidth}
        dashed
        dashSize={0.08}
        gapSize={0.06}
        depthTest={false}
      />
      {target.rot !== null ? (
        <mesh onPointerDown={(e) => press(e, target, false, "turn")}>
          <torusGeometry args={[0.7, 0.05, 8, 64]} />
          {material}
        </mesh>
      ) : null}
      {target.lin !== null ? (
        <group onPointerDown={(e) => press(e, target, false, "slide")}>
          <mesh position={[0, 0, 0.5]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.04, 0.04, 1, 8]} />
            {material}
          </mesh>
          <mesh position={[0, 0, 1.08]} rotation={[Math.PI / 2, 0, 0]}>
            <coneGeometry args={[0.12, 0.25, 12]} />
            {material}
          </mesh>
        </group>
      ) : null}
      {target.motion === "planar" ? (
        // The in-plane slide: a small square lying in the joint plane.
        <mesh onPointerDown={(e) => press(e, target, false, "plane")}>
          <planeGeometry args={[0.36, 0.36]} />
          {material}
        </mesh>
      ) : null}
    </group>
  );
}
