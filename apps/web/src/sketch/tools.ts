/**
 * Sketch tool state machine — pure functions, no three.js, no store.
 *
 * A tool is a short sequence of point placements; `placePoint` advances the
 * sequence and emits finished entities (typed by the generated client — the
 * exact shapes the sketch feature persists, CLAUDE.md DRY rule). Rectangles
 * are sugar: they emit four closed CCW lines, the schema's rectangle form
 * (design doc §6), so the constraint item (#5) can dimension them like any
 * other lines.
 */
import type { components } from "@loft/ts-client/gateway";

import type { Point2D } from "./plane";

export type SketchEntity =
  components["schemas"]["SketchParamsV1"]["entities"][number];

export type SketchTool =
  "select" | "line" | "rect" | "circle" | "arc" | "trim" | "extend" | "offset";

/**
 * Keyboard tool switching — case-insensitive at the call site. Draw tools take
 * their initials (L/R/C/A); the "clean-up" modify tools take free home-row
 * keys — every draw-tool AND constraint-verb letter (H/V/D/R/X/C/P/L/T/E/S/O/N,
 * plus G snap / M measure) is already spoken for, so trim/extend/offset claim
 * home-row keys with no mnemonic collision rather than shadow an accelerator.
 * J·K·F sit left-to-right on the home row, mirroring Trim·Extend·Offset in the
 * toolbar; F is the free index-finger key (the offset mnemonic O is taken by
 * concentric).
 */
export const TOOL_SHORTCUTS: Readonly<Record<string, SketchTool>> = {
  l: "line",
  r: "rect",
  c: "circle",
  a: "arc",
  j: "trim",
  k: "extend",
  f: "offset",
};

/** Coordinates closer than this (mm) are the same point — degenerate. */
const DEGENERATE_MM = 1e-9;

const same = (a: number, b: number): boolean => Math.abs(a - b) < DEGENERATE_MM;

const distance = (a: Point2D, b: Point2D): number =>
  Math.hypot(b.x - a.x, b.y - a.y);

const entityId = (index: number): string => `e${index}`;

export interface PlacementResult {
  /** Points still awaiting the sequence's next click. */
  pending: Point2D[];
  /** Entities finished by this placement (empty while mid-sequence). */
  entities: SketchEntity[];
  /** Next sketch-local id index after the emitted entities. */
  nextIdIndex: number;
}

const keep = (pending: Point2D[], nextIdIndex: number): PlacementResult => ({
  pending,
  entities: [],
  nextIdIndex,
});

/**
 * Advance `tool`'s placement sequence with a click at `point` (plane mm,
 * already snapped). Degenerate placements (zero length/radius/area) are
 * rejected: the sequence stays where it was, nothing is emitted.
 */
export function placePoint(
  tool: SketchTool,
  pending: Point2D[],
  point: Point2D,
  nextIdIndex: number,
): PlacementResult {
  // The modify tools never PLACE geometry — a click targets an existing curve
  // and the stateless geometry service rewrites (trim/extend) or ADDS (offset)
  // it (handled in the scene), so the placement sequence is a no-op for them
  // (as it is for select).
  switch (tool) {
    case "select":
    case "trim":
    case "extend":
    case "offset":
      return keep(pending, nextIdIndex);
    case "line": {
      const [start] = pending;
      if (start === undefined) return keep([point], nextIdIndex);
      if (distance(start, point) < DEGENERATE_MM) {
        return keep(pending, nextIdIndex);
      }
      return {
        pending: [],
        entities: [
          {
            id: entityId(nextIdIndex),
            kind: "line",
            start,
            end: point,
            construction: false,
          },
        ],
        nextIdIndex: nextIdIndex + 1,
      };
    }
    case "rect": {
      const [corner] = pending;
      if (corner === undefined) return keep([point], nextIdIndex);
      if (same(corner.x, point.x) || same(corner.y, point.y)) {
        return keep(pending, nextIdIndex); // zero width/height
      }
      return {
        pending: [],
        entities: rectangleLines(corner, point, nextIdIndex),
        nextIdIndex: nextIdIndex + 4,
      };
    }
    case "circle": {
      const [center] = pending;
      if (center === undefined) return keep([point], nextIdIndex);
      const radius = distance(center, point);
      if (radius < DEGENERATE_MM) return keep(pending, nextIdIndex);
      return {
        pending: [],
        entities: [
          {
            id: entityId(nextIdIndex),
            kind: "circle",
            center,
            radius,
            construction: false,
          },
        ],
        nextIdIndex: nextIdIndex + 1,
      };
    }
    case "arc": {
      const [center, start] = pending;
      if (center === undefined) return keep([point], nextIdIndex);
      if (start === undefined) {
        if (distance(center, point) < DEGENERATE_MM) {
          return keep(pending, nextIdIndex);
        }
        return keep([center, point], nextIdIndex);
      }
      const end = arcEndPoint(center, start, point);
      if (end === null) return keep(pending, nextIdIndex);
      return {
        pending: [],
        entities: [
          {
            id: entityId(nextIdIndex),
            kind: "arc",
            center,
            start,
            end,
            construction: false,
          },
        ],
        nextIdIndex: nextIdIndex + 1,
      };
    }
  }
}

