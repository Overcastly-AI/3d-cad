/**
 * Picking a joint origin, Fusion 360's way: hover a face of a component and
 * its snap points appear — the face's centre, the centres of the holes in it,
 * the start, middle and end of its edges — with the one nearest the cursor
 * lit; a click takes that one. The face and hole centres also stand as quiet
 * marks on every component, so the keyboard, a screen reader and touch reach
 * an origin without hovering (the SEL-4 rule every pick overlay keeps).
 *
 * ONE OWNER FOR HOVER. One pointer addresses one snap point across every
 * component, so hover lives here, not per component, and each surface stops
 * the event so only the nearest component answers (the MATE-1 lesson).
 */
import { PickNode } from "@loft/design";
import { type ThreeEvent, useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { OverlayResult } from "../api/measure";
import {
  facePoints,
  nearestPoint,
  type OriginCandidate,
  originCandidates,
  toOriginPick,
} from "../assembly/jointOrigins";
import type { JointOriginPick } from "../assembly/joints";
import { occtPointToScene, scenePointToOcct } from "../assembly/placement";
import type { SceneInstance } from "./AssemblyScene";
import { PickMark } from "./PickMark";
import { useViewportPickStamp } from "./pickStamp";
import { PickSurface } from "./pickSurface";

export interface JointOriginLayerProps {
  /** The DRAWN instances with geometry. */
  instances: readonly SceneInstance[];
  overlaysByInstance: ReadonlyMap<string, OverlayResult>;
  /** The origins already picked (the selected cue). */
  picked: readonly JointOriginPick[];
  onPick: (origin: JointOriginPick) => void;
}

interface Hover {
  instanceId: string;
  /** The candidates the hovered face reveals. */
  revealed: readonly OriginCandidate[];
  /** The one nearest the cursor: what a click takes. */
  nearest: OriginCandidate | null;
}

const SHAPE: Record<OriginCandidate["kind"], "face" | "center" | "vertex"> = {
  face_centre: "face",
  circle_centre: "center",
  edge_point: "vertex",
};

export function JointOriginLayer({
  instances,
  overlaysByInstance,
  picked,
  onPick,
}: JointOriginLayerProps) {
  const invalidate = useThree((s) => s.invalidate);
  const candidatesById = useMemo(() => {
    const map = new Map<string, OriginCandidate[]>();
    for (const inst of instances) {
      const overlay = overlaysByInstance.get(inst.id);
      if (overlay !== undefined) map.set(inst.id, originCandidates(overlay));
    }
    return map;
  }, [instances, overlaysByInstance]);

  const [hover, setHover] = useState<Hover | null>(null);
  useEffect(() => {
    setHover(null);
  }, [candidatesById, picked]);
  useEffect(() => {
    invalidate();
  }, [hover, picked, invalidate]);

  useViewportPickStamp(
    "jointPickHover",
    hover?.nearest == null ? null : `${hover.instanceId}:${hover.nearest.key}`,
  );

  /** What the pointer at this hit addresses on this instance. */
  const resolve = useCallback(
    (
      instanceId: string,
      ordinal: number | null,
      event: ThreeEvent<PointerEvent | MouseEvent>,
    ): Hover | null => {
      const candidates = candidatesById.get(instanceId);
      if (candidates === undefined) return null;
      const onFace = ordinal === null ? [] : facePoints(candidates, ordinal);
      // A curved face (a bore) has no centre of its own: offer the hole rims.
      const revealed =
        onFace.length > 0
          ? onFace
          : candidates.filter((c) => c.kind === "circle_centre");
      const local = event.object.worldToLocal(event.point.clone());
      const nearest = nearestPoint(
        revealed,
        scenePointToOcct([local.x, local.y, local.z]),
      );
      return { instanceId, revealed, nearest };
    },
    [candidatesById],
  );

  return (
    <>
      {instances.map((inst) => {
        const candidates = candidatesById.get(inst.id);
        if (inst.geometry === null || candidates === undefined) return null;
        const hovered = hover?.instanceId === inst.id ? hover : null;
        const pickedKey = picked.find((p) => p.instanceId === inst.id)?.key;
        // Quiet standing marks (face + hole centres) plus whatever the hovered
        // face reveals; one node per key.
        const shown = new Map<string, OriginCandidate>();
        for (const c of candidates) {
          if (c.kind !== "edge_point" || c.key === pickedKey)
            shown.set(c.key, c);
        }
        for (const c of hovered?.revealed ?? []) shown.set(c.key, c);
        return (
          <group
            key={`joint-origins-${inst.id}`}
            position={inst.transform.position}
            quaternion={inst.transform.quaternion}
          >
            <PickSurface
              geometry={inst.geometry.surface}
              onMove={(ordinal, event) => {
                event.stopPropagation();
                const next = resolve(inst.id, ordinal, event);
                setHover((current) =>
                  current?.instanceId === next?.instanceId &&
                  current?.nearest?.key === next?.nearest?.key &&
                  current?.revealed.length === next?.revealed.length
                    ? current
                    : next,
                );
              }}
              onOut={() =>
                setHover((current) =>
                  current?.instanceId === inst.id ? null : current,
                )
              }
              onClick={(ordinal, event) => {
                event.stopPropagation();
                const target = resolve(inst.id, ordinal, event)?.nearest;
                if (target != null) onPick(toOriginPick(inst.id, target));
              }}
            />
            {[...shown.values()].map((c) => {
              const lit = hovered?.nearest?.key === c.key;
              return (
                <PickMark
                  key={c.key}
                  position={occtPointToScene(c.point)}
                  zIndexRange={[30, 10]}
                >
                  <PickNode
                    shape={
                      c.kind === "edge_point" && c.at === "mid"
                        ? "edge"
                        : SHAPE[c.kind]
                    }
                    // The body is the primary hit-test; a mark rests quietly
                    // until it is the one the cursor would take.
                    recede={!lit}
                    selected={pickedKey === c.key}
                    data-testid={`joint-origin-${inst.id}-${c.key}`}
                    data-lit={lit ? "true" : undefined}
                    aria-label={c.label}
                    onClick={() => onPick(toOriginPick(inst.id, c))}
                  />
                </PickMark>
              );
            })}
          </group>
        );
      })}
    </>
  );
}
