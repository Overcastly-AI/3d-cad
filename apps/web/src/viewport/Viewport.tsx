import { font, viewport } from "@loft/design/tokens";
import { GizmoHelper, GizmoViewcube, OrbitControls } from "@react-three/drei";
import {
  Canvas,
  useFrame,
  useThree,
  type ThreeEvent,
} from "@react-three/fiber";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import {
  MOUSE,
  PerspectiveCamera,
  TOUCH,
  Vector3,
  type BufferGeometry,
} from "three";
import type { Box3 } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";

import { useReducedMotion } from "../lib/useReducedMotion";
import { navigationControls, usePreferences } from "../settings/preferences";
import { NavCue } from "../components/NavCue";
import { ViewBar } from "../components/ViewBar";
import { VisibilityStamp } from "../components/VisibilityStamp";
import { AdaptiveGrid } from "./AdaptiveGrid";
import { isDragGesture, type PointerPoint } from "./contextMenuGesture";
import {
  fitDistance,
  measureChrome,
  targetShift,
  unobstructedRect,
  VIEWPORT_CHROME_EVENT,
  type CameraSpacePoint,
  type Rect,
} from "./fitFraming";
import { groundShadowTexture } from "./groundShadow";
import { ModelMesh, type BodyHighlight } from "./ModelMesh";
import { OriginGeometry } from "./OriginGeometry";
import {
  hiddenBodyCount,
  isolatedBodyLabel,
  usePartViewHotkeys,
  usePartViewStore,
} from "./partView";
import {
  safeUp,
  upFor,
  useViewCommandStore,
  useViewHotkeys,
  VIEW_DIRECTIONS,
} from "./viewCommands";

/** The studio iso direction — every "home" has always opened here. */
const ISO_DIR = new Vector3(...VIEW_DIRECTIONS.iso).normalize();
/** Fit margin: orbit radius = bounds diagonal × this (the historic framing). */
const FIT_FACTOR = 1.75;
/** Default orbit radius when the scene is empty (the resting bench view). */
const EMPTY_RADIUS = 200 * FIT_FACTOR;

/**
 * The reference cube's inset from the bottom-right corner (px), and the
 * footprint the fit must keep clear.
 *
 * Was 64, and the founder's 2026-07-31 capture caught the consequence: at an
 * isometric attitude the cube's projected silhouette is its face size times ~√3
 * across the diagonal, so a 64px inset put the lower corner and the FRONT/RIGHT
 * labels hard against the frame edge. The inset now clears the diagonal, which
 * also puts the cube on the same 12px gutter the ViewBar and the floating
 * panels sit on.
 */
const CUBE_MARGIN_PX = 96;
/** Square the cube occupies, centred on the margin point — the fit avoids it. */
const CUBE_FOOTPRINT_PX = 120;

interface CameraGoal {
  position: Vector3;
  up: Vector3;
  target: Vector3;
  /** Named view stamped on the container once the move settles (QA hook). */
  view: string;
}

/**
 * The subject's eight bounding corners resolved onto the camera's own axes —
 * the silhouette a fit has to make room for, DEPTH INCLUDED (a corner nearer
 * the camera projects wider, which is what `fitDistance` solves for). Empty for
 * an empty/absent box.
 */
function boxCornersInCameraAxes(
  box: Box3 | null,
  center: Vector3,
  right: Vector3,
  up: Vector3,
  dir: Vector3,
): CameraSpacePoint[] {
  if (box === null || box.isEmpty()) return [];
  const corner = new Vector3();
  const corners: CameraSpacePoint[] = [];
  for (let i = 0; i < 8; i += 1) {
    corner
      .set(
        i & 1 ? box.max.x : box.min.x,
        i & 2 ? box.max.y : box.min.y,
        i & 4 ? box.max.z : box.min.z,
      )
      .sub(center);
    corners.push({
      a: corner.dot(right),
      b: corner.dot(up),
      c: corner.dot(dir),
    });
  }
  return corners;
}

/**
 * The camera rig: auto-fits when the fit key changes (a new body / a newly
 * loaded assembly instance — the assembly fit no longer races the GLB load),
 * and executes view commands (home/fit/snaps, reference-cube picks) with a
 * reduced-motion-aware ease. One rig owns the camera for both workspaces.
 */
