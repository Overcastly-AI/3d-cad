/**
 * Measurement (inspect mode): the overlay fetch and the measure call.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import {
  fetchEvaluationRequest,
  fetchPartOverlay,
  measureTargets,
} from "../../api/measure";
import { buildMeasureRequest } from "../../measure/geometry";
import { useMeasureStore } from "../../measure/store";
import type { PartDocument } from "./usePartDocument";
import type { PartBody } from "./usePartBody";

type MeasureSessionParams = Pick<
  PartDocument,
  "partId" | "tree" | "treeVersion"
> &
  Pick<PartBody, "meshGlbId">;

export function useMeasureSession({
  partId,
  tree,
  treeVersion,
  meshGlbId,
}: MeasureSessionParams) {
  // ---------------------------------------------------------------------
  // Measurement (inspect mode). The tool fetches the pickable overlay for the
  // current evaluated body, the user picks two vertices/edges, and the second
  // pick calls /measure for the exact nearest distance. State lives in the
  // shared measure store (the in-canvas overlay + the DOM readout both read
  // it); PartPage owns the two network effects and the mode plumbing.
  // ---------------------------------------------------------------------
  const measureActive = useMeasureStore((s) => s.active);
  const measurePicks = useMeasureStore((s) => s.picks);
  const measureResult = useMeasureStore((s) => s.result);
  const measureFailure = useMeasureStore((s) => s.measureError);
  const setMeasureOverlay = useMeasureStore((s) => s.setOverlay);
  const setMeasureOverlayError = useMeasureStore((s) => s.setOverlayError);
  const setMeasureResult = useMeasureStore((s) => s.setResult);
  const setMeasureFailure = useMeasureStore((s) => s.setMeasureError);

  // Both requests are built from the part's evaluation request, so a feature
  // whose formula no longer resolves builds nothing here either
  // (MEASURE-FROM-EVAL-REQUEST).
  const overlayQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () => fetchPartOverlay(partId),
    enabled: measureActive && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });

  useEffect(() => {
    if (measureActive && overlayQuery.data !== undefined) {
      setMeasureOverlay(overlayQuery.data);
    }
  }, [measureActive, overlayQuery.data, setMeasureOverlay]);

  useEffect(() => {
    if (measureActive && overlayQuery.error) {
      setMeasureOverlayError(
        overlayQuery.error instanceof Error
          ? overlayQuery.error.message
          : "The selection overlay could not be built.",
      );
    }
  }, [measureActive, overlayQuery.error, setMeasureOverlayError]);

  // The second pick resolves the measurement (once, per pair).
  const measureInFlight = useRef(false);
  useEffect(() => {
    if (!measureActive || measurePicks.length !== 2) return;
    if (measureResult !== null || measureFailure !== null) return;
    if (measureInFlight.current || tree.data === undefined) return;
    const [a, b] = measurePicks;
    if (a === undefined || b === undefined) return;
    measureInFlight.current = true;
    void (async () => {
      try {
        const request = buildMeasureRequest(
          a,
          b,
          await fetchEvaluationRequest(partId),
        );
        setMeasureResult(await measureTargets(request));
      } catch (error) {
        setMeasureFailure(
          error instanceof Error
            ? error.message
            : "The measurement could not be computed.",
        );
      } finally {
        measureInFlight.current = false;
      }
    })();
  }, [
    partId,
    measureActive,
    measurePicks,
    measureResult,
    measureFailure,
    tree.data,
    setMeasureResult,
    setMeasureFailure,
  ]);
  return { measureActive };
}

export type MeasureSession = ReturnType<typeof useMeasureSession>;
