import { expect, test } from "../e2e/fixtures";
import {
  armCspRecorder,
  openSeededPart,
  collectCspConsole,
  describeViolations,
  EXPECTED_CSP,
  EXPECTED_CSP_DIRECTIVES,
  readCspViolations,
} from "./distSupport";

/**
 * THE PRODUCTION CONTENT-SECURITY-POLICY, exercised by a real browser against
 * the real bundle served by the real nginx config.
 *
 * Read `playwright.dist.config.ts` first for why the dev-server suite cannot
 * cover any of this.
 *
 * THE ASSERTION THAT MATTERS IS "ZERO VIOLATIONS", NOT "THE PAGE RENDERED."
 * A CSP failure is invisible to every other check we own: a blocked font
 * leaves a legible page in a fallback typeface, a blocked worker leaves a
 * viewport that merely looks slow, a blocked blob: leaves a body that never
 * arrives — and in all three cases the DOM mounts, the status codes are 200,
 * and the suite is green. So this spec listens for the event the browser
 * actually fires and refuses on the first one.
 *
 * And "zero" is only worth anything if the listener could ever report
 * non-zero, so the second test here is a POSITIVE CONTROL that plants a
 * violation and demands to see it. Without it, a detached listener and a clean
 * policy are the same reading.
 */

test.describe("the production CSP", () => {
  test("is served on every document the app loads", async ({ page }) => {
    // The ENTRY DOCUMENT, the BUNDLE and the API all sit in different nginx
    // locations, and `add_header` is NOT additive across levels — a location
    // with any add_header of its own discards every inherited one. That rule
    // has already silently dropped two headers in this file once. So all three
    // are checked, by their SERVED value.
    const index = await page.request.get("/");
    expect(index.status()).toBe(200);
    const body = await index.text();
    expect(body).toContain('<div id="root"');

    // THE GUARD AGAINST TESTING THE WRONG SERVER. Everything below would pass
    // just as happily against `vite dev`, which emits no CSP at all — and then
    // "zero violations" would be true and meaningless. The dev server serves
    // `/src/main.tsx` and `/@vite/client`; the build serves a hashed chunk.
    const assetRef = /\/assets\/[A-Za-z0-9._-]+\.js/.exec(body)?.[0];
    expect(
      assetRef,
      "the entry document references no /assets/*.js chunk — this is not `vite build` output",
    ).toBeTruthy();
    // The dev server serves `/@vite/client` as a JavaScript module; nginx has
    // no such file and hands back index.html through the SPA fallback. So the
    // discriminator is the CONTENT TYPE, not the status — `toBe(404)` was the
    // first thing written here and it was WRONG, because `try_files $uri $uri/
    // /index.html` answers 200 for every unknown path by design. A guard that
    // fails against the server it is meant to bless is worse than no guard: it
    // is the one you delete.
    const viteClient = await page.request.get("/@vite/client");
    expect(
      viteClient.headers()["content-type"] ?? "",
      "/@vite/client was served as a script — the leg is pointed at the DEV " +
        "server, where there is no CSP to violate and every assertion below is vacuous",
    ).toContain("text/html");

    for (const [label, url] of [
      ["the entry document", "/"],
      ["the app bundle", assetRef as string],
      ["the API proxy", "/api/v1/parts"],
    ] as const) {
      const response = await page.request.get(url);
      const header = response.headers()["content-security-policy"];
      expect(
        header,
        `${label} carried no Content-Security-Policy`,
      ).toBeDefined();
      expect(
        header,
        `${label} served a policy that is not the intended one`,
      ).toBe(EXPECTED_CSP);
      // COUNT GUARD: a truncated policy is still a valid policy and still a
      // plausible string. Counting directives makes a silent loss fail.
      expect(
        (header as string).split(";").filter((part) => part.trim() !== "")
          .length,
        `${label}'s policy does not declare ${EXPECTED_CSP_DIRECTIVES} directives`,
      ).toBe(EXPECTED_CSP_DIRECTIVES);
    }

    // The bundle must be the real one, not the SPA fallback wearing its name.
    const bundle = await page.request.get(assetRef as string);
    expect(bundle.status()).toBe(200);
    const bytes = (await bundle.body()).byteLength;
    expect(
      bytes,
      `${assetRef} is ${bytes} bytes — the app chunk measures ~2.1 MB, so this is index.html or a stub`,
    ).toBeGreaterThan(1_000_000);
  });

  test("is ENFORCED — a planted inline script is blocked and reported", async ({
    page,
  }) => {
    // THE POSITIVE CONTROL for every "zero violations" assertion in this file.
    // It points at the guard itself: the recorder is armed the same way, on the
    // same page, and then given something it MUST see. If this ever passes
    // vacuously the other tests are decoration.
    await armCspRecorder(page);
    await page.goto("/");
    await expect(page.locator("#root")).not.toBeEmpty();

    const before = await readCspViolations(page);
    expect(
      before,
      `the app violated its own CSP before the control even ran:\n${describeViolations(before)}`,
    ).toHaveLength(0);

    await page.evaluate(() => {
      const script = document.createElement("script");
      // `script-src` carries no 'unsafe-inline', so this must never run.
      script.textContent = "window.__loftCspCanaryRan = true;";
      document.head.appendChild(script);
    });
    // The violation event is dispatched asynchronously from the block.
    await expect
      .poll(async () => (await readCspViolations(page)).length, {
        timeout: 5_000,
      })
      .toBe(1);

    const planted = await readCspViolations(page);
    expect(planted[0]?.directive).toMatch(/^script-src/);
    const ran = await page.evaluate(
      () =>
        (window as unknown as { __loftCspCanaryRan?: boolean })
          .__loftCspCanaryRan,
    );
    expect(
      ran,
      "the planted inline script EXECUTED — the policy is advertised but not enforced, " +
        "which makes every other assertion in this file vacuous",
    ).toBeUndefined();
  });

  test("a full modelling flow raises no violation", async ({ page }) => {
    // The flow is chosen for the CSP surfaces it touches, not for coverage:
    // module script + stylesheet + eight data: fonts on boot, then a real
    // tessellated body, which is where blob: URLs, workers and WebGL live. A
    // boot-only check would have passed the font defect this leg found on its
    // first run only because the landing page loads the same CSS — but it would
    // miss anything the viewport does, and the viewport is the app.
    const consoleReports: string[] = [];
    collectCspConsole(page, consoleReports);
    await armCspRecorder(page);

    await openSeededPart(page, "CSP plate");
    await expect(page.getByTestId("viewport")).toBeVisible();

    // THE EXPORT, because `apps/web/src/api/exportPart.ts` hands the browser a
    // `URL.createObjectURL` blob and navigates to it. That is the one code path
    // in the app whose CSP exposure cannot be reached by looking at a page.
    const downloadPromise = page.waitForEvent("download");
    await page.getByTestId("part-export-step").click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.step$/i);

    const violations = await readCspViolations(page);
    expect(
      violations,
      `the shipped bundle violates the policy the shipped nginx config serves:\n` +
        describeViolations(violations),
    ).toHaveLength(0);

    // SECOND, INDEPENDENTLY DERIVED READING. The list above is a DOM listener;
    // this is Chromium's own renderer log. Agreeing on zero is what turns
    // "nothing fired" into "nothing happened" — a listener that silently
    // detached also reports zero, and would read exactly like a pass.
    expect(
      consoleReports,
      "the DOM listener saw no violation but the console reported one — one of " +
        "the two readings is measuring something nobody named; trust neither " +
        "until checked:\n" +
        consoleReports.join("\n"),
    ).toHaveLength(0);
  });
});
