/**
 * The corner-relief bend highlight inside the WebGL viewport — the in-scene
 * answer to the editor's Bend A / Bend B selects. Each selected edge flange's
 * stored fold-edge signature is drawn as a brass line along the physical bend
 * (the shared `Segments` layer + `measure` tokens — the SAME highlight
 * primitive and palette the measurement and edge-pick overlays use, CLAUDE.md
 * DRY rule), with a small `Chip` callout ("Bend A" / "Bend B") at the bend's
 * mid-span via drei `Html` — the established DOM-in-canvas posture, so the
 * mapping is legible on screen AND assertable by QA. Presentational only and
 * non-interactive: PartPage resolves the selection to signatures; nothing here
 * captures the pointer, so orbiting stays live.
 */
import { Chip } from "@loft/design";
import { measure } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";

import type { CornerReliefBendHighlight } from "../features/sheetMetal";
import { occtToScene, polylineSegments } from "../measure/geometry";
import { concatPositions, Segments } from "./overlaySegments";

/** Callouts sit in the annotation band, under the HUD strips (edge-mark band). */
const TAG_Z_RANGE: [number, number] = [17, 0];

export interface BendHighlightOverlayProps {
  /** The resolved bends to highlight (tag + stored fold-edge signature). */
  bends: readonly CornerReliefBendHighlight[];
}

export function BendHighlightOverlay({ bends }: BendHighlightOverlayProps) {
  const invalidate = useThree((s) => s.invalidate);

  // frameloop="demand": redraw when the highlighted selection changes.
  useEffect(() => {
    invalidate();
  }, [bends, invalidate]);

  // An edge flange folds a STRAIGHT edge, so the stored signature's
  // end→mid→end polyline IS the bend line.
  const positions = useMemo(
    () =>
      concatPositions(
        bends.map(({ signature }) =>
          polylineSegments([
            signature.end_a,
            signature.midpoint,
            signature.end_b,
          ]),
        ),
      ),
    [bends],
  );

  if (bends.length === 0) return null;

  return (
    <group>
      {/* The bend lines — brass, the app's one selection color (DOM + WebGL).
          Drawn through the body (the fold tangent sits INSIDE the bend arc, so
          a depth-tested line would be swallowed) — the dimension-line idiom. */}
      <Segments
        positions={positions}
        color={measure.edgeSelected}
        depthTest={false}
        renderOrder={998}
      />

      {/* The "Bend A" / "Bend B" callouts at each bend's mid-span. */}
      {bends.map(({ tag, signature }) => (
        <Html
          key={tag}
          position={occtToScene(signature.midpoint)}
          center
          zIndexRange={TAG_Z_RANGE}
          style={{ pointerEvents: "none" }}
        >
          <Chip
            data-testid={`corner-relief-bend-tag-${tag
              .replace(/[^a-z]/gi, "")
              .toLowerCase()}`}
            className="pointer-events-none select-none whitespace-nowrap"
          >
            Bend {tag}
          </Chip>
        </Html>
      ))}
    </group>
  );
}
