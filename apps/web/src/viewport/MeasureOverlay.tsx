/**
 * The measurement overlay inside the WebGL viewport.
 *
 * EDGES are hit-tested by the edge itself: an invisible screen-space band
 * follows every polyline (`EdgeBandLayer`, SEL-4), so a measurement can be
 * taken by clicking anywhere along an edge. VERTICES are hit-tested by their
 * `PickNode` alone, which is the honest model for a point — see the comment on
 * the vertex nodes below. Neither is offered for a SWITCHED-OFF body
 * (`hiddenPicks.ts`).
 *
 * Both kinds still carry a DOM-in-canvas `PickNode` via drei `Html` — real
 * buttons, so picking is keyboard-navigable, screen-reader named, and
 * e2e-drivable — while the edge highlights and the dimension line are canvas
 * draws in the shared `measure` tokens (one palette, un-tonemapped so the hue
 * lands exactly). The dimension line ignores depth and draws last, so a
 * measurement is never hidden by the part it measures.
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
import { EdgeBandLayer } from "./EdgeBandLayer";
import type { EdgeBandInput } from "./edgeBand";
import { useHiddenPicks } from "./hiddenPicks";
import { concatPositions, Segments } from "./overlaySegments";
import { useViewportPickStamp } from "./pickStamp";

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
  const hiddenPicks = useHiddenPicks();

  /** QA hook: which edge the measurement is addressing (SEL-4 / A2). */
  useViewportPickStamp("measureEdgeHover", active ? hoverEdge : null);

  /**
   * The entities ON OFFER, each keeping its overlay index — that index is what
   * a measurement is taken BY (`EdgeTarget.index`), so filtering may thin these
   * lists but must never renumber them. A switched-off body leaves the offer
   * with its edges and its snap points: measuring geometry you cannot see is
   * the same defect as picking it (SEL-6's mirror half), and the band's 24 px
   * corridor made it easy to do by accident.
   */
  const offeredEdges = useMemo(
    () =>
      overlay === null
        ? []
        : overlay.edges.flatMap((edge, index) =>
            hiddenPicks.isHiddenEdge(edge.polyline) ? [] : [{ edge, index }],
          ),
    [overlay, hiddenPicks],
  );
  const offeredVertices = useMemo(
    () =>
      overlay === null
        ? []
        : overlay.vertices.flatMap((vertex: Vec3, index) =>
            hiddenPicks.isHiddenPoint(vertex) ? [] : [{ vertex, index }],
          ),
    [overlay, hiddenPicks],
  );

  // frameloop="demand": redraw when the pick/hover/result state changes —
  // including the OFFER, since switching a body off changes what is drawn.
  useEffect(() => {
    invalidate();
  }, [
    active,
    offeredEdges,
    offeredVertices,
    picks,
    hoverEdge,
    result,
    invalidate,
  ]);

  const bandEdges = useMemo<EdgeBandInput[]>(
    () =>
      offeredEdges.map(({ edge, index }) => ({
        index,
        polyline: edge.polyline,
      })),
    [offeredEdges],
  );

  const selectedVertices = useMemo(
    () => new Set(picks.flatMap((p) => (p.kind === "vertex" ? [p.index] : []))),
    [picks],
  );
  const selectedEdges = useMemo(
    () => new Set(picks.flatMap((p) => (p.kind === "edge" ? [p.index] : []))),
    [picks],
  );

  // The highlights follow the OFFER: a picked edge whose body is switched off
  // keeps its pick (showing the body restores it) but must not keep drawing
  // brass where the body no longer is.
  const selectedEdgePositions = useMemo(
    () =>
      concatPositions(
        offeredEdges
          .filter(({ index }) => selectedEdges.has(index))
          .map(({ edge }) => polylineSegments(edge.polyline)),
      ),
    [offeredEdges, selectedEdges],
  );

  const hoveredEdgePositions = useMemo(() => {
    if (hoverEdge === null || selectedEdges.has(hoverEdge)) {
      return new Float32Array(0);
    }
    const hit = offeredEdges.find(({ index }) => index === hoverEdge);
    return hit === undefined
      ? new Float32Array(0)
      : polylineSegments(hit.edge.polyline);
  }, [offeredEdges, hoverEdge, selectedEdges]);

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
      {/* The hit-test: a 24 px screen-space corridor along every edge. */}
      <EdgeBandLayer
        edges={bandEdges}
        onHover={setHoverEdge}
        onPick={pickEdge}
      />

      {/* Edge highlights (hover under selection). */}
      <Segments positions={hoveredEdgePositions} color={measure.edgeHover} />
      <Segments
        positions={selectedEdgePositions}
        color={measure.edgeSelected}
      />

      {/* Pickable edges — diamond marks at each edge's TRUE mid-span. Rendered
          BEFORE the vertices (and in a lower z band) so a corner click resolves
          to the vertex, an edge-midspan click to the edge.

          WIDENING THE EDGES DOES NOT COST THE VERTICES THEIR PRECEDENCE, and
          the reason is mechanical rather than a tuned z-order: a `PickNode`
          lives in a drei `Html` layer ABOVE the canvas, so a pointer over a
          vertex square is consumed by the DOM and never reaches r3f at all —
          the band cannot steal it. The `VERTEX_Z_RANGE` / `EDGE_Z_RANGE` split
          still settles edge-mark versus vertex-mark, which is a DOM-to-DOM
          contest. Asserted in `pick-affordance.spec.ts`, not assumed. */}
      {offeredEdges.map(({ edge, index }) => (
        <Html
          key={`e${index}`}
          position={occtToScene(polylineMidpoint(edge.polyline))}
          center
          zIndexRange={EDGE_Z_RANGE}
        >
          <PickNode
            shape="edge"
            // A7's recession: the edge band is this pick's primary hit-test
            // now, so the mark is the keyboard/touch fallback.
            recede
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
          band so they always win the hit-test against a nearby edge mark.

          THEY PASS NO `recede`, deliberately (SEL-4 / A7). A projected point
          has no "true boundary" to raycast — a 24 px square around it already
          IS a ~12 px screen-space proximity test — so this button is still the
          SOLE hit-test here. Dimming it would dim the aim affordance itself,
          which is the exact trade A7 refuses (`PickNode.tsx`'s opacity block
          states the same rule from the primitive's side). */}
      {offeredVertices.map(({ vertex, index }) => (
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
