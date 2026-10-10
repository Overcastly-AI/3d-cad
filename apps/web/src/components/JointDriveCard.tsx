/**
 * Move on a jointed part. The part cannot go anywhere its joint does not let
 * it, so Move offers the joint's own handle (a ring for a revolute, an arrow
 * for a slider) instead of the free triad, and this card says which joint is
 * being driven, where it is, and where it stops. The value is typed in the
 * joint dialog ("Edit joint"); Done or Esc puts the handle away.
 */
import { formatLength, Panel, PanelActionCell } from "@loft/design";

import { formatDegrees } from "../assembly/joints";
import type { DriveTarget } from "../assembly/useJointDrive";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { EditorCard } from "./EditorCard";

export interface JointDriveCardProps {
  target: DriveTarget;
  /** The value under the pointer mid-drag, else null. */
  dragValue: number | null;
  committing: boolean;
  onEdit: () => void;
  onDone: () => void;
}

export function JointDriveCard({
  target,
  dragValue,
  committing,
  onEdit,
  onDone,
}: JointDriveCardProps) {
  const unit = useDocumentLengthUnit();
  const show = (n: number) =>
    target.motion === "revolute" ? formatDegrees(n) : formatLength(n, unit);
  const value = dragValue ?? target.value;
  const [hasMin, hasMax] = target.limited;
  const range =
    hasMin || hasMax
      ? `Stops at ${hasMin ? show(target.min) : "no minimum"} and ${
          hasMax ? show(target.max) : "no maximum"
        }`
      : "No limits";
  return (
    <EditorCard
      seat="right"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          onDone();
        }
      }}
      footer={
        <div className="grid grid-cols-2 divide-x divide-hairline border border-t-0 border-hairline bg-anvil">
          <PanelActionCell
            label="Edit joint"
            data-testid="joint-drive-edit"
            onClick={onEdit}
          />
          <PanelActionCell
            label="Done"
            caption="Esc"
            data-testid="joint-drive-done"
            onClick={onDone}
          />
        </div>
      }
    >
      <Panel aria-label={`Drive ${target.label}`} data-testid="joint-drive">
        <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Drive
          <span className="ml-2 normal-case tracking-normal text-mist">
            {target.label}
          </span>
        </h2>
        <p
          className="px-3 font-data text-lg tabular-nums text-brass"
          data-testid="joint-drive-value"
          aria-live="polite"
        >
          {show(value)}
          {committing ? (
            <span className="ml-2 font-body text-xs text-gauge">Solving…</span>
          ) : null}
        </p>
        <p className="px-3 pb-3 pt-1 font-body text-xs text-gauge">
          {target.motion === "revolute"
            ? "Drag the ring or the part to turn it about the joint axis."
            : "Drag the arrow or the part to slide it along the joint axis."}{" "}
          {range}.
        </p>
      </Panel>
    </EditorCard>
  );
}
