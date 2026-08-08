/**
 * The edge-pick overlay inside the WebGL viewport — the "Pick edges" step of
 * the Fillet / Chamfer / edge-flange / hem editors. The EDGE ITSELF is the
 * hit-test: an invisible screen-space band follows every polyline
 * (`EdgeBandLayer`, SEL-4), so a click anywhere along an edge picks it. Every
 * edge also carries a DOM-in-canvas `PickNode` diamond (drei `Html`) at its
 * true mid-span, which is now the keyboard focus target, the screen-reader name
 * and the touch tap target rather than the way you aim. Clicking toggles that
 * edge into the picked set; the fillet/chamfer then rounds ONLY those edges.
 *
 * The highlight draws (selected = brass, hover = brass-hover) reuse the shared
 * `measure` tokens and the shared `Segments` layer — one selection palette, one
 * highlight primitive across both overlays (CLAUDE.md DRY rule). Selection is
 * keyed by full-precision `EdgeSignature`, never the transient overlay index,
 * so a refetch never mismarks a pick. Presentational only: the parent store
 * owns the picked set + hover.
 */
import { PickNode } from "@loft/design";
import { measure } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo } from "react";

import type { Vec3 } from "../api/measure";
import { edgeSignatureKey } from "../features/edge";
import { useEdgePickStore } from "../features/edgePickStore";
import {
  occtToScene,
  polylineMidpoint,
  polylineSegments,
} from "../measure/geometry";
import { EdgeBandLayer } from "./EdgeBandLayer";
import type { EdgeBandInput } from "./edgeBand";
import { concatPositions, Segments } from "./overlaySegments";
import { useViewportPickStamp } from "./pickStamp";

/** Edge marks sit just under the HUD strips (same band as measurement edges). */
const EDGE_Z_RANGE: [number, number] = [17, 0];

/** A located accessible name for a pickable edge (from its OCCT mid-span). */
function edgeLabel(index: number, kind: string, midpoint: Vec3): string {
  const round = (n: number) => Math.round(n * 10) / 10;
  return `Edge ${index + 1}, ${kind}, centred at ${round(midpoint.x)}, ${round(midpoint.y)}, ${round(midpoint.z)} millimetres`;
}

export function EdgePickOverlay() {
  const overlay = useEdgePickStore((s) => s.overlay);
  const picked = useEdgePickStore((s) => s.picked);
  const hoverEdge = useEdgePickStore((s) => s.hoverEdge);
  const toggle = useEdgePickStore((s) => s.toggle);
  const setHoverEdge = useEdgePickStore((s) => s.setHoverEdge);
  const invalidate = useThree((s) => s.invalidate);

  // frameloop="demand": redraw when the pick/hover set changes.
  useEffect(() => {
    invalidate();
  }, [overlay, picked, hoverEdge, invalidate]);

  /** QA hook: which edge the armed pick is addressing (SEL-4 / A2). */
  useViewportPickStamp("edgePickHover", hoverEdge);

  const pickedKeys = useMemo(
    () => new Set(picked.map(edgeSignatureKey)),
    [picked],
  );

  /** Every edge is bandable — the picked set is a choice, not a filter. */
  const bandEdges = useMemo<EdgeBandInput[]>(
    () =>
      overlay === null
        ? []
        : overlay.edges.map((edge, index) => ({
            index,
            polyline: edge.polyline,
          })),
    [overlay],
  );

  const pickBandEdge = useCallback(
    (index: number) => {
      const edge = overlay?.edges[index];
      if (edge !== undefined) toggle(edge.signature);
    },
    [overlay, toggle],
  );

  const selectedPositions = useMemo(() => {
    if (overlay === null) return new Float32Array(0);
    return concatPositions(
      overlay.edges
        .filter((edge) => pickedKeys.has(edgeSignatureKey(edge.signature)))
        .map((edge) => polylineSegments(edge.polyline)),
    );
  }, [overlay, pickedKeys]);

  const hoveredPositions = useMemo(() => {
    if (overlay === null || hoverEdge === null) return new Float32Array(0);
    const edge = overlay.edges[hoverEdge];
    if (
      edge === undefined ||
      pickedKeys.has(edgeSignatureKey(edge.signature))
    ) {
      return new Float32Array(0);
    }
    return polylineSegments(edge.polyline);
  }, [overlay, hoverEdge, pickedKeys]);

  if (overlay === null) return null;

  return (
    <group>
      {/* The hit-test: a 24 px screen-space corridor along every edge. */}
      <EdgeBandLayer
        edges={bandEdges}
        onHover={setHoverEdge}
        onPick={pickBandEdge}
      />

      {/* Highlights (hover under selection), brass token — one palette. */}
      <Segments positions={hoveredPositions} color={measure.edgeHover} />
      <Segments positions={selectedPositions} color={measure.edgeSelected} />

      {/* Pickable edges — a diamond mark at each edge's true mid-span. */}
      {overlay.edges.map((edge, index) => {
        const midpoint = polylineMidpoint(edge.polyline);
        return (
          <Html
            key={`e${index}`}
            position={occtToScene(midpoint)}
            center
            zIndexRange={EDGE_Z_RANGE}
          >
            <PickNode
              shape="edge"
              // A7's recession: the edge band is this pick's primary hit-test
              // now, so the mark is the keyboard/touch fallback and may rest
              // quiet.
              recede
              selected={pickedKeys.has(edgeSignatureKey(edge.signature))}
              data-testid={`edge-pick-${index}`}
              aria-label={edgeLabel(index, edge.kind, midpoint)}
              onClick={() => toggle(edge.signature)}
              onPointerOver={() => setHoverEdge(index)}
              onPointerOut={() => setHoverEdge(null)}
              onFocus={() => setHoverEdge(index)}
              onBlur={() => setHoverEdge(null)}
            />
          </Html>
        );
      })}
    </group>
  );
}
