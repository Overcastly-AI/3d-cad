/**
 * The CLASH inspector view — a machinist's interference-fit report. The check
 * runs the SAME solve as the evaluate, then lists every unordered instance pair
 * whose solved-world bodies overlap, each with the exact intersection volume.
 * A quiet precision instrument: the alarm hue (flag red) is spent only on each
 * row's balloons, matching the tree badge and the viewport edge (one clash
 * language, three surfaces); the eyebrow count stays quiet gauge-gray so the
 * panel reads as calm until a row draws the eye. A clash-free assembly gets an
 * explicit "No interferences found"; before the first run, an invitation to run it.
 *
 * Volume is read in mm³ with the same formatter as the inspector's mass block
 * (the assembly's number language) — a clash volume is a volume, not a length,
 * so it does not convert through the document length unit. A genuine but tiny
 * overlap (< 0.01 mm³) falls back to scientific notation so a FLAGGED pair can
 * never read a misleading "0".
 */
import { Panel, PanelSection } from "@loft/design";

import type { InstanceResponse, InterferenceResult } from "../api/assemblies";
import { formatQuantity } from "../lib/format";

/** A clash overlap in mm³. A real overlap is always positive, but a sub-0.01 mm³
 * one rounds to "0" at the shared 2-fraction-digit precision — misleading on a
 * pair the panel flags red — so tiny positive volumes read in scientific
 * notation instead (e.g. "3.2e-4"); everything ≥ 0.01 uses the shared formatter. */
function formatOverlapVolume(mm3: number): string {
  if (mm3 > 0 && mm3 < 0.01) return mm3.toExponential(1);
  return formatQuantity(mm3);
}

export interface AssemblyClashPanelProps {
  /** The graph's instances (for balloon numbers + names). */
  instances: readonly InstanceResponse[];
  /** The last check's result, or null before the first run. */
  result: InterferenceResult | null;
  /** A check is in flight. */
  busy: boolean;
  /** A non-recoverable failure of the check call itself, or null. */
  error: string | null;
}

export function AssemblyClashPanel({
  instances,
  result,
  busy,
  error,
}: AssemblyClashPanelProps) {
  const balloonById = new Map(instances.map((i, index) => [i.id, index + 1]));
  const nameById = new Map(instances.map((i) => [i.id, i.name]));
  const clashes = result?.clashes ?? [];

  const label = (id: string) => ({
    balloon: balloonById.get(id) ?? "?",
    name: nameById.get(id) ?? "Unknown part",
  });

  return (
    <aside
      className="flex w-full flex-col gap-3"
      aria-label="Interference check"
      data-testid="assembly-clash"
    >
      <Panel>
        <PanelSection
          eyebrow={
            clashes.length > 0
              ? `Interference · ${clashes.length}`
              : "Interference"
          }
        >
          {busy ? (
            <p
              data-testid="clash-status"
              className="px-3 py-3 font-body text-xs text-gauge"
              aria-live="polite"
            >
              Scanning for overlaps…
            </p>
          ) : error ? (
            <p
              role="alert"
              data-testid="clash-error"
              className="px-3 py-3 font-body text-xs text-flag"
            >
              {error}
            </p>
          ) : result === null ? (
            <p
              data-testid="clash-idle"
              className="px-3 py-3 font-body text-xs text-gauge"
            >
              Run Check interference to scan the assembly for parts that overlap
              in their solved positions.
            </p>
          ) : clashes.length === 0 ? (
            <p
              data-testid="clash-empty"
              className="px-3 py-3 font-body text-xs text-mist"
              aria-live="polite"
            >
              No interferences found. No two parts overlap in their solved
              positions.
            </p>
          ) : (
            <ul className="py-1" data-testid="clash-list">
              {clashes.map((clash) => {
                const a = label(clash.instance_a);
                const b = label(clash.instance_b);
                return (
                  <li
                    key={`${clash.instance_a}-${clash.instance_b}`}
                    data-testid="clash-row"
                    data-instance-a={clash.instance_a}
                    data-instance-b={clash.instance_b}
                    className="flex items-baseline gap-2 px-3 py-1.5"
                  >
                    <span className="min-w-0 grow">
                      <span className="block font-data text-2xs tabular-nums text-flag">
                        ①{a.balloon} ✕ ②{b.balloon}
                      </span>
                      <span className="block truncate font-body text-xs text-gauge">
                        {a.name} · {b.name}
                      </span>
                    </span>
                    <span className="shrink-0 text-right">
                      <span
                        className="block font-data text-sm tabular-nums text-mist"
                        data-testid="clash-volume"
                      >
                        {formatOverlapVolume(clash.overlap_volume_mm3)}
                      </span>
                      <span className="block font-body text-2xs text-gauge">
                        mm³ overlap
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </PanelSection>
      </Panel>
    </aside>
  );
}
