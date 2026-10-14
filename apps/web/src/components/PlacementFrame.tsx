/**
 * The view placement frame — split out of `DrawingSheet.tsx`
 * (FILE-SIZE-RATCHET); behaviour unchanged.
 */
import type {
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
} from "react";

import { drawing, font } from "@loft/design";

/**
 * The view placement frame — a quiet blueprint-blue border (the CAD view-border
 * idiom) that reveals on hover/focus, with a corner grip you drag or nudge with
 * arrow keys, and a "reset to auto-layout" control shown once the view carries a
 * dragged position. Reuses the pick-blue so placement and dimensioning read as
 * one instrument. All chrome carries `data-placement-chrome` so the SVG export
 * strips it — the print is drafting geometry only.
 */
export function PlacementFrame({
  frame,
  revealed,
  placed,
  dragging,
  busy,
  label,
  onGripPointerDown,
  onGripPointerMove,
  onGripPointerUp,
  onGripKeyDown,
  onGripFocus,
  onGripBlur,
  onReset,
}: {
  frame: { x: number; y: number; w: number; h: number };
  revealed: boolean;
  placed: boolean;
  dragging: boolean;
  busy: boolean;
  label: string;
  onGripPointerDown: (event: ReactPointerEvent<SVGElement>) => void;
  onGripPointerMove: (event: ReactPointerEvent<SVGElement>) => void;
  onGripPointerUp: (event: ReactPointerEvent<SVGElement>) => void;
  onGripKeyDown: (event: ReactKeyboardEvent) => void;
  onGripFocus: () => void;
  onGripBlur: () => void;
  onReset?: () => void;
}) {
  const grip = drawing.placementGripMm;
  const ink = dragging ? drawing.pickSelected : drawing.pickHover;
  // A placed view keeps a faint corner tick at rest so the manual placement is
  // discoverable without hovering; hover/drag brings up the full frame.
  const showFrame = revealed;
  const showGrip = revealed || placed;
  return (
    <g data-placement-chrome="frame" aria-hidden={showGrip ? undefined : true}>
      {showFrame ? (
        <rect
          data-testid="drawing-view-frame"
          x={frame.x}
          y={frame.y}
          width={frame.w}
          height={frame.h}
          fill="none"
          stroke={ink}
          strokeWidth={drawing.placementFrameWeightMm}
          strokeDasharray={`${drawing.placementFrameDashMm} ${drawing.placementFrameGapMm}`}
          pointerEvents="none"
        />
      ) : null}
      {showGrip ? (
        <g
          role="button"
          tabIndex={0}
          aria-label={`Move the ${label} view — drag, or use arrow keys to nudge`}
          data-testid="drawing-view-grip"
          style={{
            cursor: dragging ? "grabbing" : "grab",
            outline: "none",
            touchAction: "none",
          }}
          onPointerDown={onGripPointerDown}
          onPointerMove={onGripPointerMove}
          onPointerUp={onGripPointerUp}
          onPointerCancel={onGripPointerUp}
          onKeyDown={onGripKeyDown}
          onFocus={onGripFocus}
          onBlur={onGripBlur}
        >
          <rect
            x={frame.x - grip}
            y={frame.y - grip}
            width={grip * 2}
            height={grip * 2}
            fill={revealed || dragging ? drawing.pickSelected : drawing.paper}
            stroke={ink}
            strokeWidth={0.5}
          />
          {/* Move glyph — a small four-way cross, the drag vernacular. */}
          <g
            stroke={revealed || dragging ? drawing.paper : ink}
            strokeWidth={0.4}
            strokeLinecap="round"
          >
            <line
              x1={frame.x - grip * 0.55}
              y1={frame.y}
              x2={frame.x + grip * 0.55}
              y2={frame.y}
            />
            <line
              x1={frame.x}
              y1={frame.y - grip * 0.55}
              x2={frame.x}
              y2={frame.y + grip * 0.55}
            />
          </g>
        </g>
      ) : null}
      {showFrame && placed && onReset ? (
        <g
          role="button"
          tabIndex={0}
          aria-label={`Return the ${label} view to auto-layout`}
          data-testid="drawing-view-reset"
          style={{ cursor: busy ? "default" : "pointer", outline: "none" }}
          onClick={busy ? undefined : onReset}
          onKeyDown={(event) => {
            if (busy) return;
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onReset();
            }
          }}
        >
          <rect
            x={frame.x + frame.w - 15}
            y={frame.y - grip}
            width={15}
            height={grip * 2}
            fill={drawing.paper}
            stroke={ink}
            strokeWidth={0.4}
            opacity={busy ? 0.5 : 1}
          />
          <text
            x={frame.x + frame.w - 15 / 2}
            y={frame.y + 0.9}
            textAnchor="middle"
            dominantBaseline="middle"
            fill={ink}
            fontFamily={font.display}
            fontSize={2.4}
            letterSpacing={0.3}
            opacity={busy ? 0.5 : 1}
          >
            AUTO
          </text>
        </g>
      ) : null}
    </g>
  );
}
