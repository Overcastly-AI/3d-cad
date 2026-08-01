/**
 * The horizon-persistent grid (Batch 1 makeover; UI-REVIEW 2026-07-16 P0-1).
 * drei's Grid fades at a FIXED distance, so zooming out (or a large part)
 * used to leave the middle of the frame gridded and everything beyond it
 * flat void. This wrapper scales the fade with the camera's orbit radius
 * every frame — the grid always reads to the horizon, at desk scale and at
 * machine scale alike. Allocation-free: it pokes the shader uniform on the
 * existing material; `followCamera` keeps the (world-anchored) plane under
 * the camera so the sheet itself never ends.
 */
import { Grid } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import type { Mesh, Quaternion, ShaderMaterial } from "three";

export interface AdaptiveGridProps {
  /** Minor cell edge (mm). */
  cellSize: number;
  /** Major section edge (mm). */
  sectionSize: number;
  cellColor: string;
  sectionColor: string;
  position?: readonly [number, number, number];
  quaternion?: Quaternion;
  /**
   * This grid is laid ON a surface (the sketcher's plane grid sits on the model
   * face being sketched), so bias it toward the camera in depth-buffer units to
   * break the coplanar tie. Depth TESTING stays on — anything genuinely in
   * front still occludes it. Off for the world grid, which is coplanar with
   * nothing. drei's `Grid` does not forward material props, so it is set on the
   * material directly; polygon offset is read per-draw by WebGLState, so no
   * shader recompile is involved.
   */
  coplanar?: boolean;
}

/** Fade reaches this many orbit radii — past the frame edge at any zoom. */
const FADE_RADII = 7;
/** Fade floor (mm) so a tight zoom-in never collapses the horizon. */
const MIN_FADE_MM = 600;

export function AdaptiveGrid({
  cellSize,
  sectionSize,
  cellColor,
  sectionColor,
  position,
  quaternion,
  coplanar = false,
}: AdaptiveGridProps) {
  const ref = useRef<Mesh>(null);

  useEffect(() => {
    const material = ref.current?.material as ShaderMaterial | undefined;
    if (material === undefined) return;
    material.polygonOffset = coplanar;
    material.polygonOffsetFactor = coplanar ? -2 : 0;
    material.polygonOffsetUnits = coplanar ? -2 : 0;
  }, [coplanar]);

  useFrame(({ camera, controls }) => {
    const mesh = ref.current;
    if (mesh === null) return;
    const material = mesh.material as ShaderMaterial;
    const fade = material.uniforms["fadeDistance"];
    if (fade === undefined) return;
    // Orbit radius: distance to the controls target (fall back to the origin
    // via the camera's distance to world zero — length()).
    const target = (
      controls as { target?: { x: number; y: number; z: number } } | null
    )?.target;
    const radius =
      target !== undefined && target !== null
        ? Math.hypot(
            camera.position.x - target.x,
            camera.position.y - target.y,
            camera.position.z - target.z,
          )
        : camera.position.length();
    fade.value = Math.max(MIN_FADE_MM, radius * FADE_RADII);
  });

  return (
    <Grid
      ref={ref}
      position={position ? [position[0], position[1], position[2]] : undefined}
      quaternion={quaternion}
      cellSize={cellSize}
      sectionSize={sectionSize}
      cellColor={cellColor}
      sectionColor={sectionColor}
      fadeDistance={MIN_FADE_MM}
      fadeStrength={1.1}
      followCamera
      infiniteGrid
    />
  );
}
