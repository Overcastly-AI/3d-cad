import { Chip } from "@loft/design";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import {
  createDrawing,
  deleteDrawing,
  duplicateDrawing,
  type DrawingResponse,
  fetchDrawings,
  moveDrawing,
  renameDrawing,
} from "../api/drawings";
import {
  DocumentRegister,
  type RegisterCopy,
} from "../components/DocumentRegister";
import { SheetGrid } from "../components/SheetGrid";
import { TopBar } from "../components/TopBar";
import { useRegisterFiling } from "../components/useRegisterFiling";
import { WorkspaceNav } from "../components/WorkspaceNav";

/**
 * The drawings register — the third drawer. A drawing carries no document unit
 * of its own (its dimensions read the referenced part's), so `DocumentRegister`
 * drops the UNITS column here rather than ruling a blank one: the register
 * shows what a drawing HAS, never a placeholder for what it hasn't.
 */
const COPY: RegisterCopy = {
  title: "Drawing register",
  caption:
    "Your drawings, most recently worked first. Open one to lay out its views, or delete it. Last worked reads the time since its most recent edit.",
  noun: "drawing",
  nounPlural: "drawings",
  loading: "Loading drawings…",
  loadError: "Your drawings could not be loaded.",
  deleteError: "The drawing could not be deleted.",
  renameError: "The drawing could not be renamed.",
  duplicateError: "The drawing could not be duplicated.",
  createError: "The drawing could not be created.",
  emptyHeadline: "No drawings filed yet.",
  emptyBody:
    "Name your first drawing, then open it to reference a part and lay out the standard views on a sheet.",
  fieldLabel: "Drawing name",
  placeholder: "e.g. Bracket — sheet 1",
  createLabel: "New drawing",
  createFirstLabel: "Create first drawing",
};

export function DrawingsPage() {
  const queryClient = useQueryClient();
  const drawings = useQuery({
    queryKey: ["drawings"],
    queryFn: () => fetchDrawings(),
    staleTime: 30_000,
  });
  // Filing (#WS2) — see PartsPage; the wiring is shared, not repeated.
  const filing = useRegisterFiling<DrawingResponse>(
    "drawing",
    "drawings",
    moveDrawing,
  );

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <Chip data-testid="status-chip">Drawings</Chip>
      </TopBar>
      <main className="relative min-h-0 grow overflow-y-auto bg-carbide">
        <SheetGrid />
        <div
          className="pointer-events-none absolute inset-3 border border-hairline"
          aria-hidden="true"
        />
        <div className="relative mx-auto flex h-full w-full max-w-5xl flex-col px-4 py-6 sm:px-8">
          <WorkspaceNav active="drawings" />
          <DocumentRegister
            idPlural="drawings"
            idSingular="drawing"
            copy={COPY}
            documents={drawings.data ?? []}
            isLoading={drawings.isLoading}
            isError={drawings.isError}
            error={drawings.error}
            openLink={(drawing, props) => (
              <Link
                to="/drawings/$drawingId"
                params={{ drawingId: drawing.id }}
                {...props}
              >
                {drawing.name}
              </Link>
            )}
            filing={filing}
            onCreate={async (name, folderId) => {
              await createDrawing(name, folderId);
              await queryClient.invalidateQueries({ queryKey: ["drawings"] });
            }}
            onRename={async (drawing, name) => {
              await renameDrawing(drawing.id, name, drawing.doc_version);
              await queryClient.invalidateQueries({ queryKey: ["drawings"] });
            }}
            onDuplicate={async (drawing) => {
              await duplicateDrawing(drawing.id);
              await queryClient.invalidateQueries({ queryKey: ["drawings"] });
            }}
            onDelete={async (drawing) => {
              await deleteDrawing(drawing.id);
              await queryClient.invalidateQueries({ queryKey: ["drawings"] });
            }}
          />
        </div>
      </main>
    </div>
  );
}
