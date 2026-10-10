/**
 * Driving a joint by hand: drag a jointed part (or use Move on it) and it
 * turns about, or runs along, its joint's axis and nowhere else.
 *
 * The axis comes from the solve (`joint_states[].axis_world`, A's Z) through
 * the anchor origin's point on A at A's solved pose. The preview is LOCAL: the
 * part is redrawn turned / slid from its solved pose, no request is made while
 * the pointer moves, and the drag stops at the joint's limits. Release sends
 * ONE write, which the documents service records as one undo step: a value
 * `PATCH` with both axes (JOINT-VALUE-MERGE) for a turn or a slide along the
 * axis, or, for a planar joint's in-plane slide (which has no value), the
 * part's placement, whose in-plane position the solver keeps. The dragged
 * pose is held until the re-solve is drawn, as Move does.
 *
 * One scheme for every motion (`driveModeFor`): drag turns, Shift+drag
 * slides. A ball joint has no drag here: Move's free triad turns it, and the
 * solver keeps a ball's authored orientation.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  type EvaluateAssemblyResult,
  type InstancePlacementResult,
  type InstanceResponse,
  type JointMate,
  type JointState,
  type MateResponse,
  updateInstance,
  updateMate,
} from "../api/assemblies";
import {
  type DrivableMotion,
  type JointAxis,
  placementAfterDrive,
  placementAfterShift,
  worldPoint,
} from "./jointDrag";
import {
  driveLimits,
  driveValue,
  isJoint,
  jointLabels,
  originLocalPoint,
  rotates,
  slides,
} from "./joints";
import type { Placement, Vec3 } from "./placement";

/** One driveable axis of a joint: where it is and where it stops. */
export interface DriveAxis {
  /** The joint's value now (degrees or mm). */
  value: number;
  min: number;
  max: number;
  /** Which of min / max is a limit the user set (else the wire's bound). */
  limited: [boolean, boolean];
}

/** A joint a part can be dragged along. */
export interface DriveTarget {
  mateId: string;
  /** "Revolute 1". */
  label: string;
  /** The moving component (the joint's B side). */
  instanceId: string;
  motion: DrivableMotion;
  /** The stored joint: the other axis of a value PATCH comes from it. */
  joint: JointMate;
  axis: JointAxis;
  /** B's solved pose: the preview turns / slides it. */
  base: Placement;
  /** The turn about the axis, for a revolute, cylindrical or planar joint. */
  rot: DriveAxis | null;
  /** The slide along the axis, for a slider or cylindrical joint. */
  lin: DriveAxis | null;
  /** The solve has the joint on one of its limits. */
  atLimit: boolean;
}

/** One drag's reading: a value on an axis, or a planar joint's in-plane shift. */
export type DriveGesture =
  { mode: "turn" | "slide"; value: number } | { mode: "plane"; shift: Vec3 };

/** The axis a value gesture moves. */
export function gestureAxis(
  target: DriveTarget,
  mode: "turn" | "slide",
): DriveAxis | null {
  return mode === "turn" ? target.rot : target.lin;
}

/** The value gesture sits on a limit the user set. */
export function gestureAtLimit(
  target: DriveTarget,
  gesture: DriveGesture,
): boolean {
  if (gesture.mode === "plane") return target.atLimit;
  const axis = gestureAxis(target, gesture.mode);
  if (axis === null) return false;
  const [hasMin, hasMax] = axis.limited;
  return (
    (hasMin && Math.abs(gesture.value - axis.min) < 1e-9) ||
    (hasMax && Math.abs(gesture.value - axis.max) < 1e-9)
  );
}

/** Where the gesture puts the part, locally. */
export function placementForGesture(
  target: DriveTarget,
  gesture: DriveGesture,
): Placement {
  if (gesture.mode === "plane") {
    return placementAfterShift(target.base, gesture.shift);
  }
  const from = gestureAxis(target, gesture.mode)?.value ?? 0;
  return placementAfterDrive(
    target.base,
    gesture.mode,
    target.axis,
    gesture.value - from,
  );
}

