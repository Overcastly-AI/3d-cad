/**
 * PROJECTED GEOMETRY'S INK (SKETCH-PROJECT-EDGES): purple lines (dashed when
 * construction) for entities linked to a body edge, and the hazard mark a
 * SICK one wears. Split out of `SketchScene.tsx` to keep it in its budget.
 */
import { HazardIcon } from "@loft/design";
import { sketch } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useMemo } from "react";

import { planeToWorld, type PlaneBasis } from "../sketch/plane";
import {
  isProjected,
  SICK_REASON_TEXT,
  sickProjections,
} from "../sketch/project";
import { midpointOf } from "../sketch/snap";
import { useSketchStore } from "../sketch/store";
import type { SketchEntity } from "../sketch/tools";
import { entitySegmentPositions } from "../sketch/geometry";
import { InkSegments, partitionConstruction } from "./sketchInk";

/** Sick marks sit with the open-end marks, under the HUD strips. */
const SICK_Z_RANGE: [number, number] = [19, 0];

/** Projected entities' ink on `basis`, solid or dashed by construction. */
export function ProjectedInk({
  entities,
  basis,
}: {
  entities: readonly SketchEntity[];
  basis: PlaneBasis;
}) {
  const parts = useMemo(() => partitionConstruction(entities), [entities]);
  const profile = useMemo(
    () => entitySegmentPositions(parts.profile, basis),
    [parts, basis],
  );
  const construction = useMemo(
    () => entitySegmentPositions(parts.construction, basis),
    [parts, basis],
  );
  return (
    <>
      <InkSegments positions={profile} color={sketch.projectedInk} onTop />
      <InkSegments
        positions={construction}
        color={sketch.projectedInk}
        dashed
        dashSize={sketch.constructionDashMm}
        gapSize={sketch.constructionGapMm}
        onTop
      />
    </>
  );
}

/**
 * SICK PROJECTIONS (SKETCH-PROJECT-EDGES): a projected entity whose body edge
 * no longer resolves keeps its last good position, as Fusion's does, and wears
 * a hazard mark at its middle saying why (the tooltip and the accessible
 * name). The mark is the only place this is said inside the sketch; the tree
 * row says it outside (`projectionWarning`).
 */
export function SickProjectionMarks({ basis }: { basis: PlaneBasis }) {
  const entities = useSketchStore((state) => state.entities);
  const statuses = useSketchStore((state) => state.projections);
  const marks = useMemo(() => {
    const sick = sickProjections(statuses);
    return entities.flatMap((entity) => {
      const reason = sick.get(entity.id);
      if (reason === undefined || !isProjected(entity)) return [];
      const at =
        entity.kind === "circle"
          ? { x: entity.center.x, y: entity.center.y + entity.radius }
          : midpointOf(entity);
      return at === null ? [] : [{ id: entity.id, at, reason }];
    });
  }, [entities, statuses]);
  return (
    <>
      {marks.map((mark) => (
        <Html
          key={mark.id}
          position={planeToWorld(basis, mark.at)}
          center
          zIndexRange={SICK_Z_RANGE}
        >
          <span
            role="img"
            data-testid="projection-sick"
            data-entity={mark.id}
            data-reason={mark.reason}
            aria-label={`Projection lost: ${SICK_REASON_TEXT[mark.reason]}`}
            title={SICK_REASON_TEXT[mark.reason]}
            className="block cursor-help"
            style={{ color: sketch.projectedSickInk }}
          >
            <HazardIcon size={14} />
          </span>
        </Html>
      ))}
    </>
  );
}
