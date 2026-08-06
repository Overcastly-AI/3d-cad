/**
 * The face-pick overlay inside the WebGL viewport — the "Pick a face" step of
 * the sketch plane picker. Every PLANAR face of the current body gets a
 * DOM-in-canvas `PickNode` (drei `Html`) at its area centroid, so picking is
 * keyboard-navigable, screen-reader named, and e2e-drivable (the same posture
 * as the measurement overlay). Non-planar faces carry no signature and are NOT
 * pickable in v1 — they are omitted, never a dead target.
 *
 * The pick reads as TOPOLOGY, not a blanket of floating squares (UI audit
 * #19a): the face under the cursor (hovered) — or the one currently armed —
 * also gets a translucent brass patch laid ON its plane (built from the
 * signature's centroid + normal + area), so the highlight is the real surface,
 * cursor-driven. Every color/opacity comes from `@loft/design` tokens.
 *
 * A clicked face echoes its stage-1 `signature` into an `on_face` datum (the
 * parent owns that write + the sketch seating); this layer is presentational.
 */
import { PickNode } from "@loft/design";
import { viewport } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useThree, type ThreeEvent } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useState } from "react";
import { DoubleSide, Quaternion, Vector3 } from "three";

import type { OverlayFace, PlanarFaceSignature } from "../api/parts";
import { faceLabel, isPickableFace } from "../features/face";
import { occtToScene } from "../measure/geometry";
import { faceOrdinalOfTriangle } from "./glbGeometry";
import { usePartViewStore } from "./partView";

export interface FacePickOverlayProps {
  /** The evaluated body's faces (from `OverlayResult.faces`), or null. */
  faces: readonly OverlayFace[] | null;
  /** Author an `on_face` datum from the picked face and seat the sketch. */
  onPick: (face: OverlayFace & { signature: PlanarFaceSignature }) => void;
  /** The `body.faces()` index currently being authored (brass-fill busy cue). */
  pendingIndex: number | null;
}

/** +Z (a circle's rest normal) → the face's scene-space normal. */
const REST_NORMAL = new Vector3(0, 0, 1);

/** A translucent disc laid on a planar face's plane — the topology highlight. */
function FacePatch({
  signature,
  selected,
}: {
  signature: PlanarFaceSignature;
  selected: boolean;
}) {
  const { position, quaternion, radius } = useMemo(() => {
    const pos = occtToScene(signature.centroid);
    // The normal is a DIRECTION — the OCCT→scene map is a pure rotation, so the
    // same point transform carries it (no translation term).
    const n = occtToScene(signature.normal);
    const sceneNormal = new Vector3(n[0], n[1], n[2]).normalize();
    const quat = new Quaternion().setFromUnitVectors(REST_NORMAL, sceneNormal);
    // Area-equivalent disc — a plane-lying patch that reads as "this face".
    const r = Math.max(
      Math.sqrt(Math.max(signature.area_mm2, 0) / Math.PI),
      0.5,
    );
    return {
      position: new Vector3(pos[0], pos[1], pos[2]),
      quaternion: quat,
      radius: r,
    };
  }, [signature]);

  return (
    <mesh position={position} quaternion={quaternion}>
      <circleGeometry args={[radius, 48]} />
      <meshBasicMaterial
        color={selected ? viewport.facePick.selected : viewport.facePick.hover}
        transparent
        opacity={
          selected
            ? viewport.facePick.selectedOpacity
            : viewport.facePick.hoverOpacity
        }
        side={DoubleSide}
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  );
}

