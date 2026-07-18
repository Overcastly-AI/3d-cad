/**
 * The bill of materials — the assembly's parts-list schedule, drawn as the
 * drafting artifact it is: a ruled table with an ITEM number column (the same
 * numbering device the tree/viewport use as balloons), the referenced
 * document's name, a kind badge (PART / SUB-ASSEMBLY), and a right-aligned QTY
 * column set in the data face; a ruled TOTAL foot sums the direct instances.
 * Order is exactly as the service returns it (resolved name, then id) — stable
 * across reads. A referenced document deleted while still instanced surfaces
 * honestly as a flagged "(deleted)" line, its quantity preserved, never
 * silently dropped. Composes the design-system `Panel`; no restyled raw chrome.
 */
import { Panel, PanelSection } from "@loft/design";

import type { AssemblyBomResponse, RefDocumentKind } from "../api/bom";
import { formatCount } from "../lib/format";

export interface AssemblyBomPanelProps {
  bom: AssemblyBomResponse | undefined;
  loading: boolean;
  error: Error | null;
}

const KIND_LABEL: Record<RefDocumentKind, string> = {
  part: "Part",
  assembly: "Sub-assembly",
};

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

export function AssemblyBomPanel({
  bom,
  loading,
  error,
}: AssemblyBomPanelProps) {
  const lines = bom?.lines ?? [];
  const eyebrow =
    lines.length > 0 ? `Parts list · ${lines.length}` : "Parts list";

  return (
    <aside
      className="flex w-full flex-col gap-3"
      aria-label="Bill of materials"
      data-testid="bom-panel"
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
          ) : lines.length === 0 ? (
            <p
              data-testid="bom-empty"
              className="px-3 py-3 font-body text-xs text-gauge"
            >
              No components yet. Add a part to build the bill of materials.
            </p>
          ) : (
            <table
              data-testid="bom-table"
              className="w-full border-collapse font-body text-sm"
            >
              <thead>
                <tr className="border-b border-hairline text-gauge">
                  <th
                    scope="col"
                    className="w-8 px-2 py-1 text-right font-display text-2xs font-normal uppercase tracking-[0.14em]"
                  >
                    #
                  </th>
                  <th
                    scope="col"
                    className="px-1 py-1 text-left font-display text-2xs font-normal uppercase tracking-[0.14em]"
                  >
                    Part
                  </th>
                  <th
                    scope="col"
                    className="px-2 py-1 text-right font-display text-2xs font-normal uppercase tracking-[0.14em]"
                  >
                    Qty
                  </th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line, index) => (
                  <tr
                    key={line.ref_document_id}
                    data-testid="bom-row"
                    data-ref-document-id={line.ref_document_id}
                    data-missing={line.missing ? "true" : undefined}
                    className="border-b border-hairline/60 last:border-b-0"
                  >
                    <td className="px-2 py-1.5 text-right align-baseline font-data text-2xs tabular-nums text-gauge">
                      {index + 1}
                    </td>
                    <td className="min-w-0 px-1 py-1.5 align-baseline">
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
                      </span>
                    </td>
                    <td
                      data-testid="bom-quantity"
                      className="px-2 py-1.5 text-right align-baseline font-data text-base tabular-nums text-mist"
                    >
                      {formatCount(line.quantity)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-hairline">
                  <td />
                  <td className="px-1 py-1.5 font-display text-2xs uppercase tracking-[0.16em] text-gauge">
                    Total
                  </td>
                  <td
                    data-testid="bom-total"
                    className="px-2 py-1.5 text-right font-data text-base tabular-nums text-brass"
                  >
                    {formatCount(bom?.total_instances ?? 0)}
                  </td>
                </tr>
              </tfoot>
            </table>
          )}
        </PanelSection>
      </Panel>
    </aside>
  );
}
