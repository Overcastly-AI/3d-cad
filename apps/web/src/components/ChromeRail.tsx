/**
 * ChromeRail — the column an editor and its panel SHARE, so a feature editor
 * can never be opened on top of the model it is editing (FB-7, photographed).
 *
 * The founder's report was "editor panels cover the model and cannot be moved".
 * Both halves of that are true and only one is worth fixing: making the card
 * DRAGGABLE would hand the user a chore (move the panel, every time, or work
 * around it), which is the flow failure the mandate names — the tool proposes,
 * the user disposes. Docking removes the question. The editor takes the seat
 * the feature tree already occupies, one column, one width; the model keeps the
 * middle of the frame it was fitted into.
 *
 * WHY THE FIT DOES NOT LURCH WHEN AN EDITOR OPENS, which is the property that
 * made this the safe order to fix it in: the rail is the SAME column and the
 * same width as the tree panel alone, so the inset charged by
 * `viewport/fitFraming` is unchanged and no refit is needed. Measured before
 * and after on a 1600x1000 frame: free rect `356,24,888,758` either way, camera
 * unmoved. The rail announces itself only when its x or width actually moves
 * ({@link chargedInsetChanged}) — never on height, because a card that grows a
 * row as you type must not re-frame the scene under your hands.
 *
 * Visually the rail is NOTHING: no border, no ground, no label. It is structure,
 * not an instrument, and the design language already has its signature (the
 * title-block card). What it adds is a READ: the card you are operating stacked
 * above the tree you opened it from, ruled apart by the same 8px the rest of the
 * chrome breathes on — a drawing stamp laid on the sheet index, not a fourth
 * floating box competing for the same corner.
 */
import { cx } from "@loft/design";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import {
  announceChromeChange,
  chargedInsetChanged,
  type Rect,
} from "../viewport/fitFraming";

export type RailSide = "left" | "right";

/** The mounted rail element per side, or null where no rail is present. */
export type RailSlots = Readonly<Record<RailSide, HTMLElement | null>>;

const EMPTY_SLOTS: RailSlots = { left: null, right: null };

/**
 * Published rail nodes. A CONTEXT rather than a ref because a ref is still null
 * on the consumer's first render, and an editor that portals must have its
 * target on the render it mounts — with a ref the card silently falls back to
 * floating for one frame and then jumps.
 */
const RailContext = createContext<RailSlots>(EMPTY_SLOTS);

type RailRegister = (side: RailSide, node: HTMLElement | null) => void;

const RailRegisterContext = createContext<RailRegister | null>(null);

/**
 * Scope for a workspace's rails. Absent (the assembly and drawing workspaces,
 * and every component unit test) every consumer sees empty slots and keeps the
 * floating behaviour it has always had — the fallback is the default, so no
 * surface can be broken by NOT adopting the rail.
 */
export function ChromeRailProvider({ children }: { children: ReactNode }) {
  const [slots, setSlots] = useState<RailSlots>(EMPTY_SLOTS);
  const register = useCallback<RailRegister>((side, node) => {
    setSlots((current) =>
      current[side] === node ? current : { ...current, [side]: node },
    );
  }, []);
  return (
    <RailRegisterContext.Provider value={register}>
      <RailContext.Provider value={slots}>{children}</RailContext.Provider>
    </RailRegisterContext.Provider>
  );
}

/** The rail element for `side`, or null when this surface has no rail. */
export function useRailSlot(side: RailSide): HTMLElement | null {
  return useContext(RailContext)[side];
}

export interface RailDockProps {
  side?: RailSide;
  children: ReactNode;
}

/**
 * Dock anything that used to sit at `left-editor top-3` — the regeneration and
 * rebuild notices, the partial-body stamp, the mate HUD. They are the SAME seat
 * the editors took, so leaving them floating would have left the defect in
 * place for four surfaces and just moved it off the one the founder happened to
 * photograph.
 *
 * `EditorCard` does not use this (it owns a richer anatomy — pinned header,
 * scrolling body, pinned footer — and its own clamp); the two share the seat,
 * not the shell.
 */
