/**
 * The section-view author — the inline panel that sets a section view's cutting
 * plane + which half is removed (drawings-section.md §1/§4), hung from the
 * drawing command band into the viewport the way the sketch strip hangs its
 * offset-plane panel. A section slices the referenced part on a DATUM plane and
 * hatches the solid it cuts through; the compose wire (E1a) resolves + cuts +
 * hatches automatically once the view is persisted, so this surface's one job is
 * to pick that plane and the flip.
 *
 * The plane is the EXACT `GeomRef` union a sketch's plane reference uses — a
 * `DatumPlaneRef` (an XY / XZ / YZ origin plane) or a `FeatureRef` to an axis-
 * aligned datum FEATURE in the part — so it REUSES the sketch plane picker's
 * vocabulary verbatim: the three origin datums, then any reusable in-tree datums
 * resolved by {@link resolveDatumPlaneOptions} (the ONE derivation the sketcher
 * reads too). No parallel plane taxonomy is introduced (CLAUDE.md DRY rule).
 *
 * v1 cuts on an AXIS-ALIGNED plane only (§7). A non-principal datum (e.g. an
 * angular-bisector midplane) is caught here client-side — the plane math is the
 * same the kernel resolves — and the Cut control is disabled with a clear
 * reason, so the precondition surfaces before persisting rather than as a failed
 * view after (the server still guards it, returning `section_plane_not_principal`,
 * which the sheet renders as a readable failure).
 */
import { useMemo, useState } from "react";

import {
  DatumIcon,
  Panel,
  SegmentedControl,
  type SegmentOption,
  ToolButton,
  ToolGroup,
} from "@loft/design";

import type { SectionViewParams } from "../api/drawings";
import {
  DATUM_PLANES,
  type DatumPlaneOption,
  describePlane,
  planeRefFromSpec,
  resolveSpecBasis,
  type SketchPlaneSpec,
  type Vec3Tuple,
} from "../sketch/plane";

/** One selectable cutting plane — an origin datum or a reusable in-tree datum. */
interface PlaneChoice {
  key: string;
  label: string;
  testId: string;
  spec: SketchPlaneSpec;
}

/** Which half a `flip` value removes (§4): false removes the eye-side material
 * (the standard "cut away what is between you and the plane"), true the far side. */
const REMOVED_SIDE_OPTIONS: ReadonlyArray<SegmentOption<"near" | "far">> = [
  {
    value: "near",
    label: "Near",
    "data-testid": "section-flip-near",
    "aria-label": "Remove the near (eye-side) half — the standard section",
  },
  {
    value: "far",
    label: "Far",
    "data-testid": "section-flip-far",
    "aria-label": "Remove the far half",
  },
];

/** Axis-alignment tolerance — MIRRORS the kernel's `_AXIS_PARALLEL_TOL`
 * (`services/geometry/src/geometry/drawings/section.py`), so this client
 * pre-check can't drift from the server guard it stands in for. */
const AXIS_PARALLEL_TOL = 1e-7;

/** True when a plane normal is axis-aligned (the v1 section precondition, §7).
 * The EXACT test the kernel's `resolve_section_frame` runs: normalize, then the
 * largest-magnitude component must be within tol of 1 (a principal axis) — so a
 * near-axis normal in the 1e-7 window resolves the SAME way here and server-side. */
function isPrincipalNormal(n: Vec3Tuple): boolean {
  const len = Math.hypot(n[0], n[1], n[2]);
  if (len === 0) return false;
  const maxComp = Math.max(
    Math.abs(n[0] / len),
    Math.abs(n[1] / len),
    Math.abs(n[2] / len),
  );
  return maxComp >= 1 - AXIS_PARALLEL_TOL;
}

export interface SectionAuthorPanelProps {
  /** Reusable datum planes already in the referenced part's tree (FeatureRefs). */
  datumPlanes: readonly DatumPlaneOption[];
  /** True while the referenced part's datum list is still loading. */
  loadingDatums?: boolean;
  /** Persist a section view with this cutting plane (GeomRef) + flip. */
  onCut: (plane: SectionViewParams["plane"], flip: boolean) => void;
  /** Collapse the panel without authoring. */
  onClose: () => void;
  /** True while the section-view write is in flight. */
  busy?: boolean;
  /** A create-time failure (e.g. a stale version), or null. */
  error?: string | null;
}

