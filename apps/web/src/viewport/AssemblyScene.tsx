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
import { assembly as assemblyTokens, viewport } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useMemo } from "react";
import { Box3, Matrix4, Quaternion, Vector3 } from "three";

import type { OverlayResult } from "../api/measure";
import type { SceneTransform } from "../assembly/placement";
import { useMateAuthoringStore } from "../assembly/mateStore";
import { groundShadowTexture } from "./groundShadow";
import { InstanceMateOverlay } from "./InstanceMateOverlay";
import { InstanceMesh } from "./InstanceMesh";
import type { VisibilityMode } from "./instanceVisibility";
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
  /**
   * The workspace's per-instance view stop (UI-W2). `hidden` draws NOTHING for
   * this instance — no body, no contact pool, no balloon, no mate overlay: a
   * balloon floating over an absent part would point at nothing, and geometry
   * you cannot see must not be pickable. `ghost` draws it translucent.
   */
  visibility: VisibilityMode;
}

/** Is this instance drawn at all this frame? */
function isDrawn(instance: SceneInstance): boolean {
  return instance.visibility !== "hidden";
}

export interface AssemblySceneProps {
  instances: readonly SceneInstance[];
  reducedMotion: boolean;
  selectedInstanceId: string | null;
  onSelectInstance: (instanceId: string) => void;
  /** Part overlays by instance id — present only while a face/axis tool is armed. */
  overlaysByInstance: ReadonlyMap<string, OverlayResult>;
  /** MEASURED interference — edge-lit + balloon red, and said as "interfering". */
  clashingInstanceIds: ReadonlySet<string>;
  /**
   * Pairs the kernel could NOT measure. Same three states as the schedule and
   * the tree: a dashed gauge balloon and an edge-light, never the alarm.
   */
  unverifiedInstanceIds: ReadonlySet<string>;
}

/** How much the last interference check actually knows about an instance. */
type ClashState = "clash" | "unverified" | "none";

const CORNER = new Vector3();
const POS = new Vector3();
const QUAT = new Quaternion();
const SCALE = new Vector3(1, 1, 1);
const MAT = new Matrix4();

/**
 * Union Box3 of every DRAWN instance's LOADED geometry, or null. Consumed by
 * the page to drive the shared Viewport camera rig (fit + contact shadow).
 *
 * Hidden instances are excluded, so "Fit to view" after an isolate frames the
 * part you isolated — Fusion's behaviour. Merely hiding something does NOT move
 * the camera on its own: the page's fit KEY is the loaded-geometry set, which a
 * visibility change never touches, so the refit only happens when the user asks
 * for one.
 */
