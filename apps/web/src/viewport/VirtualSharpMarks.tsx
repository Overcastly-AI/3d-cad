/**
 * Virtual-sharp marks (SKETCH-FILLET-KEEP-DIMS): where a dimension is measured
 * to a corner a fillet or chamfer removed, draw that corner the way Fusion 360
 * does — a small point where the extended legs meet, with each leg's extension
 * to it as fine dashed ink — so the user can see what W and H are anchored to.
 * The geometry is `sketch/virtualSharp.ts`; this only renders it.
 */
import { sketch } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useEffect, useMemo, useRef } from "react";
import {
  BufferGeometry,
  Float32BufferAttribute,
  type LineSegments,
} from "three";

import { planeToWorld, type PlaneBasis } from "../sketch/plane";
import { useSketchStore } from "../sketch/store";
import { virtualSharpMarks } from "../sketch/virtualSharp";

/** Above the sketch ink (900) and its points (901), like every annotation. */
const MARK_RENDER_ORDER = 902;
/** Under the HUD strips, with the glyphs (ConstraintGlyphs' GLYPH_Z_RANGE). */
const MARK_Z_RANGE: [number, number] = [20, 0];

export function VirtualSharpMarks({ basis }: { basis: PlaneBasis }) {
  const constraints = useSketchStore((state) => state.constraints);
  const entities = useSketchStore((state) => state.entities);
  const marks = useMemo(
    () => virtualSharpMarks(constraints, entities),
    [constraints, entities],
  );
  const geometry = useMemo(() => {
    const positions = marks.flatMap((mark) =>
      mark.extensions.flatMap(([from, to]) => [
        ...planeToWorld(basis, from),
        ...planeToWorld(basis, to),
      ]),
    );
    const g = new BufferGeometry();
    g.setAttribute("position", new Float32BufferAttribute(positions, 3));
    return g;
  }, [marks, basis]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  const lines = useRef<LineSegments>(null);
  useEffect(() => {
    lines.current?.computeLineDistances();
  }, [geometry]);

  if (marks.length === 0) return null;
  return (
    <group>
      <lineSegments
        ref={lines}
        geometry={geometry}
        frustumCulled={false}
        renderOrder={MARK_RENDER_ORDER}
      >
        <lineDashedMaterial
          color={sketch.constructionInk}
          dashSize={sketch.constructionDashMm}
          gapSize={sketch.constructionGapMm}
          toneMapped={false}
          depthTest={false}
          depthWrite={false}
          transparent
        />
      </lineSegments>
      {marks.map((mark) => (
        <Html
          key={mark.key}
          position={planeToWorld(basis, mark.at)}
          center
          zIndexRange={MARK_Z_RANGE}
          style={{ pointerEvents: "none" }}
        >
          <span
            data-testid="virtual-sharp"
            aria-label="Virtual sharp"
            role="img"
            className="block h-1.5 w-1.5 rounded-full bg-brass"
          />
        </Html>
      ))}
    </group>
  );
}
