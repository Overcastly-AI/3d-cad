import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test } from "../e2e/fixtures";
import { waitForFrames } from "../e2e/support";

import { censusBundle, openSeededPart, THREE_MARKERS } from "./distSupport";

/**
 * HOW MANY COPIES OF `three` ARE IN THE SHIPPED BUNDLE?
 *
 * The question is not academic. `three@0.185.1`'s exports map is
 * `{"import": "./build/three.module.js", "require": "./build/three.cjs"}` —
 * ONE version, TWO builds — so a graph that pulls both ends up with two
 * distinct `PerspectiveCamera` class objects and `instanceof` that is FALSE
 * for a perfectly good camera. There is no version conflict to find and no
 * lockfile to fix. It is already measured TRUE under vitest, where
 * `@react-three/fiber` resolves to its CJS dev build; `apps/web/src` carries
 * 15 such `instanceof` sites, 13 of them in `Viewport.tsx`.
 *
 * Until this leg existed, nothing had ever loaded the built bundle, so the
 * answer for PRODUCTION was an honest unknown written into CLAUDE.md. It is
 * answered here three ways, from three different mechanisms, and they must
 * agree:
 *
 *   STATIC   count two per-copy markers in the emitted JS (different
 *            statements, so a minifier that mangles one shows up as a
 *            disagreement rather than as a wrong answer).
 *   RUNTIME  three's OWN multi-instance guard: the first copy to execute sets
 *            `window.__THREE__`; a second copy console.warns. It is the
 *            library's opinion about itself, derived from neither of the above.
 *   BEHAVIOUR the app's own `camera instanceof OrthographicCamera` — stamped on
 *            the viewport as `data-projection` by `ProjectionRig`, read FROM
 *            THE LIVE CAMERA rather than from the store. This is the only one
 *            of the three that tests the consequence anybody cares about.
 *
 * The behavioural one is the load-bearing assertion and deserves its
 * asymmetry spelled out: `"perspective"` is the FALSE branch of that
 * `instanceof`, so it is also what a BROKEN `instanceof` produces. Only
 * `"orthographic"` can be produced by a `true`, so the toggle must actually be
 * driven — reading the default tells you nothing.
 */

