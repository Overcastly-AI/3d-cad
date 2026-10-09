/**
 * The Move triad — drei `PivotControls` (MIT) hung on the instance being
 * moved: three axis arrows, three rotation rings and three planar squares,
 * Fusion 360's Move manipulator.
 *
 * FRAME. The control's matrix is the instance's SCENE transform (Y up), so a
 * drag reports a scene matrix and `sceneToPlacement` turns it back into the
 * kernel `Placement` — the one inverse of the render-time mapping, never a
 * second copy of the frame algebra. The visible handles are then turned by
 * `S` (−90° about X), so the red/green/blue arrows name the KERNEL X/Y/Z the
 * Move panel's cells and every other readout use: blue points up, as it does
 * in the modeller's head. The handles' drag maths reads their own world
 * matrices, so the turn changes only what they look like, not what they do.
 *
 * NOTHING PERSISTS HERE. A drag only reports poses; the page previews them and
 * sends ONE `PATCH` on release (`useMoveSession`).
 *
 * QA STAMP. A WebGL handle is invisible to the DOM, and a manipulator QA cannot
 * drive is one that rots. The triad publishes its handles' WORLD points and the
 * camera's view-projection on `[data-testid="viewport"]` as
 * `data-move-triad`, so a spec can project a handle to the screen and do the
 * real gesture: press on the arrow, move the pointer, release.
 */
import { assembly as assemblyTokens } from "@loft/design/tokens";
import { PivotControls } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { type Group, Matrix4, Quaternion, Vector3 } from "three";

import {
  type Placement,
  type SceneTransform,
  sceneToPlacement,
} from "../assembly/placement";

export interface MoveTriadProps {
  /** The pose the instance is drawn at right now (preview or solved). */
  transform: SceneTransform;
  /** False while a commit is in flight: the handles hold still. */
  enabled: boolean;
  /** A live pose while dragging (kernel frame). Nothing is persisted. */
  onDrag: (placement: Placement) => void;
  /** The pointer came up — the page commits the last reported pose. */
  onDragEnd: () => void;
}

/** `S`: the handles' turn from scene Y-up to the kernel's Z-up. */
const HANDLE_ROTATION: [number, number, number] = [-Math.PI / 2, 0, 0];

// drei's handle geometry in its fixed-size local units (see
// `pivotControls/AxisArrow` and `AxisRotator`): an arrow is 1 long, a ring is
// a quarter arc of radius 0.65 from `dir1` towards `dir2`.
const ARROW_GRAB = 0.9;
const RING_RADIUS = 0.65;
const AXES = [
  new Vector3(1, 0, 0),
  new Vector3(0, 1, 0),
  new Vector3(0, 0, 1),
] as const;
/** `[dir1, dir2]` of the ring that turns about each axis. */
const RING_BASIS = [
  [AXES[1], AXES[2]],
  [AXES[2], AXES[0]],
  [AXES[0], AXES[1]],
] as const;

const POS = new Vector3();
const QUAT = new Quaternion();
const SCALE = new Vector3();
const VP = new Matrix4();

/** A gizmo-local point on a ring, `deg` degrees from its `dir1` end. */
function ringPoint(axis: 0 | 1 | 2, deg: number): Vector3 {
  const [d1, d2] = RING_BASIS[axis];
  const a = (deg * Math.PI) / 180;
  return d1
    .clone()
    .multiplyScalar(RING_RADIUS * Math.cos(a))
    .addScaledVector(d2, RING_RADIUS * Math.sin(a));
}

const round = (v: Vector3): number[] =>
  [v.x, v.y, v.z].map((n) => Math.round(n * 1e4) / 1e4);

