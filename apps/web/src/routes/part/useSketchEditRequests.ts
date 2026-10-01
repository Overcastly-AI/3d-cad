/**
 * The sketcher's network hops (trim/extend, offset, mirror, corner) and the
 * workspace teardown of sketch + measure.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useEffect, useRef } from "react";

import {
  cornerSketch,
  editSketch,
  mirrorSketch,
  offsetSketch,
  SketchEditError,
} from "../../api/sketchEdit";
import { useMeasureStore } from "../../measure/store";
import { useSketchStore } from "../../sketch/store";
import type { PartDocument } from "./usePartDocument";

type SketchEditRequestsParams = Pick<
  PartDocument,
  "mode" | "edit" | "offset" | "mirrorRequest" | "cornerRequest"
>;

export function useSketchEditRequests({
  mode,
  edit,
  offset,
  mirrorRequest,
  cornerRequest,
}: SketchEditRequestsParams) {
  // Trim/extend: the scene arms an edit on a target click; this effect owns
  // the one network hop (the store stays side-effect-free). On success the
  // result's entity set is adopted and constraints are reconciled in the store
  // (dangling refs dropped) — the revision bump then re-solves through the
  // live loop for a bound sketch; an unbound buffer just re-renders locally.
  // The nonce guards against a double fire (React strict mode / re-render).
  const editNonceRef = useRef(0);
  useEffect(() => {
    if (edit === null || edit.nonce === editNonceRef.current) return;
    editNonceRef.current = edit.nonce;
    const { op, target, pick } = edit;
    void (async () => {
      try {
        const result = await editSketch(op, {
          entities: useSketchStore.getState().entities,
          target,
          pick,
        });
        const store = useSketchStore.getState();
        if (store.mode === "draw") store.applyEditResult(op, result.entities);
      } catch (error) {
        useSketchStore
          .getState()
          .failEdit(
            error instanceof SketchEditError
              ? error.message
              : "The edit could not be applied — try a different spot.",
          );
      }
    })();
  }, [edit]);

  // Offset: the scene arms a signed-distance offset once the inline editor
  // confirms; this effect owns the one network hop and APPENDS the returned
  // offset entity/entities (source unchanged — offset adds, never rewrites).
  // The revision bump then re-solves through the live loop for a bound sketch;
  // an unbound buffer just re-renders locally. The nonce guards a double fire.
  const offsetNonceRef = useRef(0);
  useEffect(() => {
    if (offset === null || offset.nonce === offsetNonceRef.current) return;
    offsetNonceRef.current = offset.nonce;
    const { target, distance } = offset;
    void (async () => {
      try {
        const result = await offsetSketch({
          entities: useSketchStore.getState().entities,
          target,
          distance,
        });
        const store = useSketchStore.getState();
        if (store.mode === "draw") store.applyOffsetResult(result.entities);
      } catch (error) {
        useSketchStore
          .getState()
          .failOffset(
            error instanceof SketchEditError
              ? error.message
              : "The offset could not be applied — try a different distance.",
          );
      }
    })();
  }, [offset]);

  // Mirror: the axis pick arms a mirror request; this effect owns the one
  // network hop and APPENDS the reflected copies (sources unchanged — mirror
  // adds, never rewrites). Like offset, the revision bump then re-solves a
  // bound sketch; an unbound buffer just re-renders. The nonce guards a double
  // fire (React strict mode / re-render).
  const mirrorNonceRef = useRef(0);
  useEffect(() => {
    if (
      mirrorRequest === null ||
      mirrorRequest.nonce === mirrorNonceRef.current
    )
      return;
    mirrorNonceRef.current = mirrorRequest.nonce;
    const { targets, axis } = mirrorRequest;
    void (async () => {
      try {
        const result = await mirrorSketch({
          entities: useSketchStore.getState().entities,
          targets,
          axis,
        });
        const store = useSketchStore.getState();
        if (store.mode === "draw") store.applyMirrorResult(result.entities);
      } catch (error) {
        useSketchStore
          .getState()
          .failMirror(
            error instanceof SketchEditError
              ? error.message
              : "The mirror could not be applied — try a different axis.",
          );
      }
    })();
  }, [mirrorRequest]);

  // Fillet/Chamfer: the value editor arms a corner request; this effect owns
  // the one network hop and SWAPS the whole rewritten set in (the two source
  // lines trimmed in place, ids preserved, plus the appended bridge) — like
  // trim/extend, unlike the additive offset/mirror. The store reconciles
  // constraints; the revision bump then re-solves through the live loop. The
  // nonce guards a double fire (React strict mode / re-render).
  const cornerNonceRef = useRef(0);
  useEffect(() => {
    if (
      cornerRequest === null ||
      cornerRequest.nonce === cornerNonceRef.current
    )
      return;
    cornerNonceRef.current = cornerRequest.nonce;
    const { op, a, b, value } = cornerRequest;
    void (async () => {
      try {
        const result = await cornerSketch(op, {
          entities: useSketchStore.getState().entities,
          a,
          b,
          value,
        });
        const store = useSketchStore.getState();
        if (store.mode === "draw") store.applyCornerResult(result.entities);
      } catch (error) {
        useSketchStore
          .getState()
          .failCorner(
            error instanceof SketchEditError
              ? error.message
              : "The corner could not be broken — try a smaller value.",
          );
      }
    })();
  }, [cornerRequest]);

  // Leaving the workspace always leaves sketch mode.
  useEffect(() => () => useSketchStore.getState().exit(), []);

  // Sketch mode owns the viewport — measurement never overlaps it.
  useEffect(() => {
    if (mode !== "off") useMeasureStore.getState().deactivate();
  }, [mode]);
  // Leaving the workspace tears the measurement overlay down.
  useEffect(() => () => useMeasureStore.getState().deactivate(), []);
}

export type SketchEditRequests = ReturnType<typeof useSketchEditRequests>;
