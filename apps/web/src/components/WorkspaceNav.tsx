/**
 * The register switch — a quiet segmented control tying the two document
 * registers together (Parts ⇄ Assemblies). Square-cornered, hairline-ruled,
 * brass on the active leaf: the same title-block grammar as everything else,
 * so the two workspaces read as siblings of one product.
 */
import { Link } from "@tanstack/react-router";

export interface WorkspaceNavProps {
  active: "parts" | "assemblies";
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
    </nav>
  );
}
