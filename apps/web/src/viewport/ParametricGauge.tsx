/**
 * THE PARAMETRIC GAUGE — one instrument, every verb (CRAFT-8, made grabbable by
 * CRAFT-7).
 *
 * ## What it is
 *
 * While a feature editor is open, a brass gauge stands on the geometry the
 * feature is about: a shaft from the seat to the value, an arrowhead on the
 * end, a grip on the arrowhead's point, and the live number hanging beside it
 * in the drafting tag the sketcher already uses, tied to the grip by a leader.
 * Take the grip — anywhere along the arrow — and the preview follows the
 * pointer; type over the number in the tag and the arrow follows the digits.
 * They are ONE value, read twice.
 *
 * THE SIGNATURE, and the one place boldness is spent: taking the grip extends a
 * GRADUATED LADDER along the track, and **the rungs it draws are exactly the
 * values the drag snaps to**. A plain arrow says "you may pull this"; a ruled
 * one says what you are pulling against and what the pointer will do when you
 * pull it, which is what makes this read as a machinist's depth gauge rather
 * than a gizmo from any 3D app.
 *
 * ## Why this file exists rather than one component per verb
 *
 * Extracted from `ExtrudeDragHandle.tsx`, which was the only manipulator in the
 * product and was about to be copied six times. What is shared across every
 * verb is STATE AND CORRECTNESS — the optimistic ask-queue and its
 * reconciliation, the grab-mode choice, pointer capture, key stepping, the
 * grip, the tag, the digit handoff, the nested Escape. What differs is
 * STATELESS ARITHMETIC — the drawn geometry, the pointer projection, the stop
 * set, the formatter, the clamp — and that lives in a {@link GaugeTrack} from
 * `@loft/design`, INJECTED here. The component never branches on what kind of
 * track it has.
 *
 * ## Why the target is DOM and the instrument is WebGL — and why that was a bug
 *
 * The drawn parts must composite with the scene (they are `depthTest: false`,
 * an x-ray, for the same reason the ghost is: the interesting sweeps happen
 * INSIDE material). The target must be focusable, nameable, and drivable by a
 * test — none of which a `<mesh>` can be. So the instrument draws in GL and the
 * controls are drei `Html`.
 *
 * **That split was also the gauge's biggest defect, and fixing it is CRAFT-7.**
 * MEASURED on the running app: `document.elementFromPoint` down the gauge's own
 * projected track resolved to the grip at **2 of 16** sample points — the
 * 24 x 24 box at the arrow's apex and nothing else — and a real
 * `page.mouse.down/move/up` from the shaft's midpoint left the distance field
 * at 40. The affordance and the hit target were ANTICORRELATED: the one place
 * you could grab was a 12 px collar on the POINT of an arrow, about 90 px from
 * where the arrow tells you to aim.
 *
 * The fix is the HIT SLEEVE: a DOM band laid along the PROJECTED track,
 * sharing the grip's pointer handlers. It is deliberately not a raycast mesh —
 * a mesh is invisible to `elementFromPoint`, to Playwright's actionability
 * check, to a touch-target audit and to assistive tech, which is how a
 * manipulator rots silently. This repo has already solved this exact problem
 * once, on the drawing sheet, where a stroked SVG `<line>` measured
 * `118.1 x 0.0 px` because `getBoundingClientRect` ignores stroke and the fix
 * was a rotated filled `<rect>` of the same band. Same shape, same answer.
 *
 * ## Keyboard
 *
 * The grip is a real slider: arrows step one increment, Shift and the Page keys
 * take ten, each landing on ITS OWN grid rather than adding to whatever
 * fraction a drag left behind, and the value it announces is the same one the
 * field shows. `Tab` goes to the tag's cell and `Shift+Tab` comes back, so the
 * precision path is one key from the grip rather than 800 px away in the rail.
 * Typing a digit anywhere opens that cell with the character already in it —
 * the same promise the sketcher makes while drawing. `Enter` commits, from
 * anywhere, through the one existing submit. `Escape` undoes the innermost
 * thing you are doing and never more than one level of it. Nothing here is
 * reachable only by pointer.
 *
 * Every colour is a `@loft/design` token; GPU resources are disposed on change
 * and unmount; the render loop allocates nothing (the sleeve and the tag's side
 * are written straight to their DOM nodes from `useFrame`, and the geometry
 * rebuilds only when the instrument's own proportions change).
 *
 * ## Motion
 *
 * None, deliberately — no fade-in, no pulse, no spring, and `AxisGrip`'s colour
 * transition already carries `motion-reduce:transition-none`. So
 * `prefers-reduced-motion` needs no new code here; that is a decision, not an
 * omission.
 */
import {
  AxisGrip,
  GaugeTag,
  type DimensionTagCellProps,
  NO_STOPS,
  orthographicUnitsPerPixel,
  perspectiveUnitsPerPixel,
  placeGaugeTag,
  type GaugeStops,
  type GaugeTagSide,
  type GaugeTrack,
  type Vec3,
} from "@loft/design";
import { viewport } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  ConeGeometry,
  CylinderGeometry,
  MeshBasicMaterial,
  Raycaster,
  Vector2,
  Vector3,
} from "three";

import { useCommandActionStore } from "../features/commandActions";
import { useCancelKey, useGlobalKeys } from "../lib/modalGate";
import { gaugePose, projectedSpineLength, spineLength } from "./gaugePose";
import { Segments } from "./overlaySegments";
import { useAskQueue } from "./useAskQueue";

/** One value cell on the gauge's tag. */
export interface GaugeCell {
  /** Terse drafting label — "D", "R", "Ø", "A", "N". */
  tagLabel: string;
  value: number;
  onChange: (value: number) => void;
  track: GaugeTrack;
  min: number;
  max: number;
}

export interface ParametricGaugeProps {
  /** What this drives. Required. e.g. "Extrude depth". Becomes the slider name. */
  label: string;
  /** Terse drafting label for the tag cell — "D", "R", "Ø", "A", "N". */
  tagLabel: string;
  /** The owner's value. The gauge never owns it. */
  value: number;
  /** Ask the owner for a new one. Fires on drag, key, and applied typing. */
  onChange: (value: number) => void;
  /** Geometry + arithmetic. Injected, never switched on. */
  track: GaugeTrack;
  min: number;
  max: number;
  /**
   * Test/query hook shared by the grip AND the hit sleeve: `data-gauge="<id>"`
   * on both, and `<id>-handle` / `-sleeve` / `-readout` / `-steps` test-ids. ONE
   * id per instrument, so a probe can ask "did this click land anywhere on the
   * gauge" without knowing which part it hit.
   */
  gaugeId: string;
  /**
   * A second cell on the same tag — hole's depth + Ø. One strip, because two
   * tags twenty millimetres apart carrying different numbers is the "two
   * dialects drawn on screen" failure literally.
   *
   * It carries its OWN track (§6.1), so a mixed-unit pair — a depth in
   * millimetres beside an angle in degrees — is formatted by the thing that
   * knows its unit. CRAFT-8 shipped this narrowed to `tagLabel | value`, which
   * formatted the companion with the PRIMARY track's formatter: right for hole
   * and wrong for anything else, and wrong SILENTLY.
   */
  companion?: GaugeCell;
  /** Unit written once at the end of the tag strip. Omit for an angle. */
  tagUnit?: string;
  /**
   * Which quadrant of the grip the tag prefers. It FLIPS rather than clamps at
   * the frame edge, so a gauge dragged into a corner keeps its leader pointing
   * at the grip instead of folding the strip over it.
   */
  tagSide?: GaugeTagSide;
  /**
   * Suppress the tag when another gauge on screen already carries the number —
   * pattern mounts two instruments and only one may speak for the pair.
   */
  tag?: "leader" | "none";
  /**
   * Announced step sentence. Derived from the track when omitted, which is the
   * normal case: a sentence written by hand is a sentence that can drift from
   * the behaviour it describes.
   */
  stepHint?: string;
  /** Extra class on the tag strip. */
  tagClassName?: string;
}

