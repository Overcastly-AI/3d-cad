import { Chip } from "@loft/design";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";

import { createPart, deletePart, fetchParts } from "../api/parts";
import {
  DocumentRegister,
  type RegisterCopy,
} from "../components/DocumentRegister";
import { SheetGrid } from "../components/SheetGrid";
import { TopBar } from "../components/TopBar";
import { WorkspaceNav } from "../components/WorkspaceNav";

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
    "Your parts, oldest first. Open a part to model it, or delete it. Last worked reads the time since its most recent edit.",
  noun: "part",
  nounPlural: "parts",
  loading: "Loading parts…",
  loadError: "Your parts could not be loaded.",
  deleteError: "The part could not be deleted.",
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
  const parts = useQuery({
    queryKey: ["parts"],
    queryFn: () => fetchParts(),
    staleTime: 30_000,
  });

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
            onCreate={async (name) => {
              const part = await createPart(name);
              await queryClient.invalidateQueries({ queryKey: ["parts"] });
              await navigate({
                to: "/parts/$partId",
                params: { partId: part.id },
              });
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