export function assemblyBounds(
  instances: readonly SceneInstance[],
): Box3 | null {
  const box = new Box3();
  let any = false;
  for (const inst of instances) {
    if (!isDrawn(inst)) continue;
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

/** A pool oversize factor — the pool reads ~2× the part footprint (== part). */
const SHADOW_FACTOR = 2;

/**
 * Per-instance contact pools + the scene floor (UI audit #19d). Each placed
 * instance's transformed footprint (XZ extent) gets its own soft pool at the
 * common floor plane, so every part in the assembly reads SEATED — the same
 * grounded depth a lone part has, instead of one flat blob under the union.
 */
interface InstancePool {
  id: string;
  /** World XZ centre of the transformed footprint. */
  center: readonly [number, number];
  /** World XZ extent (pool scale before the oversize factor). */
  size: readonly [number, number];
  /**
   * A ghosted body casts a ghosted pool. Without this a see-through part sits
   * on a full-strength shadow, which reads as a solid part you have merely
   * tinted — the seat has to go translucent with the thing that seats.
   */
  ghost: boolean;
}

function useInstancePools(instances: readonly SceneInstance[]): {
  pools: InstancePool[];
  floor: number;
} {
  return useMemo(() => {
    const pools: InstancePool[] = [];
    let floor = 0;
    for (const inst of instances) {
      if (!isDrawn(inst)) continue;
      const geom = inst.geometry?.surface;
      if (!geom) continue;
      geom.computeBoundingBox();
      const local = geom.boundingBox;
      if (!local) continue;
      const pos = new Vector3(...inst.transform.position);
      const quat = new Quaternion(...inst.transform.quaternion);
      const mat = new Matrix4().compose(pos, quat, new Vector3(1, 1, 1));
      let minX = Infinity;
      let maxX = -Infinity;
      let minZ = Infinity;
      let maxZ = -Infinity;
      for (let i = 0; i < 8; i += 1) {
        const c = new Vector3(
          i & 1 ? local.max.x : local.min.x,
          i & 2 ? local.max.y : local.min.y,
          i & 4 ? local.max.z : local.min.z,
        ).applyMatrix4(mat);
        minX = Math.min(minX, c.x);
        maxX = Math.max(maxX, c.x);
        minZ = Math.min(minZ, c.z);
        maxZ = Math.max(maxZ, c.z);
        floor = Math.min(floor, c.y);
      }
      pools.push({
        id: inst.id,
        center: [(minX + maxX) / 2, (minZ + maxZ) / 2],
        size: [Math.max(maxX - minX, 1), Math.max(maxZ - minZ, 1)],
        ghost: inst.visibility === "ghost",
      });
    }
    return { pools, floor };
  }, [instances]);
}

/** A drafting balloon — circled BOM item number, anchor mark when grounded. */
function Balloon({
  instance,
  selected,
  clashState,
  onSelect,
}: {
  instance: SceneInstance;
  selected: boolean;
  clashState: ClashState;
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
        // `data-clashing` stays MEASURED-only; the third state is named
        // separately so no consumer can read "flagged" as "interferes".
        data-clashing={clashState === "clash" ? "true" : "false"}
        data-clash-state={clashState}
        aria-label={`${instance.name}${instance.grounded ? ", grounded" : ""}${
          clashState === "clash"
            ? ", interfering"
            : clashState === "unverified"
              ? // The schedule's own words, so the screen reader and the panel
                // agree: the kernel could not measure this pair.
                ", overlap unverified"
              : ""
        }`}
        className={[
          "flex h-6 w-6 items-center justify-center rounded-full border font-display text-2xs tabular-nums",
          "transition-colors duration-fast outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brass",
          selected
            ? "border-brass bg-brass text-carbide"
            : clashState === "clash"
              ? "border-flag bg-anvil text-flag hover:border-flag"
              : clashState === "unverified"
                ? // Dashed gauge ring — the schedule's UNVERIFIED stamp, drawn
                  // round. A broken line is the drafting idiom for "not
                  // established", and it reads as attention without alarm.
                  "border-dashed border-gauge bg-anvil text-gauge hover:border-mist hover:text-mist"
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
  clashingInstanceIds,
  unverifiedInstanceIds,
}: AssemblySceneProps) {
  const { pools, floor } = useInstancePools(instances);
  const tool = useMateAuthoringStore((s) => s.tool);
  const picks = useMateAuthoringStore((s) => s.picks);
  const pickFace = useMateAuthoringStore((s) => s.pickFace);
  const pickAxis = useMateAuthoringStore((s) => s.pickAxis);
  const pickInstance = useMateAuthoringStore((s) => s.pickInstance);

  // Distance / angle pick two planar faces like coincident, so they reuse the
  // face overlay; concentric picks circular-edge axes; lock picks the body.
  const overlayTool: "coincident" | "concentric" | null =
    tool === "concentric"
      ? "concentric"
      : tool !== null && tool !== "lock"
        ? "coincident"
        : null;

  /** Measured clash wins over unverified; both are separate from rest. */
  const clashStateOf = (instanceId: string): ClashState =>
    clashingInstanceIds.has(instanceId)
      ? "clash"
      : unverifiedInstanceIds.has(instanceId)
        ? "unverified"
        : "none";

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
      {/* Per-instance contact pools — each part seated on the bench floor. */}
      {pools.map((pool) => (
        <mesh
          key={`sh-${pool.id}`}
          position={[pool.center[0], floor - 0.02, pool.center[1]]}
          scale={[
            pool.size[0] * SHADOW_FACTOR,
            pool.size[1] * SHADOW_FACTOR,
            1,
          ]}
          rotation={[-Math.PI / 2, 0, 0]}
        >
          <planeGeometry args={[1, 1]} />
          <meshBasicMaterial
            color={viewport.groundShadow}
            map={groundShadowTexture()}
            transparent
            opacity={
              pool.ghost
                ? viewport.groundShadowOpacity *
                  assemblyTokens.ghost.surfaceOpacity
                : viewport.groundShadowOpacity
            }
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
      ))}

      {instances.map((inst) =>
        inst.geometry && isDrawn(inst) ? (
          <InstanceMesh
            key={inst.id}
            geometry={inst.geometry}
            transform={inst.transform}
            selected={selectedInstanceId === inst.id}
            clashing={clashingInstanceIds.has(inst.id)}
            unverified={unverifiedInstanceIds.has(inst.id)}
            ghost={inst.visibility === "ghost"}
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
            if (!inst.geometry || !isDrawn(inst)) return null;
            return (
              <InstanceMateOverlay
                key={`ov-${inst.id}`}
                instanceId={inst.id}
                transform={inst.transform}
                // The instance's own drawn mesh IS the mate face hit-test
                // (SEL-4). Same `loadGlbGeometry` parser as the part scene, so
                // it carries the same B-rep face partition.
                geometry={inst.geometry.surface}
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

      {instances.filter(isDrawn).map((inst) => (
        <Balloon
          key={`b-${inst.id}`}
          instance={inst}
          selected={selectedInstanceId === inst.id}
          clashState={clashStateOf(inst.id)}
          onSelect={() =>
            tool === "lock" ? pickInstance(inst.id) : onSelectInstance(inst.id)
          }
        />
      ))}
    </group>
  );
}
