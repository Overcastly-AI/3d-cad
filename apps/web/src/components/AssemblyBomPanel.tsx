/**
 * The bill of materials — the assembly's parts-list schedule, drawn as the
 * drafting artifact it is: a ruled table with an ITEM number column (the same
 * numbering device the tree/viewport use as balloons), the referenced
 * document's name, a kind badge (PART / SUB-ASSEMBLY), and a right-aligned QTY
 * column set in the data face; a ruled TOTAL foot sums the quantities.
 *
 * Three views, SolidWorks' three BOM types (ASM-A3):
 * - TOP LEVEL (default): one line per document instanced directly; a
 *   sub-assembly is one line. The drawing's parts list is this view.
 * - INDENTED: each sub-assembly opened beneath its line, items numbered 2.1,
 *   2.2…; QTY is per parent, ALL is the count across the whole assembly.
 * - PARTS ONLY: every part at every level, counted once per placed part —
 *   what a shop builds.
 *
 * Order is exactly as the service returns it (resolved name, then id) — stable
 * across reads. A referenced document deleted while still instanced surfaces
 * honestly as a flagged "(deleted)" line, its quantity preserved, never
 * silently dropped. Composes the design-system `Panel`; no restyled raw chrome.
 */
import { Panel, PanelSection, SegmentedControl } from "@loft/design";
import { useState } from "react";

import type { AssemblyBomResponse, BomLine, RefDocumentKind } from "../api/bom";
import { formatCount } from "../lib/format";

export interface AssemblyBomPanelProps {
  bom: AssemblyBomResponse | undefined;
  loading: boolean;
  error: Error | null;
  /**
   * Part documents that failed to build in this assembly's last solve: their
   * lines still count (they are in the assembly) but are flagged, because no
   * body of theirs is drawn or exported (BIKE2-FAILED-PART-KILLS-PICKS).
   */
  failedDocumentIds?: ReadonlySet<string>;
}

type BomView = "top" | "indented" | "parts";

const VIEW_OPTIONS = [
  { value: "top" as const, label: "Top level", "data-testid": "bom-view-top" },
  {
    value: "indented" as const,
    label: "Indented",
    "data-testid": "bom-view-indented",
  },
  {
    value: "parts" as const,
    label: "Parts only",
    "data-testid": "bom-view-parts",
  },
];

const KIND_LABEL: Record<RefDocumentKind, string> = {
  part: "Part",
  assembly: "Sub-assembly",
};

/** One table row, whichever view it comes from. */
interface Row {
  line: BomLine;
  item: string;
  level: number;
  /** The all-levels count, shown in the indented view only. */
  total: number | null;
}

function rowsOf(bom: AssemblyBomResponse | undefined, view: BomView): Row[] {
  if (bom === undefined) return [];
  if (view === "indented") {
    return bom.indented.map((line) => ({
      line,
      item: line.item,
      level: line.level,
      total: line.total_quantity,
    }));
  }
  const lines = view === "parts" ? bom.parts_only : bom.lines;
  return lines.map((line, index) => ({
    line,
    item: String(index + 1),
    level: 0,
    total: null,
  }));
}

/** A quiet, hairline-ruled type chip — brass for a sub-assembly (it nests). */
function KindBadge({ kind }: { kind: RefDocumentKind }) {
  const sub = kind === "assembly";
  return (
    <span
      data-testid="bom-kind"
      data-kind={kind}
      className={`inline-flex shrink-0 items-center rounded-sm border px-1 font-display text-2xs uppercase tracking-[0.12em] ${
        sub ? "border-brass/60 text-brass" : "border-etch text-gauge"
      }`}
    >
      {KIND_LABEL[kind]}
    </span>
  );
}

const HEAD =
  "px-2 py-1 text-right font-display text-2xs font-normal uppercase tracking-[0.14em]";