test.describe("three in the production bundle", () => {
  test("the emitted JS contains exactly one copy", async () => {
    const census = censusBundle();
    // Say what was walked. A census whose corpus is not in the log is a number
    // nobody can check, and this one refuses on an empty walk precisely because
    // "zero copies" reads like a clean answer.
    console.log(
      `three census: ${census.files.length} JS file(s), ${census.bytes} bytes\n` +
        `  "${THREE_MARKERS.multiInstanceWarning.literal}" x ${census.counts.multiInstanceWarning}` +
        ` -> ${census.copies.multiInstanceWarning} copy/copies\n` +
        `  "${THREE_MARKERS.globalFlag.literal}" x ${census.counts.globalFlag}` +
        ` -> ${census.copies.globalFlag} copy/copies`,
    );

    expect(
      census.copies.multiInstanceWarning,
      "the two markers disagree about how many copies of three are bundled, so " +
        "one of them is no longer counting what it thinks it counts (a minifier " +
        "change is the usual cause) — trust neither until re-derived against " +
        "node_modules/three/build/three.core.js",
    ).toBe(census.copies.globalFlag);

    expect(
      census.copies.multiInstanceWarning,
      "the bundle carries more than one copy of three. Every `instanceof` " +
        "against a three class in apps/web/src is now silently false for " +
        "objects created by the other copy — 15 sites, 13 in Viewport.tsx. " +
        "This is a P1: use the duck-typed flags (isPerspectiveCamera, isMesh) " +
        "instead, and find what pulled the second build in.",
    ).toBe(1);
  });

  test("the census can SEE a second copy, and refuses an empty corpus", () => {
    // THE NEGATIVE CONTROL, pointed at the guard above rather than downstream
    // of it. `toBe(1)` is an assertion nobody in this repo has ever watched
    // fail, and an assertion you have never seen fail is not yet a gate —
    // especially this one, whose failure mode is a NUMBER being wrong rather
    // than something visibly breaking. So the same function is handed a
    // fabricated two-copy bundle and an empty one, and must disagree with
    // itself in exactly the two ways that matter.
    const root = mkdtempSync(join(tmpdir(), "loft-three-census-"));
    const assets = join(root, "assets");
    mkdirSync(assets);

    // Two copies: each marker repeated its per-copy multiple, twice over, and
    // padded past the 1 MB floor so the size guard is not what fires.
    const copy =
      `console.warn("${THREE_MARKERS.multiInstanceWarning.literal}");` +
      `window.${THREE_MARKERS.globalFlag.literal}=REVISION;` +
      `if(window.${THREE_MARKERS.globalFlag.literal}){}`;
    writeFileSync(
      join(assets, "two-copies.js"),
      copy + copy + "/*".padEnd(1_100_000, "x") + "*/",
    );
    const doubled = censusBundle(root);
    expect(
      doubled.copies.multiInstanceWarning,
      "the census cannot see a second copy of three — the `toBe(1)` above is decoration",
    ).toBe(2);
    expect(doubled.copies.globalFlag).toBe(2);

    // Empty corpus: it must REFUSE, not report zero. "Zero copies of three" is
    // the vacuous pass — it reads like a clean answer and is the shape four
    // gates in this repo have shipped.
    const empty = mkdtempSync(join(tmpdir(), "loft-three-empty-"));
    mkdirSync(join(empty, "assets"));
    expect(() => censusBundle(empty)).toThrow(/REFUSED/);
    // And a directory with no `assets/` at all — the "pointed at the dev
    // server" case — must refuse with its own message rather than crash.
    expect(() =>
      censusBundle(mkdtempSync(join(tmpdir(), "loft-three-none-"))),
    ).toThrow(/must run against/);
  });

  test("three's own multi-instance guard is quiet at runtime", async ({
    page,
  }) => {
    const warnings: string[] = [];
    page.on("console", (message) => {
      if (/Multiple instances of Three\.js/i.test(message.text())) {
        warnings.push(message.text());
      }
    });

    await page.goto("/");
    // NON-VACUITY: three must actually have executed, or "no warning" is a
    // statement about a page that never loaded it. `__THREE__` is set by the
    // FIRST copy to run, so its presence is the positive control for the
    // absence of the warning.
    await expect
      .poll(
        async () =>
          page.evaluate(
            () =>
              (window as unknown as { __THREE__?: string }).__THREE__ ?? null,
          ),
        { timeout: 30_000 },
      )
      .not.toBeNull();

    expect(
      warnings,
      "three warned that multiple instances were imported — the static census " +
        "in this file must be red too; if it is not, the census is wrong",
    ).toHaveLength(0);
  });

  test("`camera instanceof OrthographicCamera` is TRUE in the shipped app", async ({
    page,
  }) => {
    await openSeededPart(page, "Projection plate");

    const viewport = page.getByTestId("viewport");
    // The default is perspective, which is ALSO what a broken instanceof
    // stamps — assert it only to prove the toggle changed something.
    await expect(viewport).toHaveAttribute("data-projection", "perspective", {
      timeout: 20_000,
    });

    await page.getByTestId("view-projection").click();
    await expect(
      viewport,
      "the viewport still reports a perspective projection after switching to " +
        "orthographic. `ProjectionRig` stamps this from " +
        "`camera instanceof OrthographicCamera` on the LIVE camera, so either " +
        "the toggle never reached the camera or — the reason this spec is in " +
        "this file — the bundle holds two copies of three and the instanceof " +
        "is comparing against the wrong class object.",
    ).toHaveAttribute("data-projection", "orthographic", { timeout: 20_000 });
    await waitForFrames(page, 3);

    // And back, so the stamp is shown to TRACK the camera rather than to latch.
    await page.getByTestId("view-projection").click();
    await expect(viewport).toHaveAttribute("data-projection", "perspective", {
      timeout: 20_000,
    });
  });
});
