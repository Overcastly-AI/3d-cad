import {
  areaUnitLabel,
  lengthUnitLabel,
  Panel,
  PanelRow,
  PanelSection,
  volumeUnitLabel,
} from "@loft/design";

import type { ShapeProperties } from "../api/tessellate";
import { bodyStatusReadout, type PartBuild } from "../features/partBuild";
import {
  formatArea,
  formatCount,
  formatExtents,
  formatVec3,
  formatVolume,
} from "../lib/format";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { PartExportControls } from "./PartExportControls";

export interface BodyInspectorProps {
  /** Mass properties of the last-good body, or null when there is none. */
  properties: ShapeProperties | null;
  /**
   * What the workspace knows about the body on screen. The STATUS cell and the
   * EXPORT strip below it are DERIVED from this one object — the same object the
   * feature tree's SOLVE cell reads — so the three cannot disagree the way they
   * did when each computed its own answer (AUDIT-ENGINEERING J2).
   */
  build: PartBuild;
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
  build,
  partId,
}: BodyInspectorProps) {
  const props = properties;
  const em = "—";
  const readout = bodyStatusReadout(build);
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

        {/* Title-block footer: the one cell that MOVES — what this solid IS.
            UNITS (no unit system exists yet) and KERNEL (a hard-coded brand
            string, not telemetry) were decorative and are gone (UI-REVIEW
            2026-07-16, Track B).

            The cell used to fall through to "Up to date" whenever no request was
            in flight, which is a claim about HTTP wearing the words of a claim
            about the model. It now reports PROVENANCE — which state this body was
            built to, and whether the tree has moved since.

            The qualifier shares the value's LINE (a title block's `Ø10.000
            ±0.05`, not a paragraph): the panel is already at its height clamp on
            a 768px-tall screen, and a second line pushes the EXPORT strip — the
            control that matters most on a broken part — under the fold. */}
        <div
          className="border-t border-hairline px-3 py-2"
          data-testid="body-titleblock-footer"
        >
          <span className="block font-display text-2xs uppercase tracking-[0.14em] text-gauge">
            Status
          </span>
          <span className="block">
            <span
              className={`font-data text-xs ${
                readout.tone === "flag" ? "text-flag" : "text-mist"
              }`}
              data-testid="body-status"
              data-body-status={readout.status}
              aria-live="polite"
            >
              {readout.label}
            </span>
            {readout.detail !== null ? (
              <span
                className="ml-2 font-body text-xs text-gauge"
                data-testid="body-status-detail"
              >
                {readout.detail}
              </span>
            ) : null}
          </span>
        </div>

        {/* Issue the modeled body as a file — the export strip of the title
            block, gated on the SAME facts the Status cell reports. */}
        <PartExportControls partId={partId} build={build} />
      </Panel>
    </aside>
  );
}
