/**
 * The edge-flange WIDTH-EXTENT preview inside the WebGL viewport — the in-scene
 * answer to the editor's Full / Centered / Offset choice. The chosen
 * `[offset, offset + width]` span is drawn as a brass segment ON the picked edge
 * (§4.5.1), with a small `Chip` reading the span width at its mid-point, so the
 * partial extent is legible before commit AND assertable by QA. It reuses the
 * SAME `Segments` layer + `measure` selection token the bend-highlight and
 * edge-pick overlays use (CLAUDE.md DRY rule — one highlight primitive, one
 * palette across DOM + WebGL) and introduces no new colors or stores.
 *
 * Presentational only and non-interactive: PartPage owns the span (computed from
 * the live form + picked edge); nothing here captures the pointer, so orbiting
 * stays live.
 */
import { Chip } from "@loft/design";
import { measure } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";

import type { EdgeFlangeSpanPreview } from "../features/sheetMetal";
import { occtToScene, polylineSegments } from "../measure/geometry";
import { Segments } from "./overlaySegments";

/** The width caption sits in the annotation band, under the HUD strips. */
const TAG_Z_RANGE: [number, number] = [17, 0];

export interface FlangeSpanOverlayProps {
  /** The chosen span (OCCT world-mm start/end + width) — see the editor. */
  span: EdgeFlangeSpanPreview;
  /** Preformatted span width for the caption (unit-aware, from the editor). */
  label: string;
}

export function FlangeSpanOverlay({ span, label }: FlangeSpanOverlayProps) {
  const invalidate = useThree((s) => s.invalidate);

  // frameloop="demand": redraw when the previewed span changes.
  useEffect(() => {
    invalidate();
  }, [span, invalidate]);

  const positions = useMemo(
    () => polylineSegments([span.start, span.end]),
    [span],
  );
  const midpoint = useMemo(
    () =>
      occtToScene({
        x: (span.start.x + span.end.x) / 2,
        y: (span.start.y + span.end.y) / 2,
        z: (span.start.z + span.end.z) / 2,
      }),
    [span],
  );

  return (
    <group>
      {/* The span — brass, the app's one selection color (DOM + WebGL). Drawn
          without depth test so it reads on top of the edge it traces. */}
      <Segments
        positions={positions}
        color={measure.edgeSelected}
        depthTest={false}
        renderOrder={999}
      />

      <Html
        position={midpoint}
        center
        zIndexRange={TAG_Z_RANGE}
        style={{ pointerEvents: "none" }}
      >
        <Chip
          data-testid="edge-flange-span-tag"
          className="pointer-events-none select-none whitespace-nowrap"
        >
          {label}
        </Chip>
      </Html>
    </group>
  );
}