export function RailDock({ side = "left", children }: RailDockProps) {
  const rail = useRailSlot(side);
  // Nothing to dock: render NO box. A zero-height flex item would still take a
  // `gap-2` from the rail, leaving a visible seam above the tree whenever none
  // of the notices is showing — which is nearly always.
  if (children === null || children === undefined || children === false) {
    return null;
  }
  const docked = (
    <div
      className={cx(
        "pointer-events-auto w-editor max-w-full shrink-0",
        rail === null &&
          cx("absolute top-3", side === "right" ? "right-3" : "left-editor"),
      )}
    >
      {children}
    </div>
  );
  return rail === null ? docked : createPortal(docked, rail);
}

export interface ChromeRailProps {
  side: RailSide;
  /** The panel(s) that live in this column. Editors portal in above them. */
  children: ReactNode;
}

export function ChromeRail({ side, children }: ChromeRailProps) {
  const register = useContext(RailRegisterContext);
  // Two nodes with two jobs: the RAIL is the box whose edge the fit charges,
  // the SEAT is where editors portal in (first in DOM order, so the card you
  // are operating stacks above the tree you opened it from).
  const [node, setNode] = useState<HTMLElement | null>(null);
  const [seat, setSeat] = useState<HTMLElement | null>(null);
  const charged = useRef<Rect | null>(null);

  useEffect(() => {
    register?.(side, seat);
    return () => register?.(side, null);
  }, [register, side, seat]);

  // Tell the viewport when the column's WIDTH or EDGE moves — the two numbers
  // `fitFraming` charges to an inset. Collapsing the tree gives a third of the
  // frame back and a fit that was correct is now off-centre; growing a card by
  // one row gives nothing back and must not move the camera. A naive
  // ResizeObserver here would refit on every keystroke, which is exactly the
  // lurching FB-1 was fixed to stop.
  useEffect(() => {
    if (node === null || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      const box = node.getBoundingClientRect();
      const next: Rect = {
        x: box.x,
        y: box.y,
        width: box.width,
        height: box.height,
      };
      const changed = chargedInsetChanged(charged.current, next);
      // Record every measurement, announce only the ones that move an edge —
      // the first observation is the frame the fit already solved for.
      charged.current = next;
      if (changed) announceChromeChange();
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [node]);

  // TWO deliberate sizing choices, both measured rather than guessed:
  //
  // `w-fit` (not a fixed width) so a COLLAPSED panel really gives its column
  // back: the rail is exactly as wide as the widest thing in it, and the tab it
  // shrinks to is ~120px. A fixed 320 would keep charging the fit for a column
  // nobody can see, and would swallow clicks in the empty half of it.
  //
  // `top-3 bottom-*` (not `max-h-*`) so the column's height is DEFINITE. With a
  // max-height only, the rail's height is auto during layout, and a flex child's
  // percentage basis or cap then resolves against an indefinite height — CSS
  // falls back to content size, silently. Measured: the feature tree's 591px of
  // content took 71px off the open extrude card and scrolled its Operation row
  // out of sight, with no cap having any effect at all.
  const className = useMemo(
    () =>
      cx(
        "pointer-events-none absolute top-3 z-panel flex w-fit min-h-0 flex-col gap-2",
        "max-w-[calc(100%-1.5rem)]",
        // The same clearances the floating cards clamp to, as anchors: the left
        // column stops above the bottom HUD lane, the right one above the
        // in-canvas reference cube (covering the view gizmo is a 3a defect).
        side === "left" ? "bottom-hud-lane left-3" : "bottom-cube-band right-3",
      ),
    [side],
  );

  return (
    <div
      ref={setNode}
      data-viewport-chrome={`rail-${side}`}
      className={className}
    >
      {/*
        The editor seat, FIRST so a portalled card stacks above the panels.
        `display: contents` means an empty seat contributes no box (and no stray
        8px gap), and a card that does arrive becomes a direct flex child of the
        rail — sizing and scrolling in the rail's own column instead of inside a
        wrapper that would clamp it a second time.
      */}
      <div ref={setSeat} className="contents" data-rail-seat={side} />
      {children}
    </div>
  );
}
