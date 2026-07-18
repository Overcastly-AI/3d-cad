import { useId } from "react";

/**
 * The drawing-sheet grid — the SAME token palette the WebGL viewport grid
 * uses (one palette, two renderers; CLAUDE.md design mandate). It carries the
 * bench from the un-issued sheet (sign-in) into the issued register (parts
 * home): the ground under both is the same steel table. Purely decorative,
 * so `aria-hidden`; sits behind content on the carbide ground.
 */
export function SheetGrid() {
  const id = useId();
  const minor = `${id}-minor`;
  const major = `${id}-major`;
  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full text-hairline"
      aria-hidden="true"
      data-testid="sheet-grid"
    >
      <defs>
        <pattern
          id={minor}
          width="24"
          height="24"
          patternUnits="userSpaceOnUse"
        >
          <path
            d="M24 0H0V24"
            fill="none"
            stroke="currentColor"
            strokeOpacity="0.3"
          />
        </pattern>
        <pattern
          id={major}
          width="120"
          height="120"
          patternUnits="userSpaceOnUse"
        >
          <path
            d="M120 0H0V120"
            fill="none"
            stroke="currentColor"
            strokeOpacity="0.65"
          />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${minor})`} />
      <rect width="100%" height="100%" fill={`url(#${major})`} />
    </svg>
  );
}
