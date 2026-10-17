/**
 * The component tree's MIRRORS section (ASM-MIRROR-COMPONENT): one row per
 * component mirror, as SolidWorks lists a MirrorComponent feature and Fusion a
 * mirror as one entry. Each row names what it reflects (an opposite hand
 * marked) and says when the solve could not place it, or when a copy is not a
 * mirror image because its part is not symmetric. Double-click or Enter edits;
 * Remove deletes the mirror and its twins, leaving the seeds.
 */
import { PanelSection } from "@loft/design";

import type { InstanceResponse } from "../api/assemblies";
import type { MirrorResponse, MirrorState } from "../api/mirrors";
import {
  mirrorSeedNames,
  mirrorTitle,
  mirrorWarning,
} from "../assembly/mirrors";

export interface MirrorTreeSectionProps {
  mirrors: readonly MirrorResponse[];
  instances: readonly InstanceResponse[];
  /** Each mirror's state from the settled solve, by mirror id. */
  states: ReadonlyMap<string, MirrorState>;
  /** The solve is not settled: states are not claimed. */
  stale: boolean;
  busy: boolean;
  onEdit: (mirror: MirrorResponse) => void;
  onDelete: (mirror: MirrorResponse) => void;
}

export function MirrorTreeSection({
  mirrors,
  instances,
  states,
  stale,
  busy,
  onEdit,
  onDelete,
}: MirrorTreeSectionProps) {
  if (mirrors.length === 0) return null;
  return (
    <PanelSection eyebrow={`Mirrors · ${mirrors.length}`}>
      <ul className="py-1" data-testid="mirror-list">
        {mirrors.map((mirror, index) => {
          const title = mirrorTitle(mirrors, mirror);
          const state = stale ? undefined : states.get(mirror.id);
          const warning = mirrorWarning(instances, state);
          return (
            <li
              key={mirror.id}
              data-testid="mirror-row"
              data-mirror-id={mirror.id}
              data-mirror-placed={state?.placed ?? ""}
              data-mirror-warning={warning === null ? undefined : "true"}
              tabIndex={0}
              title={`Double-click to edit ${title}`}
              onDoubleClick={() => onEdit(mirror)}
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  event.target === event.currentTarget
                ) {
                  event.preventDefault();
                  onEdit(mirror);
                }
              }}
              className="flex cursor-default items-center gap-2 px-2 py-1 outline-none hover:bg-carbide focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass"
            >
              <span
                className={`flex h-5 shrink-0 items-center justify-center rounded-sm border px-1 font-data text-2xs tabular-nums ${
                  warning !== null
                    ? "border-flag text-flag"
                    : "border-etch text-gauge"
                }`}
              >
                M{index + 1}
              </span>
              <span className="min-w-0 grow">
                <span
                  className={`block font-body text-sm ${warning !== null ? "text-flag" : "text-mist"}`}
                >
                  {title}
                </span>
                <span className="block truncate font-data text-2xs text-gauge">
                  {mirrorSeedNames(instances, mirror.mirror)}
                </span>
                {warning !== null ? (
                  <span
                    className="block font-body text-2xs text-flag"
                    data-testid="mirror-warning"
                  >
                    {warning}
                  </span>
                ) : null}
              </span>
              <button
                type="button"
                onClick={() => onEdit(mirror)}
                disabled={busy}
                aria-label={`Edit ${title}`}
                data-testid={`mirror-edit-${mirror.id}`}
                className="shrink-0 rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50"
              >
                Edit
              </button>
              <button
                type="button"
                onClick={() => onDelete(mirror)}
                disabled={busy}
                aria-label={`Remove ${title}`}
                data-testid={`mirror-delete-${mirror.id}`}
                className="shrink-0 rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none hover:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50"
              >
                Remove
              </button>
            </li>
          );
        })}
      </ul>
    </PanelSection>
  );
}
