/**
 * What a sheet drafts — the drawing workspace's SOURCE model.
 *
 * A view has always referenced a part OR an assembly (`ref_document_kind`), and
 * the compose wire projects the solved assembly compound for the assembly case
 * (§7). The setup band used to offer parts only, which made every assembly
 * sheet — and therefore the whole numbered parts list that hangs off one —
 * unreachable through the UI. This module is the one place that answers "what
 * can this sheet draft, and which kind is the chosen one", so the picker, the
 * layout action, the query gating and the parts-list block cannot disagree.
 *
 * The option VALUE is the bare document id, never a `kind:id` composite: the
 * ids are server-issued uuids from two registers and the kind is recovered by
 * lookup, which keeps every existing `selectOption(part.id)` call site honest.
 */
import type { RefDocumentKind } from "../api/drawings";

/** One choosable source: a part or an assembly, by id, with its display name. */
export interface DrawingSourceOption {
  id: string;
  name: string;
  kind: RefDocumentKind;
}

/** The picker's group heading for a kind — the `<optgroup>` label. */
export const SOURCE_GROUP_LABEL: Record<RefDocumentKind, string> = {
  part: "Parts",
  assembly: "Assemblies",
};

/** The singular noun for a kind — the post-layout readout's caption. */
export const SOURCE_KIND_LABEL: Record<RefDocumentKind, string> = {
  part: "Part",
  assembly: "Assembly",
};

/**
 * The pickable sources, parts first then assemblies, each register keeping its
 * own order. Parts lead because the overwhelming majority of sheets draft one
 * and the first entry is the default selection.
 */
export function drawingSourceOptions(
  parts: readonly { id: string; name: string }[],
  assemblies: readonly { id: string; name: string }[],
): DrawingSourceOption[] {
  return [
    ...parts.map((part) => ({
      id: part.id,
      name: part.name,
      kind: "part" as const,
    })),
    ...assemblies.map((assembly) => ({
      id: assembly.id,
      name: assembly.name,
      kind: "assembly" as const,
    })),
  ];
}

/**
 * The kind of the source with this id, or `"part"` when it is unknown — the
 * pre-registers-loaded state, where "part" is both the historical default and
 * the conservative one (it gates the part-only actions on, and they carry
 * their own guards).
 */
export function drawingSourceKind(
  sources: readonly DrawingSourceOption[],
  id: string | null,
): RefDocumentKind {
  if (id === null) return "part";
  return sources.find((source) => source.id === id)?.kind ?? "part";
}

/** The chosen source's display name, or null when it is not (yet) known. */
export function drawingSourceName(
  sources: readonly DrawingSourceOption[],
  id: string | null,
): string | null {
  if (id === null) return null;
  return sources.find((source) => source.id === id)?.name ?? null;
}
