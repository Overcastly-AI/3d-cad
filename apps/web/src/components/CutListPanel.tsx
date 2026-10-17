/**
 * The Cut list (CUT-LIST) — SolidWorks' weldment cut list, Chief Architect's
 * materials list: every member of a part (each body) or an assembly (every part
 * at every level, times its quantity), grouped by member, profile, material and
 * MEASURED length, with the quantity, the total length and the shortest stock
 * length it is cut from. One component for the part workspace, the assembly
 * inspector and the drawing sheet's side panel, so the three never disagree.
 *
 * Every number is the gateway's: geometry measured the lengths and the grouping
 * is server-side, so this only formats them in the document's unit. A body that
 * matched no profile is listed as Unclassified with its measured section, never
 * dropped. CSV downloads the same lines.
 */
import { Button, lengthUnitLabel, Panel, PanelSection } from "@loft/design";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  type CutListLine,
  type CutListSource,
  exportCutListCsv,
  fetchCutList,
} from "../api/cutList";
import { downloadBlob } from "../api/exportPart";
import { fetchMaterials } from "../api/materials";
import { formatCount, formatLength } from "../lib/format";

export interface CutListPanelProps {
  kind: CutListSource;
  documentId: string;
  /**
   * The document's edit stamp (a part's tree_version; an assembly's doc_version
   * with its parts' versions): a change refetches, so the list is always the
   * current one. `undefined` while it loads.
   */
  revision: number | string | undefined;
}

const HEAD_BASE =
  "py-1 font-display text-2xs font-normal uppercase tracking-[0.14em]";
const HEAD = `${HEAD_BASE} px-1.5 text-right`;

function describe(line: CutListLine, materialName: (key: string) => string) {
  const parts = [
    line.classification === "unclassified" ? null : line.profile,
    line.material === null ? null : materialName(line.material),
  ].filter((v): v is string => v !== null && v !== undefined);
  return parts.join(" · ");
}

