/**
 * The workspace glue between a joint drive (`useJointDrive`) and the scene:
 * which joint the selected (or Move-armed) part can be dragged along, the
 * body press `AssemblyScene` offers first, and what a release means for the
 * selection. A body press that never moved is a click and selects, exactly as
 * a press on any other part does; a press that moved selects the dragged part
 * and sends its one PATCH.
 */
import type { ThreeEvent } from "@react-three/fiber";
import { useCallback, useEffect, useRef } from "react";

import type { JointPress } from "../viewport/JointDragLayer";
import type { DriveTarget, JointDriveApi } from "./useJointDrive";

export interface UseJointHandlesOptions {
  drive: JointDriveApi;
  /** Nothing else owns the pointer: no tool armed, no dialog, no Move. */
  idle: boolean;
  selectedInstanceId: string | null;
  /** Toggle-select (the click a press without a drag was). */
  selectInstance: (instanceId: string) => void;
  /** Select outright (the part just dragged). */
  select: (instanceId: string) => void;
}

export function useJointHandles({
  drive,
  idle,
  selectedInstanceId,
  selectInstance,
  select,
}: UseJointHandlesOptions) {
  const { targetFor, arm, armed, release } = drive;
  const pressRef = useRef<JointPress | null>(null);

  const target = idle ? targetFor(armed ?? selectedInstanceId) : null;

  const onBodyPress = useCallback(
    (instanceId: string, event: ThreeEvent<PointerEvent>): boolean => {
      const pressed = idle ? targetFor(instanceId) : null;
      if (pressed === null || pressRef.current === null) return false;
      pressRef.current(event, pressed, true);
      return true;
    },
    [idle, targetFor],
  );

  const onRelease = useCallback(
    (dragged: DriveTarget, value: number | null, fromBody: boolean) => {
      if (value === null && fromBody) selectInstance(dragged.instanceId);
      else if (value !== null) select(dragged.instanceId);
      release(dragged, value);
    },
    [release, selectInstance, select],
  );

  // Move's joint handle goes away when a tool arms or the part loses its joint.
  useEffect(() => {
    if (armed !== null && (!idle || targetFor(armed) === null)) arm(null);
  }, [armed, idle, targetFor, arm]);

  return { target, pressRef, onBodyPress, onRelease };
}
