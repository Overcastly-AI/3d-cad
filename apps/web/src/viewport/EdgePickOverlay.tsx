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
import {
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Vector3 } from "three";
import type { Group } from "three";

import type { Vec3 } from "../api/measure";
import { useCommandActionStore } from "../features/commandActions";
import { edgeSignatureKey } from "../features/edge";
import { useEdgePickStore } from "../features/edgePickStore";
import { PROJECT_SPLINE_HINT } from "../sketch/projectEdge";
import {
  occtToScene,
  polylineMidpoint,
  polylineSegments,
} from "../measure/geometry";
import { BuriedMark } from "./BuriedMark";
import { ANNOTATION_LAYER } from "./instruments";
import { EdgeBandLayer } from "./EdgeBandLayer";
import type { EdgeBandInput } from "./edgeBand";
import { resolveMarkPick, type ScreenEdgeMark } from "./edgeMarkResolve";
import { useHiddenPicks } from "./hiddenPicks";
import { PickMark } from "./PickMark";
import { concatPositions, HighlightLines } from "./overlaySegments";
import { useViewportPickStamp } from "./pickStamp";
import type { EdgeMarkAnchor } from "./useEdgeMarkAnchors";

/** Edge marks sit just under the HUD strips (same band as measurement edges). */
const EDGE_Z_RANGE: [number, number] = [17, 0];

/** Scratch for projecting marks and edges in the pointer handlers. */
const projectScratch = new Vector3();

/** A located accessible name for a pickable edge (from its OCCT mid-span). */
function edgeLabel(index: number, kind: string, midpoint: Vec3): string {
  const round = (n: number) => Math.round(n * 10) / 10;
  return `Edge ${index + 1}, ${kind}, centred at ${round(midpoint.x)}, ${round(midpoint.y)}, ${round(midpoint.z)} millimetres`;
}

export function EdgePickOverlay() {
  const overlay = useEdgePickStore((s) => s.overlay);
  const picked = useEdgePickStore((s) => s.picked);
  const hoverEdge = useEdgePickStore((s) => s.hoverEdge);
  const pick = useEdgePickStore((s) => s.pick);
  const purpose = useEdgePickStore((s) => s.purpose);
  const setHoverEdge = useEdgePickStore((s) => s.setHoverEdge);
  const requestSubmit = useCommandActionStore((s) => s.requestSubmit);
  const invalidate = useThree((s) => s.invalidate);
  const camera = useThree((s) => s.camera);
  const canvas = useThree((s) => s.gl.domElement);
  const groupRef = useRef<Group>(null);
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

  /**
   * WHICH EDGE A POINTER ON A MARK MEANS (EDGE-MARK-OVERLAP). The disc that
   * received the event is only whichever one the browser stacked on top; the
   * answer is the edge nearest the pointer among every live mark under it
   * (`edgeMarkResolve.ts`). A keyboard click has no pointer, so it is the
   * focused mark's own edge, and so is a lone mark with no neighbour.
   */
  const resolveMark = useCallback(
    (own: number, clientX: number, clientY: number): number => {
      const box = canvas.getBoundingClientRect();
      const px = clientX - box.left;
      const py = clientY - box.top;
      const world = groupRef.current?.matrixWorld ?? null;
      const toScreen = (p: readonly [number, number, number]) => {
        projectScratch.set(p[0], p[1], p[2]);
        if (world !== null) projectScratch.applyMatrix4(world);
        projectScratch.project(camera);
        return {
          x: ((projectScratch.x + 1) / 2) * box.width,
          y: ((1 - projectScratch.y) / 2) * box.height,
          front: projectScratch.z <= 1,
        };
      };
      const marks: ScreenEdgeMark[] = [];
      const polylines = new Map<number, readonly Vec3[]>();
      offered.forEach(({ edge, index }, slot) => {
        const anchor = anchors[slot];
        if (anchor?.buried === true && index !== own) return;
        const at = toScreen(
          anchor?.position ?? occtToScene(polylineMidpoint(edge.polyline)),
        );
        if (!at.front) return;
        marks.push({ index, x: at.x, y: at.y });
        polylines.set(index, edge.polyline);
      });
      return resolveMarkPick(px, py, own, marks, (index) => {
        const polyline = polylines.get(index);
        if (polyline === undefined) return null;
        const path: number[] = [];
        for (const v of polyline) {
          const at = toScreen(occtToScene(v));
          if (at.front) path.push(at.x, at.y);
        }
        return path;
      });
    },
    [canvas, camera, offered, anchors],
  );

  const clickMark = useCallback(
    (own: number, event: ReactMouseEvent) => {
      // `detail === 0`: Space/Enter on a focused button, not a pointer.
      const index =
        event.detail === 0
          ? own
          : resolveMark(own, event.clientX, event.clientY);
      const edge = overlay?.edges[index];
      if (edge !== undefined) pick(edge);
    },
    [overlay, resolveMark, pick],
  );

  const hoverMark = useCallback(
    (own: number, event: ReactPointerEvent) => {
      setHoverEdge(resolveMark(own, event.clientX, event.clientY));
    },
    [resolveMark, setHoverEdge],
  );

  const pickBandEdge = useCallback(
    (index: number) => {
      const edge = overlay?.edges[index];
      if (edge !== undefined) pick(edge);
    },
    [overlay, pick],
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
    <group ref={groupRef} userData={ANNOTATION_LAYER}>
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
        const hidden = anchor?.buried === true;
        // Project cannot take a spline yet (SKETCH-PROJECT-SPLINE): the mark
        // says so rather than offering a click that only earns a refusal.
        const refused =
          purpose === "project" && edge.signature.curve === "other";
        return (
          <PickMark
            key={`e${index}`}
            position={anchor?.position ?? occtToScene(midpoint)}
            zIndexRange={EDGE_Z_RANGE}
          >
            {/* The hidden-line ghost. A buried edge used to draw NOTHING, so
                "behind the part" and "not there" were the same picture — which
                is how a modeller filleted three of four corners and shipped an
                asymmetric housing. */}
            {hidden ? <BuriedMark shape="edge" /> : null}
            <PickNode
              shape="edge"
              // A7's recession: the edge band is this pick's primary hit-test
              // now, so the mark is the keyboard/touch fallback and may rest
              // quiet.
              recede
              occluded={hidden}
              selected={pickedKeys.has(edgeSignatureKey(edge.signature))}
              data-testid={`edge-pick-${index}`}
              data-buried={hidden ? "true" : "false"}
              aria-label={edgeLabel(index, edge.kind, midpoint)}
              disabled={refused || undefined}
              title={refused ? PROJECT_SPLINE_HINT : undefined}
              onClick={(event) => clickMark(index, event)}
              // Enter is the command's Create key even with focus on the last
              // edge picked; Space toggles (PICK-ENTER-UNPICKS).
              onEnterKey={requestSubmit}
              onPointerOver={(event) => hoverMark(index, event)}
              onPointerMove={(event) => hoverMark(index, event)}
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
