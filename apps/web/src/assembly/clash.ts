/**
 * Clash-schedule projection — the pure half of the {@link AssemblyClashPanel}
 * (the same split `assembly/readout.ts` uses), so the two things that were
 * wrong in the panel are testable without a DOM: the document-unit conversion
 * and the honest handling of a pair the kernel could NOT measure.
 *
 * `ClashPair.unresolved` is set when the exact B-rep boolean fails but the two
 * solved-world bounding boxes overlap. The kernel deliberately never reports
 * such a pair as clear (a false negative is the dangerous direction for a
 * collision check), so the schedule must not let it read as a measurement
 * either. Two consequences, both encoded here:
 *
 *   · a measured clash outranks an unverified one — measured rows sort first,
 *     each group keeping the kernel's deterministic request order;
 *   · an unverified magnitude is a REFERENCE figure, not a reading: it is an
 *     upper bound (the AABB overlap bounds the true overlap from above), so it
 *     is stamped in parentheses — the drafting convention for a reference
 *     dimension — and captioned "at most" instead of "overlap".
 */
import { type LengthUnit, volumeUnitLabel } from "@loft/design";

import type { ClashPair } from "../api/assemblies";
import { formatOverlapVolume } from "../lib/format";

/** One row of the schedule, ready to render. */
export interface ClashRow {
  /** Stable React key (the unordered pair is reported exactly once). */
  key: string;
  instanceA: string;
  instanceB: string;
  /** The exact boolean failed; this pair could not be measured. */
  unresolved: boolean;
  /** Overlap magnitude in the document unit³ — parenthesised when unresolved. */
  magnitude: string;
  /** Quiet caption under the magnitude, e.g. "in³ overlap" / "in³ at most". */
  magnitudeCaption: string;
}

/** Project the kernel's clash list into schedule rows in `unit`. */
export function clashRows(
  clashes: readonly ClashPair[],
  unit: LengthUnit,
): ClashRow[] {
  const measuredFirst = [
    ...clashes.filter((clash) => !clash.unresolved),
    ...clashes.filter((clash) => clash.unresolved),
  ];
  return measuredFirst.map((clash) => {
    const value = formatOverlapVolume(clash.overlap_volume_mm3, unit);
    return {
      key: `${clash.instance_a}-${clash.instance_b}`,
      instanceA: clash.instance_a,
      instanceB: clash.instance_b,
      unresolved: clash.unresolved,
      magnitude: clash.unresolved ? `(${value})` : value,
      magnitudeCaption: `${volumeUnitLabel(unit)} ${
        clash.unresolved ? "at most" : "overlap"
      }`,
    };
  });
}

/**
 * The section eyebrow. The two states are counted SEPARATELY so the header can
 * never imply the check measured more than it did: two measured overlaps plus
 * one unverified pair reads `Interference · 2 · 1 unverified`, and a report with
 * nothing but unverified pairs never shows a bare clash count.
 */
export function clashEyebrow(clashes: readonly ClashPair[]): string {
  const measured = clashes.filter((clash) => !clash.unresolved).length;
  const unresolved = clashes.length - measured;
  if (measured === 0 && unresolved === 0) return "Interference";
  const parts = ["Interference"];
  if (measured > 0) parts.push(String(measured));
  if (unresolved > 0) parts.push(`${unresolved} unverified`);
  return parts.join(" · ");
}

/** The instance-id sets the tree + viewport highlight from one clash report. */
export interface ClashInstanceIds {
  /** Instances in at least one MEASURED clash — the red "Clash" badge. */
  measured: ReadonlySet<string>;
  /** Instances that appear ONLY in unverified pairs — the "Unverified" badge. */
  unverifiedOnly: ReadonlySet<string>;
}

/**
 * Split the report's instances by how much the kernel actually knows. An
 * instance that is in both a measured and an unverified pair IS interfering, so
 * measured wins; `unverifiedOnly` is the honest "we could not tell" set.
 *
 * Both sets go to ALL THREE surfaces (schedule, tree, viewport) — there is no
 * union set on purpose. A union existed until 2026-07-30 and the viewport used
 * it, which painted an unmeasured pair in the alarm colour and announced it as
 * "interfering" (UI-REVIEW P1). "Look here" is said with the unverified
 * language, not by collapsing two states into one.
 */
export function clashInstanceIds(
  clashes: readonly ClashPair[],
): ClashInstanceIds {
  const measured = new Set<string>();
  const unresolved = new Set<string>();
  for (const clash of clashes) {
    const target = clash.unresolved ? unresolved : measured;
    target.add(clash.instance_a);
    target.add(clash.instance_b);
  }
  const unverifiedOnly = new Set(
    [...unresolved].filter((id) => !measured.has(id)),
  );
  return { measured, unverifiedOnly };
}
