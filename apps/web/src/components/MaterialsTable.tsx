/**
 * The materials list on a house set's sheet (HOUSE-DRAWINGS, CUT-LIST-PDF):
 * the drawn part's cut list as a yard order — Item, Qty, Size, Length,
 * Material, Price — placed by the composer like Chief Architect's Materials
 * List. Drawn VERBATIM from the composed model, with the cells at the offsets
 * the server's SVG, PDF and DXF read (`sheet_style._table_cells`), so the
 * sheet on screen and the PDF a yard receives read line for line the same,
 * and both read the cut-list panel's lines to the cent.
 */
import { drawing, font } from "@loft/design";

import type { components } from "@loft/ts-client/gateway";

export type ComposedMaterialsTable =
  components["schemas"]["ComposedMaterialsTable"];

/** The text inset from a column's edge (the server's `_TABLE_CELL_PAD`). */
const CELL_PAD_MM = 1.4;

/** Each non-empty cell with its x and anchor — the server's `_table_cells`. */
export function tableCells(
  table: ComposedMaterialsTable,
  blockX: number,
  cells: readonly string[],
): { text: string; x: number; anchor: "start" | "end" }[] {
  const out: { text: string; x: number; anchor: "start" | "end" }[] = [];
  cells.forEach((text, i) => {
    if (!text) return;
    const left = blockX + (table.column_dx[i] ?? 0);
    if (table.align[i] === "right" && cells.length > 1) {
      out.push({
        text,
        x: left + (table.column_w[i] ?? 0) - CELL_PAD_MM,
        anchor: "end",
      });
    } else {
      out.push({ text, x: left + CELL_PAD_MM, anchor: "start" });
    }
  });
  return out;
}

export function MaterialsTable({ table }: { table: ComposedMaterialsTable }) {
  const lines = table.blocks.flatMap((b) =>
    b.rows.filter((r) => r.kind === "line"),
  ).length;
  return (
    <g
      data-testid="drawing-materials-table"
      aria-label={`Materials list, ${lines} lines`}
    >
      {table.blocks.map((block, b) => (
        <g key={b}>
          <rect
            x={block.x}
            y={block.y}
            width={block.width}
            height={block.height}
            fill={drawing.paper}
            stroke={drawing.ink}
            strokeWidth={drawing.borderWeightMm}
          />
          <line
            x1={block.x}
            y1={block.y + table.row_height}
            x2={block.x + block.width}
            y2={block.y + table.row_height}
            stroke={drawing.ink}
            strokeWidth={drawing.hiddenWeightMm}
          />
          {tableCells(table, block.x, table.columns).map((cell, i) => (
            <text
              key={i}
              x={cell.x}
              y={block.header_y}
              textAnchor={cell.anchor}
              fill={drawing.label}
              fontFamily={font.display}
              fontSize={table.text_mm}
              letterSpacing={0.4}
            >
              {cell.text.toUpperCase()}
            </text>
          ))}
          {block.rows.map((row, r) => (
            <g
              key={r}
              data-testid="drawing-materials-row"
              data-row-kind={row.kind}
            >
              {row.kind === "total" ? (
                <line
                  x1={block.x}
                  y1={row.y - table.row_height + 1.6}
                  x2={block.x + block.width}
                  y2={row.y - table.row_height + 1.6}
                  stroke={drawing.ink}
                  strokeWidth={drawing.hiddenWeightMm}
                />
              ) : null}
              {tableCells(table, block.x, row.cells).map((cell, i) => (
                <text
                  key={i}
                  data-testid="drawing-materials-cell"
                  x={cell.x}
                  y={row.y}
                  textAnchor={cell.anchor}
                  fill={
                    row.kind === "group" ? drawing.label : drawing.dimensionText
                  }
                  fontFamily={row.kind === "group" ? font.display : font.data}
                  fontSize={table.text_mm}
                >
                  {cell.text}
                </text>
              ))}
            </g>
          ))}
        </g>
      ))}
    </g>
  );
}
