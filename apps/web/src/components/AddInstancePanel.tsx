/**
 * Add-a-component panel — the instance picker, shown in the viewport HUD (top-
 * left, the same anchor the part editors use). Lists the caller's parts, then
 * their other assemblies, as ruled action cells; choosing one adds it to the
 * assembly as a new instance (the user then grounds one and joins the rest).
 * An assembly goes in as a RIGID SUB-ASSEMBLY (Fusion's Insert into Current
 * Design, SolidWorks' Insert Component): one component that moves as a unit.
 * An assembly that already contains this one is refused by the server, whose
 * message names the chain. Each cell leads with the document's server-rendered
 * thumbnail (LIBRARY-THUMBNAILS), as Fusion's Insert-into-design list and
 * Onshape's Insert dialog show one: you pick a part by what it looks like.
 */
import { Panel, PanelActionCell, PanelSection } from "@loft/design";
import { useQuery } from "@tanstack/react-query";

import { fetchAssemblies, type AssemblyResponse } from "../api/assemblies";
import { fetchParts, type PartResponse } from "../api/parts";

import { DocumentThumbnail } from "./DocumentThumbnail";

export interface AddInstancePanelProps {
  /** The id of the document being added (its cell shows busy), or null. */
  addingPartId: string | null;
  error: string | null;
  onAdd: (part: PartResponse) => void;
  /** The assembly being edited: never offered as its own sub-assembly. */
  assemblyId?: string;
  /** Insert another assembly as a rigid sub-assembly. */
  onAddAssembly?: (assembly: AssemblyResponse) => void;
  onClose: () => void;
}

export function AddInstancePanel({
  addingPartId,
  error,
  onAdd,
  assemblyId,
  onAddAssembly,
  onClose,
}: AddInstancePanelProps) {
  const parts = useQuery({
    queryKey: ["parts"],
    queryFn: () => fetchParts(),
    staleTime: 30_000,
  });
  const assemblies = useQuery({
    queryKey: ["assemblies"],
    queryFn: () => fetchAssemblies(),
    enabled: onAddAssembly !== undefined,
    staleTime: 30_000,
  });
  const list = parts.data ?? [];
  const subs = (assemblies.data ?? []).filter((a) => a.id !== assemblyId);

  return (
    <div
      className="absolute left-editor top-3 w-editor max-w-[calc(100%-theme(inset.editor)-0.75rem)]"
      data-testid="add-instance-panel"
    >
      <Panel>
        <PanelSection eyebrow="Add a part">
          {parts.isLoading ? (
            <p className="px-3 py-3 font-data text-xs text-gauge">
              Loading parts…
            </p>
          ) : parts.isError ? (
            <p
              role="alert"
              className="px-3 py-3 font-body text-xs text-flag"
              data-testid="add-instance-error"
            >
              {parts.error instanceof Error
                ? parts.error.message
                : "Your parts could not be loaded."}
            </p>
          ) : list.length === 0 ? (
            <p className="px-3 py-3 font-body text-xs text-gauge">
              No parts to add. Model a part first, then instance it here.
            </p>
          ) : (
            <div
              className="max-h-[16rem] overflow-y-auto"
              data-testid="add-instance-list"
            >
              {list.map((part) => (
                <PanelActionCell
                  key={part.id}
                  label={part.name}
                  caption={
                    addingPartId === part.id ? "Adding…" : "Instance this part"
                  }
                  icon={
                    <DocumentThumbnail
                      kind="part"
                      id={part.id}
                      version={part.tree_version}
                      name={part.name}
                      size="sm"
                    />
                  }
                  disabled={addingPartId !== null}
                  data-testid={`add-instance-part-${part.id}`}
                  onClick={() => onAdd(part)}
                />
              ))}
            </div>
          )}
        </PanelSection>
        {onAddAssembly !== undefined && subs.length > 0 ? (
          <PanelSection eyebrow="Insert a sub-assembly">
            <div
              className="max-h-[10rem] overflow-y-auto"
              data-testid="add-instance-assembly-list"
            >
              {subs.map((sub) => (
                <PanelActionCell
                  key={sub.id}
                  label={sub.name}
                  caption={
                    addingPartId === sub.id
                      ? "Inserting…"
                      : "Insert as one rigid component"
                  }
                  icon={
                    <DocumentThumbnail
                      kind="assembly"
                      id={sub.id}
                      version={sub.updated_at}
                      name={sub.name}
                      size="sm"
                    />
                  }
                  disabled={addingPartId !== null}
                  data-testid={`add-instance-assembly-${sub.id}`}
                  onClick={() => onAddAssembly(sub)}
                />
              ))}
            </div>
          </PanelSection>
        ) : null}
        <div>
          {error ? (
            <p
              role="alert"
              className="px-3 pb-2 pt-2 font-body text-xs text-flag"
              data-testid="add-instance-submit-error"
            >
              {error}
            </p>
          ) : null}
          <div>
            <PanelActionCell
              label="Done"
              caption="Close the picker"
              data-testid="add-instance-done"
              onClick={onClose}
            />
          </div>
        </div>
      </Panel>
    </div>
  );
}