function CameraRig({
  bounds,
  fitKey,
  reducedMotion,
  framing,
  owns,
  onSettle,
}: {
  bounds: Box3 | null;
  fitKey: string;
  reducedMotion: boolean;
  /** The live canvas + unobstructed rect, measured from the DOM at fit time. */
  framing: () => { canvas: Rect; free: Rect } | null;
  /**
   * Does THIS rig own the camera right now? False while the SKETCHER owns it —
   * `SketchScene.SketchCameraRig` parks the view normal-on to the plane (and at
   * a fixed iso for the plane pick), easing the same camera object every frame.
   *
   * Two rigs easing one camera toward different poses do not average out, they
   * DEADLOCK: neither ever gets within its settle epsilon, so both keep writing
   * forever. Measured while landing FB-7 (rails announcing a chrome change when
   * the inspector leaves on entering the sketcher): the part rig wanted radius
   * 70, the sketch rig 230, and the camera oscillated around 180 indefinitely —
   * which also jitters every DOM overlay anchored to the scene, so a face-pick
   * target never becomes click-stable and the flow simply stops.
   */
  owns: boolean;
  onSettle: (view: string, position: Vector3, framed: Rect | null) => void;
}) {
  const camera = useThree((state) => state.camera);
  const controls = useThree(
    (state) => state.controls,
  ) as OrbitControlsImpl | null;
  const invalidate = useThree((state) => state.invalidate);
  const command = useViewCommandStore((state) => state.command);

  const boundsRef = useRef<Box3 | null>(bounds);
  boundsRef.current = bounds;
  const goal = useRef<CameraGoal | null>(null);
  const framedRect = useRef<Rect | null>(null);
  /** Has the modeler moved the camera by hand since the last fit? */
  const userMoved = useRef(false);

  /** Clip planes sized to the framed subject. */
  const setClipPlanes = useCallback(
    (diagonal: number) => {
      if (camera instanceof PerspectiveCamera) {
        camera.near = Math.max(diagonal / 100, 0.01);
        camera.far = Math.max(diagonal * 50, 5000);
        camera.updateProjectionMatrix();
      }
    },
    [camera],
  );

  const applyPose = useCallback(
    (pose: CameraGoal, instant: boolean) => {
      if (instant) {
        camera.position.copy(pose.position);
        camera.up.copy(pose.up);
        if (controls) {
          controls.target.copy(pose.target);
          controls.update();
        } else {
          camera.lookAt(pose.target);
        }
        goal.current = null;
        onSettle(pose.view, camera.position, framedRect.current);
      } else {
        goal.current = pose;
      }
      invalidate();
    },
    [camera, controls, invalidate, onSettle],
  );

  /**
   * Frame `center`/`diagonal` into the UNOBSTRUCTED rect rather than the whole
   * canvas (founder capture 2026-07-31 — "Fit model frames the CANVAS, not the
   * VISIBLE viewport"). Two corrections, both derived from the live DOM so a
   * collapsed panel gives its space straight back:
   *
   *  · solve the DISTANCE from the subject's projected extents against the free
   *    rect, not from a fixed multiple of its bounding diagonal. The old rule
   *    was blind twice over — to the frame it was filling AND to the subject's
   *    aspect ratio — so a compact part floated in a sea of bench while a wide
   *    one ran off the sides; and
   *  · slide the orbit TARGET so the subject sits in the middle of that rect
   *    instead of the middle of the canvas — otherwise a symmetric zoom-out
   *    just adds equal air on the side you can see and the side you cannot.
   *
   * Returns the pose. Records the rect it framed into as a QA hook.
   */
  const framePose = useCallback(
    (
      dir: Vector3,
      up: Vector3,
      center: Vector3,
      radius: number,
      view: string,
      box: Box3 | null,
    ): CameraGoal => {
      const measured = framing();
      framedRect.current = measured?.free ?? null;
      if (measured === null || !(camera instanceof PerspectiveCamera)) {
        return {
          position: dir.clone().multiplyScalar(radius).add(center),
          up,
          target: center.clone(),
          view,
        };
      }
      const { canvas, free } = measured;
      // Camera basis at the goal attitude: forward is −dir (dir points from the
      // target TO the camera), so right = up × dir and trueUp = dir × right.
      const right = new Vector3().crossVectors(up, dir).normalize();
      const trueUp = new Vector3().crossVectors(dir, right).normalize();
      // Solve the distance from the subject's ACTUAL projected extents rather
      // than a fixed multiple of its diagonal — so the part fills the frame it
      // was given whatever its aspect ratio (see `fitFraming.fitDistance`). The
      // diagonal rule stays as the fallback for a scene with no box.
      const corners = boxCornersInCameraAxes(box, center, right, trueUp, dir);
      const solved = fitDistance(corners, canvas, free, camera.fov);
      const distance = solved > 0 ? solved : radius;
      const visibleHeight =
        2 * distance * Math.tan((camera.fov * Math.PI) / 360);
      const shift = targetShift(canvas, free, {
        width: visibleHeight * (canvas.width / Math.max(canvas.height, 1)),
        height: visibleHeight,
      });
      const target = center
        .clone()
        .add(right.clone().multiplyScalar(shift.right))
        .add(trueUp.clone().multiplyScalar(shift.up));
      return {
        position: dir.clone().multiplyScalar(distance).add(target),
        up,
        target,
        view,
      };
    },
    [camera, framing],
  );

  /**
   * DOES THIS SCENE HAVE A VIEWPOINT WORTH KEEPING?
   *
   * NOT "has the auto-fit run" — that reading is what FB-20 was. Every path
   * that POSES the camera must set this: the view commands (snaps, fit,
   * reference-cube picks), the auto-fit, and the moment the sketcher takes the
   * camera, because it hands back a pose the user chose by choosing the plane.
   * If you add another way to move the camera, set it there too.
   *
   * Why the distinction is the whole bug: it used to be set in exactly ONE
   * place, inside the auto-fit. So a user who had pinned iso on the view rail,
   * then drawn a sketch and extruded it, was still `first` when their geometry
   * appeared — and the first extrude of every session snapped the view away.
   * The founder reported it as "I draw in a plane and then all of a sudden it
   * switches after an extrude" (2026-08-14), and the FB-1 gate could not see
   * it: its fixture builds a box before it starts measuring, so it had only
   * ever watched the SECOND extrude.
   */
  const framedOnce = useRef(false);

  // Auto-fit whenever the subject changes (a fresh geometry, or an assembly
  // instance's mesh landing).
  //
  // RE-FRAME, DO NOT RE-ORIENT. This used to slam the camera back to ISO_DIR
  // with up=+Y on every run, and `fitKey` includes the geometry's identity — so
  // every extrude built a new mesh and took the user's viewpoint away. The
  // founder hit it twice in one session: "after the extrude it flipped to xy",
  // and, fatally, while trying to sketch on an extruded face — "it was snapping
  // back and I couldn't see it". Sketching on a face means looking AT that face;
  // a fit that reimposes iso the moment the body changes makes the workflow
  // impossible, not merely disorienting. Fusion and Plasticity never take the
  // viewpoint away when a feature completes.
  //
  // So: fit the DISTANCE and target to the new bounds always — that is the part
  // people want, and it is why this effect exists — but keep the direction and
  // up the user is currently looking from once they have one. `userMoved` is
  // likewise only cleared on the first fit; clearing it afterwards discarded the
  // fact that the user had deliberately positioned the view.
  useEffect(() => {
    const box = boundsRef.current;
    if (box === null || box.isEmpty()) return;
    const center = box.getCenter(new Vector3());
    const diagonal = box.getSize(new Vector3()).length();
    setClipPlanes(diagonal);

    const first = !framedOnce.current;
    framedOnce.current = true;
    if (first) userMoved.current = false;

    // Direction points from the target TO the camera, matching framePose's
    // convention. The iso fallback is for a scene NOBODY has posed yet (an
    // empty part opening for the first time) and for a degenerate pose (camera
    // sitting exactly on its target), which would otherwise normalise to a zero
    // vector. It is not the "first geometry" case: see `framedOnce`.
    let dir = ISO_DIR.clone();
    let up = new Vector3(0, 1, 0);
    if (!first) {
      const currentTarget = controls?.target.clone() ?? center.clone();
      const offset = camera.position.clone().sub(currentTarget);
      if (offset.lengthSq() > 1e-12) {
        dir = offset.normalize();
        up = safeUp(dir, camera.up.clone());
      }
    }

    applyPose(
      framePose(
        dir,
        up,
        center,
        Math.max(diagonal, 1) * FIT_FACTOR,
        "fit-auto",
        box,
      ),
      true,
    );
    // The fit key IS the refit trigger; bounds/camera are read at fit time.
  }, [fitKey]);

  // Execute view commands (nonce-keyed so a repeated snap re-fires).
  const executed = useRef(0);
  useEffect(() => {
    if (command === null || command.nonce === executed.current) return;
    executed.current = command.nonce;
    // Every branch below poses the camera deliberately — a snap, a fit, or a
    // reference-cube pick — so from here on this scene HAS a viewpoint. One
    // assignment rather than three: a branch added later inherits it.
    framedOnce.current = true;
    const box = boundsRef.current;
    const hasBounds = box !== null && !box.isEmpty();
    const center = hasBounds
      ? box.getCenter(new Vector3())
      : (controls?.target.clone() ?? new Vector3());
    const diagonal = hasBounds ? box.getSize(new Vector3()).length() : 0;
    const fitRadius = hasBounds ? diagonal * FIT_FACTOR : EMPTY_RADIUS;
    const currentTarget = controls?.target.clone() ?? center.clone();
    const currentRadius = Math.max(
      camera.position.distanceTo(currentTarget),
      1,
    );

    let pose: CameraGoal;
    if (command.kind === "direction") {
      // Reference-cube pick: rotate about the CURRENT target, keep the zoom.
      const dir = new Vector3(...command.dir).normalize();
      pose = {
        position: dir.multiplyScalar(currentRadius).add(currentTarget),
        up: upFor(dir),
        target: currentTarget,
        view: "direction",
      };
    } else if (command.kind === "fit") {
      // Keep the view direction, frame the subject.
      const dir = camera.position.clone().sub(currentTarget).normalize();
      userMoved.current = false;
      pose = framePose(
        dir,
        safeUp(dir, camera.up.clone()),
        center,
        fitRadius,
        "fit",
        box,
      );
    } else {
      const named = command.kind === "home" ? "iso" : command.kind;
      const dir = new Vector3(...VIEW_DIRECTIONS[named]).normalize();
      userMoved.current = false;
      pose = framePose(dir, upFor(dir), center, fitRadius, command.kind, box);
    }
    if (hasBounds) setClipPlanes(diagonal);
    applyPose(pose, reducedMotion);
  }, [
    command,
    camera,
    controls,
    reducedMotion,
    setClipPlanes,
    applyPose,
    framePose,
  ]);

  /**
   * RELEASE THE CAMERA when another rig takes over. An ease in flight is state:
   * `goal.current` keeps this rig writing the camera every frame until it lands
   * within its settle epsilon, and if the sketcher takes the view in that
   * window, it never does — the two rigs pull the same camera to two different
   * radii and it oscillates between them forever, which is not just wrong but
   * UNCLICKABLE (every scene-anchored DOM overlay jitters, so Playwright — and
   * a hand on a trackpad — can never land on a face-pick target).
   *
   * Measured while landing FB-7: part rig wanting radius 70, sketch rig 230,
   * camera parked at ~120 and moving on every frame indefinitely.
   *
   * Handing the camera over also COUNTS AS A POSE. The sketcher parks it
   * normal-on to the plane the user picked, so whatever comes back is a
   * viewpoint they chose — by choosing that plane. Without this the first
   * extrude of a session would only keep the view if some chrome change
   * happened to fire a fit on the way out; with it the invariant holds even
   * when no panel moves.
   */
  useEffect(() => {
    if (owns) return;
    goal.current = null;
    framedOnce.current = true;
  }, [owns]);

  /**
   * Give the space back. A collapsed panel un-covers a third of the frame, and
   * a fit that was correct for the old free rect is now off-centre in the new
   * one — so the chrome announces its own change and the rig re-frames.
   *
   * Only while the modeler has NOT taken the camera by hand since the last fit:
   * yanking someone off a detail they zoomed into because they collapsed a
   * panel would be a worse defect than the one being fixed.
   */
  useEffect(() => {
    const onControlStart = () => {
      userMoved.current = true;
    };
    controls?.addEventListener("start", onControlStart);
    const onChromeChange = () => {
      // Not while another rig owns the camera, and not after the modeler has
      // taken it by hand — the two ways a refit here would be a THEFT rather
      // than a courtesy.
      if (!owns || userMoved.current) return;
      useViewCommandStore.getState().request("fit");
    };
    window.addEventListener(VIEWPORT_CHROME_EVENT, onChromeChange);
    return () => {
      controls?.removeEventListener("start", onControlStart);
      window.removeEventListener(VIEWPORT_CHROME_EVENT, onChromeChange);
    };
  }, [controls, owns]);

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
      onSettle(g.view, camera.position, framedRect.current);
    }
    invalidate();
  });

  return null;
}

