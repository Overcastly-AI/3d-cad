import { Panel, PanelRow, PanelSection } from "@loft/design";

import type { BoxParams, TessellationMetadata } from "../api/tessellate";
import {
  formatBytes,
  formatCount,
  formatExtents,
  formatQuantity,
  formatVec3,
} from "../lib/format";
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

        <PanelSection eyebrow="Mass properties">
          <PanelRow label="Volume" unit="mm³" data-testid="prop-volume">
            {props ? formatQuantity(props.volume) : em}
          </PanelRow>
          <PanelRow label="Area" unit="mm²" data-testid="prop-area">
            {props ? formatQuantity(props.surface_area) : em}
          </PanelRow>
          <PanelRow label="Centroid" unit="mm" data-testid="prop-centroid">
            {props ? formatVec3(props.centroid) : em}
          </PanelRow>
        </PanelSection>

        <PanelSection eyebrow="Bounding box">
          <PanelRow label="Extents" unit="mm" data-testid="prop-extents">
            {props
              ? formatExtents(props.bounding_box.min, props.bounding_box.max)
              : em}
          </PanelRow>
          <PanelRow label="Min" unit="mm">
            {props ? formatVec3(props.bounding_box.min) : em}
          </PanelRow>
          <PanelRow label="Max" unit="mm">
            {props ? formatVec3(props.bounding_box.max) : em}
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

        {/* Title-block footer strip: label over value, like a real drawing. */}
        <div
          className="grid grid-cols-3 divide-x divide-hairline"
          data-testid="titleblock-footer"
        >
          <div className="px-3 py-2">
            <span className="block font-display text-2xs uppercase tracking-[0.14em] text-gauge">
              Units
            </span>
            <span className="block font-data text-xs text-mist">mm</span>
          </div>
          <div className="px-3 py-2">
            <span className="block font-display text-2xs uppercase tracking-[0.14em] text-gauge">
              Kernel
            </span>
            <span className="block font-data text-xs text-mist">OCCT</span>
          </div>
          <div className="px-3 py-2">
            <span className="block font-display text-2xs uppercase tracking-[0.14em] text-gauge">
              Status
            </span>
            <span
              className="block font-data text-xs text-mist"
              data-testid="tessellation-status"
              aria-live="polite"
            >
              {error ? "Error" : isFetching ? "Meshing…" : "Up to date"}
            </span>
          </div>
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
