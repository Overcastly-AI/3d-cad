/**
 * Where a 3D sketch point can snap (SKETCH-3D): the origin, every point of an
 * earlier sketch (a 2D sketch's curve ends, centres and points, placed through
 * its plane; a 3D sketch's points), and every model vertex (an end of an
 * overlay edge, named as that edge's `a`/`b` end so it follows the body).
 * Pure: the viewport layer draws one mark per target, and a click places an
 * attached point there.
 */
import type { OverlayEdge } from "../api/measure";
import type { Sketch3DSnap, Vec3 } from "../api/parts";
import {
  planeToWorld,
  sceneToOcctTuple,
  type PlaneBasis,
} from "../sketch/plane";
import type { Sketch3DLayer } from "./sketch3d";

export interface SnapTarget {
  /** Stable test id suffix, e.g. `origin`, `Skeleton-p2`, `vertex-3`. */
  key: string;
  label: string;
  position: Vec3;
  snap: Sketch3DSnap;
}

/** A solved 2D sketch as the scene draws it (scene-space basis). */
export interface FlatSketchLayer {
  featureId: string;
  name: string;
  basis: PlaneBasis;
  entities: readonly {
    id: string;
    kind: string;
    start?: { x: number; y: number };
    end?: { x: number; y: number };
    center?: { x: number; y: number };
    position?: { x: number; y: number };
  }[];
}

const NAMED = ["start", "end", "center", "position"] as const;

function same(a: Vec3, b: Vec3): boolean {
  return (
    Math.abs(a.x - b.x) < 1e-6 &&
    Math.abs(a.y - b.y) < 1e-6 &&
    Math.abs(a.z - b.z) < 1e-6
  );
}

export function snapTargets({
  flat,
  sketches3d,
  edges,
  anchorId,
}: {
  /** Solved 2D sketches BEFORE the 3D sketch, tree order. */
  flat: readonly FlatSketchLayer[];
  /** 3D sketches BEFORE the one being edited, tree order. */
  sketches3d: readonly Sketch3DLayer[];
  /** The body's overlay edges, or null. */
  edges: readonly OverlayEdge[] | null;
  /** The body-affecting feature the edges belong to, or null. */
  anchorId: string | null;
}): SnapTarget[] {
  const out: SnapTarget[] = [
    {
      key: "origin",
      label: "Origin",
      position: { x: 0, y: 0, z: 0 },
      snap: { kind: "origin" },
    },
  ];
  for (const layer of flat) {
    for (const e of layer.entities) {
      for (const name of NAMED) {
        const local = e[name];
        if (local === undefined) continue;
        const [x, y, z] = sceneToOcctTuple(planeToWorld(layer.basis, local));
        out.push({
          key: `${layer.name}-${e.id}-${name}`,
          label: `${layer.name} ${e.id} ${name}`,
          position: { x, y, z },
          snap: {
            kind: "sketch_point",
            sketch: { kind: "feature", feature_id: layer.featureId },
            entity: e.id,
            point: name,
          },
        });
      }
    }
  }
  for (const layer of sketches3d) {
    for (const [id, position] of layer.points) {
      out.push({
        key: `${layer.name}-${id}`,
        label: `${layer.name} ${id}`,
        position,
        snap: {
          kind: "sketch_point",
          sketch: { kind: "feature", feature_id: layer.featureId },
          entity: id,
          point: "position",
        },
      });
    }
  }
  if (edges !== null && anchorId !== null) {
    const seen: Vec3[] = [];
    edges.forEach((edge, index) => {
      const s = edge.signature;
      for (const [end, at] of [
        ["a", s.end_a],
        ["b", s.end_b],
      ] as const) {
        if (seen.some((p) => same(p, at))) continue;
        seen.push(at);
        out.push({
          key: `vertex-${index}-${end}`,
          label: "Model vertex",
          position: at,
          snap: {
            kind: "vertex",
            end,
            edge: {
              kind: "subshape",
              feature_id: anchorId,
              subshape_type: "edge",
              selector: { selector_version: 1, signature: s },
            },
          },
        });
      }
    });
  }
  return out;
}
