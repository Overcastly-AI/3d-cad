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

export function ViewCube() {
  const requestDirection = useViewCommandStore(
    (state) => state.requestDirection,
  );
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
      className="absolute bottom-view-cube right-view-cube h-view-cube w-view-cube"
    >
      <Canvas
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