/** The gesture moved nothing (a value back where it was, a zero shift). */
function unmoved(target: DriveTarget, gesture: DriveGesture): boolean {
  if (gesture.mode === "plane") {
    const s = gesture.shift;
    return Math.hypot(s.x, s.y, s.z) < 1e-9;
  }
  const axis = gestureAxis(target, gesture.mode);
  return axis === null || Math.abs(gesture.value - axis.value) < 1e-9;
}

/** What a joint's row publishes for QA: the solve, at full precision. */
export interface JointProbe {
  rotDeg: number | null;
  linMm: number | null;
  atLimit: boolean;
  axis: Vec3;
  /** Each origin's point in the world, from its instance's solved pose. */
  originA: Vec3;
  originB: Vec3;
}

export interface UseJointDriveOptions {
  assemblyId: string;
  docVersion: number;
  mates: readonly MateResponse[];
  instances: readonly InstanceResponse[];
  /** The solved poses, by instance id. */
  solvedById: ReadonlyMap<string, InstancePlacementResult>;
  /**
   * The evaluation on screen: its joint states and `solvedById` come from the
   * SAME result, so an axis and the pose it turns are always one solve's.
   */
  evaluation: EvaluateAssemblyResult | undefined;
  refreshGraph: () => Promise<unknown>;
  onError: (message: string) => void;
}

function driveAxis(
  joint: JointMate,
  kind: "rot" | "lin",
  solved: number | null | undefined,
): DriveAxis {
  const stored = kind === "rot" ? joint.value?.rot_deg : joint.value?.lin_mm;
  const [min, max] = driveLimits(joint, kind);
  const limits = joint.limits;
  const limited: [boolean, boolean] =
    kind === "rot"
      ? [limits?.rot_min_deg != null, limits?.rot_max_deg != null]
      : [limits?.lin_min_mm != null, limits?.lin_max_mm != null];
  return { value: stored ?? solved ?? 0, min, max, limited };
}

