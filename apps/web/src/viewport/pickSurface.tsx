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
import { useCallback, type RefObject } from "react";
import type { BufferGeometry, Mesh } from "three";
import type { ThreeEvent } from "@react-three/fiber";

import { faceOrdinalOfTriangle } from "./glbGeometry";
import { usePartViewStore } from "./partView";

/** Shared empty set — a stable identity, so "nothing hidden" costs no render. */
const NO_HIDDEN_FACES: ReadonlySet<number> = new Set<number>();

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
   * Face ordinals to refuse. Defaults to the part store's hidden set when
   * `geometry` is omitted, and to none when it is passed (assembly instance
   * visibility is already gated upstream — an undrawn instance mounts no
   * overlay at all).
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
  const partGeometry = usePartViewStore((state) => state.pickGeometry);
  const partHiddenFaces = usePartViewStore((state) => state.pickHiddenFaces);
  const ownGeometry = geometry !== undefined;
  const target = ownGeometry ? geometry : partGeometry;
  const hidden =
    hiddenFaces ?? (ownGeometry ? NO_HIDDEN_FACES : partHiddenFaces);

  /**
   * The struck triangle → its B-rep face ordinal, or null when there is nothing
   * addressable there.
   *
   * A face of a HIDDEN body is refused explicitly, by the same rule `ModelMesh`
   * applies to its own handler. It HAS to be explicit: the mesh below takes a
   * SINGLE material, and `Mesh._computeIntersections` only consults a group's
   * material — and so its `visible` flag — when `mesh.material` is an ARRAY.
   * Every triangle of the fused mesh is therefore tested whatever its body's
   * state, so without this a hidden body in FRONT would absorb the ray and the
   * pick would address an invisible face while the modeller aimed at the
   * visible one behind it.
   *
   * Only the event's `faceIndex` is read, so the parameter is typed as exactly
   * that — which lets the click handler, whose event carries a `MouseEvent`,
   * share it without a cast.
   */
  const ordinalAt = useCallback(
    (event: Pick<ThreeEvent<PointerEvent>, "faceIndex">): number | null => {
      if (target === null || target === undefined) return null;
      const triangle = event.faceIndex;
      if (triangle === undefined || triangle === null) return null;
      const ordinal = faceOrdinalOfTriangle(target, triangle);
      if (ordinal === null || hidden.has(ordinal)) return null;
      return ordinal;
    },
    [target, hidden],
  );

  const handleMove = useCallback(
    (event: ThreeEvent<PointerEvent>) => onMove(ordinalAt(event), event),
    [ordinalAt, onMove],
  );

  const handleClick = useCallback(
    (event: ThreeEvent<MouseEvent>) => onClick?.(ordinalAt(event), event),
    [ordinalAt, onClick],
  );

  if (target === null || target === undefined) return null;

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
    */
    <mesh
      ref={meshRef}
      geometry={target}
      onPointerMove={handleMove}
      onPointerOut={onOut}
      onClick={onClick === undefined ? undefined : handleClick}
      renderOrder={-1}
    >
      <meshBasicMaterial colorWrite={false} depthWrite={false} />
    </mesh>
  );
}
