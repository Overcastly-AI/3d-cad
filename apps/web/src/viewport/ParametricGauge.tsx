/**
 * THE PARAMETRIC GAUGE — one instrument, every verb (CRAFT-8).
 *
 * ## What it is
 *
 * While a feature editor is open, a brass gauge stands on the geometry the
 * feature is about: a shaft from the seat to the value, an arrowhead on the
 * end, a grip on the arrowhead's point, and the live number hanging beside it
 * in the drafting tag the sketcher already uses. Take the grip and the preview
 * follows the pointer; the rail's field is the exact path, and the two are ONE
 * value — the drag writes the field and the field moves the arrow, because they
 * are the same state read twice.
 *
 * THE SIGNATURE, and the one place boldness is spent: taking the grip extends a
 * GRADUATED LADDER along the track. A plain arrow says "you may pull this"; a
 * ruled one says what you are pulling against, which is what makes this read as
 * a machinist's depth gauge rather than a gizmo from any 3D app.
 *
 * ## Why this file exists rather than one component per verb
 *
 * Extracted from `ExtrudeDragHandle.tsx`, which was the only manipulator in the
 * product and was about to be copied six times. What is shared across every
 * verb is STATE AND CORRECTNESS — the optimistic ask-queue and its
 * reconciliation, the grab-mode choice, pointer capture, key stepping, the
 * grip, the tag. What differs is STATELESS ARITHMETIC — the drawn geometry, the
 * pointer projection, the stop set, the formatter, the clamp — and that lives
 * in a {@link GaugeTrack} from `@loft/design`, INJECTED here. The component
 * never branches on what kind of track it has.
 *
 * That split is the whole argument: the hard part is identical across the verbs
 * and the easy part is not. Three copies of a lost-update fix whose symptom is
 * *an occasional wrong number* is the worst thing this wave could ship.
 *
 * ## Why the grip is DOM and the instrument is WebGL
 *
 * The drawn parts must composite with the scene (they are `depthTest: false`,
 * an x-ray, for the same reason the ghost is: the interesting sweeps happen
 * INSIDE material). The grip must be focusable, nameable, and drivable by a
 * test — none of which a `<mesh>` can be. So the instrument draws in GL and the
 * target is a drei `Html` slider directly over its point, the same split the
 * measurement pick nodes make.
 *
 * **KNOWN AND DELIBERATELY LEFT TO CRAFT-7:** that split is currently also the
 * gauge's biggest defect. `document.elementFromPoint` down the projected track
 * resolves to the grip at **2 of 16** sample points — the 24 x 24 box at the
 * arrow's apex and nothing else — so the drawn shaft, cone and ladder are
 * inert, and the affordance and the hit target are anticorrelated. The fix is a
 * DOM hit sleeve along the projected track; it moves pixels and hit regions,
 * which is why it is not in the extraction that must move neither.
 *
 * ## Keyboard
 *
 * The grip is a real slider: arrows step one increment, Shift and the Page keys
 * take ten, each landing on ITS OWN grid rather than adding to whatever
 * fraction a drag left behind, and the value it announces is the same one the
 * field shows. Both steps are named on the element, so a screen-reader user
 * does not have to discover them by trying. Nothing here is reachable only by
 * pointer.
 *
 * Every colour is a `@loft/design` token; GPU resources are disposed on change
 * and unmount; the render loop allocates nothing (the geometry rebuilds only
 * when the instrument's own proportions change, and those are derived from the
 * seat, not from the value).
 */
import {
  AxisGrip,
  GaugeTag,
  NO_STOPS,
  orthographicUnitsPerPixel,
  perspectiveUnitsPerPixel,
  type GaugeStops,
  type GaugeTrack,
  type Vec3,
} from "@loft/design";
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
   * Test/query hook shared by the grip and (from CRAFT-7) the hit sleeve:
   * `data-gauge="<id>"` on both, and `<id>-handle` / `-readout` / `-steps`
   * test-ids. ONE id per instrument, so a probe can ask "did this click land
   * anywhere on the gauge" without knowing which part it hit.
   */
  gaugeId: string;
  /**
   * A second cell on the same tag — hole's depth + Ø. One strip, because two
   * tags twenty millimetres apart carrying different numbers is the "two
   * dialects drawn on screen" failure literally.
   *
   * The companion has its OWN track and its own grip is the owner's business;
   * what this carries is the second number on the strip.
   */
  companion?: Pick<GaugeCell, "tagLabel" | "value">;
  /** Unit written once at the end of the tag strip. Omit for an angle. */
  tagUnit?: string;
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
  /** Extra class on the tag strip — the caller's own placement, pre-leader. */
  tagClassName?: string;
}

