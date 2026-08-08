/**
 * THE SURFACE HIT-TEST — an invisible sibling mesh over the drawn body, so an
 * armed pick addresses the geometry the modeller can see instead of a 24 px dot
 * at its centroid.
 *
 * SEL-1 / spec A2. The founder said face picking was "very difficult" and QA
 * put a number on it: 32 of 1457 sample points over the body were live targets,
 * **2.2 %**. The other 97.8 % was dead, because the only thing listening was a
 * `PickNode` at each face's area centroid. Every pick spec was green the whole
 * time — they call `getByTestId(...).click()`, which lands on that dot with
 * machine precision, so the suite proved a path no hand takes (FB-17b).
 *
 * A face is hit by RAYCASTING the drawn mesh and resolving the struck triangle
 * back to its B-rep face ordinal — the same ordinal space `OverlayFace.index`
 * uses, so no mapping table is needed and none can drift. `PickNode` stays
 * exactly where it was, demoted from sole hit-test to what
 * `docs/design/pre-selection.md` §5 asks of it: the keyboard focus target, the
 * screen-reader name, and the touch tap target.
 *
 * Extracted from `FacePickOverlay` by SEL-4, which had to make the same
 * conversion five more times. One implementation, not six.
 */
import { useCallback, useMemo, type RefObject } from "react";
import type { BufferGeometry, Intersection, Mesh, Raycaster } from "three";
import type { ThreeEvent } from "@react-three/fiber";

import { faceOrdinalOfTriangle } from "./glbGeometry";
import { usePartViewStore } from "./partView";
import { drawnSurfaceRaycast, hiddenTriangleTest } from "./pickRaycast";

/** Shared empty set — a stable identity, so "nothing hidden" costs no render. */
const NO_HIDDEN_FACES: ReadonlySet<number> = new Set<number>();

export interface PickSurfaceTarget {
  /** The raycast geometry, or null when there is nothing to hit. */
  geometry: BufferGeometry | null;
  /** The B-rep face ordinal a struck triangle belongs to, or null. */
  ordinalAt: (faceIndex: number | null | undefined) => number | null;
  /** The mesh's `raycast`, which reports the nearest DRAWN triangle only. */
  raycast: (
    this: Mesh,
    raycaster: Raycaster,
    intersects: Intersection[],
  ) => void;
}

/**
 * Resolve the pick surface, its hidden-body filter and its triangle→face rule
 * ONCE, for every consumer of it.
 *
 * WHERE THE REFUSAL LIVES, AND WHY NOT IN THE HANDLER (SEL-6). A hidden body is
 * a draw group whose material is `visible: false`, and three's raycaster does
 * not read `visible` at all — `checkIntersection()` consults only
 * `material.side` — so a switched-off body's triangles are tested exactly like
 * a drawn one's. r3f then keeps ONE hit per object, the nearest triangle. A
 * handler handed that hit can only refuse it; it never sees the drawn face
 * BEHIND it, because no second hit was ever offered. That is why this used to
 * return a three-way `PickTriangle` with a `hidden` case, and why the case is
 * gone: {@link drawnSurfaceRaycast} drops hidden triangles inside `raycast`,
 * before r3f dedupes, so the nearest DRAWN triangle is what reaches the
 * handler and `ordinalAt` has nothing left to refuse.
 */
export function usePickSurfaceTarget(
  geometry?: BufferGeometry | null,
  hiddenFaces?: ReadonlySet<number>,
): PickSurfaceTarget {
  const partGeometry = usePartViewStore((state) => state.pickGeometry);
  const partHiddenFaces = usePartViewStore((state) => state.pickHiddenFaces);
  const ownGeometry = geometry !== undefined;
  const target = (ownGeometry ? geometry : partGeometry) ?? null;
  const hidden =
    hiddenFaces ?? (ownGeometry ? NO_HIDDEN_FACES : partHiddenFaces);

  const ordinalAt = useCallback(
    (faceIndex: number | null | undefined): number | null => {
      if (target === null) return null;
      if (faceIndex === undefined || faceIndex === null) return null;
      return faceOrdinalOfTriangle(target, faceIndex);
    },
    [target],
  );

  const raycast = useMemo(
    () => drawnSurfaceRaycast(hiddenTriangleTest(target, hidden)),
    [target, hidden],
  );

  return useMemo(
    () => ({ geometry: target, ordinalAt, raycast }),
    [target, ordinalAt, raycast],
  );
}

