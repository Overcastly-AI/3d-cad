/**
 * Point-dimension ink (SKETCH-POINT-DISTANCE): the dimension and extension
 * lines that say what a point-to-point or point-to-line number measures, and
 * the live preview while a two-point dimension's label is being placed — the
 * label follows the pointer and the direction (aligned / horizontal /
 * vertical) follows Fusion's rule, so what the click will make is on screen
 * before it is made. The geometry is `sketch/pointDimension.ts`; this only
 * renders it.
 */
import { sketch } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useEffect, useMemo } from "react";
import { BufferGeometry, Float32BufferAttribute } from "three";

import { formatDimensionMm } from "../sketch/constraints";
import { datumFrame, withDatums } from "../sketch/datum";
import { planeToWorld, type PlaneBasis } from "../sketch/plane";
import {
  measurePointDimension,
  operandPoint,
  placementDirection,
  pointDimensionInk,
  pointDimensionLayout,
  type InkSegment,
  type PointDimensionSubject,
} from "../sketch/pointDimension";
import { useSketchStore } from "../sketch/store";

/** Above the sketch ink (900) and its points (901), like every annotation. */
const INK_RENDER_ORDER = 902;
const LABEL_Z_RANGE: [number, number] = [20, 0];

function Segments({
  basis,
  segments,
  color,
}: {
  basis: PlaneBasis;
  segments: readonly InkSegment[];
  color: string;
}) {
  const geometry = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute(
      "position",
      new Float32BufferAttribute(
        segments.flatMap(([from, to]) => [
          ...planeToWorld(basis, from),
          ...planeToWorld(basis, to),
        ]),
        3,
      ),
    );
    return g;
  }, [segments, basis]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  if (segments.length === 0) return null;
  return (
    <lineSegments
      geometry={geometry}
      frustumCulled={false}
      renderOrder={INK_RENDER_ORDER}
    >
      <lineBasicMaterial
        color={color}
        toneMapped={false}
        depthTest={false}
        depthWrite={false}
        transparent
      />
    </lineSegments>
  );
}

/** The label being placed: follows the pointer, shows the direction it makes. */
function PlacementPreview({ basis }: { basis: PlaneBasis }) {
  const placing = useSketchStore((state) => state.dimensionPlace);
  const cursor = useSketchStore((state) => state.cursor);
  const entities = useSketchStore((state) => state.entities);
  const frameHalfMm = useSketchStore((state) => state.datumFrameHalfMm);
  const preview = useMemo(() => {
    if (placing === null || cursor === null) return null;
    const byId = new Map(
      withDatums(entities, datumFrame(frameHalfMm)).map((e) => [e.id, e]),
    );
    const a = operandPoint(placing.a, byId);
    const b = operandPoint(placing.b, byId);
    if (a === null || b === null) return null;
    const direction = placementDirection(a, b, cursor);
    const subject: PointDimensionSubject = {
      kind: "point_distance",
      a: placing.a,
      b: placing.b,
      direction,
    };
    const layout = pointDimensionLayout(subject, byId, sketch.glyphOffsetMm);
    return {
      direction,
      value: measurePointDimension(subject, byId) ?? 0,
      ink: layout?.ink ?? [],
    };
  }, [placing, cursor, entities, frameHalfMm]);
  if (preview === null || cursor === null) return null;
  return (
    <group>
      <Segments
        basis={basis}
        segments={preview.ink}
        color={sketch.glyphDimension}
      />
      <Html
        position={planeToWorld(basis, cursor)}
        zIndexRange={LABEL_Z_RANGE}
        style={{ pointerEvents: "none" }}
      >
        <span
          data-testid="dimension-place"
          data-direction={preview.direction}
          className="ml-2 block whitespace-nowrap font-mono text-2xs text-brass"
        >
          {formatDimensionMm(preview.value)} · {preview.direction}
        </span>
      </Html>
    </group>
  );
}

export function PointDimensionInk({ basis }: { basis: PlaneBasis }) {
  const constraints = useSketchStore((state) => state.constraints);
  const entities = useSketchStore((state) => state.entities);
  const frameHalfMm = useSketchStore((state) => state.datumFrameHalfMm);
  const ink = useMemo(
    () =>
      pointDimensionInk(
        constraints,
        withDatums(entities, datumFrame(frameHalfMm)),
        sketch.glyphOffsetMm,
      ),
    [constraints, entities, frameHalfMm],
  );
  return (
    <group>
      <Segments basis={basis} segments={ink} color={sketch.glyph} />
      <PlacementPreview basis={basis} />
    </group>
  );
}
