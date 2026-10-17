/**
 * Whether the part's Cut list panel is open (CUT-LIST). A panel, not a
 * command: the Inspect group's Cut list tool toggles it, as Parameters is.
 */
import { useCallback, useState } from "react";

export interface CutListToggle {
  open: boolean;
  toggle: () => void;
  close: () => void;
}

export function useCutListToggle(): CutListToggle {
  const [open, setOpen] = useState(false);
  const toggle = useCallback(() => setOpen((value) => !value), []);
  const close = useCallback(() => setOpen(false), []);
  return { open, toggle, close };
}