export function MoveTriad({
  transform,
  enabled,
  onDrag,
  onDragEnd,
}: MoveTriadProps) {
  const matrix = useMemo(
    () =>
      new Matrix4().compose(
        new Vector3(...transform.position),
        new Quaternion(...transform.quaternion),
        new Vector3(1, 1, 1),
      ),
    [transform],
  );

  // A drag reports at pointer rate; the page re-renders per pose. Coalesce to
  // one pose per animation frame, and flush the last one before a release so
  // the commit always sends the pose the pointer let go at.
  const pending = useRef<Placement | null>(null);
  const frame = useRef<number | null>(null);
  const flush = useCallback(() => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
    const placement = pending.current;
    pending.current = null;
    if (placement !== null) onDrag(placement);
  }, [onDrag]);
  useEffect(
    () => () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    },
    [],
  );

  const handleDrag = useCallback(
    (local: Matrix4) => {
      local.decompose(POS, QUAT, SCALE);
      pending.current = sceneToPlacement({
        position: [POS.x, POS.y, POS.z],
        quaternion: [QUAT.x, QUAT.y, QUAT.z, QUAT.w],
      });
      if (frame.current === null) frame.current = requestAnimationFrame(flush);
    },
    [flush],
  );
  // ——— the camera hand-back ——————————————————————————————————————————————
  //
  // drei's handles (AxisArrow, AxisRotator, PlaneSlider in 10.7.7) switch the
  // default camera controls OFF on pointer-down and back on only in their OWN
  // pointer-up. A triad that unmounts mid-drag — Esc, a mate key, Enter in a
  // cell, leaving the page — never sees that pointer-up, and the orbit stayed
  // dead until a reload. So the triad tracks its own drag and, when it goes
  // away (or its handles are withdrawn) during one, hands the camera back.
  const controls = useThree((state) => state.controls) as {
    enabled?: boolean;
  } | null;
  const dragging = useRef(false);
  const handleDragStart = useCallback(() => {
    dragging.current = true;
  }, []);
  useEffect(
    () => () => {
      if (!dragging.current) return;
      dragging.current = false;
      if (controls !== null) controls.enabled = true;
    },
    [controls, enabled],
  );

  const handleDragEnd = useCallback(() => {
    dragging.current = false;
    flush();
    onDragEnd();
  }, [flush, onDragEnd]);

  // ——— the QA stamp ————————————————————————————————————————————————————————
  const pivotRef = useRef<Group>(null);
  const canvas = useThree((state) => state.gl.domElement);
  const host = useMemo(
    () => canvas.closest<HTMLElement>('[data-testid="viewport"]'),
    [canvas],
  );
  const lastStamp = useRef("");
  useFrame((state) => {
    const handles = pivotRef.current?.children[0];
    if (host === null || handles === undefined) return;
    handles.updateWorldMatrix(true, false);
    const world = handles.matrixWorld;
    const at = (p: Vector3) => round(p.clone().applyMatrix4(world));
    const origin = new Vector3().setFromMatrixPosition(world);
    const camera = state.camera;
    camera.updateMatrixWorld();
    VP.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    const rect = canvas.getBoundingClientRect();
    const stamp = JSON.stringify({
      // The canvas the projection lands in, in page CSS px.
      canvas: [rect.left, rect.top, rect.width, rect.height].map(Math.round),
      viewProj: VP.elements.map((n) => Math.round(n * 1e6) / 1e6),
      origin: round(origin),
      // The unit WORLD direction of each kernel axis (x, y, z).
      dirs: AXES.map((d) =>
        round(d.clone().transformDirection(world).normalize()),
      ),
      arrows: AXES.map((d) => at(d.clone().multiplyScalar(ARROW_GRAB))),
      rings: ([0, 1, 2] as const).map((axis) => ({
        grab: at(ringPoint(axis, 45)),
        quarter: at(ringPoint(axis, 135)),
      })),
    });
    if (stamp !== lastStamp.current) {
      lastStamp.current = stamp;
      host.dataset.moveTriad = stamp;
    }
  });
  useEffect(
    () => () => {
      if (host !== null) delete host.dataset.moveTriad;
    },
    [host],
  );

  const tokens = assemblyTokens.moveTriad;
  return (
    <PivotControls
      ref={pivotRef}
      matrix={matrix}
      autoTransform={false}
      enabled={enabled}
      rotation={HANDLE_ROTATION}
      fixed
      scale={tokens.sizePx}
      lineWidth={tokens.lineWidth}
      disableScaling
      depthTest={false}
      axisColors={[...tokens.axisColors] as [string, string, string]}
      hoveredColor={tokens.hovered}
      onDragStart={handleDragStart}
      onDrag={handleDrag}
      onDragEnd={handleDragEnd}
    />
  );
}
