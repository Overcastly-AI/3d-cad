/**
 * THE EXTRUDE DEPTH GAUGE — drag the arrow, the extrude follows (T-23).
 *
 * The design mandate's plainest sentence about this product: *"Fusion's extrude
 * is a draggable arrow; the numeric field is the precision fallback. Ours is a
 * form with no handle at all — the single biggest 'does not feel like a
 * modeling tool' gap we have, bigger than any missing feature."* The fifth
 * product audit swept the whole DOM in every state it could reach for
 * `[data-testid*="handle|gizmo|drag|arrow|manip"]` and got `[]`.
 *
 * WHAT IT IS. While the extrude editor is open, a brass gauge stands on the
 * profile: a shaft from the plane to the end face, an arrowhead on the end, a
 * grip on the arrowhead's point, and the live depth hanging beside it in the
 * drafting tag the sketcher already uses. Take the grip and the whole
 * preview follows the pointer; the rail's Distance field is the exact path, and
 * the two are ONE value — the drag writes the field and the field moves the
 * arrow, because they are the same state read twice.
 *
 * THE SIGNATURE, and the one place boldness is spent: taking the grip extends a
 * GRADUATED LADDER down the axis. A plain arrow says "you may pull this"; a
 * ruled one says what you are pulling against. The graduations are chosen from
 * the 1/2/5 decade series ({@link ladderTicks}), so the step is always a number
 * a person would say out loud, and they are the reason this reads as a
 * machinist's depth gauge rather than a gizmo from any 3D app.
 *
 * WHY THE GRIP IS DOM AND THE GAUGE IS WebGL. The drawn parts must composite
 * with the scene (they are `depthTest: false`, an x-ray, for the same reason
 * the ghost is: the interesting sweeps happen INSIDE material). The grip must
 * be focusable, nameable, and drivable by a test — none of which a `<mesh>` can
 * be. So the gauge draws in GL and the target is a drei `Html` slider directly
 * over its point, the same split the measurement pick nodes make.
 *
 * KEYBOARD. The grip is a real slider: arrows step one snap increment, Shift
 * and the Page keys take ten, each landing on ITS OWN grid rather than adding
 * to whatever fraction a drag left behind ({@link steppedDepth}), and the value
 * it announces is the same one the field shows. Both steps are named on the
 * element, so a screen-reader user does not have to discover them by trying.
 * Nothing here is reachable only by pointer.
 *
 * Every colour is a `@loft/design` token; GPU resources are disposed on change
 * and unmount; the render loop allocates nothing (the geometry rebuilds only
 * when the depth changes, and the camera does not touch this component).
 */
import { AxisGrip, DimensionTag, DimensionTagCell } from "@loft/design";
import { formatLength, type LengthUnit } from "@loft/design";
import { viewport } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  ConeGeometry,
  CylinderGeometry,
  MeshBasicMaterial,
  Quaternion,
  Raycaster,
  Vector2,
  Vector3,
} from "three";

import { useCommandActionStore } from "../features/commandActions";
import type { ExtrudeDirection } from "../features/extrude";
import type { PlaneBasis } from "../sketch/plane";
import {
  arrowLength,
  ARROW_RADIUS_FRAC,
  COARSE_STEP_FACTOR,
  depthAlongAxis,
  handleAxis,
  keyStepMm,
  LADDER_HALF_WIDTH_FRAC,
  ladderTicks,
  MAX_DEPTH_MM,
  MIN_DEPTH_MM,
  nudgeDepth,
  orthographicMmPerPixel,
  perspectiveMmPerPixel,
  quantizeDepth,
  sameDepth,
  screenDragDepth,
  tipPoint,
} from "./extrudeHandle";
import type { ProfileRegion } from "./profileLoops";
import { Segments } from "./overlaySegments";

