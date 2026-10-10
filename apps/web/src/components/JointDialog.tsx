/**
 * The Joint dialog — Fusion 360's, in Loft's title-block idiom.
 *
 * Top to bottom it follows Fusion's own order: the two origins it joins (the
 * reference header, pinned), then MOTION, then ALIGNMENT (Flip, Rotate 90°,
 * Offset, Angle), then the free axis's LIMITS and its drive VALUE, revealed
 * per motion. Every change re-solves the preview on the server, so B sits
 * where the joint will put it before anything is stored; OK sends one write,
 * Cancel drops it. Keyboard-first: Enter is OK, Esc is Cancel.
 *
 * Cylindrical, planar and ball are on the picker so the vocabulary is all
 * there, but disabled and labelled "coming soon": the solver does not take
 * them yet, and an enabled button for a joint that cannot solve would be a
 * promise the next click breaks.
 */
import {
  Button,
  NumberField,
  Panel,
  PanelActionCell,
  ReverseIcon,
} from "@loft/design";
import type { KeyboardEvent } from "react";

import { useJointDialogStore } from "../assembly/jointDialogStore";
import {
  JOINT_MOTIONS,
  type JointDraftField,
  parseJointDraft,
  visibleFields,
} from "../assembly/joints";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { EditorCard } from "./EditorCard";

export interface JointDialogProps {
  /** A component's display name, for the reference header. */
  instanceName: (instanceId: string) => string;
  /** The server-solved preview is in flight. */
  previewing: boolean;
  /** The preview drives one body through the other: show the Flip hint. */
  throughEachOther: boolean;
  /** Why the preview cannot place the joint, or null. */
  previewProblem: string | null;
  onSubmit: () => void;
  onCancel: () => void;
}

const ORIGIN_WORD = {
  face_centre: "Face centre",
  circle_centre: "Hole centre",
  edge_point: "Edge point",
} as const;