/** What the render probe publishes to the page (QA hook — see RenderProbe). */
interface RenderProbeWindow extends Window {
  /** Monotonic count of r3f RENDERS since load. */
  __loftRenderTick?: number;
  /** WebGL context loss/restore, in order, with `performance.now()` stamps. */
  __loftGlEvents?: { kind: "lost" | "restored"; at: number }[];
}

/**
 * THE RENDER CLOCK — the one number the browser does not already expose, and
 * the reason CI-4 could not be diagnosed.
 *
 * The canvas is `frameloop="demand"`, so `requestAnimationFrame` counts BROWSER
 * frames, not renders: the page can tick 30 rAFs while this scene has not
 * re-rendered once. Every e2e pixel census waited on rAFs and then read the
 * drawing buffer, which `preserveDrawingBuffer` happily serves from the LAST
 * render — a perfectly valid STALE frame. That is the exact shape of the CI red
 * on `c6b6c6d` (sketch ink = 0 with the frame correctly fitted), and no
 * evidence in the run could distinguish it from a rendering regression.
 *
 * `useFrame` runs inside the demand loop, so incrementing here counts renders
 * and nothing else. Default priority deliberately: a positive priority takes
 * over rendering from r3f. One integer write per rendered frame, no allocation.
 *
 * The context listeners are not only instrumentation. three's own handler
 * preventDefaults the loss (so the browser restores) and reinitialises on
 * restore — but under `demand` nothing invalidates afterwards, so a restored
 * context would sit on an empty canvas until the user happened to orbit.
 * `invalidate()` repaints it. Loss was entirely silent before this: nothing in
 * `apps/web/src` listened, so "the viewport went blank" had no signal at all,
 * in CI or in front of a user.
 */
