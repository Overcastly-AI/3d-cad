/**
 * The dimension author menu — a small popover that opens by a picked edge and
 * offers only the dimension types VALID for it (a circle → diameter / radius; a
 * straight edge → linear), so an impossible combo (a diameter on a line) is
 * never presented. Keyboard-first: the first choice is auto-focused, arrows and
 * Escape work, so a dimension can be authored without leaving the keyboard.
 * Chrome recedes — a quiet anvil card with hairline rules, the shop idiom.
 */
import { useEffect, useRef } from "react";

import { CircleIcon, DistanceIcon, RadiusIcon } from "@loft/design";

import type { ProjectedViewEdge } from "../api/drawings";

/** The dimension types v1 can author (angular deferred — BACKLOG). */
export type AuthorableType = "linear" | "diameter" | "radius";

export interface DimensionAuthorMenuProps {
  /** The picked edge's projected primitive — gates the offered types. */
  primitive: ProjectedViewEdge["primitive"];
  /** Popover anchor (viewport px). */
  x: number;
  y: number;
  busy: boolean;
  onChoose: (type: AuthorableType) => void;
  onClose: () => void;
}

interface Choice {
  type: AuthorableType;
  label: string;
  hint: string;
  icon: React.ReactNode;
}

/** The valid dimension types for a projected primitive (design §3.1). */
export function authorableTypes(
  primitive: ProjectedViewEdge["primitive"],
): AuthorableType[] {
  switch (primitive) {
    case "circle":
      return ["diameter", "radius"];
    case "arc":
      return ["radius"];
    case "line":
      return ["linear"];
    default:
      return [];
  }
}

const CHOICES: Record<AuthorableType, Choice> = {
  diameter: {
    type: "diameter",
    label: "Diameter",
    hint: "Ø",
    icon: <CircleIcon size={14} />,
  },
  radius: {
    type: "radius",
    label: "Radius",
    hint: "R",
    icon: <RadiusIcon size={14} />,
  },
  linear: {
    type: "linear",
    label: "Linear",
    hint: "↔",
    icon: <DistanceIcon size={14} />,
  },
};

export function DimensionAuthorMenu({
  primitive,
  x,
  y,
  busy,
  onChoose,
  onClose,
}: DimensionAuthorMenuProps) {
  const types = authorableTypes(primitive);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  // Auto-focus the first choice — the keyboard path authors without a mouse.
  useEffect(() => {
    itemRefs.current[0]?.focus();
  }, []);

  const focusAt = (index: number) => {
    const count = types.length;
    if (count === 0) return;
    itemRefs.current[((index % count) + count) % count]?.focus();
  };

  if (types.length === 0) return null;

  return (
    <div
      role="menu"
      aria-label="Add dimension"
      data-testid="dimension-author-menu"
      className="fixed z-50 min-w-[11rem] border border-hairline bg-anvil py-1 shadow-float"
      style={{ left: x + 8, top: y + 8 }}
      onKeyDown={(event) => {
        const current = itemRefs.current.findIndex(
          (el) => el === document.activeElement,
        );
        if (event.key === "ArrowDown") {
          event.preventDefault();
          focusAt(current + 1);
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          focusAt(current - 1);
        } else if (event.key === "Escape") {
          event.preventDefault();
          onClose();
        }
      }}
    >
      <div className="border-b border-hairline px-3 pb-1.5 pt-1 font-display text-2xs uppercase tracking-[0.16em] text-gauge">
        Add dimension
      </div>
      {types.map((type, index) => {
        const choice = CHOICES[type];
        return (
          <button
            key={type}
            ref={(el) => {
              itemRefs.current[index] = el;
            }}
            type="button"
            role="menuitem"
            disabled={busy}
            data-testid={`dimension-type-${type}`}
            className="flex w-full select-none items-center gap-2.5 px-3 py-1.5 text-left text-mist transition-colors duration-fast hover:bg-carbide focus-visible:bg-carbide focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40"
            onClick={() => onChoose(type)}
          >
            <span className="flex w-4 shrink-0 items-center justify-center text-gauge">
              {choice.icon}
            </span>
            <span className="grow font-body text-xs">{choice.label}</span>
            <span className="font-data text-2xs text-gauge">{choice.hint}</span>
          </button>
        );
      })}
    </div>
  );
}
