/**
 * In-viewport solve diagnostic — the drawing-stamp language the viewport
 * already uses for rejected meshes (border-flag, tracked eyebrow, one plain
 * instruction). Appears only when the bound sketch's solve is sick
 * (conflicting / over-constrained / diverged); a healthy solve renders
 * nothing. Never a silent failure.
 */
import { solveDiagnostic } from "../sketch/constraints";
import { useSketchStore } from "../sketch/store";

export function SolveDiagnostic() {
  const mode = useSketchStore((state) => state.mode);
  const solve = useSketchStore((state) => state.solve);
  if (mode !== "draw") return null;
  const diagnostic = solveDiagnostic(solve);
  if (diagnostic === null) return null;
  return (
    <div
      role="status"
      data-testid="solve-diagnostic"
      className="absolute bottom-3 right-3 max-w-sm border border-flag bg-anvil px-3 py-2"
    >
      <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
        {diagnostic.title}
      </span>
      <span className="mt-1 block font-body text-xs text-mist">
        {diagnostic.body}
      </span>
    </div>
  );
}