function RenderProbe(): null {
  const gl = useThree((state) => state.gl);
  const invalidate = useThree((state) => state.invalidate);
  useFrame(() => {
    const w = window as RenderProbeWindow;
    w.__loftRenderTick = (w.__loftRenderTick ?? 0) + 1;
  });
  useEffect(() => {
    const w = window as RenderProbeWindow;
    const events = (w.__loftGlEvents ??= []);
    const canvas = gl.domElement;
    const onLost = (): void => {
      events.push({ kind: "lost", at: performance.now() });
    };
    const onRestored = (): void => {
      events.push({ kind: "restored", at: performance.now() });
      invalidate();
    };
    canvas.addEventListener("webglcontextlost", onLost);
    canvas.addEventListener("webglcontextrestored", onRestored);
    return () => {
      canvas.removeEventListener("webglcontextlost", onLost);
      canvas.removeEventListener("webglcontextrestored", onRestored);
    };
  }, [gl, invalidate]);
  return null;
}

/**
 * The reference cube — view navigation that lives IN the scene (drei
 * GizmoViewcube re-skinned as a machinist's block: anvil faces, hairline
 * strokes, engraved labels, brass on hover). Clicks route through the view
 * command store so the move respects `prefers-reduced-motion`, which drei's
 * built-in tween does not.
 */
function ReferenceCube() {
  const requestDirection = useViewCommandStore((s) => s.requestDirection);
  const onCubeClick = useCallback(
    (event: ThreeEvent<MouseEvent>): null => {
      event.stopPropagation();
      // Edge/corner cubelets carry their direction as their local position;
      // the face cube sits at the origin and reports the picked face normal.
      const position = event.object.position;
      if (position.lengthSq() > 1e-6) {
        requestDirection([position.x, position.y, position.z]);
      } else if (event.face) {
        requestDirection([
          event.face.normal.x,
          event.face.normal.y,
          event.face.normal.z,
        ]);
      }
      return null;
    },
    [requestDirection],
  );
  return (
    <GizmoHelper
      alignment="bottom-right"
      margin={[CUBE_MARGIN_PX, CUBE_MARGIN_PX]}
    >
      <GizmoViewcube
        color={viewport.gizmo.face}
        hoverColor={viewport.gizmo.hover}
        textColor={viewport.gizmo.text}
        strokeColor={viewport.gizmo.stroke}
        opacity={viewport.gizmo.opacity}
        font={`600 30px ${font.data}`}
        onClick={onCubeClick}
      />
    </GizmoHelper>
  );
}

/**
 * The orbit rig's button maps (VP-1, VP-1a). One of these three is on the
 * controls at every press; which one is decided by the press itself, in
 * {@link Viewport}'s `onPointerDownCapture`.
 *
 * `unlocked` IS three-stdlib's own default, so 3D navigation outside the
 * sketcher is unchanged. The two `drawing` maps leave the sketcher's own
 * gesture alone: three-stdlib's `onMouseDown` reads `mouseButtons.LEFT`, and an
 * absent entry falls to its `default` branch (`state = STATE.NONE`, no pointer
 * capture, no `preventDefault`), so the press reaches the sketcher untouched.
 *
 * NB `MOUSE.ROTATE` is what three-stdlib swaps to PAN when ctrl/meta/shift is
 * down — Alt is not in that list, so `drawingAltOrbit`'s LEFT really rotates.
 */
const ORBIT_BUTTONS: Record<
  "unlocked" | "drawing" | "drawingAltOrbit",
  Partial<Record<"LEFT" | "MIDDLE" | "RIGHT", MOUSE>>
> = {
  unlocked: { LEFT: MOUSE.ROTATE, MIDDLE: MOUSE.DOLLY, RIGHT: MOUSE.PAN },
  drawing: { MIDDLE: MOUSE.ROTATE, RIGHT: MOUSE.PAN },
  drawingAltOrbit: {
    LEFT: MOUSE.ROTATE,
    MIDDLE: MOUSE.ROTATE,
    RIGHT: MOUSE.PAN,
  },
};