export interface PickSurfaceProps {
  /**
   * The raycast target. OMIT IT in the part workspace and the mesh published by
   * `ModelMesh` is used, together with the ordinals its hidden bodies own.
   * Pass one explicitly for a scene that has no single part mesh — the assembly
   * workspace hands each instance its own `InstanceGeometry.surface`, parsed by
   * the SAME `loadGlbGeometry`, so it carries the same face partition.
   */
  geometry?: BufferGeometry | null;
  /**
   * Face ordinals that are NOT DRAWN, and so must not absorb the ray. Defaults
   * to the part store's hidden set when `geometry` is omitted, and to none when
   * it is passed (assembly instance visibility is already gated upstream — an
   * undrawn instance mounts no overlay at all, so the filter is a no-op there).
   */
  hiddenFaces?: ReadonlySet<number>;
  /** The mesh itself, for callers that must identify its hit among others. */
  meshRef?: RefObject<Mesh | null>;
  /** Pointer moved over the surface — the resolved B-rep face ordinal. */
  onMove: (ordinal: number | null, event: ThreeEvent<PointerEvent>) => void;
  /** Pointer left the surface entirely. */
  onOut?: () => void;
  /** Click on the surface — the resolved B-rep face ordinal. */
  onClick?: (ordinal: number | null, event: ThreeEvent<MouseEvent>) => void;
}

export function PickSurface({
  geometry,
  hiddenFaces,
  meshRef,
  onMove,
  onOut,
  onClick,
}: PickSurfaceProps) {
  const {
    geometry: target,
    ordinalAt,
    raycast,
  } = usePickSurfaceTarget(geometry, hiddenFaces);

  /**
   * The struck triangle → its B-rep face ordinal, or null when the mesh carries
   * no partition there. A HIDDEN body's triangle can no longer arrive here —
   * `raycast` dropped it (SEL-6).
   *
   * Only the event's `faceIndex` is read, so the parameter is typed as exactly
   * that — which lets the click handler, whose event carries a `MouseEvent`,
   * share it without a cast.
   */
  const ordinalOf = useCallback(
    (event: Pick<ThreeEvent<PointerEvent>, "faceIndex">): number | null =>
      ordinalAt(event.faceIndex),
    [ordinalAt],
  );

  const handleMove = useCallback(
    (event: ThreeEvent<PointerEvent>) => onMove(ordinalOf(event), event),
    [ordinalOf, onMove],
  );

  const handleClick = useCallback(
    (event: ThreeEvent<MouseEvent>) => onClick?.(ordinalOf(event), event),
    [ordinalOf, onClick],
  );

  if (target === null) return null;

  return (
    /*
      The raycast target. It draws NOTHING — `colorWrite:false` plus
      `depthWrite:false` means it contributes no fragments and no depth, so the
      body on screen is still the real mesh's and this cannot tint, hide or
      z-fight with it. It exists purely so r3f's event system has a surface to
      hit, and it must actually RENDER rather than be `visible={false}`, because
      three's raycaster skips invisible objects. `renderOrder={-1}` puts it
      first within its pass; it carries no `transparent`, because
      `colorWrite:false` already guarantees nothing is written and the OPAQUE
      list is the cheaper place to draw nothing.

      `raycast` is the SEL-6 filter: it reports the nearest DRAWN triangle, so a
      hidden body in FRONT is seen past rather than merely refused. It has to be
      here and not in the handler — see {@link usePickSurfaceTarget}.
    */
    <mesh
      ref={meshRef}
      geometry={target}
      raycast={raycast}
      onPointerMove={handleMove}
      onPointerOut={onOut}
      onClick={onClick === undefined ? undefined : handleClick}
      renderOrder={-1}
    >
      <meshBasicMaterial colorWrite={false} depthWrite={false} />
    </mesh>
  );
}
