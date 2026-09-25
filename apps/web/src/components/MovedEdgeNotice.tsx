/**
 * "Edge moved" — the notice a feature carries when the kernel re-found one of
 * its picked edges only by adjacency (EDGE-RESOLVE-WARN-1). One component for
 * both places it is shown, the tree row and the feature's own editor, so the
 * two cannot say different things: the sentence and the action's name come
 * from `features/subshapeResolution`.
 *
 * It is a standing `Notice`, not an error. The feature BUILT, its status cell
 * still reads OK, and nothing is blocked: this asks the user to look. Flag ink
 * because it needs a decision only the user can make (is that the edge?), and
 * the action that answers it sits in the notice itself.
 */
import { Notice } from "@loft/design";

import {
  MOVED_EDGE_LABEL,
  type MovedEdgeWarning,
  REPICK_EDGES_ACTION,
} from "../features/subshapeResolution";

export interface MovedEdgeNoticeProps {
  warning: MovedEdgeWarning;
  /** Re-pick the moved edges (drops them and arms picking). */
  onRepick: () => void;
  /** Omit where dismissing makes no sense (the editor closes on its own). */
  onDismiss?: () => void;
  "data-testid"?: string;
  repickTestId?: string;
  dismissTestId?: string;
}

export function MovedEdgeNotice({
  warning,
  onRepick,
  onDismiss,
  "data-testid": testId,
  repickTestId,
  dismissTestId,
}: MovedEdgeNoticeProps) {
  return (
    <Notice
      role="status"
      label={MOVED_EDGE_LABEL}
      layout="stacked"
      data-testid={testId}
      action={{
        label: REPICK_EDGES_ACTION,
        onClick: onRepick,
        ...(repickTestId !== undefined ? { testId: repickTestId } : {}),
      }}
      {...(onDismiss !== undefined ? { onDismiss } : {})}
      {...(dismissTestId !== undefined ? { dismissTestId } : {})}
    >
      {warning.sentence}
    </Notice>
  );
}
