/**
 * The CLASH inspector view — a machinist's interference-fit report. The check
 * runs the SAME solve as the evaluate, then lists every unordered instance pair
 * whose solved-world bodies overlap, each with its intersection volume.
 * A quiet precision instrument: the alarm hue (flag red) is spent only on a
 * MEASURED row's balloons + its solid left rule, matching the tree badge and
 * the viewport edge (one clash language, three surfaces); the eyebrow counts
 * stay quiet gauge-gray so the panel reads as calm until a row draws the eye. A
 * clash-free assembly gets an explicit "No interferences found"; before the
 * first run, an invitation to run it.
 *
 * Two states, not one (interference hardening follow-up 2026-07-23). When the
 * exact boolean fails on a pair whose solved bounding boxes overlap, the kernel
 * reports `unresolved: true` rather than calling it clear — and the panel must
 * not quietly turn that known-unknown into a clean bill of health either. An
 * unverified pair is drawn as the drafting vernacular for "not established":
 * a DASHED left rule and a dashed-outline UNVERIFIED stamp (a shape difference,
 * not merely a hue), its balloons and figure receding to gauge, and the figure
 * itself in parentheses — a REFERENCE dimension, because it is an upper bound
 * from the bounding boxes, not a reading. A plain-language footnote states what
 * happened and what to do. Indeterminate, deliberately: not an error, not a
 * warning banner, and never "clear".
 *
 * Volume reads in the DOCUMENT unit through the shared units core, exactly like
 * the assembly + body inspectors (FINDINGS burn-down 2026-07-25) — this panel
 * was the last mm-only readout on an inch page. A genuine but tiny overlap
 * falls back to scientific notation so a flagged pair can never read "0"
 * (`formatOverlapVolume`).
 */
import { Panel, PanelSection } from "@loft/design";

import type { InstanceResponse, InterferenceResult } from "../api/assemblies";
import { clashEyebrow, clashRows } from "../assembly/clash";
import { useDocumentLengthUnit } from "../units/documentUnit";

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
  const unit = useDocumentLengthUnit();
  const rows = clashRows(clashes, unit);
  const hasUnresolved = rows.some((row) => row.unresolved);

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
        <PanelSection eyebrow={clashEyebrow(clashes)}>
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
          ) : rows.length === 0 ? (
            <p
              data-testid="clash-empty"
              className="px-3 py-3 font-body text-xs text-mist"
              aria-live="polite"
            >
              No interferences found. No two parts overlap in their solved
              positions.
            </p>
          ) : (
            <>
              <ul className="py-1" data-testid="clash-list">
                {rows.map((row) => {
                  const a = label(row.instanceA);
                  const b = label(row.instanceB);
                  return (
                    <li
                      key={row.key}
                      data-testid="clash-row"
                      data-instance-a={row.instanceA}
                      data-instance-b={row.instanceB}
                      data-unresolved={row.unresolved ? "true" : "false"}
                      className={`flex items-baseline gap-2 border-l-2 px-3 py-1.5 ${
                        row.unresolved
                          ? "border-dashed border-etch"
                          : "border-flag"
                      }`}
                    >
                      <span className="min-w-0 grow">
                        <span className="flex items-center gap-1.5">
                          <span
                            className={`font-data text-2xs tabular-nums ${
                              row.unresolved ? "text-gauge" : "text-flag"
                            }`}
                          >
                            ①{a.balloon} ✕ ②{b.balloon}
                          </span>
                          {row.unresolved ? (
                            <span
                              data-testid="clash-unverified-badge"
                              title="The exact overlap could not be measured — inspect this pair"
                              className="shrink-0 rounded-sm border border-dashed border-etch px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge"
                            >
                              Unverified
                            </span>
                          ) : null}
                        </span>
                        <span className="block truncate font-body text-xs text-gauge">
                          {a.name} · {b.name}
                        </span>
                      </span>
                      <span className="shrink-0 text-right">
                        <span
                          className={`block font-data text-sm tabular-nums ${
                            row.unresolved ? "text-gauge" : "text-mist"
                          }`}
                          data-testid="clash-volume"
                        >
                          {row.magnitude}
                        </span>
                        <span className="block font-body text-2xs text-gauge">
                          {row.magnitudeCaption}
                        </span>
                      </span>
                    </li>
                  );
                })}
              </ul>
              {hasUnresolved ? (
                <p
                  data-testid="clash-unverified-note"
                  className="mx-3 mt-1 border-t border-hairline pt-2 font-body text-xs text-gauge"
                >
                  Unverified means these parts&rsquo; volumes do overlap, but
                  the exact overlap could not be computed — so the check lists
                  the pair instead of calling it clear. The figure in
                  parentheses is an upper bound, not a measurement. Inspect the
                  pair in the viewport, or move one part clear and run the check
                  again.
                </p>
              ) : null}
            </>
          )}
        </PanelSection>
      </Panel>
    </aside>
  );
}
