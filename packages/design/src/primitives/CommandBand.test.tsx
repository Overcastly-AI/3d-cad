// @vitest-environment jsdom
/**
 * CommandBand measured tier (2026-07-24 audit P0): the band probes whether
 * the labeled row fits its own width and stamps `data-band-tier` — no
 * viewport-breakpoint arithmetic that can go stale when tool groups land.
 * jsdom has no layout, so the geometry is driven through mocked rects; the
 * real fit behavior at 1280/1440/1600 is enforced by the Playwright guard
 * (`apps/web/e2e/toolbar-overflow.spec.ts`).
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CommandBand } from "./CommandBand";
import { ToolGroup } from "./ToolButton";

afterEach(cleanup);

/** Force the band/row geometry jsdom cannot compute. */
function mockGeometry(band: HTMLElement, bandWidth: number, rowWidth: number) {
  Object.defineProperty(band, "clientWidth", {
    value: bandWidth,
    configurable: true,
  });
  const row = band.firstElementChild as HTMLElement;
  row.getBoundingClientRect = () =>
    ({ width: rowWidth, height: 46 }) as DOMRect;
}

describe("CommandBand", () => {
  it("renders children in the measured row, keeps labels when they fit, and clamps its own overflow", () => {
    render(
      <CommandBand data-testid="band">
        <button type="button">Tool</button>
      </CommandBand>,
    );
    const band = screen.getByTestId("band");

    // jsdom rects are 0×0 → the labeled row "fits" → widest tier chosen.
    expect(band).toHaveAttribute("data-band-tier", "labeled");
    expect(screen.getByRole("button", { name: "Tool" })).toBeInTheDocument();

    // The two structural guarantees ride on the primitive's classes: the
    // X-only overflow clamp (no app-level scroll, tooltips still hang below)
    // and the page-level stacking layer (tooltips above panels).
    expect(band.className).toContain("overflow-x-clip");
    expect(band.className).toContain("z-band");
    const row = band.firstElementChild as HTMLElement;
    expect(row.className).toContain("w-max");
    expect(row.className).toContain("min-w-full");
    expect(row.className).toContain("shrink-0");
  });

  it("steps to the icon tier when the labeled row cannot fit — re-measured on a content change", async () => {
    render(
      <CommandBand data-testid="band">
        <button type="button">Tool</button>
      </CommandBand>,
    );
    const band = screen.getByTestId("band");
    mockGeometry(band, 1440, 1750);

    // Any subtree mutation (a group mounting, a mode swap) re-measures — the
    // exact event that used to leave the hardcoded tier stale.
    band.firstElementChild?.appendChild(document.createElement("span"));

    await waitFor(() => expect(band).toHaveAttribute("data-band-tier", "icon"));
  });

  it("steps back up to the labeled tier when the content fits again", async () => {
    render(
      <CommandBand data-testid="band">
        <button type="button">Tool</button>
      </CommandBand>,
    );
    const band = screen.getByTestId("band");
    mockGeometry(band, 1440, 1750);
    band.firstElementChild?.appendChild(document.createElement("span"));
    await waitFor(() => expect(band).toHaveAttribute("data-band-tier", "icon"));

    // The probe always measures the LABELED tier's natural width, so there is
    // no hysteresis to go stale: once the labeled row fits, labels return.
    mockGeometry(band, 1920, 1750);
    band.firstElementChild?.appendChild(document.createElement("span"));
    await waitFor(() =>
      expect(band).toHaveAttribute("data-band-tier", "labeled"),
    );
  });
});

/**
 * Graduated shedding (EXPORT-1 fallout, 2026-08-22). Six groups made the old
 * two-position switch untenable on the part band — fully labeled it needs
 * 2650.9px against 1047.5px of icons, so nothing in the 1280–2560 range could
 * show a single label. The band now buys labels back one `labelPriority` level
 * at a time.
 *
 * jsdom computes no geometry, so the row's width is derived here from which
 * groups currently have their words — the one input the algorithm reads.
 */
type GroupCost = { readonly icon: number; readonly label: number };

