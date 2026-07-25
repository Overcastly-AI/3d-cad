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
import { PerspectiveCamera, Vector3, type BufferGeometry } from "three";
import type { Box3 } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";

import { useReducedMotion } from "../lib/useReducedMotion";
import { NavCue } from "../components/NavCue";
import { ViewBar } from "../components/ViewBar";
import { AdaptiveGrid } from "./AdaptiveGrid";
import { isDragGesture, type PointerPoint } from "./contextMenuGesture";
import { groundShadowTexture } from "./groundShadow";
import { ModelMesh, type BodyHighlight } from "./ModelMesh";
import {
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

interface CameraGoal {
  position: Vector3;
  up: Vector3;
  target: Vector3;
  /** Named view stamped on the container once the move settles (QA hook). */
  view: string;
}

/** Camera up for a snap direction — top/bottom need a non-parallel up. */
function upFor(dir: Vector3): Vector3 {
  return Math.abs(dir.y) > 0.99
    ? new Vector3(0, 0, dir.y > 0 ? -1 : 1)
    : new Vector3(0, 1, 0);
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
  onSettle,
}: {
  bounds: Box3 | null;
  fitKey: string;
  reducedMotion: boolean;
  onSettle: (view: string, position: Vector3) => void;
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
        onSettle(pose.view, camera.position);
      } else {
        goal.current = pose;
      }
      invalidate();
    },
    [camera, controls, invalidate, onSettle],
  );

  // Auto-fit whenever the subject changes (a fresh geometry, or an assembly
  // instance's mesh landing). Instant, exactly as the shell always fit.
  useEffect(() => {
    const box = boundsRef.current;
    if (box === null || box.isEmpty()) return;
    const center = box.getCenter(new Vector3());
    const diagonal = box.getSize(new Vector3()).length();
    const position = ISO_DIR.clone()
      .multiplyScalar(Math.max(diagonal, 1) * FIT_FACTOR)
      .add(center);
    setClipPlanes(diagonal);
    applyPose(
      { position, up: new Vector3(0, 1, 0), target: center, view: "fit-auto" },
      true,
    );
    // The fit key IS the refit trigger; bounds/camera are read at fit time.
  }, [fitKey]);

  // Execute view commands (nonce-keyed so a repeated snap re-fires).
  const executed = useRef(0);
  useEffect(() => {
    if (command === null || command.nonce === executed.current) return;
    executed.current = command.nonce;
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
      pose = {
        position: dir.multiplyScalar(fitRadius).add(center),
        up: camera.up.clone(),
        target: center,
        view: "fit",
      };
    } else {
      const named = command.kind === "home" ? "iso" : command.kind;
      const dir = new Vector3(...VIEW_DIRECTIONS[named]).normalize();
      pose = {
        position: dir.multiplyScalar(fitRadius).add(center),
        up: upFor(dir),
        target: center,
        view: command.kind,
      };
    }
    if (hasBounds) setClipPlanes(diagonal);
    applyPose(pose, reducedMotion);
  }, [command, camera, controls, reducedMotion, setClipPlanes, applyPose]);

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
      onSettle(g.view, camera.position);
    }
    invalidate();
  });

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
    <GizmoHelper alignment="bottom-right" margin={[64, 64]}>
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

export interface ViewportProps {
  glb?: ArrayBuffer | undefined;
  /** Extra scene content rendered inside the Canvas (e.g. the sketch layer). */
  children?: ReactNode;
  /** DOM overlays over the canvas (tool strip, DRO) — chrome stays quiet. */
  hud?: ReactNode;
  /** Orbit rotate lock — off while sketching (pan/zoom stay live). */
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
  const containerRef = useRef<HTMLDivElement>(null);
  const [geometry, setGeometry] = useState<BufferGeometry | null>(null);
  const [parseError, setParseError] = useState<Error | null>(null);
  const handleGeometry = useCallback((next: BufferGeometry) => {
    setGeometry(next);
    setParseError(null);
  }, []);
  const handleError = useCallback((error: Error) => setParseError(error), []);

  // View accelerators (1/2/3/4 snaps, 0 fit, Home) — only while the rig owns
  // the camera (not during sketch authoring).
  useViewHotkeys(viewNav);

  const bounds = useMemo<Box3 | null>(() => {
    if (worldBounds !== undefined) return worldBounds;
    return geometry?.boundingBox ?? null;
  }, [worldBounds, geometry]);
  const resolvedFitKey =
    fitKey ?? (geometry === null ? "empty" : `geometry-${geometry.id}`);

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

  /** QA hook: the settled view + camera position, stamped on the container. */
  const handleSettle = useCallback((view: string, position: Vector3) => {
    const node = containerRef.current;
    if (node === null) return;
    node.dataset["view"] = view;
    node.dataset["cameraPos"] = [position.x, position.y, position.z]
      .map((v) => v.toFixed(1))
      .join(",");
  }, []);

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full min-h-0"
      data-testid="viewport"
      aria-label="3D viewport showing the tessellated model"
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
          />
        ) : null}
        {children}
        <CameraRig
          bounds={bounds}
          fitKey={resolvedFitKey}
          reducedMotion={reducedMotion}
          onSettle={handleSettle}
        />
        {viewNav ? <ReferenceCube /> : null}
        <OrbitControls
          makeDefault
          enableDamping={!reducedMotion}
          enableRotate={rotateEnabled}
          zoomToCursor
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
