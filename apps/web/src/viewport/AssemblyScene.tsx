/**
 * The assembly viewport scene: every instance's SHARED mesh drawn at its
 * SOLVED transform, a floating drafting balloon per instance (the signature
 * device that ties the DOM tree to the WebGL viewport), and — while a mate tool
 * is armed — the per-instance mate-pick overlays. Camera fitting lives in the
 * shared Viewport rig: the page passes `assemblyBounds` + a LOADED-instance
 * fit key, so the fit fires when a mesh actually lands (no fetch race) and
 * never on a re-solve of the same set (the snap-together motion plays
 * without the camera jumping).
 */
import { Html } from "@react-three/drei";
import { useMemo } from "react";
import { Box3, Matrix4, Quaternion, Vector3 } from "three";

import type { OverlayResult } from "../api/measure";
import type { SceneTransform } from "../assembly/placement";
import { useMateAuthoringStore } from "../assembly/mateStore";
import { InstanceMateOverlay } from "./InstanceMateOverlay";
import { InstanceMesh } from "./InstanceMesh";
import type { InstanceGeometry } from "./useInstanceGeometries";

/** One placed instance the scene draws. */
export interface SceneInstance {
  id: string;
  name: string;
  /** 1-based balloon / BOM item number. */
  balloon: number;
  grounded: boolean;
  transform: SceneTransform;
  /** The shared part geometry, or null while it loads / on a bodyless part. */
  geometry: InstanceGeometry | null;
}

export interface AssemblySceneProps {
  instances: readonly SceneInstance[];
  reducedMotion: boolean;
  selectedInstanceId: string | null;
  onSelectInstance: (instanceId: string) => void;
  /** Part overlays by instance id — present only while a face/axis tool is armed. */
  overlaysByInstance: ReadonlyMap<string, OverlayResult>;
}

const CORNER = new Vector3();
const POS = new Vector3();
const QUAT = new Quaternion();
const SCALE = new Vector3(1, 1, 1);
const MAT = new Matrix4();

/**
 * Union Box3 of every placed instance's LOADED geometry, or null. Consumed by
 * the page to drive the shared Viewport camera rig (fit + contact shadow).
 */
export function assemblyBounds(
  instances: readonly SceneInstance[],
): Box3 | null {
  const box = new Box3();
  let any = false;
  for (const inst of instances) {
    const geom = inst.geometry?.surface;
    if (!geom) continue;
    geom.computeBoundingBox();
    const local = geom.boundingBox;
    if (!local) continue;
    POS.set(...inst.transform.position);
    QUAT.set(...inst.transform.quaternion);
    MAT.compose(POS, QUAT, SCALE);
    // Expand by all 8 transformed corners (a rotated box is not axis-aligned).
    for (let i = 0; i < 8; i += 1) {
      CORNER.set(
        i & 1 ? local.max.x : local.min.x,
        i & 2 ? local.max.y : local.min.y,
        i & 4 ? local.max.z : local.min.z,
      ).applyMatrix4(MAT);
      box.expandByPoint(CORNER);
      any = true;
    }
  }
  return any ? box : null;
}

/** A drafting balloon — circled BOM item number, anchor mark when grounded. */
function Balloon({
  instance,
  selected,
  onSelect,
}: {
  instance: SceneInstance;
  selected: boolean;
  onSelect: () => void;
}) {
  // Anchor at the top-centre of the instance's transformed bounds.
  const anchor = useMemo(() => {
    const geom = instance.geometry?.surface;
    const p = new Vector3(...instance.transform.position);
    if (geom) {
      geom.computeBoundingBox();
      const local = geom.boundingBox;
      if (local) {
        const c = local.getCenter(new Vector3());
        const top = new Vector3(c.x, local.max.y, c.z).applyQuaternion(
          new Quaternion(...instance.transform.quaternion),
        );
        return p.add(top).add(new Vector3(0, 6, 0));
      }
    }
    return p.add(new Vector3(0, 6, 0));
  }, [instance]);

  return (
    <Html position={anchor} center zIndexRange={[25, 5]}>
      <button
        type="button"
        onClick={onSelect}
        data-testid={`assembly-balloon-${instance.id}`}
        data-solved-x={instance.transform.position[0].toFixed(4)}
        data-solved-y={instance.transform.position[1].toFixed(4)}
        data-solved-z={instance.transform.position[2].toFixed(4)}
        data-grounded={instance.grounded ? "true" : "false"}
        aria-label={`${instance.name}${instance.grounded ? ", grounded" : ""}`}
        className={[
          "flex h-6 w-6 items-center justify-center rounded-full border font-display text-2xs tabular-nums",
          "transition-colors duration-fast outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brass",
          selected
            ? "border-brass bg-brass text-carbide"
            : instance.grounded
              ? "border-brass bg-anvil text-brass"
              : "border-etch bg-anvil text-mist hover:border-brass hover:text-brass",
        ].join(" ")}
      >
        {instance.grounded ? "⏚" : instance.balloon}
      </button>
    </Html>
  );
}

export function AssemblyScene({
  instances,
  reducedMotion,
  selectedInstanceId,
  onSelectInstance,
  overlaysByInstance,
}: AssemblySceneProps) {
  const tool = useMateAuthoringStore((s) => s.tool);
  const picks = useMateAuthoringStore((s) => s.picks);
  const pickFace = useMateAuthoringStore((s) => s.pickFace);
  const pickAxis = useMateAuthoringStore((s) => s.pickAxis);
  const pickInstance = useMateAuthoringStore((s) => s.pickInstance);

  const overlayTool =
    tool === "coincident" || tool === "concentric" ? tool : null;

  /** The face/edge index picked on a given instance (overlay highlight). */
  const selectedPickIndex = (instanceId: string): number | null => {
    const pick = picks.find((p) => p.instanceId === instanceId);
    if (pick === undefined) return null;
    if (pick.kind === "face") return pick.faceIndex;
    if (pick.kind === "axis") return pick.edgeIndex;
    return null;
  };

  return (
    <group>
      {instances.map((inst) =>
        inst.geometry ? (
          <InstanceMesh
            key={inst.id}
            geometry={inst.geometry}
            transform={inst.transform}
            selected={selectedInstanceId === inst.id}
            reducedMotion={reducedMotion}
            onSelect={() =>
              tool === "lock"
                ? pickInstance(inst.id)
                : onSelectInstance(inst.id)
            }
          />
        ) : null,
      )}

      {overlayTool
        ? instances.map((inst) => {
            const overlay = overlaysByInstance.get(inst.id) ?? null;
            if (!inst.geometry) return null;
            return (
              <InstanceMateOverlay
                key={`ov-${inst.id}`}
                instanceId={inst.id}
                transform={inst.transform}
                tool={overlayTool}
                overlay={overlay}
                selectedIndex={selectedPickIndex(inst.id)}
                onPickFace={(index, signature) =>
                  pickFace(inst.id, index, signature)
                }
                onPickAxis={(index, signature) =>
                  pickAxis(inst.id, index, signature)
                }
              />
            );
          })
        : null}

      {instances.map((inst) => (
        <Balloon
          key={`b-${inst.id}`}
          instance={inst}
          selected={selectedInstanceId === inst.id}
          onSelect={() =>
            tool === "lock" ? pickInstance(inst.id) : onSelectInstance(inst.id)
          }
        />
      ))}
    </group>
  );
}