/** Stacking band for the grip — above the sleeve, above the pick overlays. */
const GRIP_Z_RANGE: [number, number] = [39, 30];

/**
 * The sleeve sits BELOW the grip, so the 24 px round target still wins at the
 * apex and hover/focus semantics stay on the one element that has them.
 */
const SLEEVE_Z_RANGE: [number, number] = [29, 22];

/** The workspace camera's field of view — the fallback if one is ever ortho. */
const DEFAULT_FOV_DEG = 40;

/**
 * The hit band's minimum thickness, CSS pixels.
 *
 * The drawn shaft is a 3 mm rod that projects to about 5 px at the default
 * camera, and 5 px is not a target. 12 is the floor; the band takes the drawn
 * width whenever that is wider, so the target never claims more of the screen
 * than the instrument occupies. It is deliberately NOT the 24 px dense-target
 * floor: the sleeve is a SECOND route to a control that already meets it (the
 * grip is 24 x 24 at every size), and a 24 px band down the axis would swallow
 * more of the scene than the arrow covers.
 */
const SLEEVE_MIN_PX = 12;

/** Below this projected length the track has no readable direction to lay a band along. */
const SLEEVE_MIN_LENGTH_PX = 8;

/** How far the grip must travel on screen before the tag re-tests its side. */
const TAG_FLIP_HYSTERESIS_PX = 4;

/**
 * Relative change in the projected scale worth rebuilding the ladder for.
 *
 * Two per cent: fine enough that a zoom crosses a graduation threshold within a
 * frame or two of reaching it, coarse enough that float noise in a projection
 * never re-renders anything. An equality test here would rebuild the stop set,
 * the drawing and two vertex buffers on every frame of an orbit.
 */
const SCALE_EPSILON = 0.02;

function toVector3(v: Vec3): Vector3 {
  return new Vector3(v[0], v[1], v[2]);
}

/** The character that opens the tag's cell: a digit or a decimal point. */
const VALUE_CHARACTER = /^[0-9.]$/;

/**
 * How far the ladder dims while the snap is suppressed (Ctrl/Cmd).
 *
 * A modifier with no visible consequence is a modifier nobody trusts: the user
 * has to be able to see that the stops are off, or they will keep testing it.
 */
const LADDER_FREE_DIM = 0.4;

interface TypingState {
  /** 0 = the primary cell, 1 = the companion. */
  cell: 0 | 1;
  text: string;
}

/** What every grab carries, whichever mode it is in. */
interface Grab {
  /** The value the grab started from — what a mid-drag Escape reverts to. */
  value: number;
  /** The captured pointer, so a key event can release what it abandons. */
  pointerId: number;
  /** The element holding the capture: the grip or the sleeve, whichever was hit. */
  on: HTMLElement;
}

