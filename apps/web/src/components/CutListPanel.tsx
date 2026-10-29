/**
 * The Cut list (CUT-LIST) — SolidWorks' weldment cut list, Chief Architect's
 * materials list: every member of a part (each body) or an assembly (every part
 * at every level, times its quantity), grouped by member, profile, material and
 * MEASURED length, with the quantity, the total length and the shortest stock
 * length it is cut from. One component for the part workspace, the assembly
 * inspector and the drawing sheet's side panel, so the three never disagree.
 *
 * Grouped as a takeoff (CUT-LIST-PANEL): the gateway orders the lines by
 * system, Floor, Walls, Roof, Sheathing (Chief Architect's Materials List
 * categories), then by member, profile and length, with one member's pieces
 * from every wall merged; each system is a headed row group here. Member names
 * wrap, never truncate, and every figure stays on one line. In the part
 * workspace the panel is a full-height view whose left edge drags wider.
 * Expand opens the same list full width (`CutListView`), as Fusion opens its
 * BOM in a view of its own; its caption bar sticks while the panel scrolls.
 *
 * Every number is the gateway's: geometry measured the lengths and the grouping
 * is server-side, so this only formats them in the document's unit. A body that
 * matched no profile is listed as Unclassified with its measured section, never
 * dropped. CSV downloads the same lines.
 *
 * Prices (CUT-LIST-PRICES) are the gateway's too, priced from the caller's
 * price book in integer cents: the unit price of one stock piece, the extended
 * price, and a Total row of the priced lines. A line the book does not price is
 * BLANK, never $0, and the Total row counts it; clicking the blank opens the
 * Price book pre-filled with the line's material, profile and stock length.
 *
 * Sheet goods (SHEATHING) are one line per product and sheet: the panels'
 * count, their net AREA in the Length column (openings cut out), and in Stock
 * the sheets the modelled panels are cut from ("12 × 4x9", SHEET-COUNT-PIECES:
 * a yard sells whole sheets), its tooltip naming the offcut area; priced Each
 * per sheet.
 *
 * A member longer than the longest stock (CUT-LIST-LONG-STOCK) is SPLICED from
 * stock pieces, as a framer buys a long plate: Stock reads "2 × 12 ft" or
 * "16 ft + 8 ft" per member (the gateway's choice): its stock quantity counts
 * one splice set per member and its unit price is that set's pieces summed,
 * so stock qty × unit price is the extended price on every row.
 *
 * A window or door unit (OPENING-UNITS) is one line per call size, bought
 * whole: Stock reads its size and kind ("3040 window"), and its blank price
 * opens the book on that unit's key ('window_3040'), priced Each.
 *
 * Foundation lines (SLAB) head the list: a pour reads its net volume in
 * Length ("6.62 yd³") and what is ordered in Stock ("7.00 yd³", its waste
 * allowance added and rounded up to 1/4 yd³), priced per cubic yard ordered;
 * rebar reads its centreline length and the 20 ft sticks it takes ("10 × 20
 * ft"); anchor bolts are Each. Rebar and bolts are listed, never drawn. Each
 * pour is its own line and delivery (FOUNDATION-TAKEOFF), and a crawl
 * space's vents and access door are Each, their size in the member
 * ("Vent 16 x 8").
 */
