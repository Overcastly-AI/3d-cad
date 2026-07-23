/**
 * The mirror editor — the pattern editor's reflective twin, in the same
 * title-block seat top-left of the viewport (you author one feature at a time).
 * A mirror reflects the WHOLE current body about a plane and unions the
 * reflection back in, so its one authoring choice is that plane. v1 needs no
 * face pick and no point pick — just the plane.
 *
 * The plane is the EXACT `GeomRef` union a sketch's plane / the section author
 * use — a `DatumPlaneRef` (an XY / XZ / YZ origin plane) or a `FeatureRef` to a
 * datum FEATURE in the tree — so it REUSES the sketch plane picker's vocabulary
 * verbatim: the three origin datums, then any reusable in-tree datums (the ONE
 * derivation {@link resolveDatumPlaneOptions} feeds every plane picker). No
 * parallel plane taxonomy is introduced (CLAUDE.md DRY rule).
 *
 * Keyboard-first: Enter commits, Escape cancels — the sketcher's dimension
 * grammar; the origin datum buttons take focus first so the picker is reachable
 * without the mouse.
 */
import {
  DatumIcon,
  Panel,
  PanelActionCell,
  ToolButton,
  ToolGroup,
} from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import { useCommandBridge } from "../features/commandActions";
import type { MirrorParams } from "../api/parts";
import {
  buildMirrorParams,
  type MirrorForm,
  mirrorPlaneChoices,
  planeRefKey,
} from "../features/mirror";
import {
  DATUM_PLANES,
  describePlane,
  type DatumPlaneOption,
} from "../sketch/plane";

export interface MirrorEditorProps {
  mode: "create" | "edit";
  /** The seed form (new-mirror default, or an existing mirror's plane). */
  initial: MirrorForm;
  /** Reusable datum planes already in the part's tree (FeatureRefs). */
  datumPlanes: readonly DatumPlaneOption[];
  /** Commit the built params (documents/geometry handle the rest). */
  onSubmit: (params: MirrorParams) => void;
  onCancel: () => void;
  /** True while the create/update round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
}

export function MirrorEditor({
  mode,
  initial,
  datumPlanes,
  onSubmit,
  onCancel,
  saving,
  error,
}: MirrorEditorProps) {
  const choices = mirrorPlaneChoices(datumPlanes);
  // The seed selection key: the persisted plane (edit) or the first origin (new).
  // Derived from the ref alone (not the datum list), so re-seeding on a retarget
  // never fights an added/removed datum; a seed key whose datum is gone falls
  // back to the first choice at render below.
  const seedKey =
    initial.plane === null ? "origin:XY" : planeRefKey(initial.plane);
  const [selectedKey, setSelectedKey] = useState<string>(seedKey);
  // Re-seed when the editor is retargeted at a different feature (new `initial`).
  useEffect(() => setSelectedKey(seedKey), [seedKey]);

  const selected =
    choices.find((c) => c.key === selectedKey) ?? choices[0] ?? null;

  const submit = useCallback(() => {
    if (selected === null) return;
    onSubmit(buildMirrorParams(selected.spec));
  }, [selected, onSubmit]);

  const canSubmit = selected !== null && !saving;
  useCommandBridge(submit, canSubmit);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        if (event.target instanceof HTMLButtonElement) return;
        event.preventDefault();
        if (canSubmit) submit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
      }
    },
    [canSubmit, submit, onCancel],
  );

  return (
    <div
      className="absolute left-editor top-3 w-editor max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Mirror" data-testid="mirror-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New mirror" : "Edit mirror"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            {/* Mirror plane — the sketch plane picker's vocabulary: the three
                origin datums, then any reusable in-tree datums (FeatureRefs). */}
            <div className="flex flex-col gap-1.5">
              <span className="font-display text-2xs uppercase tracking-[0.16em] text-gauge">
                Mirror plane
              </span>
              <div className="flex flex-wrap items-stretch gap-1">
                {DATUM_PLANES.map((name) => (
                  <ToolButton
                    key={name}
                    icon={
                      <span className="font-display text-2xs tracking-[0.08em]">
                        {name}
                      </span>
                    }
                    label={`${name} plane`}
                    showLabel={false}
                    active={selectedKey === `origin:${name}`}
                    data-testid={`mirror-plane-${name}`}
                    aria-label={`Mirror about the ${name} plane`}
                    onClick={() => setSelectedKey(`origin:${name}`)}
                  />
                ))}
              </div>
              {datumPlanes.length > 0 ? (
                <ToolGroup
                  eyebrow="In tree"
                  aria-label="Datum planes in the part"
                >
                  {datumPlanes.map((datum) => (
                    <ToolButton
                      key={datum.id}
                      icon={<DatumIcon />}
                      label={datum.name}
                      showLabel
                      active={selectedKey === `datum:${datum.id}`}
                      data-testid={`mirror-plane-datum-${datum.id}`}
                      aria-label={`Mirror about ${datum.name}`}
                      onClick={() => setSelectedKey(`datum:${datum.id}`)}
                    />
                  ))}
                </ToolGroup>
              ) : null}
            </div>

            {/* A live readout of the chosen reflection. */}
            <p className="font-body text-xs text-gauge">
              Reflects the whole body about{" "}
              <span
                className="font-data text-mist"
                data-testid="mirror-readout"
              >
                {selected ? describePlane(selected.spec) : "—"}
              </span>{" "}
              and joins the reflection to it.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-hairline">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="mirror-cancel"
            disabled={saving}
            onClick={onCancel}
          />
          <PanelActionCell
            label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
            caption="Enter"
            data-testid="mirror-submit"
            aria-busy={saving}
            disabled={!canSubmit}
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="mirror-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
