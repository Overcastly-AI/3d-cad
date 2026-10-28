/**
 * The outline picks of a custom feature's dialog (BUILDING-OUTLINE): which
 * field the viewport picks for, what it offers there, and the browser row
 * clicks the dialog takes. The values stay the form's; this publishes them
 * to `outlinePickStore` for `viewport/OutlinePickOverlay`.
 *
 * One field is LIVE at a time, as in Fusion: the one last clicked or
 * focused. Until one is, it is the first side pick whose outline is known
 * (an opening's Wall, a roof's Defines slope), else the Outline field.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import type { FeatureResponse } from "../api/parts";
import type { PluginInput, PluginManifest } from "../api/plugins";
import {
  isOutlinePick,
  type OutlineSide,
  outlineSides,
  segmentSides,
  segmentsOutlineSketch,
  segmentsPickPartitions,
  sideName,
  supersededInputs,
} from "../features/outline";
import {
  type OutlinePickLine,
  type OutlinePickOffer,
  useOutlinePickStore,
} from "../features/outlinePickStore";
import {
  pickedIds,
  referenceOptions,
  togglePick,
} from "../features/pluginForm";
import { planeToWorld } from "../sketch/plane";
import type { SolvedSketchLayer } from "../viewport/solvedSketchLayer";

type SegmentsInput = Extract<PluginInput, { kind: "segments" }>;

/** A side pick's outline, named. */
export interface SegmentsOutline {
  readonly sketch: FeatureResponse | null;
  /** The pick is an Interior wall's partitions, not an outline's sides. */
  readonly partitions: boolean;
  readonly sides: readonly OutlineSide[] | null;
}

function sketchEntities(row: FeatureResponse | null | undefined) {
  return row?.feature.type === "sketch" ? row.feature.params.entities : null;
}

/** The value a side pick takes on a click on *lineId*. */
export function toggleSide(
  input: SegmentsInput,
  value: string,
  lineId: string,
): string {
  if (input.max_items === 1) return value === lineId ? "" : lineId;
  return togglePick(value, lineId);
}

export function useOutlinePick({
  manifest,
  values,
  setValue,
  features,
  selfId,
  layers,
}: {
  manifest: PluginManifest;
  values: Readonly<Record<string, string>>;
  setValue: (name: string, value: string) => void;
  features: readonly FeatureResponse[];
  selfId: string | null;
  layers: readonly SolvedSketchLayer[];
}) {
  const [armed, setArmed] = useState<string | null>(null);
  const hidden = useMemo(
    () => supersededInputs(manifest, values),
    [manifest, values],
  );

  /** Each side pick's outline and its named sides. */
  const outlines = useMemo(() => {
    const out = new Map<string, SegmentsOutline>();
    for (const input of manifest.inputs) {
      if (input.kind !== "segments") continue;
      const sketch = segmentsOutlineSketch(manifest, input, values, features);
      const entities = sketchEntities(sketch);
      const partitions = segmentsPickPartitions(
        manifest,
        input,
        values,
        features,
      );
      out.set(input.name, {
        sketch,
        partitions,
        sides: entities === null ? null : segmentSides(partitions, entities),
      });
    }
    return out;
  }, [manifest, values, features]);

  const live = useMemo(() => {
    const visible = manifest.inputs.filter((i) => !hidden.has(i.name));
    if (armed !== null && visible.some((i) => i.name === armed)) return armed;
    const side = visible.find(
      (i) => i.kind === "segments" && outlines.get(i.name)?.sides != null,
    );
    if (side !== undefined) return side.name;
    return visible.find(isOutlinePick)?.name ?? null;
  }, [manifest, hidden, armed, outlines]);

  const layerOf = useCallback(
    (id: string) => layers.find((layer) => layer.featureId === id) ?? null,
    [layers],
  );

  const offer = useMemo<OutlinePickOffer | null>(() => {
    const input = manifest.inputs.find((i) => i.name === live);
    if (input === undefined) return null;
    const value = values[input.name] ?? "";
    if (input.kind === "segments") {
      const outline = outlines.get(input.name);
      const layer = outline?.sketch == null ? null : layerOf(outline.sketch.id);
      if (outline?.sides == null || layer === null) return null;
      // Named from the stored sketch, drawn where the solve put it.
      const named = outline.sides;
      const lines: OutlinePickLine[] = (
        segmentSides(outline.partitions, layer.entities) ?? []
      ).map((side) => ({
        key: side.lineId,
        lineId: side.lineId,
        label: sideName(named, side.lineId),
        marked: true,
        start: planeToWorld(layer.basis, side.start),
        end: planeToWorld(layer.basis, side.end),
      }));
      return {
        kind: "segments",
        input: input.name,
        lines,
        selected: pickedIds(value),
        onPick: (key) => setValue(input.name, toggleSide(input, value, key)),
      };
    }
    if (!isOutlinePick(input)) return null;
    // Every earlier closed sketch, each line naming its sketch.
    const lines: OutlinePickLine[] = [];
    for (const option of referenceOptions(input, features, selfId)) {
      const layer = layerOf(option.value);
      const row = features.find((f) => f.id === option.value);
      const entities = sketchEntities(row);
      if (layer === null || entities === null) continue;
      if (outlineSides(entities) === null) continue;
      const sides = outlineSides(layer.entities) ?? [];
      sides.forEach((side, k) =>
        lines.push({
          key: option.value,
          lineId: side.lineId,
          label: option.label,
          marked: k === 0,
          start: planeToWorld(layer.basis, side.start),
          end: planeToWorld(layer.basis, side.end),
        }),
      );
    }
    return {
      kind: "sketch",
      input: input.name,
      lines,
      selected: value === "" ? [] : [value],
      onPick: (key) =>
        setValue(input.name, value === key && input.optional ? "" : key),
    };
  }, [manifest, live, values, outlines, layerOf, features, selfId, setValue]);

  const setOffer = useOutlinePickStore((s) => s.setOffer);
  useEffect(() => {
    setOffer(offer);
  }, [offer, setOffer]);
  useEffect(() => () => setOffer(null), [setOffer]);

  /** A browser row click: the live field if it takes it, else the first. */
  const treePick = useCallback(
    (feature: FeatureResponse): boolean => {
      const takers = manifest.inputs.filter(
        (
          input,
        ): input is Extract<PluginInput, { kind: "feature" | "features" }> =>
          (input.kind === "feature" || input.kind === "features") &&
          !hidden.has(input.name) &&
          referenceOptions(input, features, selfId).some(
            (option) => option.value === feature.id,
          ),
      );
      const input =
        takers.find((i) => i.name === live) ??
        takers.find((i) => (values[i.name] ?? "") === "") ??
        takers[0];
      if (input === undefined) return false;
      const value = values[input.name] ?? "";
      setValue(
        input.name,
        input.kind === "features" ? togglePick(value, feature.id) : feature.id,
      );
      setArmed(input.name);
      return true;
    },
    [manifest, hidden, features, selfId, live, values, setValue],
  );
  const setTreePick = useOutlinePickStore((s) => s.setTreePick);
  useEffect(() => {
    setTreePick(treePick);
  }, [treePick, setTreePick]);
  useEffect(() => () => setTreePick(null), [setTreePick]);

  return { live, arm: setArmed, outlines, hidden };
}
