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