/** Four CCW closed lines — the schema's rectangle (order: bottom, right, top, left). */
function rectangleLines(
  a: Point2D,
  b: Point2D,
  nextIdIndex: number,
): SketchEntity[] {
  const x0 = Math.min(a.x, b.x);
  const x1 = Math.max(a.x, b.x);
  const y0 = Math.min(a.y, b.y);
  const y1 = Math.max(a.y, b.y);
  const corners: Point2D[] = [
    { x: x0, y: y0 },
    { x: x1, y: y0 },
    { x: x1, y: y1 },
    { x: x0, y: y1 },
  ];
  return corners.map((start, i) => ({
    id: entityId(nextIdIndex + i),
    kind: "line" as const,
    start,
    end: corners[(i + 1) % 4] as Point2D,
    construction: false,
  }));
}

/**
 * Project the cursor direction onto the arc's circle (radius = |start −
 * center|, schema invariant). Null when the direction is degenerate or the
 * arc would have zero sweep.
 */
export function arcEndPoint(
  center: Point2D,
  start: Point2D,
  cursor: Point2D,
): Point2D | null {
  const radius = distance(center, start);
  const dx = cursor.x - center.x;
  const dy = cursor.y - center.y;
  const length = Math.hypot(dx, dy);
  if (radius < DEGENERATE_MM || length < DEGENERATE_MM) return null;
  const end = {
    x: center.x + (dx / length) * radius,
    y: center.y + (dy / length) * radius,
  };
  if (distance(end, start) < DEGENERATE_MM) return null; // zero sweep
  return end;
}

/**
 * Rubber-band geometry for the in-progress placement: entity-shaped values
 * (synthetic ids, never persisted) so the renderer treats previews exactly
 * like committed entities. Empty while nothing is pending.
 */
export function previewEntities(
  tool: SketchTool,
  pending: Point2D[],
  cursor: Point2D,
): SketchEntity[] {
  // No rubber band for the modify tools — aim feedback is the hovered target
  // curve highlight, not a placement preview (same as select).
  switch (tool) {
    case "select":
    case "trim":
    case "extend":
    case "offset":
      return [];
    case "line": {
      const [start] = pending;
      if (start === undefined) return [];
      return [
        {
          id: "preview",
          kind: "line",
          start,
          end: cursor,
          construction: false,
        },
      ];
    }
    case "rect": {
      const [corner] = pending;
      if (corner === undefined) return [];
      if (same(corner.x, cursor.x) || same(corner.y, cursor.y)) return [];
      return rectangleLines(corner, cursor, 0).map((entity, i) => ({
        ...entity,
        id: `preview-${i}`,
      }));
    }
    case "circle": {
      const [center] = pending;
      if (center === undefined) return [];
      const radius = distance(center, cursor);
      if (radius < DEGENERATE_MM) return [];
      return [
        { id: "preview", kind: "circle", center, radius, construction: false },
      ];
    }
    case "arc": {
      const [center, start] = pending;
      if (center === undefined) return [];
      if (start === undefined) {
        // Radius rubber band: a spoke from center to cursor.
        if (distance(center, cursor) < DEGENERATE_MM) return [];
        return [
          {
            id: "preview",
            kind: "line",
            start: center,
            end: cursor,
            construction: false,
          },
        ];
      }
      const end = arcEndPoint(center, start, cursor);
      if (end === null) return [];
      return [
        { id: "preview", kind: "arc", center, start, end, construction: false },
      ];
    }
  }
}

/** What Escape does next, given the drawing state (cascade, most-local first). */
export type EscapeAction =
  | "close-editor"
  | "cancel-placement"
  | "reset-tool"
  | "clear-selection"
  | "exit";

export function escapeAction(
  tool: SketchTool,
  pendingCount: number,
  hasSelection = false,
  editorOpen = false,
): EscapeAction {
  if (editorOpen) return "close-editor";
  if (pendingCount > 0) return "cancel-placement";
  if (tool !== "select") return "reset-tool";
  if (hasSelection) return "clear-selection";
  return "exit";
}
