/**
 * Client-side SVG export for the drawing sheet (Drawings v1 #5).
 *
 * The shipped `DrawingSheet` already renders the ENTIRE dimensioned print —
 * projected edges (solid/dashed), dimensions, and the title block — as ONE
 * self-contained `<svg>` whose colours are inline attribute values taken
 * straight from the `drawing` design tokens (no external stylesheet, no CSS
 * custom properties, no `<use>`/xlink references). So "export the SVG you see"
 * is a DOM serialization, not a second drafting renderer (DRY): we clone the
 * live node, give it a concrete scale-correct size + the SVG namespace, strip
 * the two screen-only affordances (the Tailwind sizing classes and the bench
 * drop-shadow), and serialize it to a standalone file. Text falls back to a
 * generic monospace — `font.data` carries the `monospace` fallback — so the
 * value stamps render in a browser/Inkscape without the self-hosted face.
 */
import { downloadBlob } from "../api/exportPart";

/** The SVG namespace — set explicitly so the file opens standalone. */
const SVG_NS = "http://www.w3.org/2000/svg";

/**
 * Slugify a drawing name into a safe `.svg` basename (no extension): lower
 * case, non-alphanumeric runs collapse to a single hyphen, edges trimmed.
 * `"Plate — dimensions"` → `"plate-dimensions"`; empty → `"drawing"`.
 */
export function sanitizeDrawingFilename(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug.length > 0 ? slug : "drawing";
}

/**
 * Serialize the live sheet `<svg>` into a standalone, self-contained SVG
 * document string (XML prolog + namespaced root). The node is CLONED so the
 * on-screen sheet is never mutated.
 */
export function serializeSheetSvg(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", SVG_NS);
  // The live node sizes itself with Tailwind `h-full w-full` classes that do
  // not exist in a standalone file; give it a concrete size from the mm
  // `viewBox` so the file opens — and prints — scale-correct (units are mm).
  const viewBox = clone.getAttribute("viewBox");
  const parts = viewBox?.split(/[\s,]+/).map(Number);
  if (parts && parts.length === 4 && parts.every((n) => Number.isFinite(n))) {
    const [, , width, height] = parts as [number, number, number, number];
    clone.setAttribute("width", `${width}mm`);
    clone.setAttribute("height", `${height}mm`);
  }
  // Screen-only chrome, not part of the print: the sizing classes and the
  // bench-seat drop-shadow (a viewport affordance, and a filter that would
  // clip against the sheet's own edges in a standalone file).
  clone.removeAttribute("class");
  clone.removeAttribute("style");
  // Interactive placement affordances (drag frame / grip / reset) are editor-only
  // — drop them so the exported print carries only drafting geometry.
  clone
    .querySelectorAll("[data-placement-chrome]")
    .forEach((node) => node.remove());
  const xml = new XMLSerializer().serializeToString(clone);
  return `<?xml version="1.0" encoding="UTF-8"?>\n${xml}\n`;
}

/**
 * Serialize the sheet and hand it to the browser as a named `.svg` download.
 * Reuses the shared {@link downloadBlob} (blob URL + synthetic anchor, URL
 * revoked after the click).
 */
export function exportSheetSvg(svg: SVGSVGElement, drawingName: string): void {
  const svgText = serializeSheetSvg(svg);
  const blob = new Blob([svgText], { type: "image/svg+xml;charset=utf-8" });
  downloadBlob(blob, `${sanitizeDrawingFilename(drawingName)}.svg`);
}
