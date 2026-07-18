/**
 * The edge-pick overlay inside the WebGL viewport — the "Pick edges" step of
 * the Fillet / Chamfer editors. Every B-rep edge of the current body gets a
 * DOM-in-canvas `PickNode` diamond (drei `Html`) at its true mid-span, so
 * picking is keyboard-navigable, screen-reader named, and e2e-drivable — the
 * same posture as the measurement overlay's edge marks. Clicking toggles that
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
import { useEffect, useMemo } from "react";

import type { Vec3 } from "../api/measure";
import { edgeSignatureKey } from "../features/edge";
import { useEdgePickStore } from "../features/edgePickStore";
import {
  occtToScene,
  polylineMidpoint,
  polylineSegments,
} from "../measure/geometry";
import { concatPositions, Segments } from "./overlaySegments";

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

  const pickedKeys = useMemo(
    () => new Set(picked.map(edgeSignatureKey)),
    [picked],
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
