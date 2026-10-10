/**
 * Driving a joint by hand: drag a jointed part (or use Move on it) and it
 * turns about, or runs along, its joint's axis and nowhere else.
 *
 * The axis comes from the solve (`joint_states[].axis_world`, A's Z) through
 * the anchor origin's point on A at A's solved pose. The preview is LOCAL: the
 * part is redrawn turned / slid from its solved pose, no request is made while
 * the pointer moves, and the drag stops at the joint's limits. Release sends
 * ONE `PATCH` of the value, with both axes (JOINT-VALUE-MERGE), which the
 * documents service records as one undo step; the dragged pose is held until
 * the re-solve is drawn, as Move does.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  type EvaluateAssemblyResult,
  type InstanceResponse,
  type JointState,
  type MateResponse,
  type InstancePlacementResult,
  updateMate,
} from "../api/assemblies";
import { type JointAxis, placementAfterDrive, worldPoint } from "./jointDrag";
import {
  driveLimits,
  driveValue,
  isJoint,
  jointLabels,
  originLocalPoint,
  rotates,
} from "./joints";
import type { Placement, Vec3 } from "./placement";

/** A joint a part can be dragged along. */
export interface DriveTarget {
  mateId: string;
  /** "Revolute 1". */
  label: string;
  /** The moving component (the joint's B side). */
  instanceId: string;
  motion: "revolute" | "slider";
  axis: JointAxis;
  /** B's solved pose: the preview turns / slides it. */
  base: Placement;
  /** The joint's value now (degrees or mm). */
  value: number;
  min: number;
  max: number;
  /** Which of min / max is a limit the user set (else the wire's bound). */
  limited: [boolean, boolean];
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
        if (joint.motion !== "revolute" && joint.motion !== "slider") continue;
        const state = statesById.get(row.id);
        const probe = probes.get(row.id);
        const base = solvedById.get(instanceId)?.placement;
        if (state === undefined || probe === undefined || !base) continue;
        const turning = rotates(joint.motion);
        const value = turning
          ? (joint.value?.rot_deg ?? state.rot_deg ?? 0)
          : (joint.value?.lin_mm ?? state.lin_mm ?? 0);
        const [min, max] = driveLimits(joint);
        const limits = joint.limits;
        const limited: [boolean, boolean] = turning
          ? [limits?.rot_min_deg != null, limits?.rot_max_deg != null]
          : [limits?.lin_min_mm != null, limits?.lin_max_mm != null];
        return {
          limited,
          mateId: row.id,
          label: labels.get(row.id) ?? "Joint",
          instanceId,
          motion: joint.motion,
          axis: { point: probe.originA, dir: state.axis_world },
          base,
          value,
          min,
          max,
        };
      }
      return null;
    },
    [instances, mates, statesById, probes, solvedById],
  );

  /** The live drag: its joint and the value the pointer is at. */
  const [drag, setDrag] = useState<{
    target: DriveTarget;
    value: number;
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

  const preview = useCallback((target: DriveTarget, value: number) => {
    setDrag({ target, value });
  }, []);

  /** The pointer came up at `value` (null: it never moved). One PATCH. */
  const release = useCallback(
    (target: DriveTarget, value: number | null) => {
      setDrag(null);
      if (value === null || Math.abs(value - target.value) < 1e-9) return;
      if (committing) return;
      const placement = placementAfterDrive(
        target.base,
        target.motion,
        target.axis,
        value - target.value,
      );
      setCommitting(true);
      setHeld({ instanceId: target.instanceId, placement, version: Infinity });
      void (async () => {
        try {
          const reply = await updateMate(assemblyId, target.mateId, {
            expected_version: docVersion,
            value: driveValue(target.motion, value),
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
        return placementAfterDrive(
          drag.target.base,
          drag.target.motion,
          drag.target.axis,
          drag.value - drag.target.value,
        );
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
    /** The value under the pointer while dragging, or null. */
    dragValue: drag?.value ?? null,
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
