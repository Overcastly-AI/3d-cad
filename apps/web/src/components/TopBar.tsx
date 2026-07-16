import { Button, Toolbar } from "@loft/design";
import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { useSessionStore } from "../auth/session";
import { LoftMark } from "./LoftMark";

export interface TopBarProps {
  /**
   * Context slot next to the wordmark — a breadcrumb or status chip. Empty by
   * default: the band carries no decorative filler (UI-REVIEW 2026-07-16,
   * Track B — the "First light" default chip + the marketing tagline were
   * both decorative and are gone).
   */
  children?: ReactNode;
}

export function TopBar({ children }: TopBarProps) {
  const user = useSessionStore((state) => state.user);
  const signOut = useSessionStore((state) => state.signOut);
  return (
    <Toolbar data-testid="topbar">
      {/* The wordmark stays the page heading AND is now the way home — every
          workspace has an exit to the registers (UI-REVIEW 2026-07-16, Track
          C P2). Logo-as-heading: an h1 wrapping the home link. */}
      <h1 className="flex">
        <Link
          to="/"
          data-testid="home-link"
          aria-label="Loft — back to parts"
          className="flex items-center gap-2 rounded-sm outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
        >
          <LoftMark />
          <span className="font-display text-md tracking-[0.32em] text-mist">
            LOFT
          </span>
        </Link>
      </h1>
      {children}
      <div className="grow" />
      {user ? (
        <span
          className="hidden font-data text-xs text-gauge sm:inline"
          data-testid="session-email"
        >
          {user.email}
        </span>
      ) : null}
      <Button onClick={signOut} data-testid="sign-out">
        Sign out
      </Button>
    </Toolbar>
  );
}
