/**
 * Add-a-part panel — the v1 instance picker, shown in the viewport HUD (top-
 * left, the same anchor the part editors use). Lists the caller's parts as
 * ruled action cells; choosing one adds it to the assembly as a new instance
 * seeded at the origin (the user then grounds one and mates the rest). Kept
 * simple for v1: a flat register pick, not a thumbnail browser we can't render.
 */
import { Panel, PanelActionCell, PanelSection } from "@loft/design";
import { useQuery } from "@tanstack/react-query";

import { fetchParts, type PartResponse } from "../api/parts";

export interface AddInstancePanelProps {
  /** The id of the part currently being added (its cell shows busy), or null. */
  addingPartId: string | null;
  error: string | null;
  onAdd: (part: PartResponse) => void;
  onClose: () => void;
}

export function AddInstancePanel({
  addingPartId,
  error,
  onAdd,
  onClose,
}: AddInstancePanelProps) {
  const parts = useQuery({
    queryKey: ["parts"],
    queryFn: () => fetchParts(),
    staleTime: 30_000,
  });
  const list = parts.data ?? [];

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
                  disabled={addingPartId !== null}
                  data-testid={`add-instance-part-${part.id}`}
                  onClick={() => onAdd(part)}
                />
              ))}
            </div>
          )}
          {error ? (
            <p
              role="alert"
              className="px-3 pb-2 font-body text-xs text-flag"
              data-testid="add-instance-submit-error"
            >
              {error}
            </p>
          ) : null}
          <div className="border-t border-hairline">
            <PanelActionCell
              label="Done"
              caption="Close the picker"
              data-testid="add-instance-done"
              onClick={onClose}
            />
          </div>
        </PanelSection>
      </Panel>
    </div>
  );
}
