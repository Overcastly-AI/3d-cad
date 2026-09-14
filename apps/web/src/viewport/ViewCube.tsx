/**
 * The REFERENCE CUBE — persistent view navigation (design mandate 3a calls a
 * ViewCube/gizmo "table stakes, not a feature"). A machinist's block: anvil
 * faces, hairline strokes, engraved labels, brass on hover. Clicking a face,
 * edge or corner routes through the view-command store so the move respects
 * `prefers-reduced-motion`, which drei's built-in tween does not.
 *
 * WHY IT HAS ITS OWN CANVAS (VIEWCUBE-1, 2026-08-17) — this is the fix, and the
 * reasoning matters because the obvious cheaper fixes were all measured and all
 * failed:
 *
 * It used to be `drei`'s `<GizmoHelper>`, which draws through `<Hud>`: a SECOND
 * `gl.render(hudScene, hudCamera)` into the MAIN canvas after `gl.clearDepth()`
 * (`@react-three/drei/core/Hud.js`). That second pass reaches the WebGL drawing
 * buffer at every frame size — a `drawImage` readback of the live canvas counts
 * ~270 label pixels at 1600x1000 AND at 1366x768 — but Chromium DROPS it from
 * the composited frame whenever a sibling `overflow-y:auto` column is actually
 * scrolling. The inspector column is exactly that, and it starts scrolling when
 * its content outgrows its clamp, i.e. below a canvas height of ~742 px. Hence
 * the founder-visible symptom: the cube was present at 1600x1000 / 1440x900 /
 * 1280x900 and ABSENT at 1400x800 / 1280x800 / 1366x768 — height-driven, on the
 * three commonest laptop frames, including the 1280x800 responsive floor the
 * mandate names and every founder screenshot is captured at.
 *
 * Ruled out by measurement, so nobody re-tries them: raising the chrome's
 * clearance band (140 -> 176) — no change; `frameloop="always"` — no change;
 * `will-change`/`translateZ(0)`/`contain:paint`/`isolation:isolate` on the
 * canvas or the viewport — no change; `scrollbar-width:none` — no change. Only
 * removing the scroll (`overflow:hidden`), hiding the column, or drawing the
 * cube OUTSIDE the two-pass canvas restored it. The first two are not options —
 * the inspector has to scroll — so the structural one is the fix: one canvas,
 * one render pass, nothing for the compositor to drop.
 *
 * Three things fall out of it that are worth more than the bug fix:
 *  - the cube is now a real DOM element, so it has a `data-testid`, an
 *    accessible name, and a rect QA can click (before this it was WebGL only,
 *    and no spec in the suite could drive it);
 *  - `data-viewport-chrome` means `fitFraming.measureChrome` sees it like every
 *    other panel, so `Viewport.framing()` no longer hand-rolls a synthetic
 *    obstruction out of duplicated placement constants; and
 *  - its size and seat are `@loft/design` tokens, so the clearance the chrome
 *    keeps (`layout.referenceCubeBand`) is DERIVED from the cube's geometry
 *    instead of transcribed beside it — the drift that let the rail reach 16 px
 *    into the block in the first place.
 */
import { font, viewport } from "@loft/design/tokens";
import { GizmoViewcube } from "@react-three/drei";
import {
  Canvas,
  useFrame,
  useThree,
  type ThreeEvent,
} from "@react-three/fiber";
import { useCallback, useEffect, useRef } from "react";
import type { Group } from "three";

import { usePickArmed } from "./armedPicks";
import {
  readViewQuaternion,
  subscribeViewQuaternion,
} from "./cameraOrientation";
import { useViewCommandStore } from "./viewCommands";

/**
 * The block itself, kept square-on to the scene: its group carries the INVERSE
 * of the scene camera's rotation, so "up" on the block is always the scene's
 * up. Identical to what `GizmoHelper` did per frame — it inverted the camera's
 * matrix and read the rotation out of it — with the camera arriving over
 * {@link readViewQuaternion} instead of r3f context.
 */
function CubeBlock({
  onPick,
}: {
  onPick: (event: ThreeEvent<MouseEvent>) => null;
}) {
  const group = useRef<Group>(null);
  const invalidate = useThree((state) => state.invalidate);

  // Demand rendering: the cube redraws when the scene camera MOVES and at no
  // other time. Without this the canvas would paint once and then lie.
  useEffect(() => subscribeViewQuaternion(invalidate), [invalidate]);

  useFrame(() => {
    const node = group.current;
    if (node === null) return;
    node.quaternion.copy(readViewQuaternion()).invert();
  });

  return (
    <group ref={group}>
      <GizmoViewcube
        color={viewport.gizmo.face}
        hoverColor={viewport.gizmo.hover}
        textColor={viewport.gizmo.text}
        strokeColor={viewport.gizmo.stroke}
        opacity={viewport.gizmo.opacity}
        font={`600 30px ${font.data}`}
        onClick={onPick}
      />
    </group>
  );
}

