/**
 * The drafting board behind the part in a squared-on parallel view (CRAFT-2).
 * The decision, the mechanism it repairs and the measurements are in
 * `benchBackdrop.ts`; this is the drawing.
 *
 * It is the SAME `AdaptiveGrid` the bench floor and the sketch plane use, at
 * the same pitch and in the same two inks — one grid primitive, three seats.
 * Nothing new is introduced to the scene: the floor stands up, and its fade
 * keeps reaching the frame edge because the primitive already scales with the
 * orbit radius.
 */
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import { Matrix4, OrthographicCamera, Quaternion, Vector3 } from "three";
import type { Box3 } from "three";
import { viewport } from "@loft/design/tokens";

import { AdaptiveGrid } from "./AdaptiveGrid";
import { backdropFor, backdropPose, type Backdrop } from "./benchBackdrop";

/** Minor cell edge (mm) — the bench's own pitch, stated once per seat. */
const CELL_MM = 5;
/** Major section edge (mm). */
const SECTION_MM = 25;

/**
 * Orient the grid's local +Y (its plane normal — `SketchScene.gridQuaternion`
 * establishes the convention) onto a world axis. Built from a basis rather
 * than `setFromUnitVectors` so the IN-PLANE axes are pinned too: the sheet's
 * lines must run along world axes, or the pitch stops meaning millimetres in
 * any direction a reader could measure.
 */
function sheetQuaternion(
  normal: readonly [number, number, number],
): Quaternion {
  const y = new Vector3(normal[0], normal[1], normal[2]);
  // Any world axis not parallel to the normal gives the in-plane u; the
  // backdrop's normal is always world X or Z, so world Y is always safe.
  const x = new Vector3(0, 1, 0).cross(y).normalize();
  const z = x.clone().cross(y);
  return new Quaternion().setFromRotationMatrix(
    new Matrix4().makeBasis(x, y, z),
  );
}

export interface BenchBackdropProps {
  /** The framed subject — the sheet hangs behind it. Null for an empty part. */
  bounds: Box3 | null;
  /**
   * QA hook: which sheet is up, or `none`. Stamped on the viewport container
   * so a census of the frame can say WHICH mechanism drew the ink it counted
   * — a pixel count alone cannot tell a backdrop from a floor, and the two are
   * exactly what CRAFT-2 has to distinguish.
   */
  onBackdropChange?: (state: string) => void;
}

export function BenchBackdrop({
  bounds,
  onBackdropChange,
}: BenchBackdropProps) {
  const [backdrop, setBackdrop] = useState<Backdrop | null>(null);
  // The rig writes the camera every frame while it eases, so the decision is
  // re-taken every frame — but it is a DISCRETE answer, so React only hears
  // about it when the answer changes. An `useFrame` that setState'd
  // unconditionally would re-render the scene 60 times a second.
  const live = useRef<Backdrop | null>(null);
  const invalidate = useThree((state) => state.invalidate);
  useFrame(({ camera, controls }) => {
    const target = (
      controls as { target?: { x: number; y: number; z: number } } | null
    )?.target;
    const direction: [number, number, number] =
      target === undefined || target === null
        ? [camera.position.x, camera.position.y, camera.position.z]
        : [
            camera.position.x - target.x,
            camera.position.y - target.y,
            camera.position.z - target.z,
          ];
    const next = backdropFor(
      direction,
      camera instanceof OrthographicCamera,
      live.current,
    );
    const changed =
      (next === null) !== (live.current === null) ||
      (next !== null &&
        live.current !== null &&
        (next.axis !== live.current.axis || next.side !== live.current.side));
    if (!changed) return;
    live.current = next;
    setBackdrop(next);
    onBackdropChange?.(
      next === null ? "none" : `${next.axis}${next.side > 0 ? "+" : "-"}`,
    );
  });

  // POST-COMMIT FRAME, and it is not a precaution — it is a defect this cost a
  // measurement to find. The scene is `frameloop="demand"`, and the decision
  // above is taken inside `useFrame`: by the time React has committed the
  // sheet's mount or unmount, the frames that the camera change asked for have
  // already been drawn, and nothing asks for another. The live scene graph is
  // then correct while the CANVAS still shows the previous state — measured on
  // the way back from front-ortho to front-perspective, where the probe
  // reported no backdrop in the graph and the frame carried 23 382 drawn
  // pixels against the 10 566 that view actually has. A user toggling
  // projection would have kept a drafting board on screen until something else
  // happened to redraw. Same seam, same reason, as `ModelMesh`'s post-commit
  // invalidate.
  useEffect(() => {
    invalidate();
  }, [backdrop, invalidate]);

  const pose = useMemo(
    () =>
      backdrop === null
        ? null
        : backdropPose(
            backdrop,
            bounds === null || bounds.isEmpty()
              ? null
              : {
                  min: [bounds.min.x, bounds.min.y, bounds.min.z],
                  max: [bounds.max.x, bounds.max.y, bounds.max.z],
                },
          ),
    [backdrop, bounds],
  );
  const quaternion = useMemo(
    () => (pose === null ? null : sheetQuaternion(pose.normal)),
    [pose],
  );
  if (pose === null || quaternion === null) return null;
  return (
    // Named for the scene probe: the DRAWN sheet, as distinct from the
    // `data-bench-backdrop` stamp, which is only what the rig DECIDED. A gate
    // that reads one and trusts the other cannot see them disagree.
    <group name="bench-backdrop">
      <AdaptiveGrid
        position={pose.position}
        quaternion={quaternion}
        cellSize={CELL_MM}
        sectionSize={SECTION_MM}
        cellColor={viewport.gridMinor}
        sectionColor={viewport.gridMajor}
      />
    </group>
  );
}
