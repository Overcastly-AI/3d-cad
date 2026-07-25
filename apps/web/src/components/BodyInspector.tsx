import {
  areaUnitLabel,
  lengthUnitLabel,
  Panel,
  PanelRow,
  PanelSection,
  volumeUnitLabel,
} from "@loft/design";

import type { ShapeProperties } from "../api/tessellate";
import {
  formatArea,
  formatCount,
  formatExtents,
  formatVec3,
  formatVolume,
} from "../lib/format";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { PartExportControls } from "./PartExportControls";

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
  /** The part this body belongs to — issued by the EXPORT strip. */
  partId: string;
}

/**
 * The body's title block — the same ruled inspection panel as first light,
 * carrying the evaluated solid's real OCCT mass properties (volume/area/bbox/
 * topology). Reuses the design primitives + readout formatters; it renders
 * the numbers the geometry service computed, never its own.
 */
export function BodyInspector({
  properties,
  status,
  partId,
}: BodyInspectorProps) {
  const props = properties;
  const em = "—";
  // Readouts honor the document unit (FINDINGS #17) — stored mm converts at the
  // display boundary through the SAME units seam the input cells use.
  const unit = useDocumentLengthUnit();
  const lenLabel = lengthUnitLabel(unit);
  return (
    <aside
      className="flex w-full flex-col gap-3"
      aria-label="Body inspector"
      data-testid="body-inspector"
    >
      <Panel>
        <PanelSection eyebrow="Mass properties">
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
          <PanelRow label="Min" unit={lenLabel} data-testid="prop-bbox-min">
            {props ? formatVec3(props.bounding_box.min, unit) : em}
          </PanelRow>
          <PanelRow label="Max" unit={lenLabel} data-testid="prop-bbox-max">
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

        {/* Title-block footer: the one cell that MOVES — the solid's render
            status. UNITS (no unit system exists yet) and KERNEL (a hard-coded
            brand string, not telemetry) were decorative and are gone
            (UI-REVIEW 2026-07-16, Track B). */}
        <div
          className="border-t border-hairline px-3 py-2"
          data-testid="body-titleblock-footer"
        >
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

        {/* Issue the modeled body as a file — the export strip of the title
            block, always actionable here because the inspector only shows once
            a body exists. */}
        <PartExportControls partId={partId} hasBody={props !== null} />
      </Panel>
    </aside>
  );
}