export function FacePickOverlay({
  faces,
  onPick,
  pendingIndex,
}: FacePickOverlayProps) {
  const invalidate = useThree((s) => s.invalidate);
  const [hovered, setHovered] = useState<number | null>(null);
  /** The drawn mesh, published by `ModelMesh` — the raycast target for A2. */
  const pickGeometry = usePartViewStore((state) => state.pickGeometry);
  /** …and which of its faces belong to a body the modeller switched off. */
  const pickHiddenFaces = usePartViewStore((state) => state.pickHiddenFaces);

  // frameloop="demand": redraw when the pickable set / pending / hover changes.
  useEffect(() => {
    invalidate();
  }, [faces, pendingIndex, hovered, invalidate]);

  // Drop a stale hover when the pickable set changes out from under it.
  useEffect(() => {
    setHovered(null);
  }, [faces]);

  /**
   * QA hook: which face the armed pick is currently addressing (SEL-1 / A2).
   * Stamped on the viewport container — the same posture `data-hovered-face`
   * and `data-body-highlight` already take — because the thing under test is a
   * RAYCAST handler, and `document.elementFromPoint` can only ever answer
   * "the canvas" for those. Without it the affordance can only be measured by
   * clicking, which mutates the document once per sample point.
   */
  const canvas = useThree((state) => state.gl.domElement);
  useEffect(() => {
    const node = canvas.closest<HTMLElement>('[data-testid="viewport"]');
    if (node === null) return;
    if (hovered === null) delete node.dataset["facePickHover"];
    else node.dataset["facePickHover"] = String(hovered);
    return () => {
      delete node.dataset["facePickHover"];
    };
  }, [hovered, canvas]);

  /**
   * SEL-1 / spec A2 — the surface IS the target.
   *
   * The founder said face picking was "very difficult" and QA put a number on
   * it: 32 of 1457 sample points over the body were live targets, **2.2 %**.
   * The other 97.8 % was dead, because the only thing listening was a 24 px
   * `PickNode` at each face's area CENTROID. Every pick spec was green the
   * whole time — they call `getByTestId(...).click()`, which lands on that dot
   * with machine precision, so the suite proved a path no hand takes (FB-17b).
   *
   * A face is now hit by RAYCASTING the drawn mesh and resolving the struck
   * triangle back to its B-rep face ordinal — the same ordinal space
   * `OverlayFace.index` uses, so no mapping table is needed and none can drift.
   * `PickNode` stays exactly where it was, demoted from sole hit-test to what
   * §5 asks of it: the keyboard focus target, the screen-reader name, and the
   * touch tap target.
   *
   * A hit on a face that is NOT pickable (non-planar — it carries no signature,
   * so there is nothing to seat a datum on) resolves to null and is IGNORED
   * rather than snapped to a nearby planar face. A pick that quietly acts on
   * geometry the user did not address is worse than one that does nothing, and
   * "nothing" here is honest: the overlay draws no patch there either, so the
   * screen already said this face is not on offer.
   *
   * A face of a HIDDEN body is refused for the same reason and by the same
   * rule `ModelMesh` applies to its own handler. It has to be refused
   * explicitly: the raycast target below takes a SINGLE material, and
   * `Mesh._computeIntersections` only consults a group's material — and so its
   * `visible` flag — when `mesh.material` is an ARRAY. Every triangle of the
   * fused mesh is therefore tested whatever its body's state, so without this a
   * hidden body in FRONT would absorb the ray and the pick would address an
   * invisible face while the modeller aimed at the visible one behind it.
   *
   * Only the `event` object's `faceIndex` is read, so the parameter is typed as
   * exactly that. It used to take a full `ThreeEvent<PointerEvent>`, which
   * forced the click handler — whose event is a `MouseEvent` — through a double
   * cast; narrowing the requirement removes the cast instead of silencing it.
   */
  const pickableAt = useCallback(
    (
      event: Pick<ThreeEvent<PointerEvent>, "faceIndex">,
    ): OverlayFace | null => {
      if (faces === null || pickGeometry === null) return null;
      const triangle = event.faceIndex;
      if (triangle === undefined || triangle === null) return null;
      const ordinal = faceOrdinalOfTriangle(pickGeometry, triangle);
      if (ordinal === null || pickHiddenFaces.has(ordinal)) return null;
      const face = faces.find((candidate) => candidate.index === ordinal);
      return face !== undefined && isPickableFace(face) ? face : null;
    },
    [faces, pickGeometry, pickHiddenFaces],
  );

  const onSurfaceMove = useCallback(
    (event: ThreeEvent<PointerEvent>) => {
      const face = pickableAt(event);
      setHovered((current) => {
        const next = face?.index ?? null;
        return current === next ? current : next;
      });
    },
    [pickableAt],
  );

  const onSurfaceClick = useCallback(
    (event: ThreeEvent<MouseEvent>) => {
      const face = pickableAt(event);
      if (face === null || !isPickableFace(face)) return;
      event.stopPropagation();
      onPick(face);
    },
    [pickableAt, onPick],
  );

  if (faces === null) return null;

  return (
    <group>
      {/*
        The raycast target. It draws NOTHING — `colorWrite:false` plus
        `depthWrite:false` means it contributes no fragments and no depth, so
        the body on screen is still `ModelMesh`'s and this cannot tint, hide or
        z-fight with it. It exists purely so r3f's event system has a surface to
        hit. `renderOrder={-1}` puts it first within its pass; it carries no
        `transparent`, because `colorWrite:false` already guarantees nothing is
        written and the OPAQUE list is the cheaper place to draw nothing (an
        earlier note claimed `renderOrder` was what kept it out of the
        transparent pass — `transparent` is what selects that list, so the flag
        was putting it in the very pass the comment said it avoided).
      */}
      {pickGeometry !== null ? (
        <mesh
          geometry={pickGeometry}
          onPointerMove={onSurfaceMove}
          onPointerOut={() => setHovered(null)}
          onClick={onSurfaceClick}
          renderOrder={-1}
        >
          <meshBasicMaterial colorWrite={false} depthWrite={false} />
        </mesh>
      ) : null}
      {faces.map((face) =>
        isPickableFace(face) ? (
          <group key={`f${face.index}`}>
            {pendingIndex === face.index || hovered === face.index ? (
              <FacePatch
                signature={face.signature}
                selected={pendingIndex === face.index}
              />
            ) : null}
            <Html
              position={occtToScene(face.signature.centroid)}
              center
              zIndexRange={[30, 10]}
            >
              <PickNode
                shape="face"
                // A7's recession, scoped to the ONE overlay that earned it: A2
                // made the drawn surface this pick's primary hit-test, so the
                // mark here is the keyboard/touch fallback and may rest quiet.
                // The overlays still hanging their only handler on `PickNode`
                // pass nothing and stay at full strength.
                recede
                selected={pendingIndex === face.index}
                data-testid={`plane-pick-face-${face.index}`}
                aria-label={faceLabel(face.index, face.signature)}
                onClick={() => onPick(face)}
                onPointerOver={() => setHovered(face.index)}
                onPointerOut={() =>
                  setHovered((h) => (h === face.index ? null : h))
                }
                onFocus={() => setHovered(face.index)}
                onBlur={() => setHovered((h) => (h === face.index ? null : h))}
              />
            </Html>
          </group>
        ) : null,
      )}
    </group>
  );
}