export interface ExtrudeDragHandleProps {
  /** The sketch plane, in SCENE coordinates (see `extrudeHandle`'s frame note). */
  basis: PlaneBasis;
  /** The solved profile loops the gauge stands on. */
  regions: readonly ProfileRegion[];
  /** The editor's current distance, canonical mm. */
  depthMm: number;
  direction: ExtrudeDirection;
  /** Document length unit — drives the snap increment and the readout. */
  unit: LengthUnit;
  /** Report a new distance in canonical mm (the editor owns the value). */
  onDepthChange: (mm: number) => void;
}

/** Stacking band for the gauge's DOM parts — above the pick overlays, under the HUD. */
const GRIP_Z_RANGE: [number, number] = [39, 30];

/** Rung half-width floor, mm, so a hairline profile still gets a readable ladder. */
const LADDER_MIN_HALF_WIDTH_MM = 2;

/** +Y — the axis `ConeGeometry` builds along, turned onto the sweep direction. */
const CONE_AXIS = new Vector3(0, 1, 0);

/** The workspace camera's field of view — the fallback if one is ever ortho. */
const DEFAULT_FOV_DEG = 40;

/** Shaft radius as a fraction of the arrowhead's — a stem, not a rod. */
const SHAFT_RADIUS_FRAC = 0.16;