export function SectionAuthorPanel({
  datumPlanes,
  loadingDatums = false,
  onCut,
  onClose,
  busy = false,
  error = null,
}: SectionAuthorPanelProps) {
  const choices = useMemo<PlaneChoice[]>(() => {
    const origins: PlaneChoice[] = DATUM_PLANES.map((name) => ({
      key: `origin:${name}`,
      label: `${name} plane`,
      testId: `section-plane-${name}`,
      spec: { kind: "origin", base: name },
    }));
    const datums: PlaneChoice[] = datumPlanes.map((datum) => ({
      key: `datum:${datum.id}`,
      label: datum.name,
      testId: `section-plane-datum-${datum.id}`,
      spec: datum.spec,
    }));
    return [...origins, ...datums];
  }, [datumPlanes]);

  // Default to the first origin datum (XY) — always principal, the common cut.
  const [selectedKey, setSelectedKey] = useState<string>(
    () => choices[0]?.key ?? "origin:XY",
  );
  const [flip, setFlip] = useState(false);

  const selected =
    choices.find((c) => c.key === selectedKey) ?? choices[0] ?? null;
  const principal = selected
    ? isPrincipalNormal(resolveSpecBasis(selected.spec).normal)
    : false;
  const canCut = selected !== null && principal && !busy;

  const cut = () => {
    if (!selected || !canCut) return;
    onCut(planeRefFromSpec(selected.spec), flip);
  };

  return (
    <div
      className="w-editor max-w-full"
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          cut();
        } else if (event.key === "Escape") {
          event.preventDefault();
          onClose();
        }
      }}
    >
      <Panel aria-label="Section view" data-testid="section-author-panel">
        <div className="flex flex-col gap-2.5 px-3 py-3">
          <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            Section view
          </h2>

          {/* Cutting plane — the sketch plane picker's vocabulary: the three
              origin datums, then any reusable in-tree datums (FeatureRefs). */}
          <div className="flex flex-col gap-1.5">
            <span className="font-display text-2xs uppercase tracking-[0.16em] text-gauge">
              Cutting plane
            </span>
            <div className="flex flex-wrap items-stretch gap-1">
              {DATUM_PLANES.map((name) => {
                const choice = choices.find((c) => c.key === `origin:${name}`)!;
                return (
                  <ToolButton
                    key={name}
                    icon={
                      <span className="font-display text-2xs tracking-[0.08em]">
                        {name}
                      </span>
                    }
                    label={`${name} plane`}
                    showLabel={false}
                    active={selectedKey === choice.key}
                    data-testid={choice.testId}
                    aria-label={`Cut on the ${name} plane`}
                    onClick={() => setSelectedKey(choice.key)}
                  />
                );
              })}
            </div>
            {datumPlanes.length > 0 ? (
              <ToolGroup
                eyebrow="In tree"
                aria-label="Datum planes in the part"
              >
                {datumPlanes.map((datum) => (
                  <ToolButton
                    key={datum.id}
                    icon={<DatumIcon />}
                    label={datum.name}
                    showLabel
                    active={selectedKey === `datum:${datum.id}`}
                    data-testid={`section-plane-datum-${datum.id}`}
                    aria-label={`Cut on ${datum.name}`}
                    onClick={() => setSelectedKey(`datum:${datum.id}`)}
                  />
                ))}
              </ToolGroup>
            ) : loadingDatums ? (
              <span className="font-body text-2xs text-gauge">
                Loading datums…
              </span>
            ) : null}
          </div>

          {/* Which half the cut removes (§4). */}
          <SegmentedControl
            label="Removed side"
            value={flip ? "far" : "near"}
            options={REMOVED_SIDE_OPTIONS}
            onChange={(v) => setFlip(v === "far")}
          />

          {/* A live readout of the chosen cut — the plane label + removed side. */}
          <p className="font-body text-2xs text-gauge">
            Cut on{" "}
            <span className="font-data text-mist" data-testid="section-readout">
              {selected ? describePlane(selected.spec) : "—"}
            </span>
            , removing the {flip ? "far" : "near"} half.
          </p>

          {/* The v1 axis-aligned precondition, surfaced BEFORE persisting. */}
          {selected && !principal ? (
            <p
              role="alert"
              data-testid="section-not-principal"
              className="border border-flag bg-anvil px-2 py-1.5 font-body text-2xs text-flag"
            >
              v1 cuts on an axis-aligned plane only. Choose XY, XZ, YZ, or an
              offset datum parallel to one.
            </p>
          ) : null}

          <div className="mt-1 flex items-center justify-between gap-2">
            <button
              type="button"
              className="font-display text-2xs uppercase tracking-[0.14em] text-gauge hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
              data-testid="section-cancel"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="button"
              className="font-display text-2xs uppercase tracking-[0.14em] text-brass hover:text-brass-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-40"
              data-testid="section-confirm"
              aria-busy={busy}
              disabled={!canCut}
              onClick={cut}
            >
              {busy ? "Cutting…" : "Cut section"}
            </button>
          </div>
        </div>
      </Panel>
      {error ? (
        <p
          role="alert"
          data-testid="section-author-error"
          className="mt-2 border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
