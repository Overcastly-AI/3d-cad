/**
 * The snap points a joint origin can take on one part, from the part's own
 * `/overlay` (part-local mm): every planar face's centre, every circular
 * edge's centre (hole rims), and the start / middle / end of every other edge.
 * Fusion shows the points of the face under the cursor and snaps to the one
 * nearest it; `facePoints` and `nearestPoint` are those two halves.
 * Pure; the viewport layer draws what this returns.
 */
import type { OverlayResult } from "../api/measure";
import type { EdgeSignature, PlanarFaceSignature } from "../api/parts";
import { isPickableFace } from "../features/face";
import {
  circleCentre,
  edgePoint,
  type JointEdgeAt,
  type JointOriginKind,
  type JointOriginPick,
} from "./joints";
import type { Vec3 } from "./placement";

export interface OriginCandidate {
  /** Unique within the part: `face-3`, `circle-7`, `edge-5-mid`. */
  key: string;
  kind: JointOriginKind;
  at: JointEdgeAt | null;
  /** Overlay face or edge index. */
  index: number;
  signature: PlanarFaceSignature | EdgeSignature;
  /** Part-local mm. */
  point: Vec3;
  /** Accessible name, ending in the point ("…at 20, 12.5, 10 millimetres"). */
  label: string;
  /** The plane a face centre is on (unit normal, point), for `facePoints`. */
  plane: { normal: Vec3; point: Vec3 } | null;
}

const round = (n: number) => {
  const r = Math.round(n * 10) / 10;
  return r === 0 ? 0 : r;
};
const at = (p: Vec3) =>
  `${round(p.x)}, ${round(p.y)}, ${round(p.z)} millimetres`;

const AT_WORD: Record<JointEdgeAt, string> = {
  start: "start",
  mid: "midpoint",
  end: "end",
};

/** Every snap point the part offers. */
export function originCandidates(overlay: OverlayResult): OriginCandidate[] {
  const out: OriginCandidate[] = [];
  for (const face of overlay.faces) {
    if (!isPickableFace(face)) continue;
    const point = face.signature.centroid;
    out.push({
      key: `face-${face.index}`,
      kind: "face_centre",
      at: null,
      index: face.index,
      signature: face.signature,
      point,
      label: `Face ${face.index + 1} centre at ${at(point)}`,
      plane: { normal: face.signature.normal, point },
    });
  }
  overlay.edges.forEach((edge, index) => {
    const signature = edge.signature;
    if (signature.curve === "circle") {
      const point = circleCentre(signature);
      out.push({
        key: `circle-${index}`,
        kind: "circle_centre",
        at: null,
        index,
        signature,
        point,
        label: `Hole centre, edge ${index + 1}, at ${at(point)}`,
        plane: null,
      });
      return;
    }
    for (const which of ["start", "mid", "end"] as const) {
      const point = edgePoint(signature, which);
      out.push({
        key: `edge-${index}-${which}`,
        kind: "edge_point",
        at: which,
        index,
        signature,
        point,
        label: `Edge ${index + 1} ${AT_WORD[which]} at ${at(point)}`,
        plane: null,
      });
    }
  });
  return out;
}

/** Distance of a point from a plane, mm. */
function planeDistance(plane: { normal: Vec3; point: Vec3 }, p: Vec3): number {
  const { normal: n, point: o } = plane;
  return Math.abs(n.x * (p.x - o.x) + n.y * (p.y - o.y) + n.z * (p.z - o.z));
}

const ON_PLANE_MM = 1e-4;

/**
 * The points a hovered face reveals: its own centre and every edge / hole
 * centre lying in its plane (the edges that bound it, in practice).
 */
export function facePoints(
  candidates: readonly OriginCandidate[],
  faceIndex: number,
): OriginCandidate[] {
  const face = candidates.find(
    (c) => c.kind === "face_centre" && c.index === faceIndex,
  );
  if (face?.plane == null) return [];
  const plane = face.plane;
  return candidates.filter(
    (c) =>
      c === face ||
      (c.kind !== "face_centre" && planeDistance(plane, c.point) < ON_PLANE_MM),
  );
}

/** The candidate nearest a part-local point, or null. */
export function nearestPoint(
  candidates: readonly OriginCandidate[],
  p: Vec3,
): OriginCandidate | null {
  let best: OriginCandidate | null = null;
  let bestD = Infinity;
  for (const c of candidates) {
    const d =
      (c.point.x - p.x) ** 2 + (c.point.y - p.y) ** 2 + (c.point.z - p.z) ** 2;
    if (d < bestD) {
      bestD = d;
      best = c;
    }
  }
  return best;
}

/** A candidate as the pick the dialog carries. */
export function toOriginPick(
  instanceId: string,
  candidate: OriginCandidate,
): JointOriginPick {
  return {
    instanceId,
    kind: candidate.kind,
    signature: candidate.signature,
    at: candidate.at,
    key: candidate.key,
  };
}
