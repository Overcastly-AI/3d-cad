import {
  areaUnitLabel,
  lengthUnitLabel,
  Panel,
  PanelRow,
  PanelSection,
  volumeUnitLabel,
} from "@loft/design";

import type { BoxParams, TessellationMetadata } from "../api/tessellate";
import {
  formatArea,
  formatBytes,
  formatCount,
  formatExtents,
  formatVec3,
  formatVolume,
} from "../lib/format";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { DimensionForm } from "./DimensionForm";
import { ExportControls } from "./ExportControls";

export interface InspectorPanelProps {
  dimensions: BoxParams;
  onApply: (params: BoxParams) => void;
  meta: TessellationMetadata | undefined;
  isFetching: boolean;
  error: Error | null;
}

/**
 * The inspection block — Loft's signature element. The inspector is composed
 * like an engineering-drawing title block: ruled cells carrying the real
 * OCCT inspection data, with the parametric dimensions as editable cells.
 */
export function InspectorPanel({
  dimensions,
  onApply,
  meta,
  isFetching,
  error,
}: InspectorPanelProps) {
  const props = meta?.properties;
  const em = "—";
  // Readouts honor the document unit (FINDINGS #17); mm outside a provider.
  const unit = useDocumentLengthUnit();
  const lenLabel = lengthUnitLabel(unit);
  return (
    <aside
      className="flex w-full flex-col gap-3"
      aria-label="Model inspector"
      data-testid="inspector"
    >
      <Panel>
        <PanelSection eyebrow="Dimensions">
          <DimensionForm
            key={`${dimensions.x}:${dimensions.y}:${dimensions.z}`}
            initial={dimensions}
            onApply={onApply}
          />
        </PanelSection>

        {/* PROPERTIES, not "mass properties" (materials.md §6.1): a title is a
            claim, and this demo surface tessellates a raw box — there is no
            document to carry a material, so `properties.mass_g` is null here
            forever. The part workspace's panel earns the word when a material
            gives it a mass; this one never can, so it never says it. */}
        <PanelSection eyebrow="Properties">
          <PanelRow
            label="Volume"
            unit={volumeUnitLabel(unit)}
            data-testid="prop-volume"
          >
            {props ? formatVolume(props.volume, unit) : em}
          </PanelRow>
          <PanelRow
            label="Area"
            unit={areaUnitLabel(unit)}
            data-testid="prop-area"
          >
            {props ? formatArea(props.surface_area, unit) : em}
          </PanelRow>
          <PanelRow
            label="Centroid"
            unit={lenLabel}
            data-testid="prop-centroid"
          >
            {props ? formatVec3(props.centroid, unit) : em}
          </PanelRow>
        </PanelSection>

        <PanelSection eyebrow="Bounding box">
          <PanelRow label="Extents" unit={lenLabel} data-testid="prop-extents">
            {props
              ? formatExtents(
                  props.bounding_box.min,
                  props.bounding_box.max,
                  unit,
                )
              : em}
          </PanelRow>
          <PanelRow label="Min" unit={lenLabel}>
            {props ? formatVec3(props.bounding_box.min, unit) : em}
          </PanelRow>
          <PanelRow label="Max" unit={lenLabel}>
            {props ? formatVec3(props.bounding_box.max, unit) : em}
          </PanelRow>
        </PanelSection>

        <PanelSection eyebrow="Topology">
          <PanelRow label="Faces" data-testid="prop-faces">
            {props ? formatCount(props.topology.faces) : em}
          </PanelRow>
          <PanelRow label="Edges">
            {props ? formatCount(props.topology.edges) : em}
          </PanelRow>
          <PanelRow label="Shells">
            {props ? formatCount(props.topology.shells) : em}
          </PanelRow>
        </PanelSection>

        <PanelSection eyebrow="Mesh">
          <PanelRow label="Triangles" data-testid="prop-triangles">
            {meta ? formatCount(meta.mesh.triangles) : em}
          </PanelRow>
          <PanelRow label="Vertices">
            {meta ? formatCount(meta.mesh.vertices) : em}
          </PanelRow>
          <PanelRow label="Payload">
            {meta ? formatBytes(meta.mesh.glb_bytes) : em}
          </PanelRow>
        </PanelSection>

        {/* Title-block footer: the one cell that MOVES — the mesh status.
            UNITS + KERNEL were decorative (UI-REVIEW 2026-07-16, Track B). */}
        {/* One ruled cell, matching the tree's SOLVE vital — caption and value
            on a line, not stacked (density pass, 2026-08-28). */}
        <div
          className="flex min-h-target-dense items-center gap-2 px-3 py-0.5"
          data-testid="titleblock-footer"
        >
          <span className="shrink-0 font-display text-2xs uppercase tracking-[0.14em] text-gauge">
            Status
          </span>
          <span
            className="grow text-right font-data text-sm text-mist"
            data-testid="tessellation-status"
            aria-live="polite"
          >
            {error ? "Error" : isFetching ? "Meshing…" : "Up to date"}
          </span>
        </div>

        {/* EXPORT row: issuing the part file is title-block business. */}
        <ExportControls dimensions={dimensions} />
      </Panel>

      {error ? (
        <p
          role="alert"
          className="font-body text-xs text-flag"
          data-testid="tessellation-error"
        >
          Tessellation failed — check that the gateway is running, then apply
          again.
        </p>
      ) : null}
    </aside>
  );
}
