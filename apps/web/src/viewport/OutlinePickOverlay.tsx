/**
 * THE OUTLINE PICK in the viewport (BUILDING-OUTLINE): the lines a custom
 * feature's dialog offers (`outlinePickStore`), drawn over the model and
 * pickable where they lie.
 *
 *  - Picking an OUTLINE: every eligible sketch's lines, a click on any line
 *    naming its sketch (Fusion picks a profile by its curves).
 *  - Picking SIDES: the picked outline's lines, each named by the way its
 *    wall faces ("Front", "Right 1"), a click toggling it, as Revit picks the
 *    walls that define a roof's slope.
 *
 * The outline is the framing's outside face, so once walls stand on it the
 * lines run along the body's outer bottom edges; the line itself is the
 * hit-test (`EdgeBandLayer`, the shared screen-space corridor every edge pick
 * uses), with a diamond per pick as the keyboard, screen-reader and touch
 * target, ghosted where the house hides it (PICKMARK-OCCLUDE-1). The lines
 * draw in sketch ink at rest, brass when picked or hovered (the one
 * selection palette).
 */
import { PickNode } from "@loft/design";
import { measure, sketch } from "@loft/design/tokens";
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo, useState } from "react";

import type { Vec3 } from "../api/measure";
import { useCommandActionStore } from "../features/commandActions";
import {
  type OutlinePickLine,
  useOutlinePickStore,
} from "../features/outlinePickStore";
import { sceneToOcctTuple } from "../sketch/plane";
import { BuriedMark } from "./BuriedMark";
import { EdgeBandLayer } from "./EdgeBandLayer";
import type { EdgeBandInput } from "./edgeBand";
import { ANNOTATION_LAYER } from "./instruments";
import { HighlightLines } from "./overlaySegments";
import { PickMark } from "./PickMark";
import { useViewportPickStamp } from "./pickStamp";
import type { EdgeMarkAnchor } from "./useEdgeMarkAnchors";

/** Same band as the edge marks: under the HUD strips. */
const OUTLINE_Z_RANGE: [number, number] = [17, 0];

function occt(point: readonly [number, number, number]): Vec3 {
  const [x, y, z] = sceneToOcctTuple([point[0], point[1], point[2]]);
  return { x, y, z };
}

function positionsOf(lines: readonly OutlinePickLine[]): Float32Array {
  const out = new Float32Array(lines.length * 6);
  lines.forEach((line, k) => {
    out.set(line.start, k * 6);
    out.set(line.end, k * 6 + 3);
  });
  return out;
}

function midpoint(line: OutlinePickLine): [number, number, number] {
  return [
    (line.start[0] + line.end[0]) / 2,
    (line.start[1] + line.end[1]) / 2,
    (line.start[2] + line.end[2]) / 2,
  ];
}

export function OutlinePickOverlay() {
  const offer = useOutlinePickStore((s) => s.offer);
  const hover = useOutlinePickStore((s) => s.hover);
  const setHover = useOutlinePickStore((s) => s.setHover);
  const requestSubmit = useCommandActionStore((s) => s.requestSubmit);
  const invalidate = useThree((s) => s.invalidate);
  const [anchors, setAnchors] = useState<readonly EdgeMarkAnchor[]>([]);

  useViewportPickStamp("outlinePickHover", hover);

  const lines = useMemo(() => offer?.lines ?? [], [offer]);
  const selected = useMemo(() => new Set(offer?.selected ?? []), [offer]);

  useEffect(() => {
    invalidate();
  }, [lines, selected, hover, invalidate]);

  const bandEdges = useMemo<EdgeBandInput[]>(
    () =>
      lines.map((line, index) => ({
        index,
        polyline: [occt(line.start), occt(line.end)],
      })),
    [lines],
  );

  const restPositions = useMemo(
    () =>
      positionsOf(lines.filter((l) => !selected.has(l.key) && l.key !== hover)),
    [lines, selected, hover],
  );
  const hoverPositions = useMemo(
    () =>
      positionsOf(lines.filter((l) => l.key === hover && !selected.has(l.key))),
    [lines, selected, hover],
  );
  const selectedPositions = useMemo(
    () => positionsOf(lines.filter((l) => selected.has(l.key))),
    [lines, selected],
  );

  if (offer === null) return null;
  const pickIndex = (index: number) => {
    const line = lines[index];
    if (line !== undefined) offer.onPick(line.key);
  };

  return (
    <group userData={ANNOTATION_LAYER}>
      <EdgeBandLayer
        edges={bandEdges}
        onHover={(index) =>
          setHover(index === null ? null : (lines[index]?.key ?? null))
        }
        onPick={pickIndex}
        onAnchors={setAnchors}
      />
      <HighlightLines
        positions={restPositions}
        color={sketch.scribeSolved}
        widthPx={measure.edgeWidthPx}
        xrayOpacity={measure.edgeXrayOpacity}
      />
      <HighlightLines
        positions={hoverPositions}
        color={measure.edgeHover}
        widthPx={measure.edgeWidthPx}
        xrayOpacity={measure.edgeXrayOpacity}
        renderOrder={2}
      />
      <HighlightLines
        positions={selectedPositions}
        color={measure.edgeSelected}
        widthPx={measure.edgeWidthPx}
        xrayOpacity={measure.edgeXrayOpacity}
        renderOrder={4}
      />
      {lines.map((line, index) => {
        if (!line.marked) return null;
        const anchor = anchors[index];
        const buried = anchor?.buried === true;
        const picked = selected.has(line.key);
        return (
          <PickMark
            key={`${line.key}:${line.lineId}`}
            position={anchor?.position ?? midpoint(line)}
            zIndexRange={OUTLINE_Z_RANGE}
          >
            {buried ? <BuriedMark shape="edge" /> : null}
            <PickNode
              shape="edge"
              recede
              occluded={buried}
              selected={picked}
              data-testid={`outline-pick-${line.key}`}
              data-buried={buried ? "true" : "false"}
              aria-label={
                offer.kind === "segments"
                  ? `${line.label} wall`
                  : `Outline ${line.label}`
              }
              onClick={() => offer.onPick(line.key)}
              onEnterKey={requestSubmit}
              onPointerOver={() => setHover(line.key)}
              onPointerOut={() => setHover(null)}
              onFocus={() => setHover(line.key)}
              onBlur={() => setHover(null)}
            />
          </PickMark>
        );
      })}
    </group>
  );
}
