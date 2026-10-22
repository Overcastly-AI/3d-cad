/**
 * 3D sketches in the viewport (SKETCH-3D): every saved 3D sketch's lines at
 * their SOLVED positions, and, while the 3D sketch editor is open, its draft
 * (as typed) with a snap mark on every target it can attach a point to (the
 * origin, earlier sketches' points, model vertices) and on its own points (a
 * click continues the chain there).
 *
 * The marks are the shared DOM `PickNode`s, so a snap is keyboard-reachable
 * and e2e-drivable by test id (`sketch3d-snap-<key>`, `sketch3d-own-<id>`).
 * Presentational: the targets come from `features/sketch3dSnaps`, the draft
 * and its edits from `features/sketch3dStore`.
 */
import { PickNode } from "@loft/design";
import { sketch } from "@loft/design/tokens";
import { useMemo } from "react";

import type { Vec3 } from "../api/parts";
import type { Sketch3DLayer as Layer } from "../features/sketch3d";
import type { SnapTarget } from "../features/sketch3dSnaps";
import { useSketch3DStore } from "../features/sketch3dStore";
import { formatVec3Mm, occtToScene } from "../measure/geometry";
import { ANNOTATION_LAYER } from "./instruments";
import { Segments } from "./overlaySegments";
import { PickMark } from "./PickMark";

export interface Sketch3DLayerProps {
  /** Every 3D sketch of the tree, solved where the rebuild has it. */
  layers: readonly Layer[];
  /** Snap targets while the editor is open (empty otherwise). */
  targets: readonly SnapTarget[];
}

function push(out: number[], a: Vec3, b: Vec3): void {
  out.push(...occtToScene(a), ...occtToScene(b));
}

export function Sketch3DSceneLayer({ layers, targets }: Sketch3DLayerProps) {
  const form = useSketch3DStore((s) => s.form);
  const editing = useSketch3DStore((s) => s.featureId);
  const snap = useSketch3DStore((s) => s.snap);
  const continueAt = useSketch3DStore((s) => s.continueAt);

  const saved = useMemo(() => {
    const real: number[] = [];
    const construction: number[] = [];
    for (const layer of layers) {
      if (form !== null && layer.featureId === editing) continue;
      for (const line of layer.lines) {
        const a = layer.points.get(line.start);
        const b = layer.points.get(line.end);
        if (a === undefined || b === undefined) continue;
        push(line.construction ? construction : real, a, b);
      }
    }
    return {
      real: new Float32Array(real),
      construction: new Float32Array(construction),
    };
  }, [layers, form, editing]);

  const draft = useMemo(() => {
    const real: number[] = [];
    const construction: number[] = [];
    if (form === null) {
      return { real: new Float32Array(), construction: new Float32Array() };
    }
    const at = new Map(form.points.map((p) => [p.id, p.position] as const));
    for (const line of form.lines) {
      const a = at.get(line.start);
      const b = at.get(line.end);
      if (a === undefined || b === undefined) continue;
      push(line.construction ? construction : real, a, b);
    }
    return {
      real: new Float32Array(real),
      construction: new Float32Array(construction),
    };
  }, [form]);

  return (
    <group userData={ANNOTATION_LAYER}>
      <Segments positions={saved.real} color={sketch.scribeSolved} />
      <Segments positions={saved.construction} color={sketch.constructionInk} />
      {form !== null ? (
        <>
          <Segments
            positions={draft.real}
            color={sketch.scribe}
            depthTest={false}
            renderOrder={998}
          />
          <Segments
            positions={draft.construction}
            color={sketch.constructionInk}
            depthTest={false}
            renderOrder={998}
          />
          {targets.map((target) => (
            <PickMark
              key={target.key}
              position={occtToScene(target.position)}
              zIndexRange={[34, 16]}
            >
              <PickNode
                shape={target.snap.kind === "vertex" ? "vertex" : "center"}
                recede
                data-testid={`sketch3d-snap-${target.key}`}
                aria-label={`Snap to ${target.label} at ${formatVec3Mm(target.position)} millimetres`}
                onClick={() => snap(target.position, target.snap)}
              />
            </PickMark>
          ))}
          {form.points.map((p) => (
            <PickMark
              key={`own-${p.id}`}
              position={occtToScene(p.position)}
              zIndexRange={[36, 18]}
            >
              <PickNode
                shape="vertex"
                selected={form.chainFrom === p.id}
                data-testid={`sketch3d-own-${p.id}`}
                aria-label={`Continue from ${p.id} at ${formatVec3Mm(p.position)} millimetres`}
                onClick={() => continueAt(p.id)}
              />
            </PickMark>
          ))}
        </>
      ) : null}
    </group>
  );
}