export interface ViewportProps {
  glb?: ArrayBuffer | undefined;
  /** Extra scene content rendered inside the Canvas (e.g. the sketch layer). */
  children?: ReactNode;
  /** DOM overlays over the canvas (tool strip, DRO) — chrome stays quiet. */
  hud?: ReactNode;
  /**
   * May orbit own the LEFT button? False while the sketcher is drawing, whose
   * own gesture is a left press-drag-release. Orbit itself stays available —
   * it moves to the middle button (VP-1) and to Alt+left (VP-1a, the gesture a
   * trackpad can produce); pan/zoom are untouched either way.
   */
  rotateEnabled?: boolean;
  /** The world ground grid; the sketch grid replaces it while drawing. */
  groundGrid?: boolean;
  /**
   * View navigation (reference cube + view rail + numeric snaps + ground
   * shadow). Off while a sketch rig owns the camera (plane pick / drawing).
   */
  viewNav?: boolean;
  /**
   * Scene bounds override (scene mm). The assembly workspace passes its
   * combined instance bounds; a part viewport derives bounds from its own
   * parsed geometry when this is undefined.
   */
  worldBounds?: Box3 | null;
  /**
   * Refit trigger: the camera re-frames `worldBounds` when this changes (the
   * assembly passes its LOADED-instance set, so the fit waits for meshes —
   * never racing the GLB fetch). Defaults to the parsed geometry's identity.
   */
  fitKey?: string;
  /**
   * The body responds to the pointer (hover glow) — off while a pick tool owns
   * the viewport. Item 11 selection/hover feedback on the body.
   */
  bodyInteractive?: boolean;
  /** The body's feature is selected in the tree (the tree→geometry link). */
  bodySelected?: boolean;
  /**
   * `body.faces()` ordinals owned by the selected feature (FINDINGS #9). A
   * proper subset localizes the selection to just those faces — the studio
   * matcap is preserved on the rest — distinguishing feature-select from the
   * whole-body select. Null/every-face falls back to the whole-body state.
   */
  bodySelectedFaces?: readonly number[] | null;
  /**
   * Right-click on the scene (UI-REVIEW #10): the workspace opens its viewport
   * context menu at the pointer. The container forwards the raw event so the
   * caller can `preventDefault` and read `clientX`/`clientY`.
   */
  onContextMenu?: (event: ReactMouseEvent) => void;
  /**
   * Draw the single aggregate contact pool under `bounds`. The assembly turns
   * this OFF and seats EACH instance on its own pool instead (UI audit #19d —
   * one big blob under a multi-part scene reads flat; per-part shadows give the
   * assembly the same grounded depth a lone part has).
   */
  groundShadow?: boolean;
}

/**
 * The hero — a full-bleed scene that reads as a place: gun-blued bench with
 * a horizon-persistent mm grid, machined-aluminum stock under a studio
 * matcap, a contact shadow seating it, and persistent view navigation
 * (reference cube, view rail, numeric snaps). Every color comes from
 * `@loft/design/tokens` — one palette, two renderers.
 */
