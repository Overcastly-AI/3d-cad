/**
 * The register switch — a quiet segmented control tying the document registers
 * together (Parts ⇄ Assemblies ⇄ Drawings). Square-cornered, hairline-ruled,
 * brass on the active leaf: the same title-block grammar as everything else,
 * so the workspaces read as siblings of one product.
 *
 * SETTINGS (#58) rides the same switch but is RULED OFF from the three: it is
 * not a drawer of documents, and separating it keeps "which register am I in"
 * answerable at a glance. It is here rather than in a top-bar overflow because
 * the preferences sheet is a place you go and come back from, and the way back
 * has to be visible from it.
 */
import { Link } from "@tanstack/react-router";

export interface WorkspaceNavProps {
  active: "parts" | "assemblies" | "drawings" | "settings";
}

export function WorkspaceNav({ active }: WorkspaceNavProps) {
  const cell = (isActive: boolean) =>
    [
      "px-3 py-1 font-display text-2xs uppercase tracking-[0.16em] outline-none",
      "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
      isActive
        ? "bg-anvil text-brass"
        : "bg-carbide text-gauge hover:text-mist",
    ].join(" ");

  return (
    <nav
      className="inline-flex divide-x divide-hairline border border-hairline"
      aria-label="Workspaces"
      data-testid="workspace-nav"
    >
      <Link to="/" className={cell(active === "parts")} data-testid="nav-parts">
        Parts
      </Link>
      <Link
        to="/assemblies"
        className={cell(active === "assemblies")}
        data-testid="nav-assemblies"
      >
        Assemblies
      </Link>
      <Link
        to="/drawings"
        className={cell(active === "drawings")}
        data-testid="nav-drawings"
      >
        Drawings
      </Link>
      {/* Ruled off with the heavier etch line: not a fourth drawer. */}
      <Link
        to="/settings"
        className={`${cell(active === "settings")} !border-l-2 !border-l-etch`}
        data-testid="nav-settings"
      >
        Settings
      </Link>
    </nav>
  );
}
