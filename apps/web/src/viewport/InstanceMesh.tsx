/**
 * One assembly instance: the SHARED part geometry drawn at this instance's
 * SOLVED transform. The transform is applied at render time over the shared
 * mesh (design §4 — never baked in), so N instances of a part are N of these
 * over one geometry.
 *
 * The signature moment — snap-on-solve: when a new mate re-solves the pose, the
 * instance TRANSITIONS from its previous place to the bolted one (a short
 * position lerp + orientation slerp) so "the parts snap together" is legible,
 * not a teleport. One deliberate motion; `prefers-reduced-motion` snaps
 * instantly. The loop stays allocation-free (reused target vectors) and drives
 * `frameloop="demand"` with `invalidate` only while moving.
 */
import { assembly as assemblyTokens } from "@loft/design/tokens";
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import {
  type Group,
  LineBasicMaterial,
  MeshMatcapMaterial,
  Quaternion,
  Vector3,
} from "three";

import type { SceneTransform } from "../assembly/placement";
import { studioMatcap } from "./studioMatcap";
import type { InstanceGeometry } from "./useInstanceGeometries";

export interface InstanceMeshProps {
  geometry: InstanceGeometry;
  /** The SOLVED scene-space transform (target of the snap transition). */
  transform: SceneTransform;
  selected: boolean;
  /** MEASURED interference — edge + surface flush red. */
  clashing?: boolean;
  /**
   * Flagged by the last check as an UNMEASURABLE pair (the exact boolean
   * failed): cooled surface + lifted edges, never the alarm flush. The viewport
   * draws attention without asserting a measurement the kernel declined to
   * make — the DOM schedule and tree already say "Unverified" in these words.
   */
  unverified?: boolean;
  reducedMotion: boolean;
  onSelect?: () => void;
}

/** Below this squared scene-mm distance the snap is considered complete. */
const SNAP_EPSILON_SQ = 1e-4;

export function InstanceMesh({
  geometry,
  transform,
  selected,
  clashing = false,
  unverified = false,
  reducedMotion,
  onSelect,
}: InstanceMeshProps) {
  const groupRef = useRef<Group>(null);
  const invalidate = useThree((s) => s.invalidate);

  // Reused animation targets — no per-frame allocation.
  const targetPos = useRef(new Vector3());
  const targetQuat = useRef(new Quaternion());
  const animating = useRef(false);
  const mounted = useRef(false);

  // The shared studio matcap — same "machined aluminum" as a lone part.
  const surfaceMaterial = useMemo(
    () => new MeshMatcapMaterial({ matcap: studioMatcap() }),
    [],
  );
  const edgeMaterial = useMemo(() => new LineBasicMaterial(), []);
  useEffect(
    () => () => {
      surfaceMaterial.dispose();
      edgeMaterial.dispose();
    },
    [surfaceMaterial, edgeMaterial],
  );

  // Selection cue: brass edges + a warm surface tint (matcaps have no
  // emissive channel; the tint multiplies the studio sphere toward brass,
  // so the machined read is preserved — boldness stays on the balloon/snap).
  // A MEASURED interference flushes the body red instead — the alarm reads over
  // the rest state but yields to an explicit selection (the user's pick wins).
  // An UNMEASURABLE pair is COOLED and its edges lifted a step: attention, no
  // assertion (three states, one clash language, three surfaces).
  useEffect(() => {
    const edge = selected
      ? assemblyTokens.selected
      : clashing
        ? assemblyTokens.clash
        : unverified
          ? assemblyTokens.unverified
          : assemblyTokens.instanceEdge;
    const tint = selected
      ? assemblyTokens.selectedTint
      : clashing
        ? assemblyTokens.clashTint
        : unverified
          ? assemblyTokens.unverifiedTint
          : assemblyTokens.restTint;
    edgeMaterial.color.set(edge);
    surfaceMaterial.color.set(tint);
    invalidate();
  }, [
    selected,
    clashing,
    unverified,
    edgeMaterial,
    surfaceMaterial,
    invalidate,
  ]);

  // Adopt a new solved transform. First mount snaps to place (no fly-in from
  // the origin); later changes animate (unless reduced motion is requested).
  useEffect(() => {
    targetPos.current.set(...transform.position);
    targetQuat.current.set(...transform.quaternion);
    const group = groupRef.current;
    if (group === null) return;
    if (!mounted.current || reducedMotion) {
      group.position.copy(targetPos.current);
      group.quaternion.copy(targetQuat.current);
      mounted.current = true;
      animating.current = false;
    } else {
      animating.current = true;
    }
    invalidate();
  }, [transform, reducedMotion, invalidate]);

  useFrame(() => {
    if (!animating.current) return;
    const group = groupRef.current;
    if (group === null) return;
    group.position.lerp(targetPos.current, 0.22);
    group.quaternion.slerp(targetQuat.current, 0.22);
    if (group.position.distanceToSquared(targetPos.current) < SNAP_EPSILON_SQ) {
      group.position.copy(targetPos.current);
      group.quaternion.copy(targetQuat.current);
      animating.current = false;
    } else {
      invalidate();
    }
  });

  return (
    <group
      ref={groupRef}
      onPointerDown={
        onSelect
          ? (event) => {
              event.stopPropagation();
              onSelect();
            }
          : undefined
      }
    >
      <mesh geometry={geometry.surface} material={surfaceMaterial} />
      <lineSegments geometry={geometry.edges} material={edgeMaterial} />
    </group>
  );
}