function mockGraduatedGeometry(
  band: HTMLElement,
  bandWidth: number,
  cost: Readonly<Record<string, GroupCost>>,
) {
  Object.defineProperty(band, "clientWidth", {
    value: bandWidth,
    configurable: true,
  });
  const row = band.firstElementChild as HTMLElement;
  row.getBoundingClientRect = () => {
    let width = 0;
    for (const group of Array.from(
      band.querySelectorAll<HTMLElement>("[data-label-priority]"),
    )) {
      const own = cost[group.getAttribute("aria-label") ?? ""];
      if (own === undefined) continue;
      width += own.icon + (group.dataset.labels === "off" ? 0 : own.label);
    }
    return { width, height: 46 } as DOMRect;
  };
}

/** Which groups kept their words, in DOM order. */
function labeledGroups(band: HTMLElement): string[] {
  return Array.from(band.querySelectorAll<HTMLElement>("[data-label-priority]"))
    .filter((group) => group.dataset.labels !== "off")
    .map((group) => group.getAttribute("aria-label") ?? "");
}

describe("CommandBand graduated label tier", () => {
  /** Three groups, 300px of icons; only the ranking decides who keeps words. */
  function renderRankedBand(bandWidth: number) {
    render(
      <CommandBand data-testid="band">
        <ToolGroup eyebrow="Sheet metal" labelPriority={0} />
        <ToolGroup eyebrow="Create" labelPriority={20} />
        <ToolGroup eyebrow="Export" labelPriority={40} />
      </CommandBand>,
    );
    const band = screen.getByTestId("band");
    mockGraduatedGeometry(band, bandWidth, {
      // Sheet metal's label is the CHEAPEST here on purpose — see the prefix
      // assertion below.
      "Sheet metal": { icon: 100, label: 30 },
      Create: { icon: 100, label: 150 },
      Export: { icon: 100, label: 60 },
    });
    band.firstElementChild?.appendChild(document.createElement("span"));
    return band;
  }

  it("keeps the highest-ranked group's words and sheds the rest", async () => {
    // 400px budget, 300px of icons: Export (+60) fits, Create (+150) does not.
    const band = renderRankedBand(400);
    await waitFor(() =>
      expect(band).toHaveAttribute("data-band-tier", "mixed"),
    );
    expect(labeledGroups(band)).toEqual(["Export"]);
  });

  it("stops at the first level that does not fit — a prefix, not a knapsack", async () => {
    // Sheet metal's label costs 30 and 40px is still spare once Export is
    // aboard, so a greedy best-fit would take it. It must NOT: the outcome has
    // to be readable off the declared order alone, or the band's appearance
    // becomes a function of which group happens to be cheapest that release.
    const band = renderRankedBand(400);
    await waitFor(() =>
      expect(band).toHaveAttribute("data-band-tier", "mixed"),
    );
    expect(labeledGroups(band)).not.toContain("Sheet metal");
  });

  it("labels everything when everything fits, and nothing when nothing does", async () => {
    const wide = renderRankedBand(810);
    await waitFor(() =>
      expect(wide).toHaveAttribute("data-band-tier", "labeled"),
    );
    expect(labeledGroups(wide)).toEqual(["Sheet metal", "Create", "Export"]);
    cleanup();

    // 300px of icons in a 320px band: no label can be afforded at all, and the
    // band reports the plain icon tier rather than a "mixed" with nothing in it.
    const narrow = renderRankedBand(320);
    await waitFor(() =>
      expect(narrow).toHaveAttribute("data-band-tier", "icon"),
    );
    expect(labeledGroups(narrow)).toEqual([]);
  });

  it("sheds peers at the same priority together, so equals are never half-dressed", async () => {
    render(
      <CommandBand data-testid="band">
        <ToolGroup eyebrow="Create" labelPriority={10} />
        <ToolGroup eyebrow="Modify" labelPriority={10} />
        <ToolGroup eyebrow="Export" labelPriority={40} />
      </CommandBand>,
    );
    const band = screen.getByTestId("band");
    // Create alone (+50) would fit in the 40px left after Export; the tranche
    // (+100) does not, so BOTH peers go to icons.
    mockGraduatedGeometry(band, 400, {
      Create: { icon: 100, label: 50 },
      Modify: { icon: 100, label: 50 },
      Export: { icon: 100, label: 60 },
    });
    band.firstElementChild?.appendChild(document.createElement("span"));
    await waitFor(() =>
      expect(band).toHaveAttribute("data-band-tier", "mixed"),
    );
    expect(labeledGroups(band)).toEqual(["Export"]);
  });
});
