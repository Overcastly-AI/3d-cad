/**
 * The assembly tree as a title block: two ruled sections — COMPONENTS (the
 * instances, each a drafting balloon number + name + a grounded/anchor toggle)
 * and MATES (the joints, each named with the two balloons it relates). The
 * balloon number is the shared device that ties this DOM tree to the WebGL
 * viewport (same number floats on the instance). Selecting a component row
 * addresses it (brass left-rule) and highlights it in the viewport; the
 * grounded row carries the anchor mark. A mate that failed to resolve or
 * conflicts is flagged inline, read from the typed diagnosis — never a parsed
 * message.
 */
import { Panel, PanelSection } from "@loft/design";

import type {
  AssemblyGraphResponse,
  EvaluateAssemblyResult,
  InstanceResponse,
  MateResponse,
} from "../api/assemblies";
import { mateLabel, mateInstanceIds } from "../assembly/mates";

export interface AssemblyTreePanelProps {
  graph: AssemblyGraphResponse | undefined;
  graphError: Error | null;
  evaluation: EvaluateAssemblyResult | undefined;
  selectedInstanceId: string | null;
  onSelectInstance: (instanceId: string) => void;
  onToggleGrounded: (instance: InstanceResponse) => void;
  onDeleteInstance: (instance: InstanceResponse) => void;
  onDeleteMate: (mate: MateResponse) => void;
  busy: boolean;
}

export function AssemblyTreePanel({
  graph,
  graphError,
  evaluation,
  selectedInstanceId,
  onSelectInstance,
  onToggleGrounded,
  onDeleteInstance,
  onDeleteMate,
  busy,
}: AssemblyTreePanelProps) {
  const instances = graph?.instances ?? [];
  const mates = graph?.mates ?? [];
  // Balloon number = 1-based position in the (order_index-sorted) instance list.
  const balloonById = new Map(instances.map((i, index) => [i.id, index + 1]));
  const failedMateIds = new Set(
    (evaluation?.mate_errors ?? []).map((e) => e.mate_id),
  );
  const conflictingMateIds = new Set(
    evaluation?.diagnosis?.conflicting_mates ?? [],
  );

  return (
    <aside
      className="flex w-full shrink-0 flex-col gap-3 overflow-y-auto p-3 md:w-inspector"
      aria-label="Assembly tree"
      data-testid="assembly-tree"
    >
      <Panel>
        <PanelSection eyebrow="Components">
          {graphError ? (
            <p
              role="alert"
              data-testid="assembly-tree-error"
              className="px-3 py-3 font-body text-xs text-flag"
            >
              {graphError.message}
            </p>
          ) : instances.length === 0 ? (
            <p
              data-testid="assembly-empty"
              className="px-3 py-3 font-body text-xs text-gauge"
            >
              No parts yet. Add a part to start the assembly, then ground one to
              fix it to the bench.
            </p>
          ) : (
            <ul className="py-1" data-testid="instance-list">
              {instances.map((instance) => {
                const selected = selectedInstanceId === instance.id;
                const balloon = balloonById.get(instance.id) ?? 0;
                return (
                  <li
                    key={instance.id}
                    data-testid="instance-row"
                    data-instance-id={instance.id}
                    className={`flex items-center gap-2 border-l-2 px-2 py-1 ${
                      selected
                        ? "border-brass bg-carbide"
                        : "border-transparent"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => onSelectInstance(instance.id)}
                      data-testid={`instance-select-${instance.id}`}
                      className="flex min-w-0 grow items-center gap-2 text-left outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass"
                    >
                      <span
                        aria-hidden
                        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border font-display text-2xs tabular-nums ${
                          instance.grounded
                            ? "border-brass text-brass"
                            : "border-etch text-gauge"
                        }`}
                      >
                        {instance.grounded ? "⏚" : balloon}
                      </span>
                      <span className="truncate font-body text-sm text-mist">
                        {instance.name}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => onToggleGrounded(instance)}
                      disabled={busy}
                      aria-pressed={instance.grounded}
                      data-testid={`instance-ground-${instance.id}`}
                      className={`shrink-0 rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50 ${
                        instance.grounded
                          ? "text-brass"
                          : "text-gauge hover:text-mist"
                      }`}
                    >
                      {instance.grounded ? "Grounded" : "Ground"}
                    </button>
                    <button
                      type="button"
                      onClick={() => onDeleteInstance(instance)}
                      disabled={busy}
                      aria-label={`Remove ${instance.name}`}
                      data-testid={`instance-delete-${instance.id}`}
                      className="shrink-0 rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none hover:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50"
                    >
                      Remove
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </PanelSection>

        <PanelSection eyebrow="Mates">
          {mates.length === 0 ? (
            <p
              data-testid="mates-empty"
              className="px-3 py-3 font-body text-xs text-gauge"
            >
              No mates yet. Pick a face on each of two parts for Coincident, a
              hole edge on each for Concentric, or two parts for Lock.
            </p>
          ) : (
            <ul className="py-1" data-testid="mate-list">
              {mates.map((mate) => {
                const [a, b] = mateInstanceIds(mate.mate);
                const failed = failedMateIds.has(mate.id);
                const conflicting = conflictingMateIds.has(mate.id);
                const sick = failed || conflicting;
                return (
                  <li
                    key={mate.id}
                    data-testid="mate-row"
                    data-mate-id={mate.id}
                    className="flex items-center gap-2 px-2 py-1"
                  >
                    <span className="min-w-0 grow">
                      <span
                        className={`block font-body text-sm ${
                          sick ? "text-flag" : "text-mist"
                        }`}
                      >
                        {mateLabel(mate.mate)}
                      </span>
                      <span className="block font-data text-2xs tabular-nums text-gauge">
                        ①{balloonById.get(a) ?? "?"} · ②
                        {balloonById.get(b) ?? "?"}
                        {failed
                          ? " · unresolved"
                          : conflicting
                            ? " · conflict"
                            : ""}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => onDeleteMate(mate)}
                      disabled={busy}
                      aria-label={`Remove ${mateLabel(mate.mate)} mate`}
                      data-testid={`mate-delete-${mate.id}`}
                      className="shrink-0 rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none hover:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50"
                    >
                      Remove
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </PanelSection>
      </Panel>
    </aside>
  );
}
