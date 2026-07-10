import { Button, Chip, Toolbar } from "@loft/design";

import { useSessionStore } from "../auth/session";
import { LoftMark } from "./LoftMark";

export function TopBar() {
  const user = useSessionStore((state) => state.user);
  const signOut = useSessionStore((state) => state.signOut);
  return (
    <Toolbar data-testid="topbar">
      <h1 className="flex items-center gap-2">
        <LoftMark />
        <span className="font-display text-md tracking-[0.32em] text-mist">
          LOFT
        </span>
      </h1>
      <Chip data-testid="status-chip">First light</Chip>
      <div className="grow" />
      <span className="hidden font-body text-xs text-gauge lg:inline">
        Parametric CAD · tessellated server-side by OCCT
      </span>
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
