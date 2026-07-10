import { Chip, Toolbar } from "@loft/design";

/** Lofted-sections glyph — stacked station profiles, drawn in brass. */
function LoftMark() {
  return (
    <svg
      width="18"
      height="14"
      viewBox="0 0 18 14"
      aria-hidden="true"
      className="text-brass shrink-0"
    >
      <path
        d="M1 13H17"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <path
        d="M3.5 8.75H14.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        opacity="0.72"
      />
      <path
        d="M5.75 4.75H12.25"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        opacity="0.48"
      />
      <path
        d="M7.75 1.25H10.25"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        opacity="0.3"
      />
    </svg>
  );
}

export function TopBar() {
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
      <span className="hidden font-body text-xs text-gauge sm:inline">
        Parametric CAD · tessellated server-side by OCCT
      </span>
    </Toolbar>
  );
}