export function Viewport({
  glb,
  children,
  hud,
  rotateEnabled = true,
  groundGrid = true,
  viewNav = true,
  worldBounds,
  fitKey,
  bodyInteractive = false,
  bodySelected = false,
  bodySelectedFaces = null,
  onContextMenu,
  groundShadow = true,
}: ViewportProps) {
  const reducedMotion = useReducedMotion();
  // The user's navigation preferences (#58) — orbit/pan/zoom sensitivity and
  // the scroll-direction flip, which is carried by the SIGN of `zoomSpeed`
  // (see `navigationControls`). Read here, applied to the one orbit rig that
  // serves both the modelling scene and the sketch layer rendered into it.
  const navigation = navigationControls(usePreferences());
  const containerRef = useRef<HTMLDivElement>(null);
  /** The orbit rig, so a press can pick its button map (VP-1a, below). */
  const orbitRef = useRef<OrbitControlsImpl>(null);
  const [geometry, setGeometry] = useState<BufferGeometry | null>(null);
  const [visibleBounds, setVisibleBounds] = useState<Box3 | null>(null);
  const [parseError, setParseError] = useState<Error | null>(null);
  const handleGeometry = useCallback((next: BufferGeometry) => {
    setGeometry(next);
    setParseError(null);
  }, []);
  const handleError = useCallback((error: Error) => setParseError(error), []);

  // View accelerators (1/2/3/4 snaps, 0 fit, Home) — only while the rig owns
  // the camera (not during sketch authoring).
  useViewHotkeys(viewNav);

  // The subject the camera frames. A part viewport prefers the bounds of what
  // is DRAWN over the whole mesh's, so hiding a body genuinely takes it out of
  // the fit (UI-W2) instead of leaving the camera parked around a solid nobody
  // can see. Origin planes/axes are deliberately excluded: they are sized FROM
  // these bounds, so feeding them back in would zoom out a step every refit.
  const bounds = useMemo<Box3 | null>(() => {
    if (worldBounds !== undefined) return worldBounds;
    return visibleBounds ?? geometry?.boundingBox ?? null;
  }, [worldBounds, visibleBounds, geometry]);
  const partBodies = usePartViewStore((state) => state.bodies);
  const partView = usePartViewStore((state) => state.view);
  const partSubject = usePartViewStore((state) => state.subjectId);
  const partHidden = hiddenBodyCount(partView, partBodies);
  const partIsolated = isolatedBodyLabel(partView, partBodies);
  const showAllBodies = usePartViewStore((state) => state.showAll);
  // `V` / `⇧V` — armed only while a PART browser has registered its subject, so
  // the assembly workspace keeps its own binding of the same keys.
  usePartViewHotkeys(viewNav && partSubject !== null);
  // The fit re-runs whenever the drawn subject changes identity, which now
  // includes "a body was hidden" — the same trigger, one more input.
  const hiddenFitKey = `${partHidden}:${partBodies.length}`;
  const resolvedFitKey =
    fitKey ??
    (geometry === null ? "empty" : `geometry-${geometry.id}-${hiddenFitKey}`);

  // Ground the stock: a soft contact pool sized to the subject's footprint.
  // Sits a hair ABOVE the grid plane so it shades the bench, never z-fights.
  const shadow = useMemo(() => {
    if (bounds === null || bounds.isEmpty()) return null;
    const center = bounds.getCenter(new Vector3());
    const size = bounds.getSize(new Vector3());
    return {
      position: [center.x, Math.min(0, bounds.min.y) - 0.02, center.z] as const,
      scale: [Math.max(size.x, 1) * 2.1, Math.max(size.z, 1) * 2.1, 1] as const,
    };
  }, [bounds]);

  /** QA hook: the body's hover/selection highlight, stamped on the container. */
  const handleHighlight = useCallback((highlight: BodyHighlight) => {
    const node = containerRef.current;
    if (node !== null) node.dataset["bodyHighlight"] = highlight;
  }, []);

  /**
   * QA hook: the highlighted face count vs the body's total face count. Proves
   * a feature-localized selection lights a PROPER subset (matcap preserved on
   * the rest) without reading WebGL pixels (FINDINGS #9).
   */
  const handleFaceSelection = useCallback((selected: number, total: number) => {
    const node = containerRef.current;
    if (node === null) return;
    node.dataset["selectedFaces"] = String(selected);
    node.dataset["totalFaces"] = String(total);
  }, []);

  /**
   * QA hook: the face ordinal under the cursor (SEL-1 / spec A1). Proves the
   * hover lights exactly ONE face of the body's `data-total-faces`, rather
   * than the whole solid, as a number — the same raster-independent posture
   * `data-selected-faces` takes for selection. Absent (attribute removed)
   * whenever no face is addressed, so "nothing hovered" and "face 0 hovered"
   * stay distinguishable — `String(0)` would collide with a falsy read.
   */
  const handleFaceHover = useCallback(
    (ordinal: number | null, total: number) => {
      const node = containerRef.current;
      if (node === null) return;
      if (ordinal === null) delete node.dataset["hoveredFace"];
      else node.dataset["hoveredFace"] = String(ordinal);
      node.dataset["totalFaces"] = String(total);
    },
    [],
  );

  /**
   * QA hook: the drawn / ghosted / hidden face census (UI-W2). The load-bearing
   * proof that a body eye moved the SCENE is the spec's pixel census; this is
   * its raster-independent companion, and it is what makes a "hidden means
   * nothing drawn" regression fail as a number rather than as a fuzzy image.
   */
  const handleBodyView = useCallback(
    (counts: { drawn: number; ghosted: number; hidden: number }) => {
      const node = containerRef.current;
      if (node === null) return;
      node.dataset["drawnFaces"] = String(counts.drawn);
      node.dataset["ghostFaces"] = String(counts.ghosted);
      node.dataset["hiddenFaces"] = String(counts.hidden);
    },
    [],
  );

  /**
   * Right-drag PANS, right-CLICK opens the menu (FINDINGS burn-down #4). The
   * orbit rig binds the right button to pan and its own `contextmenu` handler
   * only `preventDefault()`s — the event still reaches this container — so
   * before this gate every pan ended with the menu popping open. The gate is
   * the standard click-slop test, applied whenever the browser chooses to fire
   * `contextmenu`:
   *
   *  - fired on PRESS (Chromium/Linux): the travel isn't known yet, so the
   *    request is held and released on pointerup — only if the pointer stayed
   *    put. The menu therefore opens on release of a stationary right-click,
   *    exactly as Fusion 360 / Plasticity do.
   *  - fired on RELEASE (Windows/macOS): the gesture's travel is already
   *    recorded, so the decision is immediate.
   *  - fired with no right press at all (the keyboard menu key): always opens.
   */
  const rightGesture = useRef<{
    down: PointerPoint;
    up: PointerPoint | null;
  } | null>(null);
  const heldMenuRequest = useRef<ReactMouseEvent | null>(null);

  const handlePointerDown = useCallback((event: ReactPointerEvent) => {
    if (event.button !== 2) return;
    rightGesture.current = {
      down: { x: event.clientX, y: event.clientY },
      up: null,
    };
    heldMenuRequest.current = null;
  }, []);

  const handleContextMenu = useCallback(
    (event: ReactMouseEvent) => {
      const gesture = rightGesture.current;
      if (gesture === null) {
        onContextMenu?.(event); // keyboard menu key — no drag to weigh
        return;
      }
      // The browser default is already suppressed by the orbit controls; keep
      // it suppressed on our own path too.
      event.preventDefault();
      if (gesture.up === null) {
        heldMenuRequest.current = event; // decide when the button comes up
        return;
      }
      rightGesture.current = null;
      if (!isDragGesture(gesture.down, gesture.up)) onContextMenu?.(event);
    },
    [onContextMenu],
  );

  const handlePointerUp = useCallback(
    (event: ReactPointerEvent) => {
      if (event.button !== 2) return;
      const gesture = rightGesture.current;
      if (gesture === null) return;
      const up = { x: event.clientX, y: event.clientY };
      gesture.up = up;
      const held = heldMenuRequest.current;
      if (held === null) return; // the contextmenu event is still to come
      heldMenuRequest.current = null;
      rightGesture.current = null;
      if (!isDragGesture(gesture.down, up)) onContextMenu?.(held);
    },
    [onContextMenu],
  );

  /**
   * VP-1 — the orbit rig's button map. `rotateEnabled` says whether orbit may
   * own the LEFT button; it is false exactly while the sketcher is drawing,
   * and the sketcher draws with a left press-drag-release.
   *
   * That lock used to be spelled `enableRotate={false}`, which took orbit off
   * EVERY button, so a modeller could not look around mid-sketch (founder
   * report). Fusion 360 never binds orbit to the drawing button in the first
   * place, so orbit is always live there. So the lock now MOVES the gesture
   * rather than removing it: LEFT goes unbound, ROTATE takes MIDDLE, and RIGHT
   * stays PAN (the right-drag pan the context-menu click-slop gate above
   * depends on). Nothing is lost: MIDDLE was DOLLY, and the wheel already
   * dollies. See {@link ORBIT_BUTTONS} for why an absent LEFT is inert.
   *
   * This is the map React hands the rig; the press-time override below can
   * swap it for the Alt one before three-stdlib reads it.
   */
  const mouseButtons = rotateEnabled
    ? ORBIT_BUTTONS.unlocked
    : ORBIT_BUTTONS.drawing;

  /**
   * VP-1a — Alt(Option)+left-drag ALSO orbits while the sketcher owns LEFT,
   * because a trackpad has no middle button and VP-1's gesture therefore never
   * reached the founder, who reported the original complaint.
   *
   * Why Alt: it is the only modifier free here. Ctrl/Cmd suppresses snapping
   * and Shift locks the aim to an axis inside the sketcher (`SketchScene`'s
   * `modifiers`), and three-stdlib itself reads ctrl/meta/shift at mousedown to
   * swap ROTATE for PAN, so either of those would mean two things at once.
   * Alt+left is also what Blender ("emulate 3 button mouse") and Maya bind
   * tumble to, i.e. the convention for exactly this hardware gap.
   *
   * Why a press-time override rather than a modifier-tracking `useState`:
   * three-stdlib has no modifier support in `mouseButtons`, so the usual
   * technique swaps the map on keydown/keyup — which stores a copy of keyboard
   * state that a repaint can lag, and that an Alt released over another window
   * leaves stuck ON (hence the customary blur/visibilitychange cleanup). Here
   * the map is instead DERIVED, at every press, from the modifier the press
   * itself carries: `altKey` on the very pointerdown three-stdlib is about to
   * handle. There is no copy of the keyboard to go stale, nothing to reset on
   * blur, and no keydown that can be missed. It is the same argument
   * `SketchScene`'s `modifiers` already makes for reading Ctrl/Shift off the
   * event rather than off a tracked flag.
   *
   * Ordering is what makes it work: the capture phase runs at this container
   * (an ancestor of the canvas) before the target-phase `pointerdown` listener
   * three-stdlib registered on the canvas, so the assignment always lands
   * first. The handler is TOTAL — every branch assigns — so the rig can never
   * be left holding the previous press's map.
   */
  const handlePointerDownCapture = useCallback(
    (event: ReactPointerEvent) => {
      const controls = orbitRef.current;
      if (controls === null) return;
      controls.mouseButtons = rotateEnabled
        ? ORBIT_BUTTONS.unlocked
        : event.altKey
          ? ORBIT_BUTTONS.drawingAltOrbit
          : ORBIT_BUTTONS.drawing;
    },
    [rotateEnabled],
  );

  /**
   * Touch keeps precisely the behaviour it had. `enableRotate` has to be true
   * now (it gates the rotate MOVE handler as well as the press, so a false
   * would leave the middle button orbiting nothing), and one finger defaults
   * to ROTATE — which would newly spin the view under a finger dragged across
   * a sketch. Unbinding ONE while the lock is on reproduces the old
   * `enableRotate={false}` outcome for that gesture; TWO is dolly+pan either
   * way. VP-1a reaches a TRACKPAD (whose click-drag is a mouse pointer with a
   * modifier), not a touchscreen, which has neither a middle button nor a
   * modifier key — orbit-while-drawing is still out of reach there.
   */
  const touches = useMemo(
    () =>
      rotateEnabled
        ? { ONE: TOUCH.ROTATE, TWO: TOUCH.DOLLY_PAN }
        : { TWO: TOUCH.DOLLY_PAN },
    [rotateEnabled],
  );

  /** QA hook: the settled view + camera position, stamped on the container. */
  const handleSettle = useCallback(
    (view: string, position: Vector3, framed: Rect | null) => {
      const node = containerRef.current;
      if (node === null) return;
      node.dataset["view"] = view;
      node.dataset["cameraPos"] = [position.x, position.y, position.z]
        .map((v) => v.toFixed(1))
        .join(",");
      // The rect the fit actually framed into — the free viewport, not the
      // canvas. The e2e reads it and asserts the body's projected bbox lies
      // inside it with margin on all four sides.
      node.dataset["fitRect"] =
        framed === null
          ? ""
          : [framed.x, framed.y, framed.width, framed.height]
              .map((v) => Math.round(v))
              .join(",");
    },
    [],
  );

  /**
   * The unobstructed rect, measured from the live DOM at fit time. Includes the
   * in-canvas reference cube, which is WebGL and therefore has no rect of its
   * own — a fit that tucked a part under the nav cube would be the same defect
   * as one that tucked it under the inspector.
   */
  const framing = useCallback(() => {
    const node = containerRef.current;
    if (node === null) return null;
    const { canvas, obstructions } = measureChrome(node);
    if (canvas.width <= 0 || canvas.height <= 0) return null;
    if (viewNav) {
      obstructions.push({
        x: canvas.width - CUBE_MARGIN_PX - CUBE_FOOTPRINT_PX / 2,
        y: canvas.height - CUBE_MARGIN_PX - CUBE_FOOTPRINT_PX / 2,
        width: CUBE_FOOTPRINT_PX,
        height: CUBE_FOOTPRINT_PX,
      });
    }
    return { canvas, free: unobstructedRect(canvas, obstructions) };
  }, [viewNav]);

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full min-h-0"
      data-testid="viewport"
      aria-label="3D viewport showing the tessellated model"
      // QA hooks: the numbers the orbit rig was actually GIVEN, so a preference
      // that stops reaching the camera fails a spec instead of a bug report. A
      // negative zoom speed is the inverted-scroll binding.
      data-nav-rotate-speed={navigation.rotateSpeed}
      data-nav-pan-speed={navigation.panSpeed}
      data-nav-zoom-speed={navigation.zoomSpeed}
      onPointerDownCapture={handlePointerDownCapture}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onContextMenu={handleContextMenu}
      style={{
        // The scene's air — a skylight glow falling into the deep shop edge.
        // Painted behind the transparent canvas; tokens only.
        background: `radial-gradient(120% 85% at 50% 30%, ${viewport.atmosphere.horizon} 0%, ${viewport.background} 55%, ${viewport.atmosphere.abyss} 100%)`,
      }}
    >
      <Canvas
        className="!absolute inset-0"
        frameloop="demand"
        dpr={[1, 2]}
        gl={{ antialias: true, preserveDrawingBuffer: true, alpha: true }}
        camera={{ fov: 40, position: [45, 32, 60] }}
      >
        <RenderProbe />
        {groundGrid ? (
          <AdaptiveGrid
            position={[0, -0.05, 0]}
            cellSize={5}
            sectionSize={25}
            cellColor={viewport.gridMinor}
            sectionColor={viewport.gridMajor}
          />
        ) : null}
        {groundShadow && viewNav && shadow !== null ? (
          <mesh
            position={[
              shadow.position[0],
              shadow.position[1],
              shadow.position[2],
            ]}
            scale={[shadow.scale[0], shadow.scale[1], shadow.scale[2]]}
            rotation={[-Math.PI / 2, 0, 0]}
          >
            <planeGeometry args={[1, 1]} />
            <meshBasicMaterial
              color={viewport.groundShadow}
              map={groundShadowTexture()}
              transparent
              opacity={viewport.groundShadowOpacity}
              depthWrite={false}
              toneMapped={false}
            />
          </mesh>
        ) : null}
        {glb ? (
          <ModelMesh
            glb={glb}
            onGeometry={handleGeometry}
            onError={handleError}
            interactive={bodyInteractive}
            selected={bodySelected}
            selectedFaceIndices={bodySelectedFaces}
            onHighlightChange={handleHighlight}
            onFaceSelectionChange={handleFaceSelection}
            onFaceHoverChange={handleFaceHover}
            onVisibleBounds={setVisibleBounds}
            onBodyViewChange={handleBodyView}
          />
        ) : null}
        {/* Origin planes + axes (UI-W2). Renders nothing until the browser
            enables a row, and never contributes to the camera fit. */}
        {viewNav ? <OriginGeometry bounds={bounds} /> : null}
        {children}
        <CameraRig
          bounds={bounds}
          fitKey={resolvedFitKey}
          reducedMotion={reducedMotion}
          framing={framing}
          // `viewNav` is already the workspace's own statement of "the part
          // camera is in charge" — it is false exactly while the sketcher owns
          // the view, which is when a second rig is easing this same camera.
          owns={viewNav}
          onSettle={handleSettle}
        />
        {viewNav ? <ReferenceCube /> : null}
        <OrbitControls
          ref={orbitRef}
          makeDefault
          enableDamping={!reducedMotion}
          // Always enabled — `enableRotate` gates the rotate MOVE handler as
          // well as the press, so the lock lives in `mouseButtons` instead
          // (see above), where it can move orbit to another button rather
          // than delete it.
          enableRotate
          mouseButtons={mouseButtons}
          touches={touches}
          zoomToCursor
          rotateSpeed={navigation.rotateSpeed}
          panSpeed={navigation.panSpeed}
          zoomSpeed={navigation.zoomSpeed}
        />
      </Canvas>
      {/* Vignette — the edge of the light pool. Above the canvas, below the
          HUD; pointer-transparent, token-only. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 z-10"
        style={{
          background: `radial-gradient(125% 125% at 50% 42%, transparent 58%, ${viewport.atmosphere.abyss} 130%)`,
          opacity: viewport.atmosphere.vignetteOpacity,
        }}
      />
      {/*
        HUD strips sit above the in-canvas annotation overlays (drei Html,
        zIndexRange [20, 0] in ConstraintGlyphs). The wrapper is inert;
        each strip re-enables its own pointer events.
      */}
      <div className="pointer-events-none absolute inset-0 z-hud [&>*]:pointer-events-auto">
        {viewNav ? <ViewBar /> : null}
        {viewNav ? <NavCue /> : null}
        {/* The way back from an isolate / a hand-hidden scene (UI-W2). The same
            derived stamp the assembly workspace shows, over bodies. */}
        {viewNav && partSubject !== null ? (
          <VisibilityStamp
            isolatedName={partIsolated}
            hiddenCount={partHidden}
            onShowAll={showAllBodies}
          />
        ) : null}
        {hud}
      </div>
      {/*
        Rejection stamp — shown when the GLB fails to parse. The stale mesh
        has already been cleared (ModelMesh.onError), so the viewport never
        shows a model that doesn't match the inspector. Static, token-only
        (flag = error), same drawing-stamp language as the title block.
      */}
      {parseError ? (
        <div
          role="alert"
          data-testid="viewport-error"
          className="absolute left-1/2 top-3 z-hud max-w-sm -translate-x-1/2 rounded-sm border border-flag bg-anvil px-3 py-2"
        >
          <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
            Mesh rejected · {parseError.name}
          </span>
          <span className="mt-1 block font-body text-xs text-mist">
            The model could not be displayed and was cleared. Apply the
            dimensions again to re-mesh.
          </span>
        </div>
      ) : null}
    </div>
  );
}
