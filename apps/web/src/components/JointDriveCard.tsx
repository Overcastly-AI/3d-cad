/**
 * Move on a jointed part. The part cannot go anywhere its joint does not let
 * it, so Move offers the joint's own handle (a ring to turn, an arrow to slide
 * along, a square to slide across) instead of the free triad, and this card
 * says which joint is being driven, where each of its axes is, where they
 * stop, and how to drag: a plain drag turns, Shift+drag slides. An "at limit"
 * stamp shows while the joint sits on a limit. The value is typed in the joint
 * dialog ("Edit joint"); Done or Esc puts the handle away.
 */
import { formatLength, Panel, PanelActionCell, Stamp } from "@loft/design";

import { formatDegrees } from "../assembly/joints";
import {
  type DriveAxis,
  type DriveGesture,
  type DriveTarget,
  gestureAtLimit,
} from "../assembly/useJointDrive";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { EditorCard } from "./EditorCard";

export interface JointDriveCardProps {
  target: DriveTarget;
  /** Where the pointer has the joint mid-drag, else null. */
  gesture: DriveGesture | null;
  committing: boolean;
  onEdit: () => void;
  onDone: () => void;
}

/** How to drag this joint (Fusion puts a handle per axis; so does the card). */
const HOW: Record<DriveTarget["motion"], string> = {
  revolute: "Drag the ring or the part to turn it about the joint axis.",
  slider: "Drag the arrow or the part to slide it along the joint axis.",
  cylindrical:
    "Drag to turn about the joint axis; Shift+drag (or the arrow) to slide along it.",
  planar:
    "Drag to turn about the plane's normal; Shift+drag (or the square) to slide in the plane.",
};

export function JointDriveCard({
  target,
  gesture,
  committing,
  onEdit,
  onDone,
}: JointDriveCardProps) {
  const unit = useDocumentLengthUnit();
  const deg = formatDegrees;
  const mm = (n: number) => formatLength(n, unit);
  const live = (mode: "turn" | "slide", axis: DriveAxis) =>
    gesture !== null && gesture.mode === mode ? gesture.value : axis.value;
  const range = (axis: DriveAxis, show: (n: number) => string) => {
    const [hasMin, hasMax] = axis.limited;
    return hasMin || hasMax
      ? `stops at ${hasMin ? show(axis.min) : "no minimum"} and ${
          hasMax ? show(axis.max) : "no maximum"
        }`
      : "no limits";
  };
  const readings = [
    target.rot === null
      ? null
      : {
          key: "rot",
          text: deg(live("turn", target.rot)),
          range: range(target.rot, deg),
        },
    target.lin === null
      ? null
      : {
          key: "lin",
          text: mm(live("slide", target.lin)),
          range: range(target.lin, mm),
        },
  ].filter((r) => r !== null);
  const atLimit =
    gesture === null ? target.atLimit : gestureAtLimit(target, gesture);
  const shifted =
    gesture?.mode === "plane"
      ? mm(Math.hypot(gesture.shift.x, gesture.shift.y, gesture.shift.z))
      : null;
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
        <h2 className="flex items-center px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Drive
          <span className="ml-2 normal-case tracking-normal text-mist">
            {target.label}
          </span>
          {atLimit ? (
            <Stamp
              tone="brass"
              className="ml-auto"
              data-testid="joint-drive-at-limit"
            >
              at limit
            </Stamp>
          ) : null}
        </h2>
        <p
          className="px-3 font-data text-lg tabular-nums text-brass"
          data-testid="joint-drive-value"
          aria-live="polite"
        >
          {readings.map((r) => r.text).join(" · ")}
          {shifted !== null ? (
            <span className="ml-2 font-data text-xs text-mist">
              slid {shifted}
            </span>
          ) : null}
          {committing ? (
            <span className="ml-2 font-body text-xs text-gauge">Solving…</span>
          ) : null}
        </p>
        <p className="px-3 pb-3 pt-1 font-body text-xs text-gauge">
          {HOW[target.motion]}{" "}
          {readings
            .map((r) =>
              readings.length > 1
                ? `${r.key === "rot" ? "Turn" : "Slide"} ${r.range}`
                : r.range.charAt(0).toUpperCase() + r.range.slice(1),
            )
            .join("; ")}
          .
        </p>
      </Panel>
    </EditorCard>
  );
}