export function ParametricGauge({
  label,
  tagLabel,
  value,
  onChange,
  track,
  min,
  max,
  gaugeId,
  companion,
  tagUnit,
  tagSide = "up-right",
  tag = "leader",
  stepHint,
  tagClassName,
}: ParametricGaugeProps) {
  const invalidate = useThree((state) => state.invalidate);
  const camera = useThree((state) => state.camera);
  const canvas = useThree((state) => state.gl.domElement);
  const size = useThree((state) => state.size);

  /**
   * The grab, held for the length of the drag. Two modes, chosen ONCE at
   * pointer-down (the camera cannot move mid-drag, so the choice cannot go
   * stale):
   *
   *  · `track` — the pointer is projected onto the track. The real gesture: the
   *    arrowhead stays under the cursor because it IS the cursor's position on
   *    that line.
   *  · `screen` — the track points at the eye, so it has no readable direction
   *    on screen; travel drives the value at the grip's own scale. Reached by
   *    the most ordinary path in the product (save a sketch, press Extrude: the
   *    camera is normal to the plane), which is why the fallback is not
   *    optional.
   *
   * Both are RELATIVE to where the grab started, so the arrow never jumps to
   * the cursor on mousedown — the difference between a handle and a teleport.
   */
  const grabRef = useRef<
    | ({ mode: "track"; at: number } & Grab)
    | ({
        mode: "screen";
        x: number;
        y: number;
        unitsPerPixel: number;
      } & Grab)
    | null
  >(null);

  /**
   * THE OPTIMISTIC VALUE — what this gauge has ASKED for but not yet seen come
   * back, and the reason a fast pair of key presses does not lose one.
   *
   * The gauge never owns its value: it asks, the owner's form takes the number,
   * the ghost redraws and the new prop arrives several renders later. A SECOND
   * input landing inside that window would compute from the stale prop and
   * overwrite the first — two quick taps of Up giving 10.5 rather than 11,
   * intermittently, which is how it was found (the e2e passed alone and failed
   * under load: a lost update, not a flake). The first fix held ONE pending
   * value and dropped it on any change of the prop, which throws press two away
   * on the acknowledgement of press one; 13 of 20 fast `Up, Up, Shift+Up`
   * sequences came back wrong, 15.5 where 16 was asked for.
   *
   * THE RULES ARE NOT HERE ANY MORE, AND THAT IS THE POINT. They are five pure
   * transitions in `@loft/design`'s `gauge.ts`, checked by name on every unit
   * run, with the React wiring in {@link useAskQueue} checked in jsdom.
   *
   * `shown` is the newest outstanding ask when there is one, so the arrow, the
   * tag and `aria-valuenow` show what the user last asked for rather than a
   * value two commits stale.
   */
  const authoring = useCallback(() => grabRef.current !== null, []);
  const [shown, queue] = useAskQueue({
    value,
    // Bound rather than passed by reference: the hook parks it in a ref, and a
    // track that ever reads `this` should not care which.
    same: (a, b) => track.same(a, b),
    onChange,
    authoring,
  });
  const { readBase } = queue;
  const [grabbed, setGrabbed] = useState(false);

  /**
   * The ladder. Built only while the grip is held or focused — at rest the
   * gauge is an arrow and nothing more, which is the whole restraint argument.
   */
  const [ladderOn, setLadderOn] = useState(false);

  /**
   * Is the snap suppressed right now (Ctrl/Cmd)? Held in state ONLY so the
   * ladder can dim: a modifier with no visible consequence is a modifier nobody
   * trusts, and the snap itself reads the live event rather than this.
   *
   * Sampled from pointer events rather than from a `keydown`/`keyup` pair on
   * the window, deliberately: `useGlobalKeys` covers keydown only, a raw
   * listener is what `modalGate`'s audit exists to stop, and the dim is wanted
   * at the moment the pointer MOVES under the modifier — which is the first
   * thing that happens after you press it mid-drag.
   */
  const [free, setFree] = useState(false);

  /**
   * World units per screen pixel at the grip, for the shallow-track fallback
   * AND for choosing which graduations are far enough apart to draw.
   *
   * The orthographic branch is not optional and not symmetric with the
   * perspective one: under a PARALLEL projection the scale is a property of the
   * camera alone — distance cannot change it, that is the definition of one —
   * so the perspective formula (which is all distance) reports a drag rate that
   * is simply wrong once the ortho toggle is on. ORTHO-1 already paid for this;
   * it is derived here ONCE so no later gauge re-derives it.
   */
  const measureScale = useCallback(
    (at: number): number => {
      if (
        "isOrthographicCamera" in camera &&
        (camera as { isOrthographicCamera?: boolean }).isOrthographicCamera ===
          true
      ) {
        return orthographicUnitsPerPixel(
          (camera as unknown as { zoom: number }).zoom,
        );
      }
      const fov =
        "isPerspectiveCamera" in camera &&
        (camera as { isPerspectiveCamera?: boolean }).isPerspectiveCamera ===
          true
          ? (camera as unknown as { fov: number }).fov
          : DEFAULT_FOV_DEG;
      const rect = canvas.getBoundingClientRect();
      return perspectiveUnitsPerPixel(
        fov,
        camera.position.distanceTo(toVector3(track.pointAt(at))),
        rect.height,
      );
    },
    [camera, canvas, track],
  );

  /**
   * WORLD UNITS PER PIXEL ALONG THE TRACK — what decides which graduations are
   * far enough apart to draw, and therefore what the drag snaps to.
   *
   * Measured from the SHAFT'S OWN PROJECTION in the frame loop below, not from
   * `measureScale`. Two reasons, and the first is a defect this replaces.
   *
   * (a) It used to be sampled once, when the ladder was ARMED, and never again.
   * So "zoom in and the ladder subdivides" — the whole of the zoom-aware snap —
   * was unreachable in the running app: MEASURED over 40 wheel notches, the
   * shaft went from 3.86 to 28.48 px/mm and `data-snap` never moved off 5 mm.
   * A feature that cannot be reached is the decorative-chrome defect mandate 3c
   * names, and it was invisible because the ladder still LOOKED right.
   *
   * (b) `measureScale` reports the rate PERPENDICULAR to the view, which is the
   * right rate for a screen-travel drag and the wrong one for a ladder: the
   * question a graduation asks is whether its neighbours are 14 px away ALONG
   * THE TRACK, and a track at three-quarters to the eye is foreshortened. The
   * projection already answers that exactly, for free, with no
   * `getBoundingClientRect` in the frame loop.
   */
  const [scale, setScale] = useState(1);
  const armLadder = useCallback(() => {
    setLadderOn(true);
    setScale((prev) => {
      const sampled = measureScale(readBase());
      // Only if the frame loop has not measured yet — its along-track reading
      // is better, and clobbering it on every hover would make the ladder flick
      // between two pitches as the pointer arrives.
      return prev === 1 ? sampled : prev;
    });
  }, [measureScale, readBase]);
  const disarmLadder = useCallback(() => setLadderOn(grabbed), [grabbed]);

  const stops: GaugeStops = useMemo(
    () => (ladderOn ? track.stops(shown, scale) : NO_STOPS),
    [ladderOn, track, shown, scale],
  );
  /**
   * The ladder the DRAG obeys, read from a ref so a `pointermove` always sees
   * the stops currently on screen without the handler being rebuilt per frame.
   * The rungs ARE the stops (§3.1): a drag that snapped to something other than
   * what is drawn is the decorative-chrome defect in the signature element.
   */
  const stopsRef = useRef(stops);
  stopsRef.current = stops;

  const drawing = useMemo(
    () => track.draw(shown, stops),
    [track, shown, stops],
  );

  /** The arrowhead's point — where the grip and the tag ride. */
  const apex = useMemo(() => toVector3(drawing.head.tip), [drawing]);
  /** The seat — where the shaft starts, and the far end of the hit sleeve. */
  const seat = useMemo(() => toVector3(drawing.spine[0] as Vec3), [drawing]);

  const rungPositions = (rungs: readonly (readonly [Vec3, Vec3])[]) => {
    const out = new Float32Array(rungs.length * 6);
    for (let i = 0; i < rungs.length; i += 1) {
      const [from, to] = rungs[i] as readonly [Vec3, Vec3];
      out[i * 6] = from[0];
      out[i * 6 + 1] = from[1];
      out[i * 6 + 2] = from[2];
      out[i * 6 + 3] = to[0];
      out[i * 6 + 4] = to[1];
      out[i * 6 + 5] = to[2];
    }
    return out;
  };
  const majorPositions = useMemo(() => rungPositions(drawing.rungs), [drawing]);
  const minorPositions = useMemo(
    () => rungPositions(drawing.minorRungs),
    [drawing],
  );

  // The arrowhead: a cone whose BASE sits on the end of the spine and whose
  // point is the grip. Memoised on its own DIMENSIONS rather than on the
  // drawing, because the drawing changes on every pointermove and the cone
  // usually does not — it is sized from the seat, and bounded by the shaft only
  // so it can never outgrow the rod it terminates (§2.2).
  const headLength = drawing.head.length;
  const headRadius = drawing.head.radius;
  const spineRadius = drawing.spineRadius;
  const headGeometry = useMemo(
    () => new ConeGeometry(headRadius, headLength, 20, 1, true),
    [headRadius, headLength],
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
      grabbed || ladderOn
        ? viewport.manipulator.active
        : viewport.manipulator.axis,
    );
    invalidate();
  }, [grabbed, ladderOn, headMaterial, invalidate]);
  useEffect(() => () => headGeometry.dispose(), [headGeometry]);
  useEffect(() => () => headMaterial.dispose(), [headMaterial]);

  /**
   * The SPINE is a thin cylinder, not a `lineSegments`.
   *
   * WebGL line width is clamped to 1 px on every desktop driver we target, so a
   * GL line gives a hairline at any zoom — which reads as an annotation, the way
   * a dimension leader does, and this is not an annotation. Side by side against
   * Fusion's extrude arrow the hairline was the single thing that most said
   * "diagram" rather than "manipulator". A unit cylinder SCALED to the length
   * costs one geometry for the lifetime of the drag: the rebuild is a scale, not
   * an allocation, so the drag stays allocation-free.
   */
  const spineGeometry = useMemo(
    () => new CylinderGeometry(spineRadius, spineRadius, 1, 12, 1, true),
    [spineRadius],
  );
  useEffect(() => () => spineGeometry.dispose(), [spineGeometry]);

  /**
   * Where every mesh goes. {@link gaugePose} rather than a `useMemo` here,
   * because the defect it fixes — the shell drawing a CHORD across a polyline
   * spine, 29 % of the radius out at 90 degrees — was invisible to every gate
   * we own while it lived inside this component. It is arithmetic; it belongs
   * where arithmetic can be measured.
   */
  const pose = useMemo(() => gaugePose(drawing), [drawing]);

  useEffect(() => invalidate(), [shown, ladderOn, free, invalidate]);

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

  /** The pointer ray as the track's plain tuples. */
  const trackValueAt = useCallback(
    (clientX: number, clientY: number): number | null => {
      const ray = rayFor(clientX, clientY);
      return track.valueAt(
        [ray.origin.x, ray.origin.y, ray.origin.z],
        [ray.direction.x, ray.direction.y, ray.direction.z],
      );
    },
    [rayFor, track],
  );

  const ask = queue.ask;

  /**
   * {@link endDrag}, reachable from {@link onPointerMove}, which is declared
   * above it. A ref rather than a reorder: `endDrag` closes over `finishDrag`,
   * which closes over the queue, and hoisting that whole chain above the
   * pointer handlers to satisfy one call would put the drag's teardown a
   * screen away from the drag. The indirection is also correct rather than
   * merely convenient — the move handler wants whatever `endDrag` is NOW, not
   * the one that existed when it was memoised.
   */
  const endDragRef = useRef<() => void>(() => {});

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return;
      const target = event.currentTarget;
      // `base`, not the prop: a grab taken straight after a key press must
      // anchor on the value that press ASKED for, or the arrow jumps back a
      // step the instant the pointer moves.
      const from = readBase();
      const at = trackValueAt(event.clientX, event.clientY);
      // The CAPTURING element and the pointer id travel with the grab, so a
      // mid-drag Escape — which arrives as a key event with no pointer on it —
      // can still release the capture it is abandoning. Without that the
      // pointer stays captured by a node the cancel is about to unmount.
      //
      // `currentTarget` is the element the HANDLER is on, never the one the
      // pointer landed on, and both of this component's two routes into a grab
      // put that handler on a node with the gauge's own lifetime: the grip, and
      // the sleeve WRAPPER. That is load-bearing — see the sleeve's note. A
      // capture host that a redraw can unmount loses the gesture in silence.
      const held = { value: from, pointerId: event.pointerId, on: target };
      if (at !== null) {
        grabRef.current = { mode: "track", at, ...held };
      } else {
        grabRef.current = {
          mode: "screen",
          x: event.clientX,
          y: event.clientY,
          unitsPerPixel: measureScale(from),
          ...held,
        };
      }
      setGrabbed(true);
      setFree(event.ctrlKey || event.metaKey);
      armLadder();
      queue.hold();
      event.currentTarget.setPointerCapture(event.pointerId);
      event.stopPropagation();
      event.preventDefault();
    },
    [trackValueAt, measureScale, armLadder, readBase, queue],
  );

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const grab = grabRef.current;
      if (grab === null) return;
      // NO BUTTON, NO DRAG — the backstop for a release that never arrived.
      //
      // Capture is what guarantees the terminating `pointerup` comes back to
      // us, and capture can be taken away by things this component does not
      // control: a node it loses (the defect above), a browser-level cancel, a
      // context menu, an alt-tab that eats the button-up. When that happens
      // `grabRef` stays set and every later move is read as authoring, so the
      // value follows a pointer with nothing held down — the gauge appears
      // possessed, and the only way out is Escape, which DISCARDS.
      //
      // `buttons` is a bitmask of what is CURRENTLY held, reported on every
      // pointer event, so it is the one witness that cannot go stale: zero
      // means the gesture is over no matter how it ended. Ending it here (not
      // merely ignoring the move) releases the ask-queue's hold as well, so
      // the prop becomes the truth again exactly as a real release would leave
      // it. This is deliberately independent of the capture fix below — that
      // one makes the loss unlikely, this one makes the BAD STATE unreachable.
      //
      // PROVEN LIVE, because a guard nobody has seen fire is not a guard. It
      // was applied ALONE to the unfixed tree — capture still lost on the arc —
      // and the possessed-gauge symptom stopped: the bare mouse afterwards took
      // the sweep from 90 to 165 without it and left it at 90 with it, while
      // the two assertions about the capture loss itself stayed red. That is
      // the negative control, and it is why this stays even though the sleeve
      // below can no longer lose its host.
      if (event.buttons === 0) {
        endDragRef.current();
        return;
      }
      let raw: number;
      if (grab.mode === "track") {
        const at = trackValueAt(event.clientX, event.clientY);
        // The track went shallow mid-drag (it cannot: the camera is held). Keep
        // the last good value rather than invent one.
        if (at === null) return;
        raw = grab.value + (at - grab.at);
      } else {
        raw = track.screenValueAt(
          grab.value,
          event.clientX - grab.x,
          grab.y - event.clientY,
          grab.unitsPerPixel,
        );
      }
      const suppressed = event.ctrlKey || event.metaKey;
      setFree(suppressed);
      ask(track.quantize(raw, suppressed, stopsRef.current));
    },
    [ask, track, trackValueAt],
  );

  /** Let go: the prop is the truth again, `base` keeps where the drag ended. */
  const finishDrag = useCallback(() => {
    const grab = grabRef.current;
    if (grab === null) return null;
    grabRef.current = null;
    if (grab.on.hasPointerCapture(grab.pointerId)) {
      grab.on.releasePointerCapture(grab.pointerId);
    }
    setGrabbed(false);
    setFree(false);
    // The pointer is done authoring, so the prop is the truth from here — but
    // `base` keeps the value the drag ended on, so an arrow pressed straight
    // afterwards steps off WHAT YOU DRAGGED TO, not off a prop that has not
    // caught up yet. That is the case a free (Ctrl) drag makes load-bearing:
    // it ends on something like 12.4713, and the first press has to be able to
    // put it back on a grid.
    queue.release();
    return grab.value;
  }, [queue]);

  const endDrag = useCallback(() => {
    finishDrag();
  }, [finishDrag]);
  endDragRef.current = endDrag;

  const requestSubmit = useCommandActionStore((s) => s.requestSubmit);

  /** What a press is worth, in track units — announced, and asserted against. */
  const fineStep = track.step(stops);
  const coarseStep = track.coarseStep(stops);
  const stepHintId = useId();

  // --- THE PRECISION FALLBACK: the readout IS the input ----------------------

  const [typing, setTyping] = useState<TypingState | null>(null);
  /**
   * The same thing, readable SYNCHRONOUSLY.
   *
   * Two digits pressed in quick succession arrive as two separate events before
   * React has committed the first one's state, so a window listener gated on
   * `typing` fires TWICE and the second `openCell` replaces the first
   * character: MEASURED as `18` typed and `8` in the cell — the newest half of
   * the input winning and the oldest silently discarded. Exactly the lost
   * update the ask-queue exists for, one layer up, and it fails the same way:
   * intermittently, and only when somebody types at a normal speed.
   */
  const typingRef = useRef<TypingState | null>(null);
  const gripRef = useRef<HTMLDivElement | null>(null);
  const cellRefs = useRef<(HTMLInputElement | null)[]>([]);
  const cells = useMemo<GaugeCell[]>(
    () =>
      companion === undefined
        ? [{ tagLabel, value: shown, onChange: ask, track, min, max }]
        : [
            { tagLabel, value: shown, onChange: ask, track, min, max },
            companion,
          ],
    [companion, tagLabel, shown, ask, track, min, max],
  );

  /**
   * Open a cell with `seed` in it, or with the cell's own value when the caller
   * has nothing to seed (the `Tab` route). The NUMBER DOES NOT MOVE ON SCREEN:
   * `DimensionTagCell` renders readout and input at the same place in the same
   * face, so this reads as "the readout became typeable" rather than as a field
   * appearing, and that is the whole point of reusing the cell.
   */
  const openCell = useCallback(
    (cell: 0 | 1, seed: string | null) => {
      const target = cells[cell];
      if (target === undefined) return;
      focusPending.current = true;
      const next: TypingState = {
        cell,
        text: seed ?? target.track.format(target.value, { unitSuffix: false }),
      };
      typingRef.current = next;
      setTyping(next);
    },
    [cells],
  );

  const closeCell = useCallback((focusGrip: boolean) => {
    typingRef.current = null;
    setTyping(null);
    if (focusGrip) gripRef.current?.focus();
  }, []);

  /**
   * FOCUS THE CELL FROM ITS OWN REF CALLBACK, NOT FROM AN EFFECT HERE.
   *
   * MEASURED, and it is a trap worth knowing for anything imperative inside a
   * drei `Html`: **`Html` renders its children into a SEPARATE React root**
   * (`ReactDOM.createRoot(el)` in `@react-three/drei/web/Html.js`), so that
   * root's commit is not ordered against this component's effects. A
   * `useEffect` here that reads `cellRefs.current[cell]` therefore runs BEFORE
   * the input exists and reads `undefined` — which it did: the cell opened with
   * the right value, in the right place, and never took the caret, so the
   * second digit went to whatever had focus before. Nothing throws and the DOM
   * looks perfect.
   *
   * The ref callback runs in the CHILD root's own commit, which is by
   * definition the moment the node exists. The pending flag makes it fire once
   * per OPEN rather than on every re-render — a bare `node?.focus()` in a ref
   * would reset the caret to the end on every keystroke, which is the same
   * class of defect one layer down.
   */
  const focusPending = useRef(false);

  /**
   * CONTRACT α — the digit handoff is a WINDOW listener, and it goes through
   * `modalGate`, never through a raw `window.addEventListener`.
   *
   * The sketcher already promises "type a digit anywhere and it goes in the
   * first cell" from the instant a shape is placed (`drawDimensionKeys`), and
   * FLOW-A1 paid for making that true down to the 27 ms mark. The gauge
   * discarded digits until this item. Everything that is NOT a value character
   * falls through untouched — the gauge must not swallow the keyboard, or the
   * command band's advertised keys quietly stop working, which is the mistake
   * FLOW-A1 explicitly rejected.
   */
  useGlobalKeys(
    `gauge-digits:${gaugeId}`,
    tag === "none"
      ? null
      : (event: KeyboardEvent) => {
          if (event.altKey || event.ctrlKey || event.metaKey) return;
          if (!VALUE_CHARACTER.test(event.key)) return;
          event.preventDefault();
          // STOP IT HERE. `0`-`4` are the VIEW SHORTCUTS (front/top/right/iso
          // and fit) and `5` toggles the projection, registered by
          // `useViewHotkeys` as a raw window listener that predates the seam —
          // so it does not read `defaultPrevented` and would steer the camera
          // as well as take the digit. MEASURED before this line: a `2` pressed
          // on the focused grip arrived at window capture unprevented and left
          // window bubble prevented, and the view jumped to TOP.
          //
          // The live gauge wins, which is the cancel cascade's rule applied to
          // a different key: the innermost surface owns it. A number typed
          // while a dimension is on screen is that dimension — and the view
          // vocabulary is still one click away in the rail and on the cube,
          // whereas the depth would have nowhere else to be typed.
          event.stopPropagation();
          // APPEND rather than re-open when the cell is already up. Reaching
          // here with a cell open means the CARET HAS NOT ARRIVED YET: drei
          // `Html` commits its children in a separate React root, so between
          // the digit that opens the cell and the focus landing there is a
          // window of a frame or two in which the input exists and does not
          // have the keyboard. `useGlobalKeys` bails on a typing target, so
          // once focus IS in the cell this listener never runs and the input
          // handles its own characters.
          //
          // Both failure modes were MEASURED by typing `18` at normal speed:
          // gating on the STATE gave `8` (the second press re-opened the cell
          // and threw the first character away), and returning early gave `1`
          // (the second press went to the grip, which has no use for it, and
          // vanished). The sketcher's promise is "type a digit and it goes in
          // the cell"; half of a two-digit number is not that promise.
          const open = typingRef.current;
          if (open === null) openCell(0, event.key);
          else onCellInput(open.text + event.key, open.cell);
        },
    // CAPTURE, for the same reason `ProposalNote` uses it: this has to run
    // before a bubble listener that claims the same key. Plain
    // `stopPropagation`, never `stopImmediatePropagation` — the gate's own
    // shield and its leak alarm are registered on this target in this phase and
    // are diagnostics we want to keep hearing from.
    { capture: true },
  );

  /**
   * CONTRACT γ — `Escape` undoes the INNERMOST thing you are doing, and it is
   * taken here before the global editor cancel sees it.
   *
   * Registered on the cascade's `drag` rung rather than as another raw window
   * listener: `lib/modalGate.ts` already declares the order (drag > offer >
   * mark), runs exactly one rung per press, and its audit test fails by name if
   * a new global listener appears. A gesture in progress is the most transient
   * thing on screen and the one nothing else can plausibly have meant — and an
   * open tag cell is a gesture in progress in the same sense.
   *
   * The broken state if this is missing, which is what shipped before: the
   * editor unmounts while the pointer is still captured by a node that no
   * longer exists, the drag has no terminator, and the next `pointerup` goes
   * nowhere. It does not throw and it does not show in a screenshot.
   *
   * `whileTyping` because the cell case is BY DEFINITION typing, and because a
   * drag can be started from a row that left focus in a text field.
   */
  const revertInnermost = useCallback(() => {
    if (grabRef.current !== null) {
      const from = finishDrag();
      // Back to the value the grab STARTED from — Escape only ever discards,
      // and it discards exactly one level: the command stays open, and a second
      // press cancels it.
      if (from !== null) ask(track.clamp(from));
      return;
    }
    if (typing !== null) closeCell(true);
  }, [ask, closeCell, finishDrag, track, typing]);

  useCancelKey("drag", grabbed || typing !== null ? revertInnermost : null, {
    whileTyping: true,
  });

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      // The band promises "OK · ENTER" while a command is open, and after a
      // drag the focus is HERE — so Enter has to commit from here too, or the
      // one control that finally lets you set a value by hand is the one place
      // the advertised key does nothing (the flow rule's "no dead ends"). It
      // goes through the in-command action bus rather than a second submit: one
      // commit path, the editor's own, driven from a third place.
      if (event.key === "Enter") {
        event.preventDefault();
        requestSubmit();
        return;
      }
      // Tab is the KEYBOARD ROUTE TO PRECISION and it is one key. It used to go
      // to `view-home` — 800 px away in the view rail, mid-command, which is
      // the dead end FB-13 describes wearing a different hat.
      if (event.key === "Tab" && !event.shiftKey) {
        event.preventDefault();
        openCell(0, null);
        return;
      }
      const next = track.nudge(readBase(), event.key, event.shiftKey);
      if (next === null) return;
      event.preventDefault();
      event.stopPropagation();
      ask(next);
    },
    [ask, openCell, readBase, requestSubmit, track],
  );

  const onCellKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLInputElement>, cell: 0 | 1) => {
      // ONE MEANING, ALWAYS: Enter accepts what is in front of you and commits,
      // through the same single path the grip uses.
      if (event.key === "Enter") {
        event.preventDefault();
        typingRef.current = null;
        setTyping(null);
        requestSubmit();
        return;
      }
      if (event.key === "Tab") {
        const back = event.shiftKey;
        const next = back ? cell - 1 : cell + 1;
        if (next < 0) {
          event.preventDefault();
          closeCell(true);
          return;
        }
        if (next < cells.length) {
          event.preventDefault();
          openCell(next as 0 | 1, null);
          return;
        }
        // Past the last cell: let the browser have it, so the gauge is not a
        // focus trap.
        closeCell(false);
      }
    },
    [cells.length, closeCell, openCell, requestSubmit],
  );

  const onCellInput = useCallback(
    (text: string, cell: 0 | 1) => {
      const next: TypingState = { cell, text };
      typingRef.current = next;
      setTyping(next);
      const target = cells[cell];
      if (target === undefined) return;
      const parsed = Number.parseFloat(text);
      if (!Number.isFinite(parsed)) return;
      // A TYPED VALUE IS NEVER SNAPPED — that is the whole reason the fallback
      // exists. Clamped, because a value the owning form would refuse is the
      // dead end the flow rule's fourth test forbids.
      target.onChange(target.track.clamp(parsed));
    },
    [cells],
  );

  // --- THE HIT SLEEVE, AND THE TAG'S SIDE, WRITTEN FROM THE FRAME LOOP -------

  /**
   * ONE HIT BAND PER DRAWN SPINE SEGMENT. `[0]` is the band at the arrow's
   * point, and for a straight track it is the only one — see the frame loop.
   */
  const bandRefs = useRef<(HTMLDivElement | null)[]>([]);
  /** Scratch for the band projection: the frame loop allocates nothing. */
  const bandPoint = useRef(new Vector3());
  /** The projected sleeve vertices, `x, y` interleaved — scratch, reused. */
  const bandXY = useRef<number[]>([]);
  const projected = useRef({ a: new Vector3(), b: new Vector3() });
  const lastAnchor = useRef({ x: Number.NaN, y: Number.NaN });
  const [side, setSide] = useState<GaugeTagSide>(tagSide);
  useEffect(() => setSide(tagSide), [tagSide]);

  /** The tag strip's measured box — `placeGaugeTag` needs it to flip. */
  const stripRef = useRef<HTMLDivElement | null>(null);
  const [tagBox, setTagBox] = useState({ width: 96, height: 28 });
  useLayoutEffect(() => {
    const el = stripRef.current;
    if (el === null) return;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return;
    setTagBox((prev) =>
      Math.abs(prev.width - rect.width) < 0.5 &&
      Math.abs(prev.height - rect.height) < 0.5
        ? prev
        : { width: rect.width, height: rect.height },
    );
  });

  const placement = useMemo(() => placeGaugeTag(side, tagBox), [side, tagBox]);

  useFrame(() => {
    const { a, b } = projected.current;
    a.copy(seat).project(camera);
    b.copy(apex).project(camera);
    const ax = ((a.x + 1) / 2) * size.width;
    const ay = ((1 - a.y) / 2) * size.height;
    const bx = ((b.x + 1) / 2) * size.width;
    const by = ((1 - b.y) / 2) * size.height;

    const dx = ax - bx;
    const dy = ay - by;
    // Seat to TIP: the span of the hit sleeve and the anchor the tag rides on.
    // It is NOT the scale's denominator — see below.
    const length = Math.sqrt(dx * dx + dy * dy);

    // THE LADDER'S SCALE, re-read every frame the camera moves.
    //
    // BOTH ENDS DESCRIBE ONE SEGMENT. `spineLength` runs seat -> head BASE, so
    // the pixels it is divided by have to as well; dividing it by the seat ->
    // TIP projection above inflated the reading by `(value + head) / value`
    // — 1.180 at a 40 mm depth, 1.450 at 10 mm — and silently turned the
    // ladder's 14 px floor into 11.9 px, then 9.7 px as the feature shortened.
    // `projectedSpineLength` measures the same polyline, vertex for vertex.
    //
    // Guarded by a RELATIVE threshold rather than by equality: a projection
    // wanders in the last decimal from float noise alone, and a `setState` per
    // frame would rebuild the stop set, the drawing and two vertex buffers
    // every frame of an orbit.
    const trackPx = projectedSpineLength(
      drawing.spine,
      camera,
      size.width,
      size.height,
    );
    const world = spineLength(pose.segments);
    if (trackPx >= SLEEVE_MIN_LENGTH_PX && world > 0) {
      const perPixel = world / trackPx;
      if (Math.abs(perPixel - scale) > scale * SCALE_EPSILON)
        setScale(perPixel);
    }

    // THE SLEEVE FOLLOWS THE DRAWN POLYLINE, VERTEX FOR VERTEX.
    //
    // One band per projected spine segment, walked back from the arrow's point
    // to the seat. For a STRAIGHT track that is the single band this always
    // laid — a two-point spine is one segment, anchored at the apex, spanning
    // `length`, at `atan2(dy, dx)` — so extrude, fillet, shell and datum are
    // untouched. For an ARC it is the whole difference between a target on the
    // instrument and one across the space the sweep encloses: at radius 20 a
    // 90-degree chord departs from its own arc by 5.86 world units, 29 % of the
    // radius, and the chord band reached the drawn track at 1 of 16 sample
    // points — WORSE than the 2 of 16 CRAFT-7 was raised to fix. The drawing
    // became a polyline in CRAFT-7; the sleeve did not follow it until now.
    //
    // The walk starts at `head.tip` and then skips the LAST spine vertex,
    // because that vertex IS `head.base` — both track builders seat the cone on
    // the end of the spine — so the first band covers the arrowhead plus the
    // final segment in one straight run, which is how the head is drawn anyway.
    const bands = bandRefs.current;
    const vertices = drawing.spine.length;
    if (length < SLEEVE_MIN_LENGTH_PX || vertices < 2) {
      // The track points at the eye: there is no direction to lay a band
      // along, so there is no band. The grip is still a 24 px target and the
      // screen-travel fallback still drives the value — which is exactly the
      // case that fallback exists for.
      for (const band of bands) if (band !== null) band.style.display = "none";
    } else {
      // The drawn shaft's own width, projected: `spineRadius` world units
      // scale by the same factor the shaft's length does, so this needs no
      // second camera measurement and cannot disagree with the first. Both
      // terms are the SPINE's — pairing the shaft's world radius with a
      // seat-to-tip pixel span is the same unit mismatch as above, and it
      // made the band 18 % wider than the rod it is meant to trace.
      const drawn = (2 * spineRadius * trackPx) / Math.max(world, 1e-6);
      const thickness = Math.max(SLEEVE_MIN_PX, drawn);
      const xy = bandXY.current;
      for (let i = 0; i < vertices; i += 1) {
        const v = (
          i === 0 ? drawing.head.tip : drawing.spine[vertices - 1 - i]
        ) as Vec3;
        const q = bandPoint.current.set(v[0], v[1], v[2]).project(camera);
        xy[2 * i] = ((q.x + 1) / 2) * size.width;
        xy[2 * i + 1] = ((1 - q.y) / 2) * size.height;
      }
      for (let i = 0; i + 1 < vertices; i += 1) {
        const band = bands[i];
        if (band === null || band === undefined) continue;
        const px = xy[2 * i] as number;
        const py = xy[2 * i + 1] as number;
        const sx = (xy[2 * i + 2] as number) - px;
        const sy = (xy[2 * i + 3] as number) - py;
        const span = Math.sqrt(sx * sx + sy * sy);
        if (span < 1) {
          // A segment the camera has collapsed to a point. Its neighbours still
          // carry the track, so this is a sub-pixel gap, not a hole.
          band.style.display = "none";
          continue;
        }
        band.style.display = "block";
        band.style.width = `${span}px`;
        band.style.height = `${thickness}px`;
        band.style.transform =
          `translate(${px - bx}px, ${py - by}px) translateY(-50%) ` +
          `rotate(${Math.atan2(sy, sx)}rad)`;
      }
      // The spine re-tessellates as the sweep changes, so a shorter drawing can
      // leave bands from a longer one mounted. An element still holding last
      // frame's box would be a hit target where nothing is drawn.
      for (let i = vertices - 1; i < bands.length; i += 1) {
        const band = bands[i];
        if (band !== null && band !== undefined) band.style.display = "none";
      }
    }

    // The tag's SIDE, re-tested only when the grip has actually moved. The flip
    // rule itself lives in `placeGaugeTag`, so it is stated once for the gauge
    // and the proposal note both; what is here is only the decision of WHEN to
    // ask, which keeps the frame loop from allocating on a static camera.
    const moved =
      Math.abs(bx - lastAnchor.current.x) > TAG_FLIP_HYSTERESIS_PX ||
      Math.abs(by - lastAnchor.current.y) > TAG_FLIP_HYSTERESIS_PX;
    if (!moved) return;
    lastAnchor.current.x = bx;
    lastAnchor.current.y = by;
    const wanted = placeGaugeTag(tagSide, tagBox, {
      anchor: { x: bx, y: by },
      frame: { width: size.width, height: size.height },
    }).side;
    if (wanted !== side) setSide(wanted);
  });

  /**
   * One cell's props — READOUT or INPUT, decided by whether the caret is in it,
   * and `DimensionTagCell` renders the number in the same place either way. The
   * number not moving between the two states is what makes this read as "the
   * readout became typeable" rather than as a field appearing over the model.
   */
  const cellProps = (i: 0 | 1): DimensionTagCellProps => {
    const cell = cells[i] as GaugeCell;
    if (typing === null || typing.cell !== i) {
      return {
        label: cell.tagLabel,
        readout: cell.track.format(cell.value, { unitSuffix: false }),
      };
    }
    return {
      label: cell.tagLabel,
      value: typing.text,
      "aria-label": `${label} value`,
      ref: (node: HTMLInputElement | null) => {
        cellRefs.current[i] = node;
        if (node === null || !focusPending.current) return;
        focusPending.current = false;
        node.focus();
        // Caret AFTER what was typed, so the character that opened the cell is
        // the first one in it rather than the one you overtype.
        const end = node.value.length;
        node.setSelectionRange(end, end);
      },
      onChange: (event: ChangeEvent<HTMLInputElement>) => {
        onCellInput(event.target.value, i);
      },
      onKeyDown: (event: ReactKeyboardEvent<HTMLInputElement>) => {
        onCellKeyDown(event, i);
      },
      onBlur: () => closeCell(false),
    };
  };

  const hint =
    stepHint ??
    `Arrow keys step ${track.format(fineStep)}; Shift or Page keys step ${track.format(coarseStep)}. Enter saves.`;

  const dim = free ? LADDER_FREE_DIM : 1;
  const majorOpacity = viewport.manipulator.ladderMajorOpacity * dim;
  const minorOpacity = viewport.manipulator.ladderMinorOpacity * dim;

  return (
    <group name={`gauge-${gaugeId}`}>
      {pose.segments.map((segment, i) => (
        <mesh
          key={i}
          name={`gauge-${gaugeId}-spine`}
          geometry={spineGeometry}
          material={headMaterial}
          position={segment.centre}
          quaternion={segment.quaternion}
          scale={[1, Math.max(segment.length, 1e-3), 1]}
          renderOrder={13}
        />
      ))}
      {/* Two weights, two draws. A per-stroke weight would need a vertex
          attribute and a custom material; two `Segments` is one draw call each
          and says the drafting convention out loud. */}
      <Segments
        positions={majorPositions}
        color={viewport.manipulator.axis}
        opacity={majorOpacity}
        depthTest={false}
        renderOrder={12}
      />
      <Segments
        positions={minorPositions}
        color={viewport.manipulator.axis}
        opacity={minorOpacity}
        depthTest={false}
        renderOrder={12}
      />
      <mesh
        name={`gauge-${gaugeId}-head`}
        geometry={headGeometry}
        material={headMaterial}
        position={pose.headCentre}
        quaternion={pose.quaternion}
        renderOrder={13}
      />
      {/* THE HIT SLEEVE. Anchored at the apex — the same point as the grip —
          and laid back down the projected track ONE SEGMENT AT A TIME, so the
          band the pointer can take is exactly the arrow the eye can see, arc
          and all. It carries no name, no role and no tab stop: it is a second
          route to the grip, not a second control, and announcing it twice to a
          screen reader would be a lie about how many things are here — which is
          as true of twenty-four bands as it was of one. */}
      <Html
        position={apex}
        zIndexRange={SLEEVE_Z_RANGE}
        style={{ pointerEvents: "none" }}
      >
        {/* EVERY POINTER HANDLER IS THE WRAPPER'S, not each band's — hover for
            the reason below, and the DRAG because the band under your finger
            is not guaranteed to outlive your finger.

            Hover first, since it came first: React dispatches enter/leave along
            the ancestor path, so crossing a seam between two bands fires
            nothing here while arriving from outside and leaving the sleeve
            entirely each fire exactly once. Per-band handlers would disarm and
            re-arm the ladder at every seam, which on a 24-segment arc is a
            ladder that strobes as the pointer slides along it.

            THE DRAG, AND THE P0 THIS FIXES. The band list's LENGTH is a
            function of the value being dragged — an angular track tessellates
            `ceil(|value| / 360 * 96)` segments, so a sweep carries 32 bands at
            120 degrees and 24 at 90 — and the list is keyed by index, so
            shrinking the sweep UNMOUNTS the high-index bands at the seat end.
            `setPointerCapture` on the band you happened to grab therefore ends
            the moment the arc re-tessellates past it, and a REMOVED capture
            host does not merely stop capturing: MEASURED in Chromium, it emits
            no `lostpointercapture` at all, so there is not even an event to
            recover on. Everything after that is silent — moves that miss a
            12 px band do nothing, and the terminating `pointerup` reaches
            nobody, which leaves `grabRef` set, the ask-queue held, and the
            value tracking a pointer with no button down.
            Measured on the running app before this change: press the drawn arc
            near its seat on a 120-degree sweep, drag wide, and the value froze
            at 90 for the rest of the gesture, `data-grabbed` was still "true"
            after the release, and moving the bare mouse afterwards took it from
            90 to 165.

            The wrapper is the only node in this subtree whose lifetime is the
            GAUGE'S rather than the tessellation's, so capture taken on it
            cannot be revoked by a redraw. The bands stay exactly what they were
            — pure hit shapes, `pointer-events: auto`, one per drawn segment —
            so `elementFromPoint` reach along the arc is unchanged; only the
            LISTENER moved, from N transient nodes to one stable one. (It also
            costs four listeners instead of four per band, which on a full turn
            is 96 bands' worth.)

            Two alternatives were rejected. Capturing on `bandRefs.current[0]`
            works today only because `display: none` does NOT release capture in
            Blink (measured) — the frame loop hides band 0 whenever its segment
            collapses — and that is an implementation detail the Pointer Events
            spec does not promise; it also leaves the handlers on transient
            nodes, so the next hand re-opens the hole. Keeping the band count
            monotonic for the duration of a grab makes the RENDER a function of
            gesture state, an invariant invisible in this JSX, and deliberately
            keeps a hit target over a segment that is no longer drawn — the
            exact thing the frame loop's own tail-hiding guard exists to
            prevent.

            The wrapper is still not a target itself: `pointer-events` is
            inherited, the `Html` above turns it off, only the bands turn it
            back on, and its own box measures 0x0 because every child is
            absolutely positioned. Capture does not care — it bypasses hit
            testing, measured here on a `pointer-events: none` host. */}
        <div
          onPointerEnter={armLadder}
          onPointerLeave={disarmLadder}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
          {Array.from({ length: Math.max(1, drawing.spine.length - 1) }).map(
            (_, i) => (
              <div
                // The bands are positional by construction — band `i` is the
                // i-th segment back from the point — and the list only changes
                // length when the tessellation does.
                key={i}
                ref={(node) => {
                  bandRefs.current[i] = node;
                }}
                aria-hidden
                tabIndex={-1}
                data-gauge={gaugeId}
                /* `[0]` keeps the un-suffixed id: on a straight track it is the
                   ONLY band, and it is the one every existing gauge spec counts
                   and the one the grip's own segment always is. */
                data-testid={
                  i === 0 ? `${gaugeId}-sleeve` : `${gaugeId}-sleeve-${i}`
                }
                className={`pointer-events-auto absolute left-0 top-0 touch-none select-none ${
                  grabbed ? "cursor-grabbing" : "cursor-grab"
                }`}
                /* Inline, not a Tailwind utility: this theme's scales are
                   CLOSED and an unknown class emits no rule at all — a defect
                   this repo has already measured as a control with zero width.
                   The frame loop writes `transform` on this same node, so the
                   origin belongs beside it either way. `display: none` until
                   the first frame has measured the projection, so a zero-length
                   band is never briefly hittable. */
                /* No pointer handlers: a band is a HIT SHAPE, and the gesture
                   belongs to the wrapper above, whose lifetime a redraw cannot
                   end. Events still arrive there by bubbling, so this element
                   is exactly as grabbable as it was. */
                style={{ transformOrigin: "0 50%", display: "none" }}
              />
            ),
          )}
        </div>
      </Html>
      <Html position={apex} center zIndexRange={GRIP_Z_RANGE}>
        <AxisGrip
          ref={gripRef}
          aria-label={label}
          aria-describedby={stepHintId}
          data-testid={`${gaugeId}-handle`}
          data-gauge={gaugeId}
          data-value={shown}
          data-step={fineStep}
          data-coarse-step={coarseStep}
          /* WHAT A DRAG WILL SNAP TO, in track units — the drawn ladder's own
             pitch, or 0 when no ladder is legible at this camera and the track
             falls back to its configured snap. On the element because "the
             rungs ARE the stops" is otherwise a claim nothing can check: a
             ladder drawn at one grid while the pointer obeys another is exactly
             the defect CRAFT-7 exists to remove, and it is invisible in a
             screenshot. */
          data-snap={stops.pitch}
          value={shown}
          min={min}
          max={max}
          valueText={track.format(shown)}
          grabbed={grabbed}
          addressed={ladderOn}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onKeyDown={onKeyDown}
          onFocus={armLadder}
          onBlur={disarmLadder}
          onPointerEnter={armLadder}
          onPointerLeave={disarmLadder}
        />
        {/* ARIA has `aria-valuenow`/`min`/`max` and no way at all to say what a
            press is WORTH, so a slider whose step is only in the source is a
            slider a screen-reader user has to discover by trying it. The steps
            are named here instead — in the track's own unit, from the same
            numbers the key handler uses, so the sentence cannot drift from the
            behaviour — and the same two values are on the element as data
            attributes, which is what lets a test assert that the spoken step
            and the applied step are one thing. */}
        <span
          id={stepHintId}
          className="sr-only"
          data-testid={`${gaugeId}-steps`}
        >
          {hint}
        </span>
      </Html>
      {tag === "none" ? null : (
        /* `pointerEvents: none` on the WRAPPER, not just the tag: drei gives
           every `Html` its own positioned div, and this one is anchored at the
           same point as the grip. Without it the tag's box sits over the grip's
           24 px target and swallows the press — the drag then does nothing at
           all, which is exactly how the first browser run failed. The STRIP
           re-enables pointer events for itself, because it is now a control. */
        <Html
          position={apex}
          zIndexRange={GRIP_Z_RANGE}
          style={{ pointerEvents: "none" }}
        >
          {/* The number, where the eye already is, and TIED to the grip. The
              rail's field is 800 px away (T-4); a drag that makes you look over
              there to read what you just did is not direct manipulation, and a
              number floating unattached beside the arrow is a HUD chip that
              happens to be near some geometry. The leader makes the claim. */}
          <GaugeTag
            ref={stripRef}
            data-testid={`${gaugeId}-readout`}
            {...(tagUnit !== undefined ? { unit: tagUnit } : {})}
            className={`pointer-events-auto ${tagClassName ?? ""}`}
            placement={placement}
            cells={
              cells[1] === undefined
                ? [cellProps(0)]
                : [cellProps(0), cellProps(1)]
            }
          />
        </Html>
      )}
    </group>
  );
}
