import { Panel, PanelRow, PanelSection } from "@loft/design";

import type { ShapeProperties } from "../api/tessellate";
import {
  formatCount,
  formatExtents,
  formatQuantity,
  formatVec3,
} from "../lib/format";

/** Solid-render status shown in the title-block footer's Status cell. */
export type BodyStatus = "up-to-date" | "evaluating" | "regenerating" | "error";

const STATUS_LABEL: Record<BodyStatus, string> = {
  "up-to-date": "Up to date",
  evaluating: "Solving…",
  regenerating: "Regenerating…",
  error: "Error",
};

export interface BodyInspectorProps {
  /** Mass properties of the last-good body, or null when there is none. */
  properties: ShapeProperties | null;
  status: BodyStatus;
}

/**
 * The body's title block — the same ruled inspection panel as first light,
 * carrying the evaluated solid's real OCCT mass properties (volume/area/bbox/
 * topology). Reuses the design primitives + readout formatters; it renders
 * the numbers the geometry service computed, never its own.
 */
export function BodyInspector({ properties, status }: BodyInspectorProps) {
  const props = properties;
  const em = "—";
  return (
    <aside
      className="flex w-full shrink-0 flex-col gap-3 overflow-y-auto p-3 md:w-inspector"
      aria-label="Body inspector"
      data-testid="body-inspector"
    >
      <Panel>
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

        {/* Title-block footer strip: label over value, like a real drawing. */}
        <div
          className="grid grid-cols-3 divide-x divide-hairline border-t border-hairline"
          data-testid="body-titleblock-footer"
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
              data-testid="body-status"
              aria-live="polite"
            >
              {STATUS_LABEL[status]}
            </span>
          </div>
        </div>
      </Panel>
    </aside>
  );
}