export function useJointDrive({
  assemblyId,
  docVersion,
  mates,
  instances,
  solvedById,
  evaluation,
  refreshGraph,
  onError,
}: UseJointDriveOptions) {
  const statesById = useMemo(
    () =>
      new Map<string, JointState>(
        (evaluation?.joint_states ?? []).map((s) => [s.mate_id, s]),
      ),
    [evaluation],
  );

  /** Every joint's solved readout, for the tree's probe attributes. */
  const probes = useMemo(() => {
    const out = new Map<string, JointProbe>();
    for (const row of mates) {
      if (!isJoint(row.mate)) continue;
      const state = statesById.get(row.id);
      const a = solvedById.get(row.mate.a.instance_id)?.placement;
      const b = solvedById.get(row.mate.b.instance_id)?.placement;
      if (state === undefined || a === undefined || b === undefined) continue;
      out.set(row.id, {
        rotDeg: state.rot_deg ?? null,
        linMm: state.lin_mm ?? null,
        atLimit: state.at_limit,
        axis: state.axis_world,
        originA: worldPoint(a, originLocalPoint(row.mate.a)),
        originB: worldPoint(b, originLocalPoint(row.mate.b)),
      });
    }
    return out;
  }, [mates, statesById, solvedById]);

  /** The joint `instanceId` can be dragged along, or null. */
  const targetFor = useCallback(
    (instanceId: string | null): DriveTarget | null => {
      if (instanceId === null) return null;
      const instance = instances.find((i) => i.id === instanceId);
      if (instance === undefined || instance.grounded) return null;
      const labels = jointLabels(mates);
      for (const row of mates) {
        const joint = row.mate;
        if (!isJoint(joint) || joint.b.instance_id !== instanceId) continue;
        const motion = joint.motion;
        if (motion === "rigid" || motion === "ball") continue;
        const state = statesById.get(row.id);
        const probe = probes.get(row.id);
        const base = solvedById.get(instanceId)?.placement;
        if (state === undefined || probe === undefined || !base) continue;
        return {
          mateId: row.id,
          label: labels.get(row.id) ?? "Joint",
          instanceId,
          motion,
          joint,
          axis: { point: probe.originA, dir: state.axis_world },
          base,
          rot: rotates(motion) ? driveAxis(joint, "rot", state.rot_deg) : null,
          lin: slides(motion) ? driveAxis(joint, "lin", state.lin_mm) : null,
          atLimit: state.at_limit,
        };
      }
      return null;
    },
    [instances, mates, statesById, probes, solvedById],
  );

  /** The live drag: its joint and where the pointer has it. */
  const [drag, setDrag] = useState<{
    target: DriveTarget;
    gesture: DriveGesture;
  } | null>(null);
  /** A released value held on screen until its re-solve lands. */
  const [held, setHeld] = useState<{
    instanceId: string;
    placement: Placement;
    version: number;
  } | null>(null);
  const [committing, setCommitting] = useState(false);
  /** Move on a jointed part: the joint's handle is up for this instance. */
  const [armed, setArmed] = useState<string | null>(null);

  const preview = useCallback((target: DriveTarget, gesture: DriveGesture) => {
    setDrag({ target, gesture });
  }, []);

  /** The pointer came up at `gesture` (null: it never moved). One write. */
  const release = useCallback(
    (target: DriveTarget, gesture: DriveGesture | null) => {
      setDrag(null);
      if (gesture === null || unmoved(target, gesture)) return;
      if (committing) return;
      const placement = placementForGesture(target, gesture);
      setCommitting(true);
      setHeld({ instanceId: target.instanceId, placement, version: Infinity });
      void (async () => {
        try {
          const reply =
            gesture.mode === "plane"
              ? await updateInstance(assemblyId, target.instanceId, {
                  expected_version: docVersion,
                  placement,
                })
              : await updateMate(assemblyId, target.mateId, {
                  expected_version: docVersion,
                  value: driveValue(
                    target.joint,
                    gesture.mode === "turn" ? "rot" : "lin",
                    gesture.value,
                  ),
                });
          setHeld({
            instanceId: target.instanceId,
            placement,
            version: reply.doc_version,
          });
          await refreshGraph();
        } catch (error) {
          setHeld(null);
          onError(
            error instanceof Error
              ? error.message
              : `${target.label} could not be driven.`,
          );
        } finally {
          setCommitting(false);
        }
      })();
    },
    [committing, assemblyId, docVersion, refreshGraph, onError],
  );

  const overrideFor = useCallback(
    (instanceId: string): Placement | null => {
      if (drag !== null && drag.target.instanceId === instanceId) {
        return placementForGesture(drag.target, drag.gesture);
      }
      if (held !== null && held.instanceId === instanceId) {
        return held.placement;
      }
      return null;
    },
    [drag, held],
  );

  const heldVersion = held?.version ?? null;
  const releaseHeld = useCallback(() => setHeld(null), []);

  return {
    probes,
    targetFor,
    /** Where the pointer has the joint while dragging, or null. */
    gesture: drag?.gesture ?? null,
    dragging: drag !== null,
    committing,
    busy: committing || held !== null,
    heldVersion,
    releaseHeld,
    armed,
    arm: setArmed,
    preview,
    release,
    overrideFor,
  };
}

export type JointDriveApi = ReturnType<typeof useJointDrive>;

/** Drop the held drag pose once the solve for its version is drawn. */
export function useReleaseDriveWhenSolved(
  drive: JointDriveApi,
  docVersion: number,
  solveSettled: boolean,
): void {
  const { heldVersion, committing, releaseHeld } = drive;
  useEffect(() => {
    if (heldVersion === null || committing) return;
    if (docVersion >= heldVersion && solveSettled) releaseHeld();
  }, [heldVersion, committing, docVersion, solveSettled, releaseHeld]);
}