export function AssemblyBomPanel({
  bom,
  loading,
  error,
  failedDocumentIds,
}: AssemblyBomPanelProps) {
  const [view, setView] = useState<BomView>("top");
  const rows = rowsOf(bom, view);
  const indented = view === "indented";
  const total =
    view === "parts" ? (bom?.total_parts ?? 0) : (bom?.total_instances ?? 0);
  const eyebrow =
    (bom?.lines.length ?? 0) > 0 ? `Parts list · ${rows.length}` : "Parts list";

  return (
    <aside
      className="flex w-full flex-col gap-3"
      aria-label="Bill of materials"
      data-testid="bom-panel"
      data-bom-view={view}
    >
      <Panel>
        <PanelSection eyebrow={eyebrow}>
          {error ? (
            <p
              role="alert"
              data-testid="bom-error"
              className="px-3 py-3 font-body text-xs text-flag"
            >
              {error.message}
            </p>
          ) : loading && bom === undefined ? (
            <p
              data-testid="bom-loading"
              className="px-3 py-3 font-body text-xs text-gauge"
              aria-live="polite"
            >
              Reading the bill of materials…
            </p>
          ) : (bom?.lines.length ?? 0) === 0 ? (
            <p
              data-testid="bom-empty"
              className="px-3 py-3 font-body text-xs text-gauge"
            >
              No components yet. Add a part to build the bill of materials.
            </p>
          ) : (
            <>
              <SegmentedControl
                label="BOM type"
                hideLabel
                size="dense"
                value={view}
                onChange={setView}
                options={VIEW_OPTIONS}
                className="px-2 pb-2 pt-1"
              />
              <table
                data-testid="bom-table"
                className="w-full border-collapse font-body text-sm"
              >
                <thead>
                  <tr className="border-b border-hairline text-gauge">
                    <th scope="col" className={`w-8 ${HEAD}`}>
                      #
                    </th>
                    <th scope="col" className={`${HEAD} px-1 text-left`}>
                      Part
                    </th>
                    <th scope="col" className={HEAD}>
                      Qty
                    </th>
                    {indented ? (
                      <th
                        scope="col"
                        className={HEAD}
                        title="How many the whole assembly holds"
                      >
                        All
                      </th>
                    ) : null}
                  </tr>
                </thead>
                <tbody>
                  {rows.map(({ line, item, level, total: all }) => (
                    <tr
                      key={`${item}-${line.ref_document_id}`}
                      data-testid="bom-row"
                      data-ref-document-id={line.ref_document_id}
                      data-item={item}
                      data-level={level}
                      data-missing={line.missing ? "true" : undefined}
                      data-failed={
                        failedDocumentIds?.has(line.ref_document_id)
                          ? "true"
                          : undefined
                      }
                      className="border-b border-hairline/60 last:border-b-0"
                    >
                      <td className="px-2 py-1.5 text-right align-baseline font-data text-2xs tabular-nums text-gauge">
                        {item}
                      </td>
                      <td
                        className="min-w-0 px-1 py-1.5 align-baseline"
                        style={{ paddingLeft: `${0.25 + level * 0.875}rem` }}
                      >
                        <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
                          {line.missing ? (
                            <span
                              className="flex min-w-0 items-baseline gap-1 italic text-flag"
                              data-testid="bom-name"
                              title="The referenced document was deleted while still instanced."
                            >
                              <span aria-hidden>⚠</span>
                              <span className="truncate">(deleted)</span>
                            </span>
                          ) : (
                            <span
                              data-testid="bom-name"
                              className="truncate text-mist"
                            >
                              {line.name}
                            </span>
                          )}
                          <KindBadge kind={line.ref_document_kind} />
                          {failedDocumentIds?.has(line.ref_document_id) ? (
                            <span
                              data-testid="bom-failed"
                              title="This part failed to build: it is not drawn or exported."
                              className="shrink-0 rounded-sm border border-flag px-1 font-display text-2xs uppercase tracking-[0.14em] text-flag"
                            >
                              Failed
                            </span>
                          ) : null}
                        </span>
                      </td>
                      <td
                        data-testid="bom-quantity"
                        className="px-2 py-1.5 text-right align-baseline font-data text-base tabular-nums text-mist"
                      >
                        {formatCount(line.quantity)}
                      </td>
                      {all !== null ? (
                        <td
                          data-testid="bom-total-quantity"
                          className="px-2 py-1.5 text-right align-baseline font-data text-base tabular-nums text-gauge"
                        >
                          {formatCount(all)}
                        </td>
                      ) : null}
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-hairline">
                    <td />
                    <td className="px-1 py-1.5 font-display text-2xs uppercase tracking-[0.16em] text-gauge">
                      {view === "parts" ? "Total parts" : "Total"}
                    </td>
                    <td
                      data-testid="bom-total"
                      className="px-2 py-1.5 text-right font-data text-base tabular-nums text-brass"
                    >
                      {formatCount(total)}
                    </td>
                    {indented ? <td /> : null}
                  </tr>
                </tfoot>
              </table>
            </>
          )}
        </PanelSection>
      </Panel>
    </aside>
  );
}
