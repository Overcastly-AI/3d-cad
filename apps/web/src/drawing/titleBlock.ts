/**
 * Title-block secondary free-text fields (author/date/notes) — the DOM twin of
 * the server composer's `_tb_fields` (drawings D1). The optional TitleBlock
 * free-text stamps as labeled DRAWN / DATE / NOTES rows in the left cell's
 * mid-band, below the primary title. This is the ONE place the "which rows
 * render, and where" decision lives on the client, mirroring the server EXACTLY
 * (fixed captions, field keys, and per-field baselines), so the on-screen sheet
 * and the exported SVG/PDF/DXF stamp the same rows at the same places. A `null`
 * / blank field is skipped (the composer's additive posture — an empty title
 * block emits none of these rows).
 */
import type { ComposedTitleBlock } from "../api/drawings";

/** One rendered secondary row: caption, its stamped value, the field key (for the
 * `title-block-{key}` test hook), and the baseline y offset from the block top. */
export interface TitleBlockFieldRow {
  caption: "DRAWN" | "DATE" | "NOTES";
  key: "author" | "date" | "notes";
  value: string;
  /** Baseline y offset (mm) from the block TOP edge — fixed per field, so a
   * present field keeps its place whether or not the others are set. */
  dy: number;
}

/** Fixed caption + baseline per field, in field order — mirrors the server's
 * `_TB_FIELD_CAPTIONS` / `_TB_FIELD_KEYS` / `_TB_FIELD_ROWS_DY`. */
const FIELDS: readonly {
  caption: TitleBlockFieldRow["caption"];
  key: TitleBlockFieldRow["key"];
  dy: number;
}[] = [
  { caption: "DRAWN", key: "author", dy: 20.5 },
  { caption: "DATE", key: "date", dy: 23.5 },
  { caption: "NOTES", key: "notes", dy: 26.5 },
];

/** The secondary rows to stamp for a title block, in field order — a `null` /
 * undefined field is skipped (an all-unset block yields `[]`). */
export function titleBlockFields(
  block: ComposedTitleBlock,
): TitleBlockFieldRow[] {
  const values: Record<TitleBlockFieldRow["key"], string | null | undefined> = {
    author: block.author,
    date: block.date,
    notes: block.notes,
  };
  const rows: TitleBlockFieldRow[] = [];
  for (const field of FIELDS) {
    const value = values[field.key];
    if (value != null) {
      rows.push({ ...field, value });
    }
  }
  return rows;
}
