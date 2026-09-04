/**
 * The edge-pick overlay inside the WebGL viewport — the "Pick edges" step of
 * the Fillet / Chamfer / edge-flange / hem editors. The EDGE ITSELF is the
 * hit-test: an invisible screen-space band follows every polyline
 * (`EdgeBandLayer`, SEL-4), so a click anywhere along an edge picks it. Every
 * edge also carries a DOM-in-canvas `PickNode` diamond (drei `Html`) at its
 * true mid-span, which is now the keyboard focus target, the screen-reader name
 * and the touch tap target rather than the way you aim. Clicking toggles that
 * edge into the picked set; the fillet/chamfer then rounds ONLY those edges.
 * Edges of a SWITCHED-OFF body are not offered at all (`hiddenPicks.ts`) —
 * neither corridor, nor mark, nor highlight.
 *
 * The highlight draws (selected = brass, hover = brass-hover) reuse the shared
 * `measure` tokens and the shared `HighlightLines` layer — one selection
 * palette, one highlight primitive across both overlays (CLAUDE.md DRY rule).
 * `HighlightLines` and not `Segments`: an edge highlight is coincident with the
 * body's own surface, and a plain GL line at that depth is discarded outright
 * (SEL-8 — the hover state was firing all along and drawing nothing).
 *
 * Selection is
 * keyed by full-precision `EdgeSignature`, never the transient overlay index,
 * so a refetch never mismarks a pick. Presentational only: the parent store
 * owns the picked set + hover.
 */
import { PickNode } from "@loft/design";
import { measure } from "@loft/design/tokens";
import { useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useState } from "react";

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
import { useHiddenPicks } from "./hiddenPicks";
import { PickMark } from "./PickMark";
import { concatPositions, HighlightLines } from "./overlaySegments";
import { useViewportPickStamp } from "./pickStamp";
import type { EdgeMarkAnchor } from "./useEdgeMarkAnchors";

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
  const hiddenPicks = useHiddenPicks();
  /**
   * WHERE EACH DIAMOND SITS (PICKMARK-OCCLUDE-1) — published by the band,
   * because the band is what decides whether a point of an edge is reachable.
   * The mid-span is used until the first answer arrives.
   */
  const [anchors, setAnchors] = useState<readonly EdgeMarkAnchor[]>([]);

  /** QA hook: which edge the armed pick is addressing (SEL-4 / A2). */
  useViewportPickStamp("edgePickHover", hoverEdge);

  const pickedKeys = useMemo(
    () => new Set(picked.map(edgeSignatureKey)),
    [picked],
  );

  /**
   * The edges ON OFFER — every edge of a DRAWN body, each keeping its overlay
   * index (that index is the pick's identity, so filtering may thin the list
   * but must never renumber it). A switched-off body's edges leave the offer
   * entirely: SEL-6's first half stopped a hidden body eating the pick behind
   * it, and this is its mirror — an edge you cannot see must not be hoverable
   * through the band's 24 px corridor, nor paint a brass highlight over the
   * empty space where its body used to be.
   */
  const offered = useMemo(() => {
    if (overlay === null) return [];
    return overlay.edges.flatMap((edge, index) =>
      hiddenPicks.isHiddenEdge(edge.polyline) ? [] : [{ edge, index }],
    );
  }, [overlay, hiddenPicks]);

  // frameloop="demand": redraw when the offer / pick / hover set changes —
  // switching a body off changes what is drawn here, not just what is pickable.
  useEffect(() => {
    invalidate();
  }, [offered, picked, hoverEdge, invalidate]);

  /** Every offered edge is bandable — the picked set is a choice, not a filter. */
  const bandEdges = useMemo<EdgeBandInput[]>(
    () =>
      offered.map(({ edge, index }) => ({
        index,
        polyline: edge.polyline,
      })),
    [offered],
  );

  const pickBandEdge = useCallback(
    (index: number) => {
      const edge = overlay?.edges[index];
      if (edge !== undefined) toggle(edge.signature);
    },
    [overlay, toggle],
  );

  // Highlights follow the OFFER, not the store: hiding a body does not unpick
  // its edges (the pick survives showing it again), but their brass must not
  // keep drawing where the body no longer is.
  const selectedPositions = useMemo(
    () =>
      concatPositions(
        offered
          .filter(({ edge }) =>
            pickedKeys.has(edgeSignatureKey(edge.signature)),
          )
          .map(({ edge }) => polylineSegments(edge.polyline)),
      ),
    [offered, pickedKeys],
  );

  const hoveredPositions = useMemo(() => {
    if (hoverEdge === null) return new Float32Array(0);
    const hit = offered.find(({ index }) => index === hoverEdge);
    if (
      hit === undefined ||
      pickedKeys.has(edgeSignatureKey(hit.edge.signature))
    ) {
      return new Float32Array(0);
    }
    return polylineSegments(hit.edge.polyline);
  }, [offered, hoverEdge, pickedKeys]);

  if (overlay === null) return null;

  return (
    <group>
      {/* The hit-test: a 24 px screen-space corridor along every edge. */}
      <EdgeBandLayer
        edges={bandEdges}
        onHover={setHoverEdge}
        onPick={pickBandEdge}
        onAnchors={setAnchors}
      />

      {/* Highlights (hover under selection), brass token — one palette. */}
      <HighlightLines
        positions={hoveredPositions}
        color={measure.edgeHover}
        widthPx={measure.edgeWidthPx}
        xrayOpacity={measure.edgeXrayOpacity}
      />
      <HighlightLines
        positions={selectedPositions}
        color={measure.edgeSelected}
        widthPx={measure.edgeWidthPx}
        xrayOpacity={measure.edgeXrayOpacity}
        renderOrder={2}
      />

      {/* Pickable edges — a diamond mark at the point of each edge the band
          answers with (PICKMARK-OCCLUDE-1). The accessible NAME still carries
          the true mid-span, because the name describes the EDGE and not where
          its mark happens to be reachable from this camera. */}
      {offered.map(({ edge, index }, slot) => {
        const midpoint = polylineMidpoint(edge.polyline);
        const anchor = anchors[slot];
        return (
          <PickMark
            key={`e${index}`}
            position={anchor?.position ?? occtToScene(midpoint)}
            zIndexRange={EDGE_Z_RANGE}
          >
            <PickNode
              shape="edge"
              // A7's recession: the edge band is this pick's primary hit-test
              // now, so the mark is the keyboard/touch fallback and may rest
              // quiet.
              recede
              occluded={anchor?.buried ?? false}
              selected={pickedKeys.has(edgeSignatureKey(edge.signature))}
              data-testid={`edge-pick-${index}`}
              data-buried={anchor?.buried === true ? "true" : "false"}
              aria-label={edgeLabel(index, edge.kind, midpoint)}
              onClick={() => toggle(edge.signature)}
              onPointerOver={() => setHoverEdge(index)}
              onPointerOut={() => setHoverEdge(null)}
              onFocus={() => setHoverEdge(index)}
              onBlur={() => setHoverEdge(null)}
            />
          </PickMark>
        );
      })}
    </group>
  );
}
