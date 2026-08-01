import { Chip } from "@loft/design";

import { SettingsSheet } from "../components/SettingsSheet";
import { SheetGrid } from "../components/SheetGrid";
import { TopBar } from "../components/TopBar";
import { WorkspaceNav } from "../components/WorkspaceNav";

/**
 * The settings surface (#58) — a sibling of the three registers, not a modal:
 * it is a place you go and come back from, and the workspace switch stays on
 * screen so it is one step out again. The sheet itself is `SettingsSheet`; this
 * page supplies the same drawer chrome every register has.
 */
export function SettingsPage() {
  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <Chip data-testid="status-chip">Settings</Chip>
      </TopBar>
      <main className="relative min-h-0 grow overflow-y-auto bg-carbide">
        <SheetGrid />
        <div
          className="pointer-events-none absolute inset-3 border border-hairline"
          aria-hidden="true"
        />
        <div className="relative mx-auto flex h-full w-full max-w-5xl flex-col px-4 py-6 sm:px-8">
          <WorkspaceNav active="settings" />
          <SettingsSheet />
        </div>
      </main>
    </div>
  );
}