export function CutListPanel({
  kind,
  documentId,
  revision,
}: CutListPanelProps) {
  const cutList = useQuery({
    queryKey: ["cut-list", kind, documentId, revision],
    queryFn: () => fetchCutList(kind, documentId),
    enabled: revision !== undefined,
    // Keep the last list on screen while an edit re-measures (same document).
    placeholderData: (previous, query) =>
      query?.queryKey[2] === documentId ? previous : undefined,
  });
  const materials = useQuery({
    queryKey: ["materials"],
    queryFn: () => fetchMaterials(),
    staleTime: Infinity,
  });
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const data = cutList.data;
  const unit = data?.length_unit ?? "mm";
  const unitLabel = lengthUnitLabel(unit);
  const materialName = (key: string) =>
    materials.data?.find((m) => m.key === key)?.name ?? key;

  async function downloadCsv() {
    setExporting(true);
    setExportError(null);
    try {
      const file = await exportCutListCsv(kind, documentId);
      downloadBlob(file.blob, file.filename);
    } catch (error) {
      setExportError(
        error instanceof Error
          ? error.message
          : "The CSV could not be written.",
      );
    } finally {
      setExporting(false);
    }
  }

  const lines = data?.lines ?? [];
  return (
    <aside
      className="flex w-full flex-col gap-3"
      aria-label="Cut list"
      data-testid="cut-list-panel"
      data-source-kind={kind}
    >
      <Panel>
        <PanelSection
          eyebrow={lines.length > 0 ? `Cut list · ${lines.length}` : "Cut list"}
        >
          {cutList.error ? (
            <p
              role="alert"
              data-testid="cut-list-error"
              className="px-3 py-3 font-body text-xs text-flag"
            >
              {cutList.error.message}
            </p>
          ) : data === undefined ? (
            <p
              data-testid="cut-list-loading"
              aria-live="polite"
              className="px-3 py-3 font-body text-xs text-gauge"
            >
              Measuring the members…
            </p>
          ) : lines.length === 0 ? (
            <p
              data-testid="cut-list-empty"
              className="px-3 py-3 font-body text-xs text-gauge"
            >
              No bodies to cut yet. Each body becomes a line here, measured
              along its length.
            </p>
          ) : (
            <table
              data-testid="cut-list-table"
              aria-label={`Cut list, ${lines.length} lines, ${data.total_quantity} pieces`}
              className="w-full border-collapse font-body text-sm"
            >
              <thead>
                <tr className="border-b border-hairline text-gauge">
                  <th
                    scope="col"
                    className={`${HEAD_BASE} pl-3 pr-1 text-left`}
                  >
                    Member
                  </th>
                  <th scope="col" className={HEAD}>
                    Qty
                  </th>
                  <th
                    scope="col"
                    className={HEAD}
                    title={`Each (${unitLabel})`}
                  >
                    Length
                  </th>
                  <th
                    scope="col"
                    className={HEAD}
                    title={`Qty × length (${unitLabel})`}
                  >
                    Total
                  </th>
                  <th
                    scope="col"
                    className={`${HEAD_BASE} pl-1.5 pr-3 text-right`}
                    title="Shortest standard stock that covers each piece"
                  >
                    Stock
                  </th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line, index) => {
                  const unclassified = line.classification === "unclassified";
                  const caption = unclassified
                    ? `Unclassified · ${line.section_mm
                        .map((v) => formatLength(v, unit))
                        .join(" × ")} ${unitLabel}`
                    : describe(line, materialName);
                  return (
                    <tr
                      key={index}
                      data-testid="cut-list-row"
                      data-member={line.member ?? ""}
                      data-profile={line.profile ?? ""}
                      data-classification={line.classification}
                      className="border-b border-hairline/60 last:border-b-0"
                    >
                      <td className="min-w-0 py-1.5 pl-3 pr-1 align-baseline">
                        <span
                          data-testid="cut-list-member"
                          className={`block truncate ${
                            unclassified ? "italic text-gauge" : "text-mist"
                          }`}
                        >
                          {line.member ?? line.profile ?? "Body"}
                        </span>
                        {caption ? (
                          <span
                            data-testid="cut-list-caption"
                            className="block truncate text-2xs text-gauge"
                            title={caption}
                          >
                            {caption}
                          </span>
                        ) : null}
                      </td>
                      <td
                        data-testid="cut-list-qty"
                        className="px-1.5 py-1.5 text-right align-baseline font-data tabular-nums text-mist"
                      >
                        {formatCount(line.quantity)}
                      </td>
                      <td
                        data-testid="cut-list-length"
                        className="px-1.5 py-1.5 text-right align-baseline font-data tabular-nums text-mist"
                      >
                        {formatLength(line.length_mm, unit)}
                      </td>
                      <td
                        data-testid="cut-list-total-length"
                        className="px-1.5 py-1.5 text-right align-baseline font-data tabular-nums text-gauge"
                      >
                        {formatLength(line.total_length_mm, unit)}
                      </td>
                      <td
                        data-testid="cut-list-stock"
                        className="py-1.5 pl-1.5 pr-3 text-right align-baseline font-data tabular-nums text-mist"
                        title={
                          line.waste_mm === null
                            ? undefined
                            : `${formatLength(line.waste_mm, unit)} ${unitLabel} offcut each`
                        }
                      >
                        {line.stock_length_ft === null
                          ? "—"
                          : `${line.stock_length_ft} ft`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="border-t border-hairline">
                  <td className="py-1.5 pl-3 font-display text-2xs uppercase tracking-[0.16em] text-gauge">
                    Pieces
                  </td>
                  <td
                    data-testid="cut-list-total"
                    className="px-1.5 py-1.5 text-right font-data tabular-nums text-brass"
                  >
                    {formatCount(data.total_quantity)}
                  </td>
                  <td
                    colSpan={3}
                    className="py-1.5 pr-3 text-right font-body text-2xs text-gauge"
                  >
                    Lengths in {unitLabel}
                  </td>
                </tr>
              </tfoot>
            </table>
          )}
        </PanelSection>
        <div className="flex items-center gap-2 border-t border-hairline px-3 py-2">
          {data !== undefined && data.unclassified > 0 ? (
            <span
              data-testid="cut-list-unclassified"
              className="font-body text-2xs text-gauge"
            >
              {data.unclassified} unclassified
            </span>
          ) : null}
          <span className="grow" />
          <Button
            data-testid="cut-list-csv"
            disabled={lines.length === 0 || exporting}
            onClick={() => void downloadCsv()}
            aria-label="Download the cut list as CSV"
          >
            {exporting ? "Writing…" : "CSV"}
          </Button>
        </div>
        {exportError !== null ? (
          <p
            role="alert"
            data-testid="cut-list-csv-error"
            className="px-3 pb-2 font-body text-2xs text-flag"
          >
            {exportError}
          </p>
        ) : null}
      </Panel>
    </aside>
  );
}
