/**
 * GUARD: the design system's closed token scales must be able to emit every
 * utility the sources ask for.
 *
 * The failure mode this catches is silent by construction — a Tailwind utility
 * whose theme step is missing produces no rule, no warning and no build error,
 * so the element just has no size and the screenshot looks intentional. It cost
 * us the feature tree's rollback bar, the tapped-hole thread callout, the
 * active-tool brass scribe, a 16px-tall command band and the measure HUD's
 * anchor, across three audits that all photographed the result and passed it
 * (UI-REVIEW 2026-07-30 P1).
 *
 * Scales stay CLOSED (the whole point of the preset): if a step is genuinely
 * outside the design language, the fix is an arbitrary value (`bottom-[4.5rem]`)
 * or a named `layout` token — not reopening the scale.
 */
import { describe, expect, it } from "vitest";

import {
  findUnresolvable,
  harvestCandidates,
  loadWebConfig,
  scannedRoots,
} from "./tailwindUtilities";

describe("tailwind utility resolution", () => {
  it("emits a rule for every utility the scanned sources ask for", async () => {
    const candidates = harvestCandidates(scannedRoots());
    // Sanity: the harvest must actually find the app's classes, or this test
    // passes vacuously (a green that means "I scanned nothing").
    expect(candidates.length).toBeGreaterThan(100);

    const config = await loadWebConfig();
    const dead = await findUnresolvable(
      candidates.map((c) => c.utility),
      config,
    );

    const byUtility = new Map(candidates.map((c) => [c.utility, c.files]));
    const report = dead.map(
      (u) => `${u}  <-  ${(byUtility.get(u) ?? []).join(", ")}`,
    );
    expect(
      report,
      "These classes appear in source but the theme emits NO rule for them, " +
        "so they render as nothing. Add the step to the token scale if it " +
        "belongs to the design language, otherwise use an arbitrary value.",
    ).toEqual([]);
  }, 60_000);

  it("resolves the design system's named vocabulary", async () => {
    const config = await loadWebConfig();
    // Named token utilities can't be told apart from `data-testid="top-toolbar"`
    // by shape, so the harvest skips them and this curated list covers them:
    // every named class the shell composes with.
    expect(
      await findUnresolvable(
        [
          "h-toolbar",
          "h-band",
          "w-inspector",
          "w-editor",
          "left-editor",
          "bottom-hud-lane",
          "max-h-hud-card",
          "max-h-cube-card",
          "rounded-none",
          "rounded-sm",
          "rounded-md",
          "rounded-full",
          "text-2xs",
          "duration-fast",
          "z-hud",
          "z-panel",
          "z-band",
          "z-menu",
        ],
        config,
      ),
    ).toEqual([]);
  }, 60_000);

  it("resolves the half-steps the design language uses", async () => {
    const config = await loadWebConfig();
    // Fixture: the exact classes that were dead on 2026-07-30. `h-px` is the
    // signature hairline (rollback bar, thread-note rule, active scribe);
    // `1.5`/`2.5` are the sub-4px rhythm of the dense chrome.
    expect(
      await findUnresolvable(
        [
          "h-px",
          "w-px",
          "py-1.5",
          "px-1.5",
          "gap-1.5",
          "gap-2.5",
          "inset-x-1.5",
          "mt-1.5",
        ],
        config,
      ),
    ).toEqual([]);
  }, 60_000);

  it("still reports steps that are outside the closed scale", async () => {
    const config = await loadWebConfig();
    // Negative fixture — proves the detector has teeth rather than emitting
    // every candidate it is handed. These are the one-off sizes the audit
    // found dead; they stay out of the scale by design and must be written as
    // arbitrary values at the use site.
    expect(
      await findUnresolvable(
        ["bottom-16", "max-h-64", "w-52", "min-w-24", "p-7"],
        config,
      ),
    ).toEqual(["bottom-16", "max-h-64", "w-52", "min-w-24", "p-7"]);
  }, 60_000);
});