import {
  Button,
  CloseIcon,
  ExpandIcon,
  type LengthUnit,
  lengthUnitLabel,
  Panel,
  PanelSection,
} from "@loft/design";
import { useQuery } from "@tanstack/react-query";
import {
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";

import {
  type CutListLine,
  type CutListSource,
  exportCutListCsv,
  fetchCutList,
} from "../api/cutList";
import { downloadBlob } from "../api/exportPart";
import { fetchMaterials } from "../api/materials";
import { PRICE_UNIT_LABEL } from "../api/priceBook";
import { formatArea, formatCount, formatLength } from "../lib/format";
import { useModalLayer } from "../lib/modalGate";
import { formatMoney } from "../lib/money";
import { containFocus } from "./dialogKeys";
import { PriceBookDialog, type PriceBookSeed } from "./PriceBookDialog";

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
/** Narrow seats (the drawing's 320 px panel) tighten the column gutters. */
const NARROW_GUTTER = "[@container(max-width:439px)]:px-1";
const HEAD = `${HEAD_BASE} px-1.5 text-right ${NARROW_GUTTER}`;

const CELL = `whitespace-nowrap px-1.5 py-1.5 text-right align-baseline font-data tabular-nums ${NARROW_GUTTER}`;

/** How each system's group is headed (Chief Architect's categories). */
export const SYSTEM_LABEL: Record<CutListLine["system"], string> = {
  foundation: "Foundation",
  floor: "Floor",
  walls: "Walls",
  roof: "Roof",
  sheathing: "Sheathing",
  deck: "Deck",
  frame: "Frame",
  casework: "Casework",
  other: "Other",
};

/** The gateway's lines (already in system order) as runs of one system,
 * each line keeping its index in the list. */
export function groupBySystem(lines: readonly CutListLine[]): {
  system: CutListLine["system"];
  lines: (CutListLine & { index: number })[];
}[] {
  const groups: ReturnType<typeof groupBySystem> = [];
  lines.forEach((line, index) => {
    const last = groups[groups.length - 1];
    if (last !== undefined && last.system === line.system) {
      last.lines.push({ ...line, index });
    } else {
      groups.push({ system: line.system, lines: [{ ...line, index }] });
    }
  });
  return groups;
}
/**
 * The run (qty x length) column gives way in a narrow seat (the drawing's
 * 320 px side panel): with the two price columns the table would otherwise
 * clip its extended price, and the run is the one column a buyer can do
 * without (Qty and Length are both beside it). Wider, it is shown.
 */
const RUN_COLUMN = "[@container(max-width:439px)]:hidden";

/** "1 line unpriced" / "6 lines unpriced". */
export function unpricedLabel(count: number): string {
  return `${count} ${count === 1 ? "line" : "lines"} unpriced`;
}

/** A foundation item counted by the piece (a bolt, a vent, an access door):
 * Each, with no length to list. */
function isEachItem(line: CutListLine): boolean {
  return (
    line.item === "anchor_bolt" ||
    line.item === "foundation_vent" ||
    line.item === "access_door" ||
    line.item === "post_base"
  );
}

/** What a blank price would be priced as, or null when no entry could. */
function seedFor(line: CutListLine): PriceBookSeed | null {
  if (
    line.classification === "unclassified" ||
    line.material === null ||
    line.profile === null
  ) {
    return null;
  }
  if (
    (line.item !== null && line.item !== undefined) ||
    (line.casework !== null && line.casework !== undefined)
  ) {
    // A foundation or casework item: the book resolves its name to its key.
    return {
      material: line.material,
      profile: line.profile,
      stockLengthFt: line.stock_length_ft ?? null,
    };
  }
  if (line.unit !== null && line.unit !== undefined) {
    // A custom-size unit has no key: no catalogue entry prices it.
    const key = line.unit_key ?? null;
    return key === null
      ? null
      : {
          material: line.material,
          profile: line.profile,
          stockLengthFt: null,
          unitKey: key,
        };
  }
  const sheet = line.sheet ?? null;
  if (sheet !== null) {
    return {
      material: line.material,
      profile: line.profile,
      stockLengthFt: null,
      sheet,
    };
  }
  const feet = line.stock_length_ft ?? line.stock_pieces_ft?.[0] ?? null;
  if (feet === null) return null;
  return {
    material: line.material,
    profile: line.profile,
    stockLengthFt: feet,
    // A splice needs every piece priced: the book adds a row for each length
    // it does not price yet (16 + 8 with only 16 priced opens on 8).
    stockLengthsFt: splice(line) ?? undefined,
  };
}

/** Cubic yards as ready-mix is listed: two places ("6.62"). */
export function formatYd3(yd3: number): string {
  return yd3.toFixed(2);
}

/** in³ per yd³, and mm³ per in³: a pour's net volume in cubic yards. */
const MM3_PER_YD3 = 46656 * 25.4 ** 3;

/** A member's stock pieces as a framer writes them: "16 ft", "2 × 12 ft",
 * "16 ft + 8 ft" (longest first, as the gateway sends them). */
export function spliceLabel(pieces: readonly number[]): string {
  const counts = new Map<number, number>();
  for (const feet of pieces) counts.set(feet, (counts.get(feet) ?? 0) + 1);
  return [...counts]
    .map(([feet, n]) => (n === 1 ? `${feet} ft` : `${n} × ${feet} ft`))
    .join(" + ");
}

/** The pieces one member of the line is spliced from, or null for one. */
function splice(line: CutListLine): readonly number[] | null {
  const pieces = line.stock_pieces_ft ?? null;
  return pieces !== null && pieces.length > 1 ? pieces : null;
}

/** What the line buys: "12 ft" of lumber, "9 × 4x9" sheets, a "3040
 * window", or a dash. */
function stockLabel(line: CutListLine): string {
  if (line.casework !== null && line.casework !== undefined) {
    // Banding is bought in whole feet; hardware by the piece.
    return line.casework === "edge_banding"
      ? `${formatCount(line.stock_quantity ?? 0)} ft`
      : "Each";
  }
  if (line.item === "concrete") {
    // A deck's footings buy whole 80 lb bags (DECK-FOOTINGS).
    if (line.bags !== null && line.bags !== undefined) {
      return `${formatCount(line.bags)} bags`;
    }
    return line.order_yd3 === null || line.order_yd3 === undefined
      ? "—"
      : `${formatYd3(line.order_yd3)} yd³`;
  }
  if (line.item === "rebar") {
    return `${formatCount(line.stock_quantity ?? 0)} × ${line.stock_length_ft ?? 20} ft`;
  }
  if (isEachItem(line)) return "Each";
  if (line.unit !== null && line.unit !== undefined) {
    return line.profile === null ? line.unit : `${line.profile} ${line.unit}`;
  }
  if (line.area_mm2 !== null && line.area_mm2 !== undefined) {
    return line.sheet === null || line.sheet === undefined
      ? "—"
      : `${formatCount(line.stock_quantity ?? 0)} × ${line.sheet}`;
  }
  const pieces = splice(line);
  if (pieces !== null) return spliceLabel(pieces);
  return line.stock_length_ft === null ? "—" : `${line.stock_length_ft} ft`;
}

/** A sheet line's stock tooltip: the sheets the panels are cut from and the
 *  offcut (the sheets' area less the net area). */
function sheetsTitle(
  line: CutListLine,
  sheet: string,
  unit: LengthUnit,
  unitLabel: string,
): string {
  const sheets = `${formatCount(line.stock_quantity ?? 0)} sheets of ${sheet}, cut from the panels`;
  const offcut = line.offcut_area_mm2 ?? null;
  return offcut === null
    ? sheets
    : `${sheets}; ${formatArea(offcut, unit)} ${unitLabel}² offcut`;
}

/** How the line's unit price was reached, for its tooltip. */
function priceBasis(line: CutListLine): string | undefined {
  if (line.price_unit === null) return undefined;
  if (line.item === "concrete") {
    return line.bags !== null && line.bags !== undefined
      ? "Each, per 80 lb bag"
      : "Per cubic yard ordered";
  }
  if (line.item === "rebar") return "Each, per 20 ft stick";
  if (line.item === "anchor_bolt") return "Each, per bolt";
  if (line.item === "post_base") return "Each, per post base";
  if (isEachItem(line)) return "Each, per unit";
  if (line.unit !== null && line.unit !== undefined) return "Each, per unit";
  if (line.casework === "edge_banding")
    return "Per ft, on the whole feet bought";
  if (line.casework !== null && line.casework !== undefined)
    return "Each, per piece";
  if (line.sheet !== null && line.sheet !== undefined) {
    return `Each per ${line.sheet} sheet`;
  }
  const pieces = splice(line);
  if (pieces !== null) {
    const label = spliceLabel(pieces);
    const each =
      line.price_unit === "each"
        ? `Each: ${label}`
        : `${PRICE_UNIT_LABEL[line.price_unit]}, ${label} stock`;
    return `${each}: one member's spliced stock`;
  }
  const basis =
    line.price_unit === "each"
      ? `Each at ${line.stock_length_ft} ft`
      : `${PRICE_UNIT_LABEL[line.price_unit]}, ${line.stock_length_ft} ft stock`;
  return `${basis}: one stock piece`;
}

function describe(line: CutListLine, materialName: (key: string) => string) {
  const parts = [
    line.classification === "unclassified" ? null : line.profile,
    line.material === null ? null : materialName(line.material),
  ].filter((v): v is string => v !== null && v !== undefined);
  return parts.join(" · ");
}

/**
 * The cut list at full width (CUT-LIST-PANEL), as Fusion opens the BOM in its
 * own large view: the same grouped, priced table, its head held while the
 * rows scroll, with the Price book and CSV below. A modal layer: Esc or Close
 * shuts it (an open Price book takes Esc first), and it keeps nothing.
 */
function CutListView({
  name,
  summary,
  onClose,
  children,
}: {
  name: string;
  summary: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const titleId = useId();
  const onKeyDown = useCallback(
    (event: KeyboardEvent, insidePanel: boolean) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      containFocus(panelRef.current, event, insidePanel);
    },
    [onClose],
  );
  useModalLayer("cut list", panelRef, onKeyDown);
  useEffect(() => {
    panelRef.current?.focus();
  }, []);
  return createPortal(
    <div
      data-testid="cut-list-expanded-backdrop"
      className="fixed inset-0 z-menu flex justify-center bg-carbide/85 p-4"
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        data-testid="cut-list-expanded"
        className="flex min-h-0 w-full max-w-7xl flex-col border border-etch bg-anvil text-mist shadow-float outline-none"
      >
        <header className="flex shrink-0 items-center gap-x-4 border-b border-hairline bg-carbide py-1.5 pl-4 pr-2">
          <h2
            id={titleId}
            className="font-display text-2xs uppercase tracking-[0.2em] text-gauge"
          >
            Cut list
          </h2>
          <span className="min-w-0 truncate font-body text-sm text-mist">
            {name}
          </span>
          <span className="font-data text-xs text-gauge">{summary}</span>
          <span className="grow" />
          <Button
            size="dense"
            data-testid="cut-list-expanded-close"
            aria-label="Close the full cut list"
            title="Close (Esc)"
            onClick={onClose}
          >
            <CloseIcon size={12} />
            Close
          </Button>
        </header>
        {children}
      </div>
    </div>,
    document.body,
  );
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
  /** The Price book is open: null seed from the button, a line's from a blank. */
  const [priceBook, setPriceBook] = useState<{
    seed: PriceBookSeed | null;
  } | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  /** The full-width view is open (view state only: nothing is saved). */
  const [expanded, setExpanded] = useState(false);
  const asideRef = useRef<HTMLElement | null>(null);
  const closeExpanded = useCallback(() => {
    setExpanded(false);
    // Focus goes back to the Expand button it was opened from.
    asideRef.current
      ?.querySelector<HTMLElement>('[data-testid="cut-list-expand"]')
      ?.focus();
  }, []);

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
  // The gateway orders the lines by system; each run is one group.
  const groups = groupBySystem(lines);
  // Deleted parts an assembly still places: listed, never silently dropped.
  const missingPieces = (data?.missing ?? []).reduce(
    (sum, part) => sum + part.quantity,
    0,
  );
  /** The table (or its state), in the panel or in the full-width view. */
  const table = (seat: "panel" | "expanded") => {
    const expandedSeat = seat === "expanded";
    return cutList.error ? (
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
        No bodies to cut yet. Each body becomes a line here, measured along its
        length.
      </p>
    ) : (
      <div
        data-testid="cut-list-scroll"
        className={
          expandedSeat
            ? // The view scrolls both ways itself; its head stays put.
              "min-h-0 flex-1 overflow-auto [container-type:inline-size]"
            : "overflow-x-auto [container-type:inline-size]"
        }
      >
        <table
          data-testid="cut-list-table"
          aria-label={`Cut list, ${lines.length} lines, ${data.total_quantity} pieces`}
          className="w-full border-collapse font-body text-sm"
        >
          <thead
            className={
              expandedSeat
                ? "sticky top-0 z-[1] bg-anvil [&_th]:whitespace-nowrap"
                : undefined
            }
          >
            <tr className="border-b border-hairline text-gauge">
              <th scope="col" className={`${HEAD_BASE} pl-3 pr-1 text-left`}>
                Member
              </th>
              <th scope="col" className={HEAD}>
                Qty
              </th>
              <th scope="col" className={HEAD} title={`Each (${unitLabel})`}>
                Length
              </th>
              <th
                scope="col"
                className={`${HEAD} ${RUN_COLUMN}`}
                title={`Qty × length (${unitLabel})`}
              >
                Run
              </th>
              <th
                scope="col"
                className={HEAD}
                title="Shortest standard stock that covers each piece, or the pieces a longer one is spliced from"
              >
                Stock
              </th>
              <th
                scope="col"
                className={HEAD}
                title={`Unit price: one piece's stock (${data.currency})`}
              >
                Unit price
              </th>
              <th
                scope="col"
                className={`${HEAD_BASE} pl-1.5 pr-3 text-right`}
                title={`Extended price: stock qty × unit price (${data.currency})`}
              >
                Ext. price
              </th>
            </tr>
          </thead>
          {(() => {
            const row = (line: CutListLine, index: number) => {
              const unclassified = line.classification === "unclassified";
              const caption = unclassified
                ? `Unclassified · ${line.section_mm
                    .map((v) => formatLength(v, unit))
                    .join(" × ")} ${unitLabel}`
                : describe(line, materialName);
              const seed = seedFor(line);
              const name = line.member ?? line.profile ?? "Body";
              const area = line.area_mm2 ?? null;
              const sheet = line.sheet ?? null;
              // A pour lists its volume; a bolt has no length to list.
              const volume =
                line.item === "concrete" ? (line.volume_mm3 ?? 0) : null;
              // A bolt, vent or hinge is counted, not measured: no length.
              const bolt =
                isEachItem(line) ||
                (line.casework !== null &&
                  line.casework !== undefined &&
                  line.casework !== "edge_banding");
              const noRun = area !== null || volume !== null || bolt;
              return (
                <tr
                  key={index}
                  data-testid="cut-list-row"
                  data-member={line.member ?? ""}
                  data-profile={line.profile ?? ""}
                  data-classification={line.classification}
                  data-sheet={sheet ?? undefined}
                  data-system={line.system}
                  data-item={line.item ?? undefined}
                  className="border-b border-hairline/60 last:border-b-0"
                >
                  {/* The member column takes what the figures leave
                            (max-w-0: its text never widens the table) and
                            WRAPS: a member's name is never cut off. */}
                  <td className="w-full max-w-0 py-1.5 pl-3 pr-1 align-baseline [overflow-wrap:anywhere]">
                    <span
                      data-testid="cut-list-member"
                      className={`block ${
                        unclassified ? "italic text-gauge" : "text-mist"
                      }`}
                    >
                      {line.member ?? line.profile ?? "Body"}
                    </span>
                    {caption ? (
                      <span
                        data-testid="cut-list-caption"
                        // The profile and material are one line, so
                        // a row is two: the material's long name gives
                        // way (in full on hover), the member's never.
                        className="block truncate text-2xs text-gauge"
                        title={caption}
                      >
                        {caption}
                      </span>
                    ) : null}
                  </td>
                  <td
                    data-testid="cut-list-qty"
                    className={`${CELL} text-mist`}
                  >
                    {formatCount(line.quantity)}
                  </td>
                  <td
                    data-testid="cut-list-length"
                    className={`${CELL} text-mist`}
                    title={
                      volume !== null
                        ? "Net volume, measured"
                        : area === null
                          ? undefined
                          : "Net area, openings cut out"
                    }
                  >
                    {volume !== null ? (
                      <span
                        data-testid="cut-list-volume"
                        className="whitespace-nowrap"
                      >
                        {formatYd3(volume / MM3_PER_YD3)} yd³
                      </span>
                    ) : bolt ? (
                      "—"
                    ) : area === null ? (
                      formatLength(line.length_mm, unit)
                    ) : (
                      <span
                        data-testid="cut-list-area"
                        className="whitespace-nowrap"
                      >
                        {formatArea(area, unit)} {unitLabel}²
                      </span>
                    )}
                  </td>
                  <td
                    data-testid="cut-list-total-length"
                    className={`${CELL} text-gauge ${RUN_COLUMN}`}
                  >
                    {noRun ? null : formatLength(line.total_length_mm, unit)}
                  </td>
                  <td
                    data-testid="cut-list-stock"
                    className={`${CELL} whitespace-nowrap text-mist`}
                    title={
                      volume !== null
                        ? `${formatYd3(volume / MM3_PER_YD3)} yd³ + ${line.waste_percent ?? 0}% waste, ${
                            line.bags !== null && line.bags !== undefined
                              ? "in 80 lb bags of 0.60 ft³, rounded up to whole bags"
                              : "rounded up to 1/4 yd³"
                          }`
                        : line.item === "rebar"
                          ? "20 ft sticks, lapped 24 in at each joint"
                          : sheet !== null
                            ? sheetsTitle(line, sheet, unit, unitLabel)
                            : line.waste_mm === null
                              ? // Why a joist past 24 ft has no stock (NO-SPLICE-SPANS).
                                (line.stock_note ?? undefined)
                              : `${formatLength(line.waste_mm, unit)} ${unitLabel} offcut each`
                    }
                  >
                    {stockLabel(line)}
                  </td>
                  <td
                    data-testid="cut-list-unit-price"
                    className={`${CELL} text-mist`}
                    title={priceBasis(line)}
                  >
                    {line.unit_price_cents !== null ? (
                      formatMoney(line.unit_price_cents, data.currency)
                    ) : seed !== null ? (
                      // Blank, never $0: the cell is the way to price it.
                      <button
                        type="button"
                        data-testid="cut-list-price-blank"
                        aria-label={
                          line.unit !== null && line.unit !== undefined
                            ? `Price ${name}, ${stockLabel(line)} unit`
                            : sheet === null
                              ? `Price ${name}, ${line.profile} at ${stockLabel(line)}`
                              : `Price ${name}, ${line.profile} ${sheet} sheet`
                        }
                        aria-haspopup="dialog"
                        title="Not in your price book. Click to price it."
                        onClick={() => setPriceBook({ seed })}
                        className="-my-1 inline-flex min-h-target-dense w-full min-w-10 items-center justify-end rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-transparent outline-none transition-colors duration-fast hover:bg-carbide hover:text-brass focus-visible:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass"
                      >
                        Price
                      </button>
                    ) : null}
                  </td>
                  <td
                    data-testid="cut-list-ext-price"
                    className="whitespace-nowrap py-1.5 pl-1.5 pr-3 text-right align-baseline font-data tabular-nums text-mist"
                    title={
                      line.extended_price_cents === null ||
                      line.unit_price_cents === null
                        ? undefined
                        : line.bags !== null && line.bags !== undefined
                          ? `${formatCount(line.bags)} bags × ${formatMoney(line.unit_price_cents, data.currency)}`
                          : line.item === "concrete"
                            ? `${formatYd3(line.order_yd3 ?? 0)} yd³ × ${formatMoney(line.unit_price_cents, data.currency)}`
                            : splice(line) !== null
                              ? `${formatCount(line.stock_quantity ?? 0)} × (${spliceLabel(splice(line) ?? [])}) × ${formatMoney(line.unit_price_cents, data.currency)}`
                              : `${formatCount(line.stock_quantity ?? 0)} stock × ${formatMoney(line.unit_price_cents, data.currency)}`
                    }
                  >
                    {line.extended_price_cents === null
                      ? null
                      : formatMoney(line.extended_price_cents, data.currency)}
                  </td>
                </tr>
              );
            };
            return groups.map((group, at) => (
              <tbody
                key={`${group.system}-${at}`}
                data-testid="cut-list-group"
                data-system={group.system}
              >
                {groups.length > 1 ? (
                  <tr className="border-b border-hairline">
                    <th
                      scope="rowgroup"
                      colSpan={7}
                      data-testid="cut-list-group-label"
                      className="bg-carbide/40 pb-1 pl-3 pr-3 pt-2.5 text-left font-display text-2xs font-normal uppercase tracking-[0.16em] text-gauge"
                    >
                      {SYSTEM_LABEL[group.system]}
                      <span className="ml-2 font-data normal-case tracking-normal text-gauge/70">
                        {formatCount(group.lines.length)}
                      </span>
                    </th>
                  </tr>
                ) : null}
                {group.lines.map((line) => row(line, line.index))}
              </tbody>
            ));
          })()}
          <tfoot>
            <tr className="border-t border-hairline">
              <td className="py-1.5 pl-3 font-display text-2xs uppercase tracking-[0.16em] text-gauge">
                Pieces
              </td>
              <td
                data-testid="cut-list-total"
                className="whitespace-nowrap px-1.5 py-1.5 text-right font-data tabular-nums text-brass"
              >
                {formatCount(data.total_quantity)}
              </td>
              <td />
              <td className={RUN_COLUMN} />
              <td
                colSpan={3}
                className="py-1.5 pr-3 text-right font-body text-2xs text-gauge"
              >
                Lengths in {unitLabel}
              </td>
            </tr>
            <tr data-testid="cut-list-price-row">
              <th
                scope="row"
                colSpan={3}
                className="py-1.5 pl-3 text-left align-baseline font-normal"
              >
                <span className="font-display text-2xs uppercase tracking-[0.16em] text-gauge">
                  Total
                </span>
                {data.unpriced_lines > 0 ? (
                  <span
                    data-testid="cut-list-unpriced"
                    className="ml-2 font-body text-2xs text-flag"
                  >
                    {unpricedLabel(data.unpriced_lines)}
                  </span>
                ) : null}
              </th>
              <td className={RUN_COLUMN} />
              <td colSpan={2} />
              <td
                data-testid="cut-list-price-total"
                className="whitespace-nowrap py-1.5 pl-1.5 pr-3 text-right align-baseline font-data tabular-nums text-brass"
              >
                {data.total_price_cents === null
                  ? null
                  : formatMoney(data.total_price_cents, data.currency)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    );
  };
  /** What follows the table: deleted parts, Price book and CSV. */
  const footer = () => (
    <>
      {missingPieces > 0 ? (
        <p
          role="note"
          data-testid="cut-list-missing"
          className="border-t border-hairline px-3 py-2 font-body text-2xs text-flag"
        >
          {missingPieces === 1
            ? "1 placement of a deleted part is not listed."
            : `${missingPieces} placements of deleted parts are not listed.`}
        </p>
      ) : null}
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
          data-testid="cut-list-price-book"
          aria-haspopup="dialog"
          onClick={() => setPriceBook({ seed: null })}
        >
          Price book
        </Button>
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
    </>
  );
  return (
    <aside
      ref={asideRef}
      className="flex w-full flex-col gap-3"
      aria-label="Cut list"
      data-testid="cut-list-panel"
      data-source-kind={kind}
    >
      <Panel>
        <PanelSection
          eyebrow={lines.length > 0 ? `Cut list · ${lines.length}` : "Cut list"}
          stickyCaption
          actions={
            lines.length > 0 ? (
              <Button
                size="dense"
                data-testid="cut-list-expand"
                aria-label="Expand the cut list"
                aria-haspopup="dialog"
                title="Open the cut list full width (Esc closes)"
                onClick={() => setExpanded(true)}
              >
                <ExpandIcon size={12} />
                Expand
              </Button>
            ) : undefined
          }
        >
          {table("panel")}
        </PanelSection>
        {footer()}
      </Panel>
      {expanded && data !== undefined ? (
        <CutListView
          name={data.name}
          summary={`${formatCount(lines.length)} lines · ${formatCount(data.total_quantity)} pieces`}
          onClose={closeExpanded}
        >
          {table("expanded")}
          <div className="shrink-0">{footer()}</div>
        </CutListView>
      ) : null}
      {priceBook !== null ? (
        <PriceBookDialog
          seed={priceBook.seed}
          onClose={() => setPriceBook(null)}
        />
      ) : null}
    </aside>
  );
}
