/**
 * The measurement overlay inside the WebGL viewport. Pickable vertices and
 * edges are DOM-in-canvas via drei `Html` — real buttons, so picking is
 * keyboard-navigable, screen-reader named, and e2e-drivable — while the edge
 * highlights and the dimension line are canvas draws in the shared `measure`
 * tokens (one palette, un-tonemapped so the hue lands exactly). The dimension
 * line ignores depth and draws last, so a measurement is never hidden by the
 * part it measures.
 */
import { PickNode } from "@loft/design";
import { measure } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import { BufferGeometry, Float32BufferAttribute } from "three";

import type { Vec3 } from "../api/measure";
import {
  formatVec3Mm,
  occtToScene,
  polylineMidpoint,
  polylineSegments,
} from "../measure/geometry";
import { useMeasureStore } from "../measure/store";
import { concatPositions, Segments } from "./overlaySegments";

/**
 * Overlay pick-node stacking, kept under the HUD strips (Viewport hud sits at
 * z-40). Vertices occupy a strictly higher band than edges so that when an edge
 * mark lands near a corner (a short edge's mid-span), a real click on the corner
 * still resolves to the VERTEX — vertices win both the DOM order (rendered last)
 * and the z-index. Both bands stay below the HUD.
 */
const VERTEX_Z_RANGE: [number, number] = [36, 18];
const EDGE_Z_RANGE: [number, number] = [17, 0];

/** Witness marks (screen-space points) with disposal. */
function Marks({
  positions,
  color,
  sizePx,
  renderOrder = 0,
}: {
  positions: Float32Array;
  color: string;
  sizePx: number;
  renderOrder?: number;
}) {
  const geometry = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute("position", new Float32BufferAttribute(positions, 3));
    return g;
  }, [positions]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  if (positions.length === 0) return null;
  return (
    <points geometry={geometry} frustumCulled={false} renderOrder={renderOrder}>
      <pointsMaterial
        color={color}
        size={sizePx}
        sizeAttenuation={false}
        toneMapped={false}
        depthTest={false}
        depthWrite={false}
        transparent
      />
    </points>
  );
}

export function MeasureOverlay() {
  const active = useMeasureStore((s) => s.active);
  const overlay = useMeasureStore((s) => s.overlay);
  const picks = useMeasureStore((s) => s.picks);
  const hoverEdge = useMeasureStore((s) => s.hoverEdge);
  const result = useMeasureStore((s) => s.result);
  const pickVertex = useMeasureStore((s) => s.pickVertex);
  const pickEdge = useMeasureStore((s) => s.pickEdge);
  const setHoverEdge = useMeasureStore((s) => s.setHoverEdge);
  const invalidate = useThree((s) => s.invalidate);

  // frameloop="demand": redraw when the pick/hover/result state changes.
  useEffect(() => {
    invalidate();
  }, [active, overlay, picks, hoverEdge, result, invalidate]);

  const selectedVertices = useMemo(
    () => new Set(picks.flatMap((p) => (p.kind === "vertex" ? [p.index] : []))),
    [picks],
  );
  const selectedEdges = useMemo(
    () => new Set(picks.flatMap((p) => (p.kind === "edge" ? [p.index] : []))),
    [picks],
  );

  const selectedEdgePositions = useMemo(() => {
    if (overlay === null) return new Float32Array(0);
    return concatPositions(
      [...selectedEdges].map((i) =>
        polylineSegments(overlay.edges[i]?.polyline ?? []),
      ),
    );
  }, [overlay, selectedEdges]);

  const hoveredEdgePositions = useMemo(() => {
    if (
      overlay === null ||
      hoverEdge === null ||
      selectedEdges.has(hoverEdge)
    ) {
      return new Float32Array(0);
    }
    return polylineSegments(overlay.edges[hoverEdge]?.polyline ?? []);
  }, [overlay, hoverEdge, selectedEdges]);

  const dimensionPositions = useMemo(() => {
    if (result === null) return new Float32Array(0);
    const out = new Float32Array(6);
    out.set(occtToScene(result.point_on_a), 0);
    out.set(occtToScene(result.point_on_b), 3);
    return out;
  }, [result]);

  if (!active || overlay === null) return null;

  return (
    <group>
      {/* Edge highlights (hover under selection). */}
      <Segments positions={hoveredEdgePositions} color={measure.edgeHover} />
      <Segments
        positions={selectedEdgePositions}
        color={measure.edgeSelected}
      />

      {/* Pickable edges — diamond marks at each edge's TRUE mid-span. Rendered
          BEFORE the vertices (and in a lower z band) so a corner click resolves
          to the vertex, an edge-midspan click to the edge. */}
      {overlay.edges.map((edge, index) => (
        <Html
          key={`e${index}`}
          position={occtToScene(polylineMidpoint(edge.polyline))}
          center
          zIndexRange={EDGE_Z_RANGE}
        >
          <PickNode
            shape="edge"
            selected={selectedEdges.has(index)}
            data-testid={`measure-edge-${index}`}
            aria-label={`Edge ${index + 1}, ${edge.kind}`}
            onClick={() => pickEdge(index)}
            onPointerOver={() => setHoverEdge(index)}
            onPointerOut={() => setHoverEdge(null)}
            onFocus={() => setHoverEdge(index)}
            onBlur={() => setHoverEdge(null)}
          />
        </Html>
      ))}

      {/* Pickable vertices — round snap nodes, rendered LAST + in the higher z
          band so they always win the hit-test against a nearby edge mark. */}
      {overlay.vertices.map((vertex: Vec3, index) => (
        <Html
          key={`v${index}`}
          position={occtToScene(vertex)}
          center
          zIndexRange={VERTEX_Z_RANGE}
        >
          <PickNode
            shape="vertex"
            selected={selectedVertices.has(index)}
            data-testid={`measure-vertex-${index}`}
            aria-label={`Vertex at ${formatVec3Mm(vertex)} millimetres`}
            onClick={() => pickVertex(index, vertex)}
          />
        </Html>
      ))}

      {/* The dimension line + witness marks — brass, always on top. */}
      <Segments
        positions={dimensionPositions}
        color={measure.dimension}
        depthTest={false}
        renderOrder={999}
      />
      <Marks
        positions={dimensionPositions}
        color={measure.dimension}
        sizePx={measure.witnessSizePx}
        renderOrder={1000}
      />
    </group>
  );
}
