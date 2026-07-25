/**
 * Composed view → persisted view ROW correlation, kept out of React so it runs
 * (and is tested) without a DOM — the `authoring.ts` posture.
 *
 * A `ComposedView` is pure placed geometry: the server-composed sheet carries no
 * view ids, only the projection each placed view was projected along. Every
 * per-view interaction the sheet offers (edge/endpoint picks, drag-to-place, the
 * AUTO reset) must nevertheless target a persisted ROW — `PATCH /views/{id}` —
 * so the renderer maps projection → row.
 *
 * That map is exact because `(sheet_id, projection)` is UNIQUE server-side
 * (documents migration `0011`, engineering audit **H3**). Before that constraint
 * a sheet could hold two `section` views: only one composed, the map was
 * last-write-wins, and dragging the rendered view PATCHed the OTHER row's
 * position — silent corruption of a persisted document from a UI gesture. This
 * helper is first-write-wins (the sheet's stored `order_index` order, i.e. the
 * row the composer anchored, for any legacy row predating the constraint) and is
 * also what supplies the stable per-VIEW-ID React key, so element identity
 * follows the row a drag actually targets rather than the projection slot.
 */
import type { ViewProjection } from "../api/drawings";

/** The minimum a persisted view row must expose to be correlated. */
export interface ProjectedRow {
  id: string;
  projection: ViewProjection;
}

/**
 * Index persisted view rows by projection, keeping the FIRST row per projection.
 *
 * @param views persisted rows in the sheet's stored order.
 */
export function viewRowsByProjection<T extends ProjectedRow>(
  views: readonly T[],
): Map<ViewProjection, T> {
  const byProjection = new Map<ViewProjection, T>();
  for (const view of views) {
    if (byProjection.has(view.projection)) continue;
    byProjection.set(view.projection, view);
  }
  return byProjection;
}
