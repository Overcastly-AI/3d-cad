import { Chip } from "@loft/design";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import {
  createAssembly,
  deleteAssembly,
  fetchAssemblies,
} from "../api/assemblies";
import {
  DocumentRegister,
  type RegisterCopy,
} from "../components/DocumentRegister";
import { SheetGrid } from "../components/SheetGrid";
import { TopBar } from "../components/TopBar";
import { WorkspaceNav } from "../components/WorkspaceNav";

/**
 * The assemblies register — the same drawer as parts (`DocumentRegister`) with
 * the assembly vocabulary and the route into the instances/mates workspace.
 * Filing an assembly does NOT open it: unlike a part, a new assembly has
 * nothing to work on until parts are added to it, so the register keeps focus
 * on the scribe line for the next one.
 */
const COPY: RegisterCopy = {
  title: "Assembly register",
  caption:
    "Your assemblies, oldest first. Open one to compose it, or delete it. Last worked reads the time since its most recent edit.",
  noun: "assembly",
  nounPlural: "assemblies",
  loading: "Loading assemblies…",
  loadError: "Your assemblies could not be loaded.",
  deleteError: "The assembly could not be deleted.",
  createError: "The assembly could not be created.",
  emptyHeadline: "No assemblies filed yet.",
  emptyBody:
    "Name your first assembly, then add parts to it, ground one, and bolt the rest together with mates.",
  fieldLabel: "Assembly name",
  placeholder: "e.g. Bolted plates",
  createLabel: "New assembly",
  createFirstLabel: "Create first assembly",
};

export function AssembliesPage() {
  const queryClient = useQueryClient();
  const assemblies = useQuery({
    queryKey: ["assemblies"],
    queryFn: () => fetchAssemblies(),
    staleTime: 30_000,
  });

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <Chip data-testid="status-chip">Assemblies</Chip>
      </TopBar>
      <main className="relative min-h-0 grow overflow-y-auto bg-carbide">
        <SheetGrid />
        <div
          className="pointer-events-none absolute inset-3 border border-hairline"
          aria-hidden="true"
        />
        <div className="relative mx-auto flex h-full w-full max-w-5xl flex-col px-4 py-6 sm:px-8">
          <WorkspaceNav active="assemblies" />
          <DocumentRegister
            idPlural="assemblies"
            idSingular="assembly"
            copy={COPY}
            documents={assemblies.data ?? []}
            isLoading={assemblies.isLoading}
            isError={assemblies.isError}
            error={assemblies.error}
            openLink={(assembly, props) => (
              <Link
                to="/assemblies/$assemblyId"
                params={{ assemblyId: assembly.id }}
                {...props}
              >
                {assembly.name}
              </Link>
            )}
            onCreate={async (name) => {
              await createAssembly(name);
              await queryClient.invalidateQueries({ queryKey: ["assemblies"] });
            }}
            onDelete={async (assembly) => {
              await deleteAssembly(assembly.id);
              await queryClient.invalidateQueries({ queryKey: ["assemblies"] });
            }}
          />
        </div>
      </main>
    </div>
  );
}
