/**
 * EDIT IN PLACE in the assembly workspace (ASM-A3-IN-CONTEXT).
 *
 * - {@link useEditInPlace}: the component menu's "Edit in place", which opens
 *   the part's workspace in place in this assembly (the other components drawn
 *   around it, Project offering their edges).
 * - {@link InContextIssues}: every in-context reference this evaluation could
 *   not resolve, named by the part that holds it and said in plain words. A
 *   reference to a removed or replaced component is an error here, never a
 *   silent re-attachment; the part keeps its last geometry.
 */
import { useNavigate } from "@tanstack/react-router";
import { useCallback } from "react";

import type {
  EvaluateAssemblyResult,
  InstanceResponse,
} from "../api/assemblies";
import { IN_CONTEXT_REASON_TEXT } from "./inContext";

/** Open a part of this assembly in place, at one of its occurrences. */
export function useEditInPlace(
  assemblyId: string,
): (partId: string, occurrenceId: string) => void {
  const navigate = useNavigate();
  return useCallback(
    (partId, occurrenceId) =>
      void navigate({
        to: "/parts/$partId",
        params: { partId },
        search: { context: assemblyId, occurrence: occurrenceId },
      }),
    [navigate, assemblyId],
  );
}

export function InContextIssues({
  evaluation,
  instances,
}: {
  evaluation: EvaluateAssemblyResult | undefined;
  instances: readonly InstanceResponse[];
}) {
  const statuses = evaluation?.in_context ?? [];
  if (statuses.length === 0) return null;
  const errors = statuses.filter((status) => status.state === "error");
  const partName = (partId: string) =>
    instances.find((instance) => instance.ref_document_id === partId)?.name ??
    "A part";
  return (
    <div
      role={errors.length > 0 ? "alert" : undefined}
      data-testid="assembly-in-context"
      className="pointer-events-none absolute bottom-3 left-1/2 z-10 flex max-w-[min(36rem,calc(100%-2rem))] -translate-x-1/2 flex-col gap-1"
    >
      {errors.map((status) => (
        <p
          key={`${status.feature_id}/${status.entity_id}`}
          data-testid={`assembly-in-context-error-${status.entity_id}`}
          data-reason={status.reason ?? ""}
          className="rounded-sm border border-flag/60 bg-anvil/95 px-3 py-2 font-body text-xs text-flag"
        >
          <span className="font-display text-2xs uppercase tracking-[0.18em]">
            In-context reference
          </span>{" "}
          <span className="font-medium">{partName(status.part_id)}:</span>{" "}
          {status.reason
            ? IN_CONTEXT_REASON_TEXT[status.reason]
            : (status.message ?? "")}
        </p>
      ))}
      {statuses.map((status) => {
        const curve = status.resolved;
        return (
          // A raster-independent stamp of each link, for QA.
          <span
            key={`stamp-${status.feature_id}/${status.entity_id}`}
            hidden
            data-testid={`assembly-in-context-link-${status.entity_id}`}
            data-state={status.state}
            data-centre={
              curve?.kind === "circle"
                ? `${curve.center.x},${curve.center.y},${curve.center.z}`
                : ""
            }
          />
        );
      })}
    </div>
  );
}
