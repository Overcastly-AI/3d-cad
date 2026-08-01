import {
  areaUnitLabel,
  formatMass,
  lengthUnitLabel,
  massUnitFor,
  Panel,
  PanelRow,
  PanelSection,
  volumeUnitLabel,
} from "@loft/design";

import type { ShapeProperties } from "../api/tessellate";
import { massState, propertiesEyebrow } from "../features/materials";
import { bodyStatusReadout, type PartBuild } from "../features/partBuild";
import {
  formatArea,
  formatCount,
  formatExtents,
  formatVec3,
  formatVolume,
} from "../lib/format";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { MaterialSection, type MaterialControls } from "./MaterialSection";

export interface BodyInspectorProps {
  /** Geometric properties of the last-good body, or null when there is none. */
  properties: ShapeProperties | null;
  /**
   * What the workspace knows about the body on screen. The STATUS cell here and
   * the EXPORT strip pinned under this panel are DERIVED from this one object —
   * the same object the feature tree's SOLVE cell reads — so the three cannot
   * disagree the way they did when each computed its own answer
   * (AUDIT-ENGINEERING J2). The strip is a sibling rather than a child so the
   * panel can pin it: see `FloatingPanel.footer`.
   */
  build: PartBuild;
  /** The material library + assignment writes (docs/design/materials.md §6). */
  material: MaterialControls;
}

/**
 * The body's title block — the same ruled inspection panel as first light,
 * carrying the evaluated solid's real OCCT properties (mass/volume/area/bbox/
 * topology). Reuses the design primitives + readout formatters; it renders
 * the numbers the geometry service computed, never its own.
 *
 * THE TITLE IS A CLAIM (materials.md §6.1). This panel was titled MASS
 * PROPERTIES for months while reporting no mass, because nothing in the product
 * had a density — the same overstated-surface class as the false CLASH badge
 * and "Up to date" derived from `isFetching`. It now earns the word: while
 * `properties.mass_g` is null the section is PROPERTIES, there is no mass row
 * at all (never `0 g`, which would be a claim about a real massless body), and
 * the MATERIAL cell offers the way to fix that.
 */
export function BodyInspector({
  properties,
  build,
  material,
}: BodyInspectorProps) {
  const props = properties;
  const em = "—";
  const readout = bodyStatusReadout(build);
  // Readouts honor the document unit (FINDINGS #17) — stored mm converts at the
  // display boundary through the SAME units seam the input cells use.
  const unit = useDocumentLengthUnit();
  const lenLabel = lengthUnitLabel(unit);
  // Mass rides that same seam: the wire is canonical grams and the mass unit
  // DERIVES from the document length unit (materials.md §5) — no second setting.
  const mass = massState(props?.mass_g, material.rows);
  const centreOfMass = props?.center_of_mass ?? null;
  return (
    <aside
      className="flex w-full flex-col gap-3"
      aria-label="Body inspector"
      data-testid="body-inspector"
    >
      <Panel>
        {/* MATERIAL sits where a drawing's title block puts it: above the
            numbers it explains. It is the first cell because on a part with no
            material it is the only actionable thing on the panel. */}
        <PanelSection eyebrow="Material">
          <MaterialSection
            {...material}
            state={mass}
            formatBodyMass={(grams) => formatMass(grams, unit)}
          />
        </PanelSection>

        <PanelSection eyebrow={propertiesEyebrow(mass)}>
          {mass.kind === "known" ? (
            <PanelRow
              label="Mass"
              unit={massUnitFor(unit, mass.massG)}
              data-testid="prop-mass"
            >
              {formatMass(mass.massG, unit, { unitSuffix: false })}
            </PanelRow>
          ) : null}
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
          {/* Two DIFFERENT points, named apart because they differ: the centre
              of MASS is mass-weighted (null until every body has a material),
              the centroid is the volume centre and needs no material. They
              coincide only for a single-material shape — the mixed-material
              golden measures 32.3368 mm against the centroid's 25 mm, and the
              assembly roll-up used to CALL its volume weighting mass-weighted
              (materials.md §3). */}
          {centreOfMass !== null ? (
            <PanelRow
              label="Centre of mass"
              unit={lenLabel}
              data-testid="prop-center-of-mass"
            >
              {formatVec3(centreOfMass, unit)}
            </PanelRow>
          ) : null}
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
            ±0.05`, not a paragraph) because that is how a title block reads —
            NOT, any more, to buy vertical space: the export strip is now pinned
            by the panel (`FloatingPanel.footer`) instead of trailing this
            column, so nothing here can push it under the fold. Trimming copy to
            protect the strip failed twice; the layout protects it now. */}
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
      </Panel>
    </aside>
  );
}
