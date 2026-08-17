import { Chip } from "@loft/design";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";

import {
  createPart,
  deletePart,
  duplicatePart,
  fetchParts,
  movePart,
  renamePart,
} from "../api/parts";
import {
  DocumentRegister,
  type RegisterCopy,
} from "../components/DocumentRegister";
import { SheetGrid } from "../components/SheetGrid";
import { TopBar } from "../components/TopBar";
import { useRegisterFiling } from "../components/useRegisterFiling";
import { WorkspaceNav } from "../components/WorkspaceNav";
import { usePreferencesStore } from "../settings/preferences";
import type { PartResponse } from "../api/parts";

/**
 * The parts home — the landing surface after sign-in. The drawer itself lives
 * in `DocumentRegister` (one register, three configs); this page supplies the
 * parts vocabulary, the route into a part's workspace, and the one behaviour
 * that is genuinely parts-only: creating a part OPENS it (FINDINGS #22), so
 * naming a sheet starts drawing on it rather than filing it and standing still.
 */
const COPY: RegisterCopy = {
  title: "Parts register",
  caption:
    "Your parts, most recently worked first. Open a part to model it, or delete it. Last worked reads the time since its most recent edit.",
  noun: "part",
  nounPlural: "parts",
  loading: "Loading parts…",
  loadError: "Your parts could not be loaded.",
  deleteError: "The part could not be deleted.",
  renameError: "The part could not be renamed.",
  duplicateError: "The part could not be duplicated.",
  createError: "The part could not be created.",
  emptyHeadline: "Nothing filed here yet.",
  emptyBody:
    "Name your first part to open a fresh sheet — sketch it, extrude it, and it will be filed here for next time.",
  fieldLabel: "Part name",
  placeholder: "e.g. Bracket plate",
  createLabel: "New part",
  createFirstLabel: "Create first part",
};

export function PartsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  // The user's "units for new documents" preference (#58) is stamped on the
  // part at CREATION; after that the document owns its unit.
  const newDocumentUnit = usePreferencesStore((state) => state.newDocumentUnit);
  const parts = useQuery({
    queryKey: ["parts"],
    queryFn: () => fetchParts(),
    staleTime: 30_000,
  });
  // Filing (#WS2) — the folder tree for THIS drawer plus its four verbs, wired
  // once for all three registers.
  const filing = useRegisterFiling<PartResponse>("part", "parts", movePart);

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <Chip data-testid="status-chip">Parts</Chip>
      </TopBar>
      <main className="relative min-h-0 grow overflow-y-auto bg-carbide">
        <SheetGrid />
        {/* Sheet border, matching the sign-in un-issued sheet. */}
        <div
          className="pointer-events-none absolute inset-3 border border-hairline"
          aria-hidden="true"
        />
        <div className="relative mx-auto flex h-full w-full max-w-5xl flex-col px-4 py-6 sm:px-8">
          <WorkspaceNav active="parts" />
          <DocumentRegister
            idPlural="parts"
            idSingular="part"
            copy={COPY}
            documents={parts.data ?? []}
            isLoading={parts.isLoading}
            isError={parts.isError}
            error={parts.error}
            openLink={(part, props) => (
              <Link to="/parts/$partId" params={{ partId: part.id }} {...props}>
                {part.name}
              </Link>
            )}
            filing={filing}
            onCreate={async (name, folderId) => {
              // The folder the register is standing in rides the create, so a
              // part named inside a folder is filed there in one call.
              const part = await createPart(name, newDocumentUnit, folderId);
              await queryClient.invalidateQueries({ queryKey: ["parts"] });
              await navigate({
                to: "/parts/$partId",
                params: { partId: part.id },
              });
            }}
            onRename={async (part, name) => {
              // The rename rides the part's CURRENT tree_version as its
              // optimistic-concurrency guard — the same guard every other part
              // write uses — and the register then refetches, so the row shows
              // the name the server stored rather than the one that was typed.
              await renamePart(part.id, name, part.tree_version);
              await queryClient.invalidateQueries({ queryKey: ["parts"] });
            }}
            onDuplicate={async (part) => {
              // No name is sent and none is predicted: the copy comes back
              // named, and the refetched list is what the register renders.
              await duplicatePart(part.id);
              await queryClient.invalidateQueries({ queryKey: ["parts"] });
            }}
            onDelete={async (part) => {
              await deletePart(part.id);
              await queryClient.invalidateQueries({ queryKey: ["parts"] });
            }}
          />
        </div>
      </main>
    </div>
  );
}
