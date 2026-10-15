/**
 * EDIT IN PLACE, the scene half (ASM-A3-IN-CONTEXT): the assembly's other
 * components drawn ghosted around the part being edited, at their solved
 * poses relative to it, as Fusion 360 dims the rest of the assembly while a
 * component is active.
 *
 * While the sketcher's Project tool is armed, each component offers its
 * straight and circular edges through the SAME pick overlay a mate axis uses
 * (`InstanceMateOverlay`, riding the component's pose). A click projects that
 * edge into the sketch as an in-context link: the edge is carried into this
 * part's frame for the first draw, and the link stores it in the component's
 * own frame for geometry to follow.
 */
import { assembly } from "@loft/design/tokens";
import { useCallback, useState } from "react";
import { DoubleSide } from "three";

import { placementToScene } from "../assembly/placement";
import {
  carryOverlayEdge,
  type ContextComponent,
  inContextLink,
} from "../assembly/inContext";
import type { ContextEdge } from "../sketch/projectActions";
import { useSketchStore } from "../sketch/store";
import type { InContextSession } from "../routes/part/useInContext";
import { InstanceMateOverlay } from "./InstanceMateOverlay";

function ContextComponentGhost({
  session,
  component,
  projecting,
  hovered,
  onHover,
}: {
  session: InContextSession;
  component: ContextComponent;
  projecting: boolean;
  hovered: number | null;
  onHover: (index: number | null) => void;
}) {
  const geometry = session.geometryOf(component);
  const transform = placementToScene(component.placement);
  const overlay = session.overlays.get(component.partId) ?? null;
  const onPickAxis = useCallback(
    (index: number) => {
      const picked = overlay?.edges[index];
      if (picked === undefined) return;
      const edge: ContextEdge = {
        ...carryOverlayEdge(picked, component.placement),
        inContext: inContextLink({
          assemblyId: session.assemblyId,
          hostOccurrenceId: session.hostOccurrenceId,
          component,
          edge: picked,
        }),
      };
      useSketchStore.getState().projectEdge(edge, "");
    },
    [overlay, component, session.assemblyId, session.hostOccurrenceId],
  );
  if (geometry === null) return null;
  return (
    <>
      <group
        position={transform.position}
        quaternion={transform.quaternion}
        userData={{ inContextComponent: component.occurrenceId }}
      >
        <mesh geometry={geometry.surface} raycast={() => null}>
          <meshStandardMaterial
            color={assembly.instanceSurface}
            transparent
            opacity={assembly.ghost.surfaceOpacity}
            depthWrite={false}
            side={DoubleSide}
          />
        </mesh>
        <lineSegments geometry={geometry.edges} raycast={() => null}>
          <lineBasicMaterial
            color={assembly.instanceEdge}
            transparent
            opacity={assembly.ghost.edgeOpacity}
          />
        </lineSegments>
      </group>
      {projecting && overlay !== null ? (
        <InstanceMateOverlay
          instanceId={component.occurrenceId}
          transform={transform}
          geometry={geometry.surface}
          tool="concentric"
          straightEdges
          overlay={overlay}
          selectedIndex={null}
          hovered={hovered}
          onHover={onHover}
          onPickFace={() => undefined}
          onPickAxis={onPickAxis}
        />
      ) : null}
    </>
  );
}

export function InContextLayer({
  session,
  drawing,
}: {
  session: InContextSession | null;
  /** Sketching: Project may be armed. */
  drawing: boolean;
}) {
  const projecting = useSketchStore((s) => s.tool === "project") && drawing;
  const [hover, setHover] = useState<{ id: string; index: number } | null>(
    null,
  );
  if (session === null) return null;
  return (
    <>
      {session.components.map((component) => (
        <ContextComponentGhost
          key={component.occurrenceId}
          session={session}
          component={component}
          projecting={projecting}
          hovered={hover?.id === component.occurrenceId ? hover.index : null}
          onHover={(index) =>
            setHover(
              index === null ? null : { id: component.occurrenceId, index },
            )
          }
        />
      ))}
    </>
  );
}
