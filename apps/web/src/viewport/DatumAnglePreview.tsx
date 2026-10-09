/**
 * The plane-at-an-angle preview (DATUM-PLANE-ANGLE): the plane the datum
 * editor's current form resolves to, drawn as a square OUTLINE through its
 * line while the editor is open — the same "about to be" line-work the offset
 * datum's preview uses (`DatumGauge`), so an engineer sees where the plane
 * lands before Save. No gauge: the offset gauge is linear, and an angle has
 * no instrument to stand on yet.
 *
 * The square is centred on the plane's origin (the point of its line nearest
 * the world origin) and squared to its axes: u along the line, v across it.
 */
import { addScaled, type Vec3 } from "@loft/design";
import { viewport } from "@loft/design/tokens";
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";

import type { PlaneBasis } from "../sketch/plane";
import { DATUM_SHEET_HALF_MM } from "./faceAnchor";
import { Segments } from "./overlaySegments";

/** A square outline of half-side `half` on `basis`, as segment pairs. */
export function planeOutline(basis: PlaneBasis, half: number): Float32Array {
  const { origin, u, v } = basis;
  const corners: Vec3[] = [
    addScaled(addScaled(origin, u, -half), v, -half),
    addScaled(addScaled(origin, u, half), v, -half),
    addScaled(addScaled(origin, u, half), v, half),
    addScaled(addScaled(origin, u, -half), v, half),
  ];
  const out = new Float32Array(corners.length * 6);
  for (let i = 0; i < corners.length; i += 1) {
    out.set(corners[i] as Vec3, i * 6);
    out.set(corners[(i + 1) % corners.length] as Vec3, i * 6 + 3);
  }
  return out;
}

export function DatumAnglePreview({ basis }: { basis: PlaneBasis }) {
  const invalidate = useThree((state) => state.invalidate);
  const outline = useMemo(
    () => planeOutline(basis, DATUM_SHEET_HALF_MM * 2),
    [basis],
  );
  useEffect(() => {
    invalidate();
  }, [outline, invalidate]);
  return (
    <group name="datum-angle-sheet">
      <Segments
        positions={outline}
        color={viewport.preview.edge}
        opacity={viewport.preview.edgeOpacity}
        depthTest={false}
        renderOrder={11}
      />
    </group>
  );
}
