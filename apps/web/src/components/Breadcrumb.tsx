/**
 * The workspace breadcrumb — the honest "where am I" trail that replaces the
 * inert part-name chip (UI-REVIEW 2026-07-16, Track C P2 + the founder's
 * navigation ask). Register → document → mode, so a workspace always shows its
 * place AND its current mode (part › Sketch), and every segment above the
 * document is a real route out. Same title-block grammar as WorkspaceNav:
 * tracked caps, hairline separators, brass on the live leaf.
 */
import { Link } from "@tanstack/react-router";

export interface BreadcrumbProps {
  /** Which register this document lives in — sets the parent link + label. */
  register: "parts" | "assemblies" | "drawings";
  /** The document's name (the current, non-link leaf when no mode is active). */
  documentName: string;
  /** Test hook on the document segment — kept as `part-name`/`assembly-name`. */
  documentTestId: string;
  /**
   * The active workspace mode, e.g. "Sketch" / "Pick a plane" / "Measure" /
   * "Fillet". Shown as the live brass leaf when set; absent = plain model mode.
   */
  mode?: string | null;
}

const REGISTER = {
  parts: { to: "/" as const, label: "Parts" },
  assemblies: { to: "/assemblies" as const, label: "Assemblies" },
  drawings: { to: "/drawings" as const, label: "Drawings" },
};

function Separator() {
  return (
    <span aria-hidden className="font-display text-2xs text-etch">
      ›
    </span>
  );
}

export function Breadcrumb({
  register,
  documentName,
  documentTestId,
  mode,
}: BreadcrumbProps) {
  const { to, label } = REGISTER[register];
  const modeActive = mode != null && mode !== "";
  return (
    <nav
      aria-label="Breadcrumb"
      data-testid="breadcrumb"
      className="flex min-w-0 items-center gap-2"
    >
      <Link
        to={to}
        data-testid="breadcrumb-register"
        className="shrink-0 rounded-sm font-display text-2xs uppercase tracking-[0.16em] text-gauge outline-none hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
      >
        {label}
      </Link>
      <Separator />
      <span
        data-testid={documentTestId}
        className={`min-w-0 truncate font-display text-2xs uppercase tracking-[0.16em] ${
          modeActive ? "text-gauge" : "text-brass"
        }`}
      >
        {documentName}
      </span>
      {modeActive ? (
        <>
          <Separator />
          <span
            data-testid="workspace-mode"
            className="shrink-0 font-display text-2xs uppercase tracking-[0.16em] text-brass"
          >
            {mode}
          </span>
        </>
      ) : null}
    </nav>
  );
}