/** Stacking band for the gauge's DOM parts — above the pick overlays, under the HUD. */
const GRIP_Z_RANGE: [number, number] = [39, 30];

/** +Y — the axis `ConeGeometry` and `CylinderGeometry` build along. */
const BUILD_AXIS = new Vector3(0, 1, 0);

/** The workspace camera's field of view — the fallback if one is ever ortho. */
const DEFAULT_FOV_DEG = 40;

function toVector3(v: Vec3): Vector3 {
  return new Vector3(v[0], v[1], v[2]);
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
  tag = "leader",
  stepHint,
  tagClassName,
}: ParametricGaugeProps) {
  const invalidate = useThree((state) => state.invalidate);
  const camera = useThree((state) => state.camera);
  const canvas = useThree((state) => state.gl.domElement);

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
    | { mode: "track"; at: number; value: number }
    | {
        mode: "screen";
        x: number;
        y: number;
        value: number;
        unitsPerPixel: number;
      }
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
   * run, with the React wiring in {@link useAskQueue} checked in jsdom. They
   * used to be four mutations of three refs in this file, standing on one
   * Playwright case that catches a queue-clearing mutant **2 runs in 12** —
   * green was the mutant's modal outcome, so the browser case is real evidence
   * and was never sufficient evidence. It stays; it is now the second opinion
   * rather than the only one.
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
   * The scale, SAMPLED rather than derived on every render. It is read at the
   * two moments it can change meaningfully — when the ladder is addressed, and
   * at pointer-down — because `measureScale` calls `getBoundingClientRect`, and
   * a forced layout on every `pointermove` is the kind of cost that does not
   * show up until somebody drags on a big assembly. The camera is held for the
   * length of a drag, so the sample cannot go stale inside one.
   */
  const [scale, setScale] = useState(1);
  const armLadder = useCallback(() => {
    setLadderOn(true);
    setScale(measureScale(readBase()));
  }, [measureScale, readBase]);
  const disarmLadder = useCallback(() => setLadderOn(grabbed), [grabbed]);

  const stops: GaugeStops = useMemo(
    () => (ladderOn ? track.stops(shown, scale) : NO_STOPS),
    [ladderOn, track, shown, scale],
  );

  const drawing = useMemo(
    () => track.draw(shown, stops),
    [track, shown, stops],
  );

  /** The arrowhead's point — where the grip and the tag ride. */
  const apex = useMemo(() => toVector3(drawing.head.tip), [drawing]);

  const ladderPositions = useMemo(() => {
    const out = new Float32Array(drawing.rungs.length * 6);
    for (let i = 0; i < drawing.rungs.length; i += 1) {
      const [from, to] = drawing.rungs[i] as readonly [Vec3, Vec3];
      out[i * 6] = from[0];
      out[i * 6 + 1] = from[1];
      out[i * 6 + 2] = from[2];
      out[i * 6 + 3] = to[0];
      out[i * 6 + 4] = to[1];
      out[i * 6 + 5] = to[2];
    }
    return out;
  }, [drawing]);

  // The arrowhead: a cone whose BASE sits on the end of the spine and whose
  // point is the grip. Memoised on its own DIMENSIONS rather than on the
  // drawing, because the drawing changes on every pointermove and the cone does
  // not — its size comes from the seat, never from the value, so it holds still
  // while you drag (a manipulator that grows under the cursor reads as the
  // model moving) and the drag stays allocation-free.
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
      grabbed ? viewport.manipulator.active : viewport.manipulator.axis,
    );
    invalidate();
  }, [grabbed, headMaterial, invalidate]);
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

  const pose = useMemo(() => {
    const from = toVector3(drawing.spine[0] as Vec3);
    const to = toVector3(drawing.spine[drawing.spine.length - 1] as Vec3);
    const headBase = toVector3(drawing.head.base);
    const headDir = apex.clone().sub(headBase).normalize();
    const quaternion = new Quaternion().setFromUnitVectors(BUILD_AXIS, headDir);
    // ConeGeometry is centred on its own axis, so the base lands on the end of
    // the spine when the centre sits half a length along.
    const headCentre = headBase
      .clone()
      .addScaledVector(headDir, headLength / 2);
    const spineLength = to.distanceTo(from);
    const spineDir =
      spineLength > 0
        ? to.clone().sub(from).divideScalar(spineLength)
        : headDir;
    return {
      quaternion,
      headCentre,
      spineCentre: from.clone().addScaledVector(spineDir, spineLength / 2),
      spineQuaternion: new Quaternion().setFromUnitVectors(
        BUILD_AXIS,
        spineDir,
      ),
      spineLength,
    };
  }, [drawing, apex, headLength]);

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

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return;
      // `base`, not the prop: a grab taken straight after a key press must
      // anchor on the value that press ASKED for, or the arrow jumps back a
      // step the instant the pointer moves.
      const from = readBase();
      const at = trackValueAt(event.clientX, event.clientY);
      if (at !== null) {
        grabRef.current = { mode: "track", at, value: from };
      } else {
        grabRef.current = {
          mode: "screen",
          x: event.clientX,
          y: event.clientY,
          value: from,
          unitsPerPixel: measureScale(from),
        };
      }
      setGrabbed(true);
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
      const free = event.ctrlKey || event.metaKey;
      ask(track.quantize(raw, free));
    },
    [ask, track, trackValueAt],
  );

  const endDrag = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (grabRef.current === null) return;
      grabRef.current = null;
      setGrabbed(false);
      // The pointer is done authoring, so the prop is the truth from here — but
      // `base` keeps the value the drag ended on, so an arrow pressed straight
      // afterwards steps off WHAT YOU DRAGGED TO, not off a prop that has not
      // caught up yet. That is the case a free (Ctrl) drag makes load-bearing:
      // it ends on something like 12.4713, and the first press has to be able to
      // put it back on a grid.
      queue.release();
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    },
    [queue],
  );

  const requestSubmit = useCommandActionStore((s) => s.requestSubmit);

  /** What a press is worth, in track units — announced, and asserted against. */
  const fineStep = track.step(stops);
  const coarseStep = track.coarseStep(stops);
  const stepHintId = useId();

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      // The band promises "OK · ENTER" while a command is open, and after a
      // drag the focus is HERE — so Enter has to commit from here too, or the
      // one control that finally lets you set a value by hand is the one place
      // the advertised key does nothing (the flow rule's "no dead ends", and
      // the same defect FINDINGS #11 fixed for Escape). It goes through the
      // in-command action bus rather than a second submit: one commit path, the
      // editor's own, driven from a third place.
      if (event.key === "Enter") {
        event.preventDefault();
        requestSubmit();
        return;
      }
      const next = track.nudge(readBase(), event.key, event.shiftKey);
      if (next === null) return;
      event.preventDefault();
      event.stopPropagation();
      ask(next);
    },
    [ask, readBase, requestSubmit, track],
  );

  const hint =
    stepHint ??
    `Arrow keys step ${track.format(fineStep)}; Shift or Page keys step ${track.format(coarseStep)}. Enter saves.`;

  return (
    <group name={`gauge-${gaugeId}`}>
      <mesh
        geometry={spineGeometry}
        material={headMaterial}
        position={pose.spineCentre}
        quaternion={pose.spineQuaternion}
        scale={[1, Math.max(pose.spineLength, 1e-3), 1]}
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
        position={pose.headCentre}
        quaternion={pose.quaternion}
        renderOrder={13}
      />
      <Html position={apex} center zIndexRange={GRIP_Z_RANGE}>
        <AxisGrip
          aria-label={label}
          aria-describedby={stepHintId}
          data-testid={`${gaugeId}-handle`}
          data-gauge={gaugeId}
          data-value={shown}
          data-step={fineStep}
          data-coarse-step={coarseStep}
          value={shown}
          min={min}
          max={max}
          valueText={track.format(shown)}
          grabbed={grabbed}
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
           all, which is exactly how the first browser run failed. */
        <Html
          position={apex}
          zIndexRange={GRIP_Z_RANGE}
          style={{ pointerEvents: "none" }}
        >
          {/* The number, where the eye already is. The rail's field is 800 px
              away (T-4); a drag that makes you look over there to read what you
              just did is not direct manipulation. Read-only while the pointer
              owns this value, which is the distinction `DimensionTagCell`
              already carries. */}
          <GaugeTag
            data-testid={`${gaugeId}-readout`}
            {...(tagUnit !== undefined ? { unit: tagUnit } : {})}
            className={tagClassName ?? ""}
            cells={
              companion === undefined
                ? [
                    {
                      label: tagLabel,
                      readout: track.format(shown, { unitSuffix: false }),
                    },
                  ]
                : [
                    {
                      label: tagLabel,
                      readout: track.format(shown, { unitSuffix: false }),
                    },
                    {
                      label: companion.tagLabel,
                      readout: track.format(companion.value, {
                        unitSuffix: false,
                      }),
                    },
                  ]
            }
          />
        </Html>
      )}
    </group>
  );
}
