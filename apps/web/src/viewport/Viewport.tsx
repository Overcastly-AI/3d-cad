import { viewport } from "@loft/design/tokens";
import { Grid, OrbitControls } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { useCallback, useEffect, useState } from "react";
import { PerspectiveCamera, Vector3, type BufferGeometry } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";

import { useReducedMotion } from "../lib/useReducedMotion";
import { ModelMesh } from "./ModelMesh";

/** Fits camera + orbit target to the current model whenever it changes. */
function FitCamera({ geometry }: { geometry: BufferGeometry | null }) {
  const camera = useThree((state) => state.camera);
  const controls = useThree(
    (state) => state.controls,
  ) as OrbitControlsImpl | null;
  const invalidate = useThree((state) => state.invalidate);

  useEffect(() => {
    const box = geometry?.boundingBox;
    if (!box) {
      return;
    }
    const center = box.getCenter(new Vector3());
    const diagonal = box.getSize(new Vector3()).length();
    const offset = new Vector3(1, 0.68, 1.35)
      .normalize()
      .multiplyScalar(diagonal * 1.75);
    camera.position.copy(center).add(offset);
    if (camera instanceof PerspectiveCamera) {
      camera.near = Math.max(diagonal / 100, 0.01);
      camera.far = diagonal * 50;
      camera.updateProjectionMatrix();
    }
    if (controls) {
      controls.target.copy(center);
      controls.update();
    } else {
      camera.lookAt(center);
    }
    invalidate();
  }, [geometry, camera, controls, invalidate]);

  return null;
}

export interface ViewportProps {
  glb: ArrayBuffer | undefined;
}

/**
 * The hero. Server-tessellated GLB in a token-lit studio: gun-blued ground,
 * machined-aluminum model, mm grid. Every color comes from
 * `@loft/design/tokens` — one palette, two renderers.
 */
export function Viewport({ glb }: ViewportProps) {
  const reducedMotion = useReducedMotion();
  const [geometry, setGeometry] = useState<BufferGeometry | null>(null);
  const handleGeometry = useCallback(
    (next: BufferGeometry) => setGeometry(next),
    [],
  );

  return (
    <div
      className="relative h-full min-h-0 grow"
      data-testid="viewport"
      aria-label="3D viewport showing the tessellated model"
    >
      <Canvas
        className="!absolute inset-0"
        frameloop="demand"
        dpr={[1, 2]}
        gl={{ antialias: true, preserveDrawingBuffer: true }}
        camera={{ fov: 40, position: [45, 32, 60] }}
      >
        <color attach="background" args={[viewport.background]} />
        {/* Soft studio: warm key, cool fill, quiet ambient. */}
        <ambientLight color={viewport.lightFill} intensity={0.55} />
        <directionalLight
          color={viewport.lightKey}
          position={[60, 90, 120]}
          intensity={1.5}
        />
        <directionalLight
          color={viewport.lightFill}
          position={[-80, 40, -60]}
          intensity={0.45}
        />
        <Grid
          position={[0, -0.05, 0]}
          cellSize={5}
          sectionSize={25}
          cellColor={viewport.gridMinor}
          sectionColor={viewport.gridMajor}
          fadeDistance={420}
          fadeStrength={1.2}
          infiniteGrid
        />
        {glb ? <ModelMesh glb={glb} onGeometry={handleGeometry} /> : null}
        <FitCamera geometry={geometry} />
        <OrbitControls makeDefault enableDamping={!reducedMotion} />
      </Canvas>
    </div>
  );
}
