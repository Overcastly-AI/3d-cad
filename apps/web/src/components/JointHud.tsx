/**
 * The joint surfaces in the viewport HUD: the Joint dialog while one is being
 * made or edited, else the drive card while Move holds a jointed part. One
 * seat, so the two never stack.
 */
import type { InstanceResponse, MateResponse } from "../api/assemblies";
import { componentName, type NestedPart } from "../assembly/subAssemblies";
import type { JointDialogApi } from "../assembly/useJointDialog";
import type { DriveTarget, JointDriveApi } from "../assembly/useJointDrive";
import { JointDialog } from "./JointDialog";
import { JointDriveCard } from "./JointDriveCard";

export interface JointHudProps {
  dialog: JointDialogApi;
  drive: JointDriveApi;
  /** The joint the armed part is driven along, or null. */
  driveTarget: DriveTarget | null;
  instances: readonly InstanceResponse[];
  mates: readonly MateResponse[];
  /** Parts inside sub-assemblies, so a joint origin on one is named. */
  nested?: ReadonlyMap<string, NestedPart>;
}

export function JointHud({
  dialog,
  drive,
  driveTarget,
  instances,
  mates,
  nested,
}: JointHudProps) {
  if (dialog.open) {
    return (
      <JointDialog
        instanceName={(id) =>
          componentName(instances, nested, id) ?? "Component"
        }
        previewing={dialog.previewing}
        throughEachOther={dialog.throughEachOther}
        previewProblem={dialog.previewProblem}
        onSubmit={dialog.submit}
        onCancel={dialog.cancel}
      />
    );
  }
  if (drive.armed === null || driveTarget === null) return null;
  return (
    <JointDriveCard
      target={driveTarget}
      gesture={drive.gesture}
      committing={drive.committing}
      onDone={() => drive.arm(null)}
      onEdit={() => {
        const row = mates.find((m) => m.id === driveTarget.mateId);
        if (row !== undefined) dialog.openEdit(row);
      }}
    />
  );
}
