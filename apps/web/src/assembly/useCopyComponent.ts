/**
 * Copy — Fusion's Copy/Paste of one component, kept to one gesture (ASM-COPY).
 *
 * ONE `POST /instances/{id}/copy` makes the copy: same part, same orientation,
 * +20 mm along X (the server's default nudge), never grounded, named with the
 * next free "<n>", recorded as ONE undo step. The page then selects the copy
 * and opens Move on it, which is Fusion's paste: the copy is placed at once
 * rather than left lying on top of its source.
 *
 * A grounded component can be copied; only "nothing selected" and "another
 * write is in flight" block the command.
 */
import { useCallback, useRef, useState } from "react";

import {
  copyInstance,
  type InstanceResponse,
  StaleAssemblyVersionError,
} from "../api/assemblies";

/** Why Copy is unavailable, or null when the selection can be copied. */
export function copyBlocker(
  instance: InstanceResponse | null,
  writing: boolean,
): string | null {
  if (instance === null) return "Select a component to copy";
  return writing ? "Waiting for the current edit…" : null;
}

export interface UseCopyComponentOptions {
  assemblyId: string;
  docVersion: number;
  refreshGraph: () => Promise<unknown>;
  onError: (message: string | null) => void;
}

export function useCopyComponent({
  assemblyId,
  docVersion,
  refreshGraph,
  onError,
}: UseCopyComponentOptions) {
  const [copying, setCopying] = useState(false);
  // A held chord repeats keydown faster than a render: the ref, not the
  // state, is what keeps it to one POST.
  const inFlight = useRef(false);

  /**
   * Copy `instanceId`; resolves to the new instance once the graph that holds
   * it has been refetched (so the caller can select it and open Move), or to
   * null when the write failed. A stale version resyncs the graph so the
   * retry is against what the user now sees.
   */
  const copy = useCallback(
    async (instanceId: string): Promise<InstanceResponse | null> => {
      if (inFlight.current) return null;
      inFlight.current = true;
      setCopying(true);
      onError(null);
      try {
        const reply = await copyInstance(assemblyId, instanceId, {
          expected_version: docVersion,
        });
        await refreshGraph();
        return reply.instance;
      } catch (error) {
        if (error instanceof StaleAssemblyVersionError) void refreshGraph();
        onError(
          error instanceof Error
            ? error.message
            : "The component could not be copied.",
        );
        return null;
      } finally {
        inFlight.current = false;
        setCopying(false);
      }
    },
    [assemblyId, docVersion, refreshGraph, onError],
  );

  return { copying, copy };
}
