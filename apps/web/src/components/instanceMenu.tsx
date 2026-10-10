/**
 * The component row's right-click menu (UI-W2), as data. Isolate is a VERB,
 * not an icon (infrequent, destructive to view state), so it lives here with
 * its accelerator rather than adding a third control to every row. The page
 * builds it on open, so each row reads the freshest state, and every item is a
 * wired action.
 */
import {
  CloseIcon,
  type ContextMenuSection,
  DuplicateIcon,
  EyeIcon,
  EyeOffIcon,
  FixedIcon,
  formatChord,
  IsolateIcon,
  MoveIcon,
} from "@loft/design";

import type { InstanceResponse } from "../api/assemblies";
import { CHORD_COPY_INSTANCE, KEY_MOVE_INSTANCE } from "../shortcuts/registry";

/** Why Move is unavailable for `instance`, or null when it can move. */
export function moveBlocker(instance: InstanceResponse | null): string | null {
  return instance === null
    ? "Select a component to move"
    : instance.grounded
      ? "Grounded components stay put. Unground it to move it."
      : null;
}

/** What the menu reads about the workspace when it opens. */
export interface InstanceMenuState {
  hidden: boolean;
  /** Isolate needs a second component to hide. */
  canIsolate: boolean;
  hiddenCount: number;
  moveBlocker: string | null;
  copyBlocker: string | null;
  /** A graph write is in flight (Ground / Remove wait for it). */
  busy: boolean;
}

/** The menu's verbs, already bound to the row's component. */
export interface InstanceMenuActions {
  toggleVisibility: () => void;
  isolate: () => void;
  showAll: () => void;
  move: () => void;
  copy: () => void;
  toggleGrounded: () => void;
  remove: () => void;
}

const WAITING = "Waiting for the current edit…";

export function instanceMenuSections(
  instance: InstanceResponse,
  state: InstanceMenuState,
  actions: InstanceMenuActions,
): ContextMenuSection[] {
  return [
    {
      key: "view",
      label: instance.name,
      items: [
        {
          key: "hide",
          label: state.hidden ? "Show" : "Hide",
          icon: state.hidden ? <EyeIcon /> : <EyeOffIcon />,
          shortcut: "V",
          onSelect: actions.toggleVisibility,
          "data-testid": "instance-ctx-hide",
        },
        {
          key: "isolate",
          label: "Isolate",
          icon: <IsolateIcon />,
          shortcut: "⇧V",
          disabled: !state.canIsolate,
          disabledReason: "Add a second part before isolating one",
          onSelect: actions.isolate,
          "data-testid": "instance-ctx-isolate",
        },
        {
          key: "show-all",
          label: "Show all",
          icon: <EyeIcon />,
          disabled: state.hiddenCount === 0,
          disabledReason: "Every component is already shown",
          onSelect: actions.showAll,
          "data-testid": "instance-ctx-show-all",
        },
      ],
    },
    {
      key: "edit",
      items: [
        {
          key: "move",
          label: "Move",
          icon: <MoveIcon />,
          shortcut: KEY_MOVE_INSTANCE.toUpperCase(),
          disabled: state.moveBlocker !== null,
          disabledReason: state.moveBlocker ?? undefined,
          onSelect: actions.move,
          "data-testid": "instance-ctx-move",
        },
        {
          key: "copy",
          label: "Copy",
          icon: <DuplicateIcon />,
          shortcut: formatChord(CHORD_COPY_INSTANCE),
          disabled: state.copyBlocker !== null,
          disabledReason: state.copyBlocker ?? undefined,
          onSelect: actions.copy,
          "data-testid": "instance-ctx-copy",
        },
        {
          key: "ground",
          label: instance.grounded ? "Unground" : "Ground",
          icon: <FixedIcon />,
          disabled: state.busy,
          disabledReason: WAITING,
          onSelect: actions.toggleGrounded,
          "data-testid": "instance-ctx-ground",
        },
        {
          key: "remove",
          label: "Remove",
          icon: <CloseIcon />,
          danger: true,
          disabled: state.busy,
          disabledReason: WAITING,
          onSelect: actions.remove,
          "data-testid": "instance-ctx-remove",
        },
      ],
    },
  ];
}