export function ExtrudeDragHandle({
  basis,
  regions,
  depthMm,
  direction,
  unit,
  onDepthChange,
}: ExtrudeDragHandleProps) {
  const invalidate = useThree((state) => state.invalidate);
  const camera = useThree((state) => state.camera);
  const canvas = useThree((state) => state.gl.domElement);

  /**
   * THE OPTIMISTIC DEPTH — what this handle has ASKED for but not yet seen come
   * back.
   *
   * The value round-trips (handle -> editor form -> ghost -> back here), which
   * is the right architecture — one value, one owner — and it is several
   * renders long. Two consequences, and the second is not cosmetic:
   *
   *  · the arrow would trail the cursor by a frame; and
   *  · a SECOND input arriving inside that window would compute from the stale
   *    prop and overwrite the first. Two quick taps of Up gave 10.5 rather than
   *    11, intermittently, which is how it was found: the e2e passed alone and
   *    failed under load, the signature of a lost update rather than a flake.
   *
   * THE FIRST VERSION OF THAT FIX HELD ONE PENDING VALUE AND DROPPED IT ON ANY
   * CHANGE OF `depthMm`, WHICH LOSES THE UPDATE IT WAS BUILT TO SAVE. The
   * acknowledgement that arrives is the one for the FIRST press, and dropping
   * the pending value on it throws away the second. Measured over 20 fast
   * `Up, Up, Shift+Up` sequences on the real stack, 13 came back wrong, the
   * browser saying so itself:
   *
   *     key=ArrowUp  pending=null  depthMm=10    from=10    next=10.5
   *     key=ArrowUp  pending=10.5  depthMm=10    from=10.5  next=11
   *     effect depthMm=10.5 pending=11      <- ack for press 1 clears press 2
   *     key=ArrowUp  pending=null  depthMm=10.5  from=10.5  next=15.5
   *
   * — 15.5 where 16 was asked for, and the same log shows the second variant,
   * where the ack lands cleanly but the KEY HANDLER still reads the previous
   * `depthMm` (the grip is portalled out through drei `Html`, so the prop the
   * handler closes over can trail the effect by a commit). Both are the same
   * mistake: reasoning from a value that is neither the last one requested nor
   * the last one confirmed.
   *
   * So the handle keeps the QUEUE of values it has asked for, oldest first, and
   * a `base` the next step reasons from:
   *
   *  · an arriving `depthMm` that MATCHES an outstanding ask (to within the
   *    kernel's linear tolerance — the field is a display string, see
   *    {@link sameDepth}) retires that ask and every older one, and leaves
   *    `base` alone, because a later ask has already superseded it;
   *  · an arriving `depthMm` that matches NOTHING we asked for is somebody
   *    else's edit — a typed distance, a re-seeded editor — and wins outright:
   *    the queue is abandoned and it becomes the new `base`.
   *
   * `live` renders the newest outstanding ask, so the arrow, the tag and
   * `aria-valuenow` show what the user last asked for rather than a value two
   * commits stale.
   */
  const [live, setLive] = useState<number | null>(null);
  const asksRef = useRef<readonly number[]>([]);
  const baseRef = useRef(depthMm);
  const [grabbed, setGrabbed] = useState(false);
  const shown = live ?? depthMm;

  const axis = useMemo(
    () => handleAxis(basis, direction, regions),
    [basis, direction, regions],
  );
  const tip = useMemo(() => tipPoint(axis, shown), [axis, shown]);
  const headLength = arrowLength(axis.radius);
  /** The arrowhead's point — where the grip and the readout ride. */
  const apex = useMemo(
    () => tip.clone().addScaledVector(axis.dir, headLength),
    [tip, axis, headLength],
  );

  /**
   * The ladder. Built only while the grip is held or focused — at rest the
   * gauge is an arrow and nothing more, which is the whole restraint argument.
   */
  const [ladderOn, setLadderOn] = useState(false);
  const ladderPositions = useMemo(() => {
    if (!ladderOn) return new Float32Array(0);
    const ticks = ladderTicks(shown);
    const half = Math.max(
      LADDER_MIN_HALF_WIDTH_MM,
      axis.radius * LADDER_HALF_WIDTH_FRAC,
    );
    // A CROSS at each graduation, not a single rung. A rung lies along one
    // in-plane axis, so from a three-quarter view it projects as a skewed dash
    // that reads as debris rather than a scale — measured on the first founder
    // capture. Two arms (u and v) always project to something centred on the
    // axis, from any camera, which is what makes it read as a graduation.
    const armU = new Vector3(...basis.u).normalize().multiplyScalar(half);
    const armV = new Vector3(...basis.v).normalize().multiplyScalar(half);
    const out = new Float32Array(ticks.length * 12);
    for (let i = 0; i < ticks.length; i += 1) {
      const at = axis.base
        .clone()
        .addScaledVector(axis.dir, ticks[i] as number);
      const base = i * 12;
      for (const [n, arm] of [armU, armV].entries()) {
        out[base + n * 6] = at.x - arm.x;
        out[base + n * 6 + 1] = at.y - arm.y;
        out[base + n * 6 + 2] = at.z - arm.z;
        out[base + n * 6 + 3] = at.x + arm.x;
        out[base + n * 6 + 4] = at.y + arm.y;
        out[base + n * 6 + 5] = at.z + arm.z;
      }
    }
    return out;
  }, [ladderOn, shown, axis, basis]);

  // The arrowhead: a cone whose BASE sits on the end face and whose point is
  // the grip. Sized from the profile, never from the depth, so it holds still
  // while you drag (a manipulator that grows under the cursor reads as the
  // model moving).
  const headGeometry = useMemo(
    () =>
      new ConeGeometry(headLength * ARROW_RADIUS_FRAC, headLength, 20, 1, true),
    [headLength],
  );
  const headMaterial = useMemo(() => {
    const material = new MeshBasicMaterial({
      color: viewport.manipulator.axis,
    });
    material.toneMapped = false;
    material.transparent = true;
    material.opacity = viewport.manipulator.axisOpacity;
    material.depthTest = false;
    material.depthWrite = false;
    return material;
  }, []);
  useEffect(() => {
    headMaterial.color.set(
      grabbed ? viewport.manipulator.active : viewport.manipulator.axis,
    );
    invalidate();
  }, [grabbed, headMaterial, invalidate]);
  useEffect(() => () => headGeometry.dispose(), [headGeometry]);
  useEffect(() => () => headMaterial.dispose(), [headMaterial]);

  /**
   * The SHAFT is a thin cylinder, not a `lineSegments`.
   *
   * WebGL line width is clamped to 1 px on every desktop driver we target, so a
   * GL line gives a hairline at any zoom — which reads as an annotation, the way
   * a dimension leader does, and this is not an annotation. Side by side against
   * Fusion's extrude arrow the hairline was the single thing that most said
   * "diagram" rather than "manipulator". A unit cylinder SCALED to the depth
   * costs one geometry for the lifetime of the drag: the rebuild is a scale, not
   * an allocation, so the drag stays allocation-free.
   */
  const shaftGeometry = useMemo(
    () =>
      new CylinderGeometry(
        headLength * ARROW_RADIUS_FRAC * SHAFT_RADIUS_FRAC,
        headLength * ARROW_RADIUS_FRAC * SHAFT_RADIUS_FRAC,
        1,
        12,
        1,
        true,
      ),
    [headLength],
  );
  useEffect(() => () => shaftGeometry.dispose(), [shaftGeometry]);

  const headPose = useMemo(() => {
    const quaternion = new Quaternion().setFromUnitVectors(CONE_AXIS, axis.dir);
    // ConeGeometry is centred on its own axis, so the base lands on the end
    // face when the centre sits half a length along the sweep.
    const centre = tip.clone().addScaledVector(axis.dir, headLength / 2);
    // The shaft spans plane -> end face, so its centre is halfway up.
    const shaftCentre = axis.base.clone().addScaledVector(axis.dir, shown / 2);
    return { quaternion, centre, shaftCentre };
  }, [axis, tip, headLength, shown]);

  useEffect(() => invalidate(), [shown, ladderOn, invalidate]);

  /** Pointer ray, in world space, from a DOM pointer event over the canvas. */
  const rayRef = useRef(new Raycaster());
  const ndcRef = useRef(new Vector2());
  const rayFor = useCallback(
    (clientX: number, clientY: number) => {
      const rect = canvas.getBoundingClientRect();
      ndcRef.current.set(
        ((clientX - rect.left) / rect.width) * 2 - 1,
        -((clientY - rect.top) / rect.height) * 2 + 1,
      );
      rayRef.current.setFromCamera(ndcRef.current, camera);
      return rayRef.current.ray;
    },
    [camera, canvas],
  );

  /**
   * The grab, held for the length of the drag. Two modes, chosen ONCE at
   * pointer-down (the camera cannot move mid-drag, so the choice cannot go
   * stale):
   *
   *  · `axis` — the pointer is projected onto the pull axis. The real gesture:
   *    the arrowhead stays under the cursor because it IS the cursor's position
   *    on that line.
   *  · `screen` — the axis points at the eye, so it has no readable direction
   *    on screen; vertical travel drives the depth at the tip's own scale.
   *    Reached by the most ordinary path in the product (save a sketch, press
   *    Extrude: the camera is normal to the plane), which is why the fallback
   *    is not optional. See {@link AXIS_SHALLOW}.
   *
   * Both are RELATIVE to where the grab started, so the arrow never jumps to
   * the cursor on mousedown — the difference between a handle and a teleport.
   */
  const grabRef = useRef<
    | { mode: "axis"; t: number; depth: number }
    | { mode: "screen"; y: number; depth: number; mmPerPixel: number }
    | null
  >(null);

  /**
   * Ask the editor for a depth — the ONE place a new value leaves this handle,
   * whether it came from the pointer or from a key.
   *
   * The ask is recorded before it is sent, so the next input reasons from it
   * even if no render has happened in between; that is the whole point of the
   * queue described above.
   */
  const ask = useCallback(
    (mm: number) => {
      baseRef.current = mm;
      // Mid-drag there is nothing to reconcile — the effect below stands aside
      // for the pointer and `endDrag` empties the queue — so a drag does not
      // grow one entry per `pointermove`, and the render loop stays as
      // allocation-free as it was.
      if (grabRef.current === null) asksRef.current = [...asksRef.current, mm];
      setLive(mm);
      onDepthChange(mm);
    },
    [onDepthChange],
  );

  // The owner has spoken. Retire the ask it acknowledges (and every older one);
  // if it acknowledges none of ours, it is somebody else's edit and it wins.
  // Skipped mid-drag, where the pointer is still the author and the props are
  // chasing it.
  useEffect(() => {
    if (grabRef.current !== null) return;
    const at = asksRef.current.findIndex((mm) => sameDepth(mm, depthMm));
    if (at >= 0) {
      asksRef.current = asksRef.current.slice(at + 1);
    } else {
      asksRef.current = [];
      baseRef.current = depthMm;
    }
    setLive(asksRef.current.at(-1) ?? null);
  }, [depthMm]);

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return;
      // `base`, not the prop: a grab taken straight after a key press must
      // anchor on the value that press ASKED for, or the arrow jumps back a
      // step the instant the pointer moves.
      const from = baseRef.current;
      const ray = rayFor(event.clientX, event.clientY);
      const t = depthAlongAxis(axis, ray.origin, ray.direction);
      if (t !== null) {
        grabRef.current = { mode: "axis", t, depth: from };
      } else {
        const rect = canvas.getBoundingClientRect();
        const at = tipPoint(axis, from);
        // Under a PARALLEL projection the scale is a property of the camera
        // alone — depth cannot change it — so the perspective formula (which is
        // all distance) would report a drag rate that is simply wrong once
        // ORTHO-1's toggle is on. Read the zoom instead; see
        // `orthographicMmPerPixel`.
        const parallel =
          "isOrthographicCamera" in camera &&
          (camera as { isOrthographicCamera?: boolean })
            .isOrthographicCamera === true
            ? (camera as unknown as { zoom: number }).zoom
            : null;
        const fov =
          "isPerspectiveCamera" in camera &&
          (camera as { isPerspectiveCamera?: boolean }).isPerspectiveCamera ===
            true
            ? (camera as unknown as { fov: number }).fov
            : DEFAULT_FOV_DEG;
        grabRef.current = {
          mode: "screen",
          y: event.clientY,
          depth: from,
          mmPerPixel:
            parallel !== null
              ? orthographicMmPerPixel(parallel)
              : perspectiveMmPerPixel(
                  fov,
                  camera.position.distanceTo(at),
                  rect.height,
                ),
        };
      }
      setGrabbed(true);
      setLadderOn(true);
      setLive(from);
      event.currentTarget.setPointerCapture(event.pointerId);
      event.stopPropagation();
      event.preventDefault();
    },
    [axis, camera, canvas, rayFor],
  );

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const grab = grabRef.current;
      if (grab === null) return;
      let raw: number;
      if (grab.mode === "axis") {
        const ray = rayFor(event.clientX, event.clientY);
        const t = depthAlongAxis(axis, ray.origin, ray.direction);
        // The axis went shallow mid-drag (it cannot: the camera is held). Keep
        // the last good value rather than invent one.
        if (t === null) return;
        raw = grab.depth + (t - grab.t);
      } else {
        raw = screenDragDepth(
          grab.depth,
          grab.y - event.clientY,
          grab.mmPerPixel,
        );
      }
      const free = event.ctrlKey || event.metaKey;
      ask(quantizeDepth(raw, unit, free));
    },
    [ask, axis, rayFor, unit],
  );

  const endDrag = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (grabRef.current === null) return;
    grabRef.current = null;
    setGrabbed(false);
    // The pointer is done authoring, so the prop is the truth from here — but
    // `base` keeps the value the drag ended on, so an arrow pressed straight
    // afterwards steps off WHAT YOU DRAGGED TO, not off a prop that has not
    // caught up yet. That is the case a free (Ctrl) drag makes load-bearing:
    // it ends on something like 12.4713, and the first press has to be able to
    // put it back on a grid.
    asksRef.current = [];
    setLive(null);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const requestSubmit = useCommandActionStore((s) => s.requestSubmit);

  /** What a press is worth, in canonical mm — announced, and asserted against. */
  const fineStepMm = keyStepMm(unit);
  const coarseStepMm = fineStepMm * COARSE_STEP_FACTOR;
  const stepHintId = useId();

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      // The band promises "OK · ENTER" while a command is open, and after a
      // drag the focus is HERE — so Enter has to commit from here too, or the
      // one control that finally lets you set a depth by hand is the one place
      // the advertised key does nothing (the flow rule's "no dead ends", and
      // the same defect FINDINGS #11 fixed for Escape). It goes through the
      // in-command action bus rather than a second submit: one commit path, the
      // editor's own, driven from a third place.
      if (event.key === "Enter") {
        event.preventDefault();
        requestSubmit();
        return;
      }
      const next = nudgeDepth(baseRef.current, event.key, unit, event.shiftKey);
      if (next === null) return;
      event.preventDefault();
      event.stopPropagation();
      ask(next);
    },
    [ask, requestSubmit, unit],
  );

  if (regions.length === 0 || depthMm <= 0) return null;

  return (
    <group name="extrude-drag-handle">
      <mesh
        geometry={shaftGeometry}
        material={headMaterial}
        position={headPose.shaftCentre}
        quaternion={headPose.quaternion}
        scale={[1, Math.max(shown, 1e-3), 1]}
        renderOrder={13}
      />
      <Segments
        positions={ladderPositions}
        color={viewport.manipulator.axis}
        opacity={viewport.manipulator.ladderOpacity}
        depthTest={false}
        renderOrder={12}
      />
      <mesh
        geometry={headGeometry}
        material={headMaterial}
        position={headPose.centre}
        quaternion={headPose.quaternion}
        renderOrder={13}
      />
      <Html position={apex} center zIndexRange={GRIP_Z_RANGE}>
        <AxisGrip
          aria-label="Extrude depth"
          aria-describedby={stepHintId}
          data-testid="extrude-depth-handle"
          data-depth-mm={shown}
          data-step-mm={fineStepMm}
          data-coarse-step-mm={coarseStepMm}
          value={shown}
          min={MIN_DEPTH_MM}
          max={MAX_DEPTH_MM}
          valueText={formatLength(shown, unit)}
          grabbed={grabbed}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onKeyDown={onKeyDown}
          onFocus={() => setLadderOn(true)}
          onBlur={() => setLadderOn(grabbed)}
          onPointerEnter={() => setLadderOn(true)}
          onPointerLeave={() => setLadderOn(grabbed)}
        />
        {/* ARIA has `aria-valuenow`/`min`/`max` and no way at all to say what a
            press is WORTH, so a slider whose step is only in the source is a
            slider a screen-reader user has to discover by trying it. The steps
            are named here instead — in the document's own unit, from the same
            constants the key handler uses, so the sentence cannot drift from
            the behaviour — and the same two numbers are on the element as data
            attributes, which is what lets a test assert that the spoken step
            and the applied step are one thing. */}
        <span
          id={stepHintId}
          className="sr-only"
          data-testid="extrude-depth-steps"
        >
          {`Arrow keys step ${formatLength(fineStepMm, unit)}; Shift or Page keys step ${formatLength(coarseStepMm, unit)}. Enter saves.`}
        </span>
      </Html>
      {/* `pointerEvents: none` on the WRAPPER, not just the tag: drei gives
          every `Html` its own positioned div, and this one is anchored at the
          same point as the grip. Without it the tag's box sits over the grip's
          24 px target and swallows the press — the drag then does nothing at
          all, which is exactly how the first browser run failed. */}
      <Html
        position={apex}
        zIndexRange={GRIP_Z_RANGE}
        style={{ pointerEvents: "none" }}
      >
        {/* The number, where the eye already is. The rail's Distance field is
            800 px away (T-4); a drag that makes you look over there to read
            what you just did is not direct manipulation. Read-only by design —
            the pointer owns this value, and `DimensionTag` carries exactly that
            distinction already. */}
        <DimensionTag
          unit={unit}
          data-testid="extrude-depth-readout"
          className="pointer-events-none -translate-y-8 translate-x-4 whitespace-nowrap"
        >
          <DimensionTagCell
            label="D"
            readout={formatLength(shown, unit, { unitSuffix: false })}
          />
        </DimensionTag>
      </Html>
    </group>
  );
}