export function JointDialog({
  instanceName,
  previewing,
  throughEachOther,
  previewProblem,
  onSubmit,
  onCancel,
}: JointDialogProps) {
  const unit = useDocumentLengthUnit();
  const target = useJointDialogStore((s) => s.target);
  const draft = useJointDialogStore((s) => s.draft);
  const error = useJointDialogStore((s) => s.error);
  const submitting = useJointDialogStore((s) => s.submitting);
  const dispatch = useJointDialogStore((s) => s.dispatch);
  if (target === null) return null;

  const editing = target.mode === "edit";
  const parsed = parseJointDraft(draft, unit);
  const invalid = parsed.ok ? new Set<JointDraftField>() : parsed.invalid;
  const shown = visibleFields(draft.motion);
  const turning = shown.has("rotValue");
  const sliding = shown.has("linValue");
  const canCommit = parsed.ok && !submitting;

  const origins =
    target.mode === "create"
      ? [
          { side: "A", id: target.a.instanceId, kind: target.a.kind },
          { side: "B", id: target.b.instanceId, kind: target.b.kind },
        ]
      : [
          {
            side: "A",
            id: target.joint.a.instance_id,
            kind: target.joint.a.kind,
          },
          {
            side: "B",
            id: target.joint.b.instance_id,
            kind: target.joint.b.kind,
          },
        ];

  const field = (
    key: JointDraftField,
    label: string,
    cellUnit: string,
    placeholder?: string,
  ) => (
    <NumberField
      key={key}
      label={label}
      unit={cellUnit}
      placeholder={placeholder}
      data-testid={`joint-${key}`}
      value={draft[key]}
      error={invalid.has(key) ? "Not a number" : null}
      onChange={(event) =>
        dispatch({ type: "field", field: key, value: event.target.value })
      }
      onFocus={(event) => event.currentTarget.select()}
    />
  );

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (canCommit) onSubmit();
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      onCancel();
    }
  };

  return (
    <EditorCard
      seat="right"
      onKeyDown={onKeyDown}
      header={
        <div className="border border-b-0 border-hairline bg-anvil px-3 pb-2 pt-3">
          <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {editing ? `Edit ${target.label}` : "Joint"}
          </h2>
          <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-2 font-data text-2xs text-mist">
            {origins.map((o) => (
              <div key={o.side} className="contents">
                <dt className="text-brass">{o.side}</dt>
                <dd className="truncate" data-testid={`joint-origin-${o.side}`}>
                  {ORIGIN_WORD[o.kind]} · {instanceName(o.id)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      }
      footer={
        <div className="border border-t-0 border-hairline bg-anvil">
          {error ? (
            <p
              role="alert"
              data-testid="joint-error"
              className="border-b border-hairline px-3 py-2 font-body text-xs text-flag"
            >
              {error}
            </p>
          ) : null}
          <div className="grid grid-cols-2 divide-x divide-hairline">
            <PanelActionCell
              label="Cancel"
              caption="Esc"
              data-testid="joint-cancel"
              disabled={submitting}
              onClick={onCancel}
            />
            <PanelActionCell
              label={submitting ? "Solving…" : "OK"}
              caption="Enter"
              data-testid="joint-ok"
              aria-busy={submitting}
              disabled={!canCommit}
              disabledReason={
                parsed.ok ? undefined : "Enter a number in each marked cell"
              }
              onClick={onSubmit}
            />
          </div>
        </div>
      }
    >
      <Panel
        aria-label={editing ? `Edit ${target.label}` : "Joint"}
        data-testid="joint-dialog"
        data-joint-mode={target.mode}
        data-previewing={previewing ? "true" : "false"}
      >
        <Section title="Motion">
          <div
            role="radiogroup"
            aria-label="Motion"
            className="grid grid-cols-3 gap-1"
          >
            {JOINT_MOTIONS.map((m) => {
              const checked = draft.motion === m.motion;
              // A joint's motion is fixed once stored (the edit has no motion
              // field): delete and add it again to change it.
              const locked = editing && !checked;
              const disabled = !m.supported || locked;
              return (
                <button
                  key={m.motion}
                  type="button"
                  role="radio"
                  aria-checked={checked}
                  disabled={disabled}
                  title={
                    !m.supported
                      ? `${m.label} joints are coming soon`
                      : locked
                        ? "Delete and add the joint again to change its motion"
                        : undefined
                  }
                  data-testid={`joint-motion-${m.motion}`}
                  onClick={() => dispatch({ type: "motion", motion: m.motion })}
                  className={[
                    "flex flex-col items-start rounded-sm border px-2 py-1 text-left",
                    "outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass",
                    checked
                      ? "border-brass text-brass"
                      : "border-etch text-mist hover:border-brass",
                    disabled
                      ? "cursor-not-allowed opacity-40 hover:border-etch"
                      : "",
                  ].join(" ")}
                >
                  <span className="font-display text-2xs uppercase tracking-[0.12em]">
                    {m.label}
                  </span>
                  {!m.supported ? (
                    <span className="font-body text-2xs text-gauge">
                      coming soon
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </Section>

        <Section title="Alignment">
          <div className="flex items-center gap-2">
            <Button
              variant={draft.flip ? "solid" : "ghost"}
              aria-pressed={draft.flip}
              data-testid="joint-flip"
              onClick={() => dispatch({ type: "flip" })}
            >
              <ReverseIcon size={14} /> Flip
            </Button>
            <Button
              variant="ghost"
              data-testid="joint-rotate"
              aria-label={`Rotate 90°, now ${draft.quarterTurns * 90}°`}
              onClick={() => dispatch({ type: "rotate" })}
            >
              Rotate 90°
              <span className="ml-1 font-data text-2xs tabular-nums text-gauge">
                {draft.quarterTurns * 90}°
              </span>
            </Button>
          </div>
          {throughEachOther ? (
            <p
              role="status"
              data-testid="joint-flip-hint"
              className="mt-1 font-body text-xs text-brass"
            >
              B passes through A here. Flip to seat it face to face.
            </p>
          ) : null}
          <div className="mt-2 grid grid-cols-2 gap-2">
            {field("offset", "Offset", unit)}
            {field("angle", "Angle", "°")}
          </div>
        </Section>

        {turning || sliding ? (
          <Section title="Limits">
            <div className="grid grid-cols-2 gap-2">
              {turning ? (
                <>
                  {field("rotMin", "Min", "°", "none")}
                  {field("rotMax", "Max", "°", "none")}
                </>
              ) : null}
              {sliding ? (
                <>
                  {field("linMin", "Min", unit, "none")}
                  {field("linMax", "Max", unit, "none")}
                </>
              ) : null}
            </div>
          </Section>
        ) : null}

        {turning || sliding ? (
          <Section title="Value">
            <div className="grid grid-cols-2 gap-2">
              {turning ? field("rotValue", "Angle", "°", "free") : null}
              {sliding ? field("linValue", "Distance", unit, "free") : null}
            </div>
            <p className="mt-1 font-body text-2xs text-gauge">
              Empty leaves it free to drag.
            </p>
          </Section>
        ) : null}

        {previewProblem ? (
          <p
            data-testid="joint-preview-problem"
            className="px-3 pb-3 font-body text-xs text-flag"
          >
            {previewProblem}
          </p>
        ) : null}
      </Panel>
    </EditorCard>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-b border-hairline px-3 py-2 last:border-b-0">
      <h3 className="pb-1.5 font-display text-2xs uppercase tracking-[0.16em] text-gauge">
        {title}
      </h3>
      {children}
    </section>
  );
}