/** Stable identity — a new object per render would re-style the canvas. */
const YIELDED = { pointerEvents: "none" } as const;

export function ViewCube() {
  const requestDirection = useViewCommandStore(
    (state) => state.requestDirection,
  );
  const pickArmed = usePickArmed();
  const onPick = useCallback(
    (event: ThreeEvent<MouseEvent>): null => {
      event.stopPropagation();
      // Edge/corner cubelets carry their direction as their local position;
      // the face cube sits at the origin and reports the picked face normal.
      // Both are object-space, which IS scene space here because the group's
      // only transform is the inverse camera rotation.
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
    <div
      // `role`+name so the control is announced and so QA has something to
      // address; the keyboard path to the same views is the ViewBar beside it
      // and the numeric snaps (`useViewHotkeys`), not a second binding here.
      role="group"
      aria-label="View cube"
      data-testid="view-cube"
      // Read by `fitFraming.measureChrome`: a fit must not tuck the model under
      // the cube, exactly as it must not tuck it under a panel.
      data-viewport-chrome="view-cube"
      // WHILE A PICK IS ARMED THE BLOCK IS A READOUT, NOT A CONTROL.
      //
      // Its seat is 108 px square in the HUD layer, above every pick mark by
      // construction (marks top out at z-index 30; `z-hud` is 40). With a body
      // panned into this corner at 1280x800, cross-item QA measured 5 of 6
      // `plane-pick-face-N` marks resolving to `view-cube`, 49 of 49 grid
      // points the same, and the surface pick under it gone as well — the
      // corner of the model went dead exactly while the tool was asking the
      // modeller to pick a face there.
      //
      // Giving up the POINTER and keeping the PIXELS is the trade that costs
      // least: CRAFT-6's own argument for mounting the cube through authoring
      // is that it is "an orientation READOUT before it is a control", and a
      // readout is unharmed by this. Re-stacking instead would hand the same
      // defect to the ViewBar and the proposal chip. Orbit, pan and zoom are
      // canvas gestures and were never blocked; drawing does not yield the cube
      // at all, because the sketcher's snap marks are not pick marks.
      //
      // The stamp is the QA hook: a spec can prove the yield is a STATE rather
      // than reading it off a lucky hit test.
      data-pick-yield={pickArmed ? "1" : undefined}
      // INLINE, and it has to be. The HUD layer this sits in is
      // `pointer-events-none … [&>*]:pointer-events-auto` — a `.hud > *` rule
      // at specificity (0,2,0), which beats a `.pointer-events-none` utility
      // (0,1,0) on the child itself. Measured: with the class applied and
      // `data-pick-yield="1"` in the DOM, `getComputedStyle` still read
      // `pointer-events: auto` and 5 of 6 marks still resolved to the cube.
      // A class that loses to the layer it lives in is a yield that never
      // happens, and it is success-shaped from every angle except the pixel.
      style={pickArmed ? YIELDED : undefined}
      className="absolute bottom-view-cube right-view-cube h-view-cube w-view-cube"
    >
      <Canvas
        // THE YIELD HAS TO LAND HERE, not only on the host above. r3f's
        // `<Canvas>` writes `pointerEvents: 'auto'` INLINE on its own root div
        // (`react-three-fiber.esm.js`: `const pointerEvents = eventSource ?
        // 'none' : 'auto'`), and an inline declaration beats an inherited one —
        // so a `pointer-events-none` class on the wrapper is silently
        // overridden and the seat keeps eating clicks. Measured: 5 of 6 pick
        // marks still resolved to `view-cube` with only the wrapper yielding.
        // This is the same family as the documented trap that
        // `pointer-events: none` on the `<canvas>` element does nothing because
        // r3f listens on the container. The `style` prop is spread LAST into
        // that object, which is why it is the one thing that wins.
        style={pickArmed ? YIELDED : undefined}
        orthographic
        // zoom 1 with an r3f-sized frustum makes ONE scene unit ONE CSS pixel,
        // which is why `viewCube.size` can be derived from `viewCube.face`.
        camera={{ position: [0, 0, 200], zoom: 1 }}
        frameloop="demand"
        dpr={[1, 2]}
        gl={{ alpha: true, antialias: true }}
      >
        <CubeBlock onPick={onPick} />
      </Canvas>
    </div>
  );
}
