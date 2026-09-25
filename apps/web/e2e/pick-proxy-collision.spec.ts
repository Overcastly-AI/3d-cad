/**
 * BOARD #76 — THE PICK PROXIES COLLIDE, AND A REAL USER SHIPPED A WRONG PART.
 *
 * A product audit modelled a gearbox housing, filleted THREE of four corners
 * without noticing, and caught it only from the volume. Not a crash and not a
 * refusal: a silently asymmetric part. The mechanism was that the pick
 * affordances lie about themselves — a mark that is drawn where its subject
 * cannot be reached, a mark that turns itself off the instant you point at it,
 * and a mark standing on a face the modeller cannot see.
 *
 * ## What this file measures, and the discipline it measures with
 *
 * `document.elementFromPoint` does NOT decide pickability here, and using it as
 * the verdict is the error the auditor made first: the raycast is in WebGL and
 * wins, so a real click at a point where `elementFromPoint` returns only
 * `CANVAS` still picks the face. So:
 *
 *  · **the verdict is a real pointer** — `page.mouse.move` / `page.mouse.click`,
 *    read back through the app's OWN state (`data-edge-pick-hover`,
 *    `data-shell-face-hover`, `data-face-pick-hover`, the picked set). There is
 *    no `force: true` anywhere in this file;
 *  · **`elementFromPoint` is used only for ATTRIBUTION** — to name what is on
 *    top of a proxy. "Behind the body" and "under another live control" need
 *    completely different fixes and a bare count cannot tell them apart, which
 *    is why every table below reports an occluder per proxy rather than a
 *    total;
 *  · **attribution, not subtraction.** Each proxy is read together with what
 *    the BODY answers at the same pixel once the marks are muted, so the three
 *    outcomes are distinguished directly rather than inferred from a delta:
 *    the proxy reaches its own subject; the proxy is buried and correctly
 *    YIELDS that pixel to the face in front of it; or something took it;
 *  · **the settles are named out loud.** Burial is decided by rotating
 *    per-frame budgets — `data-edge-mark-seats` for edges,
 *    `data-face-mark-seats` for faces — and a reading taken mid-drain is not a
 *    reading. The camera is settled by POSITION as well, because a re-fit is a
 *    pure re-frame that a direction-only rest check returns in the middle of.
 */
import { expect, test, type Page } from "./fixtures";

import { installSceneProbe, waitForCameraStill } from "./invariants";

import { createFeature, rectangleSketch } from "./partSeed";
import {
  createPartViaApi,
  distinctCanvasColors,
  expectSeatsSettled,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * THE AUDIT'S HOUSING — 130 x 80 x 40 with four Ø8 through-holes.
 *
 * The size is load-bearing and is why this spec does not reuse the 20 mm cube
 * every other spec builds: the defect is proxies colliding in SCREEN space, and
 * a small six-faced part puts every mark centimetres from its neighbours. It
 * takes a part with enough topology to crowd the frame before the collisions
 * are even expressible — the four bores contribute eight circular edges and
 * four cylinder seams on top of the box's twelve.
 */
async function seedHousing(
  page: Page,
  token: string,
  partId: string,
): Promise<void> {
  const plate = await createFeature(page, token, partId, {
    name: "Housing",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(0, 0, 130, 80),
    },
    expected_tree_version: 0,
  });
  const solid = await createFeature(page, token, partId, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: plate.feature.id },
        distance_mm: 40,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: plate.tree_version,
  });
  const bores = await createFeature(page, token, partId, {
    name: "Bolt holes",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [
          { x: 15, y: 15 },
          { x: 115, y: 15 },
          { x: 115, y: 65 },
          { x: 15, y: 65 },
        ].map((centre, i) => ({
          id: `h${i + 1}`,
          kind: "circle",
          center: centre,
          radius: 4,
        })),
        constraints: [],
      },
    },
    expected_tree_version: solid.tree_version,
  });
  await createFeature(page, token, partId, {
    name: "Drill",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: bores.feature.id },
        distance_mm: 40,
        operation: "cut",
        direction: "normal",
      },
    },
    expected_tree_version: bores.tree_version,
  });
}

/**
 * THE AUDIT'S HOUSING AS IT WAS WHEN THE HOLE WENT WRONG — hollowed to a 3 mm
 * wall with the top left open.
 *
 * This is the shape that put an INNER wall's mark 9 px from its OUTER wall's:
 * each wall now has a twin 3 mm behind it, facing the other way, and from any
 * outside view the inner twin's centroid projects onto the outer wall. A solid
 * box cannot show that at all, which is why this is a separate fixture rather
 * than a flag nobody would think to set.
 */
async function seedShelledHousing(
  page: Page,
  token: string,
  partId: string,
): Promise<void> {
  const plate = await createFeature(page, token, partId, {
    name: "Housing",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(0, 0, 130, 80),
    },
    expected_tree_version: 0,
  });
  const solid = await createFeature(page, token, partId, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: plate.feature.id },
        distance_mm: 40,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: plate.tree_version,
  });
  await createFeature(page, token, partId, {
    name: "Shell1",
    feature: {
      type: "shell",
      version: 1,
      params: {
        thickness_mm: 3,
        faces: {
          kind: "faces",
          refs: [
            {
              kind: "subshape",
              feature_id: solid.feature.id,
              subshape_type: "face",
              selector: {
                selector_version: 1,
                signature: {
                  subshape_type: "face",
                  surface: "plane",
                  area_mm2: 130 * 80,
                  centroid: { x: 65, y: 40, z: 40 },
                  normal: { x: 0, y: 0, z: 1 },
                },
              },
            },
          ],
        },
      },
    },
    expected_tree_version: solid.tree_version,
  });
}

/**
 * Wait until gauge chrome has stopped arriving and moving.
 *
 * A pick mounts its gauge only after a server-backed preview answers, so for a
 * while after `aria-pressed` flips there is NO gauge — and a seat pass read in
 * that window reports `settled` truthfully, about a world the gauge is about to
 * change. Measured: the toggle proof clicked `edge-pick-0` at its old seat while
 * `fillet-radius-handle` was mounting onto it. So this settle is on the chrome
 * itself: its quantised rectangles unchanged across consecutive reads.
 */
async function waitForChromeStill(page: Page, timeoutMs = 10_000) {
  const read = () =>
    page.evaluate(() =>
      [...document.querySelectorAll('[data-gauge], [data-testid$="-readout"]')]
        .map((el) => {
          const r = el.getBoundingClientRect();
          return [r.left, r.top, r.width, r.height]
            .map((v) => Math.round(v / 4))
            .join(",");
        })
        .join("|"),
    );
  const deadline = Date.now() + timeoutMs;
  let previous = await read();
  let still = 0;
  while (still < 3) {
    await page.waitForTimeout(150);
    const current = await read();
    still = current === previous ? still + 1 : 0;
    previous = current;
    if (Date.now() > deadline) {
      throw new Error(`waitForChromeStill: gauge chrome still moving`);
    }
  }
}

/** The face-burial pass has drained against the CURRENT camera. */
async function expectFaceSeatsSettled(page: Page, label: string) {
  const started = Date.now();
  await expect(page.getByTestId("viewport")).toHaveAttribute(
    "data-face-mark-seats",
    "settled",
    { timeout: 60_000 },
  );
  console.log(
    `    [face-seats] ${label}: settled in ${Date.now() - started} ms`,
  );
}

/** One pick proxy as the census sees it. */
interface Proxy {
  id: string;
  /** The overlay ordinal parsed out of the test id, or -1 when it has none. */
  index: number;
  label: string;
  /** The overlay's own claim that this mark's subject is behind the material. */
  buried: boolean;
  /** Is a hidden-line ghost drawn for it? */
  ghost: boolean;
  cx: number;
  cy: number;
  w: number;
  h: number;
  /** What `elementFromPoint` resolves to at the proxy's own centre. */
  topId: string;
  topTag: string;
}

/**
 * Every proxy matching any of `prefixes`, with the element on top of each.
 *
 * ONE `page.evaluate`, because a per-proxy round trip is the cost in a
 * browser-driven census and a hundred of them is most of a minute.
 */
async function censusProxies(
  page: Page,
  prefixes: readonly string[],
): Promise<Proxy[]> {
  return page.evaluate((wanted: readonly string[]) => {
    const selector = wanted.map((p) => `[data-testid^="${p}"]`).join(",");
    return [...document.querySelectorAll(selector)].map((el) => {
      const rect = el.getBoundingClientRect();
      const id = el.getAttribute("data-testid") ?? "?";
      const cx = Math.round((rect.left + rect.right) / 2);
      const cy = Math.round((rect.top + rect.bottom) / 2);
      const top = document.elementFromPoint(cx, cy);
      const trailing = /-(\d+)$/.exec(id);
      return {
        id,
        index: trailing === null ? -1 : Number(trailing[1]),
        label: el.getAttribute("aria-label") ?? "",
        buried: el.getAttribute("data-buried") === "true",
        ghost:
          el.parentElement?.querySelector("[data-buried-ghost]") !== null &&
          el.parentElement?.querySelector("[data-buried-ghost]") !== undefined,
        cx,
        cy,
        w: Math.round(rect.width * 10) / 10,
        h: Math.round(rect.height * 10) / 10,
        topId:
          top === null
            ? "(none)"
            : (top.getAttribute("data-testid") ??
              top.closest("[data-testid]")?.getAttribute("data-testid") ??
              "(untagged)"),
        topTag: top === null ? "(none)" : top.tagName,
      };
    });
  }, prefixes);
}

/**
 * Take every mark out of the pointer's path — the mark AND the slot wrappers
 * around it, stopping BEFORE the ancestor that also contains the canvas, which
 * is the r3f container and would take the hit-test down with it. Returns how
 * many nodes were muted, so a mute that silently did nothing cannot be mistaken
 * for a body that answers nothing.
 *
 * ## Restore EXACTLY, not to the empty string
 *
 * The obvious undo (`style.pointerEvents = ""`) is not an undo: the shared
 * portal host carries `pointer-events:none` as part of its own INLINE
 * `cssText`, so clearing the property deletes the host's own rule and leaves it
 * live for the rest of the page's life. That cost a whole diagnostic pass here
 * — the first version of this spec ran three armed modes in one test, and the
 * fillet leg's "undo" silently changed what the shell leg was measuring, which
 * read as a fix that had not worked. Each previous value is snapshotted on the
 * node and put back verbatim.
 */
async function muteMarks(page: Page, prefixes: readonly string[]) {
  return page.evaluate((wanted: readonly string[]) => {
    const canvas = document.querySelector('[data-testid="viewport"] canvas');
    const selector = wanted.map((p) => `[data-testid^="${p}"]`).join(",");
    let muted = 0;
    for (const el of document.querySelectorAll(selector)) {
      let node: HTMLElement | null = el as HTMLElement;
      while (node !== null && !node.contains(canvas)) {
        if (node.dataset["mutedFrom"] === undefined) {
          node.dataset["mutedFrom"] = node.style.pointerEvents;
        }
        node.style.pointerEvents = "none";
        muted += 1;
        node = node.parentElement;
      }
    }
    return muted;
  }, prefixes);
}

/** Undo {@link muteMarks}, restoring each node's own previous inline value. */
async function unmuteMarks(page: Page): Promise<void> {
  await page.evaluate(() => {
    for (const el of document.querySelectorAll<HTMLElement>(
      "[data-muted-from]",
    )) {
      el.style.pointerEvents = el.dataset["mutedFrom"] ?? "";
      delete el.dataset["mutedFrom"];
    }
  });
}

/** How long a hover answer is allowed to take to appear before it is "none". */
const HOVER_SETTLE_MS = 1_500;

/** Read one dataset stamp off the viewport. */
async function readStamp(page: Page, stamp: string): Promise<string | null> {
  return page.getByTestId("viewport").getAttribute(stamp);
}

/** Poll `stamp` until `done`, or give up and return what it last read. */
async function pollStamp(
  page: Page,
  stamp: string,
  done: (value: string | null) => boolean,
): Promise<[string | null, boolean]> {
  const deadline = Date.now() + HOVER_SETTLE_MS;
  for (;;) {
    const value = await readStamp(page, stamp);
    if (done(value)) return [value, true];
    if (Date.now() > deadline) return [value, false];
    await page.waitForTimeout(25);
  }
}

/**
 * Move a REAL pointer to a screen point and read back what the app says is
 * under it. This — not `elementFromPoint` — is the reachability verdict.
 *
 * ## The settle, named
 *
 * The stamp is written from a React effect after a state update, while
 * `waitForFrames` counts r3f frames on a DEMAND-driven loop; the two are not
 * ordered with respect to one another, so a fixed frame count would be supplying
 * the synchronisation by accident. Both halves are therefore explicit: park off
 * the model and wait for the stamp to CLEAR — which is what stops a latched
 * neighbour being scored as this proxy's success — then move onto the point and
 * wait for a value to APPEAR. A point that never produces one within the budget
 * is genuinely unanswered, and is reported as `(none)` rather than inferred from
 * silence.
 *
 * (Measured: making this explicit changed nothing about the readings — they were
 * byte-identical to the frame-counted version — which is the evidence that the
 * settle is discipline rather than a patch over a race.)
 */
async function verdictAt(
  page: Page,
  x: number,
  y: number,
  stamp: string,
): Promise<string | null> {
  await page.mouse.move(4, 4);
  const [, cleared] = await pollStamp(page, stamp, (v) => v === null);
  if (!cleared) {
    throw new Error(
      `verdictAt: ${stamp} would not clear with the pointer parked off the ` +
        `model — every reading after this one would be a stale latch`,
    );
  }
  await page.mouse.move(x, y);
  const [value] = await pollStamp(page, stamp, (v) => v !== null);
  return value;
}

/** One proxy, scored. */
interface CensusRow extends Proxy {
  /**
   * `data-buried` as drawn AT REST — read in the opening snapshot, before the
   * pointer has moved at all. Compared with `buried` (read at the hover) it
   * catches a mark whose drawn state is stale until something re-renders it.
   */
  restBuried: boolean;
  /** What the app answered under a real pointer, marks LIVE. */
  live: string | null;
  /** What the app answered at the same pixel with every mark muted. */
  body: string | null;
  /** The proxy answers with its own subject. */
  reaches: boolean;
  /**
   * The proxy is buried and hands the pixel to whatever is in front of it —
   * the DESIRED behaviour, not a defect: that pixel belongs to the face the
   * modeller can see, and the keyboard is the route to the buried one.
   */
  yields: boolean;
  /**
   * The proxy takes a pixel whose visible owner is something else — a live
   * mark standing on a face in front of it. This is the defect that let
   * "click the front wall" open the bottom one.
   */
  steals: boolean;
}

/**
 * Read one proxy's own state AT THIS MOMENT — burial, ghost, and what is on
 * top of it.
 *
 * Deliberately re-read per hover rather than taken from the opening snapshot.
 * Burial is a live property of the current camera, and the seat passes
 * legitimately revise it as the scene settles; comparing a snapshot taken
 * minutes earlier against a verdict taken now is the same error as taking a
 * BEFORE and an AFTER in two different states, and it reports correct yielding
 * behaviour as a defect. Measured: seven edge marks were classified
 * UNREACHABLE purely because the census had recorded `buried=false` for them
 * before the pass had revised it.
 */
async function stateOf(
  page: Page,
  id: string,
  x: number,
  y: number,
): Promise<Pick<Proxy, "buried" | "ghost" | "topId" | "topTag">> {
  return page.evaluate(
    ([testId, px, py]: [string, number, number]) => {
      const el = document.querySelector(`[data-testid="${testId}"]`);
      const top = document.elementFromPoint(px, py);
      return {
        buried: el?.getAttribute("data-buried") === "true",
        ghost: el?.parentElement?.querySelector("[data-buried-ghost]") != null,
        topId:
          top === null
            ? "(none)"
            : (top.getAttribute("data-testid") ??
              top.closest("[data-testid]")?.getAttribute("data-testid") ??
              "(untagged)"),
        topTag: top === null ? "(none)" : top.tagName,
      };
    },
    [id, x, y] as [string, number, number],
  );
}

/** Hover every proxy twice — marks live, then marks muted — and classify. */
async function scoreProxies(
  page: Page,
  proxies: readonly Proxy[],
  stamp: string,
  prefixes: readonly string[],
): Promise<CensusRow[]> {
  const live: (string | null)[] = [];
  const atHover: Awaited<ReturnType<typeof stateOf>>[] = [];
  for (const proxy of proxies) {
    live.push(await verdictAt(page, proxy.cx, proxy.cy, stamp));
    atHover.push(await stateOf(page, proxy.id, proxy.cx, proxy.cy));
  }
  const muted = await muteMarks(page, prefixes);
  expect(
    muted,
    "the mute must actually take nodes out of the pointer's path, or every " +
      "body reading below is really a mark reading",
  ).toBeGreaterThan(0);
  const body: (string | null)[] = [];
  for (const proxy of proxies) {
    body.push(await verdictAt(page, proxy.cx, proxy.cy, stamp));
  }
  await unmuteMarks(page);

  return proxies.map((proxy, i) => {
    const l = live[i] ?? null;
    const b = body[i] ?? null;
    // The state AS READ AT THE HOVER, not as snapshotted before the pass had
    // finished revising it — see `stateOf`.
    const now = atHover[i] ?? proxy;
    const reaches = l !== null && Number(l) === proxy.index;
    return {
      ...proxy,
      restBuried: proxy.buried,
      ...now,
      live: l,
      body: b,
      reaches,
      // A buried mark's whole obligation is to NOT answer for its own
      // subject: the pixel belongs to whatever the user can see there —
      // the body, or a live mark standing on a face in front. Requiring it
      // to yield to the BODY specifically was wrong, and measured wrong: on
      // the shelled housing the outer floor's ghost sits a few px from the
      // cavity floor's LIVE mark, and the pointer correctly takes that.
      yields: !reaches && now.buried,
      steals: reaches && !now.buried && b !== null && Number(b) !== proxy.index,
    };
  });
}

/** The census, printed as the attribution table the board item asks for. */
function reportCensus(title: string, rows: readonly CensusRow[]): void {
  const reach = rows.filter((r) => r.reaches && !r.steals);
  const yields = rows.filter((r) => r.yields);
  const steals = rows.filter((r) => r.steals);
  const lost = rows.filter((r) => !r.reaches && !r.yields);
  console.log(
    `\n    == ${title} ==\n` +
      `    ${rows.length} proxies: ` +
      `${reach.length} reach their own subject, ` +
      `${yields.length} buried and correctly yielding, ` +
      `${steals.length} STEALING a visible neighbour's pixel, ` +
      `${lost.length} UNREACHABLE`,
  );
  const table = (label: string, set: readonly CensusRow[]) => {
    if (set.length === 0) return;
    console.log(`      -- ${label}`);
    const by = new Map<string, number>();
    for (const row of set) {
      const key = row.buried ? `buried behind body (${row.topId})` : row.topId;
      by.set(key, (by.get(key) ?? 0) + 1);
    }
    for (const [occluder, count] of [...by].sort((a, b) => b[1] - a[1])) {
      console.log(`      ${String(count).padStart(3)}  <- ${occluder}`);
    }
    for (const row of set) {
      console.log(
        `         ${row.id} @ (${row.cx},${row.cy}) ${row.w}x${row.h} ` +
          `buried=${row.buried} ghost=${row.ghost} top=${row.topId}/${row.topTag} ` +
          `live=${row.live ?? "-"} body=${row.body ?? "-"}`,
      );
    }
  };
  const flipped = rows.filter((r) => r.restBuried !== r.buried);
  console.log(
    `      at rest: ${rows.filter((r) => r.restBuried).length} drawn buried, ` +
      `${rows.filter((r) => !r.restBuried).length} drawn live; burial CHANGED ` +
      `by the pointer arriving: ${
        flipped.length === 0
          ? "none"
          : flipped
              .map((r) => `${r.id}(${r.restBuried}->${r.buried})`)
              .join(" ")
      }`,
  );
  table("buried, yielding to what is in front (correct)", yields);
  table("STEALING a visible neighbour's pixel", steals);
  table("UNREACHABLE", lost);
}

/** Open the housing, framed and rendered. */
async function openHousing(
  page: Page,
  options: { shelled?: boolean } = {},
): Promise<void> {
  await installSceneProbe(page); // before goto: the settles read the camera
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Gearbox housing");
  await (options.shelled === true ? seedShelledHousing : seedHousing)(
    page,
    account.token,
    part.id,
  );
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
    .toBeGreaterThan(16);
  await page.getByTestId("view-iso").click();
  await waitForCameraStill(page);
  const viewport = page.getByTestId("viewport");
  await viewport.evaluate((node) => {
    node.dataset["fitRect"] = "";
  });
  await page.getByTestId("view-fit").click();
  await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
    timeout: 20_000,
  });
  await waitForCameraStill(page);
}

async function armFillet(page: Page): Promise<void> {
  await expect(page.getByTestId("new-fillet")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-fillet").click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
  await page.getByTestId("fillet-mode-pick").click();
  await expect(
    page.locator('[data-testid^="edge-pick-"]').first(),
  ).toBeAttached({ timeout: 20_000 });
  await expectSeatsSettled(page, "fillet armed");
  await waitForCameraStill(page);
}

async function armShell(page: Page): Promise<void> {
  await expect(page.getByTestId("new-shell")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-shell").click();
  await expect(page.getByTestId("shell-editor")).toBeVisible();
  await expect(
    page.locator('[data-testid^="shell-face-"]').first(),
  ).toBeAttached({ timeout: 20_000 });
  await expectFaceSeatsSettled(page, "shell armed");
  await waitForCameraStill(page);
}

async function armHoleFacePick(page: Page): Promise<void> {
  await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-hole").click();
  await expect(page.getByTestId("hole-editor")).toBeVisible();
  await expect(
    page.locator('[data-testid^="plane-pick-face-"]').first(),
  ).toBeAttached({ timeout: 20_000 });
  await expectFaceSeatsSettled(page, "hole face pick armed");
  await waitForCameraStill(page);
}

/**
 * ONE ARMED MODE PER TEST, on its own page.
 *
 * The first version of this spec censused all three in one test and the legs
 * contaminated each other through the shared portal host — see `muteMarks`. A
 * census is a measurement, and a measurement that shares mutable state with the
 * previous measurement is reporting the two of them together.
 */
async function censusLeg(
  page: Page,
  title: string,
  arm: (page: Page) => Promise<void>,
  prefix: string,
  stamp: string,
  options: { shelled?: boolean; shot?: string } = {},
): Promise<CensusRow[]> {
  await openHousing(page, { shelled: options.shelled });
  await arm(page);
  const proxies = await censusProxies(page, [prefix]);
  expect(
    proxies.length,
    `no ${prefix} proxies were found at all — a census that walks nothing ` +
      `makes every assertion below vacuously true`,
  ).toBeGreaterThan(0);
  const rows = await scoreProxies(page, proxies, stamp, [prefix]);
  reportCensus(title, rows);
  await captureEvidence(page, options.shot ?? prefix);
  return rows;
}

/**
 * Before/after evidence for the founder, written ONLY when `PICK_PROXY_SHOTS`
 * names a directory. Not `docs/screenshots/`: those are committed baselines
 * this change does not own, and a routine run must never rewrite them.
 */
async function captureEvidence(page: Page, slug: string): Promise<void> {
  const dir = process.env["PICK_PROXY_SHOTS"];
  if (dir === undefined || dir === "") return;
  const size = page.viewportSize();
  // Park the pointer off the model so no hover highlight is in the shot.
  await page.mouse.move(4, 4);
  await waitForFrames(page, 2);
  await page.screenshot({
    path: `${dir}/${slug.replace(/-$/, "")}-${size?.width ?? 0}.png`,
  });
}

test.describe("board #76 — pick proxy census", () => {
  test("fillet edge marks reach their edge, or say they are behind the part", async ({
    page,
  }) => {
    test.setTimeout(600_000);
    const rows = await censusLeg(
      page,
      "fillet / edge marks",
      armFillet,
      "edge-pick-",
      "data-edge-pick-hover",
    );
    await expectNoLostProxies(page, rows, {
      toggles: true,
      settle: (p) => expectSeatsSettled(p, "after a pick"),
    });
  });

  test("shell face marks reach their face, or yield it to the face in front", async ({
    page,
  }) => {
    test.setTimeout(600_000);
    const rows = await censusLeg(
      page,
      "shell / face marks",
      armShell,
      "shell-face-",
      "data-shell-face-hover",
    );
    await expectNoLostProxies(page, rows, {
      toggles: true,
      settle: (p) => expectFaceSeatsSettled(p, "after a pick"),
    });
  });

  test("hole plane-pick marks reach their face, or yield it to the face in front", async ({
    page,
  }) => {
    test.setTimeout(600_000);
    const rows = await censusLeg(
      page,
      "hole / plane-pick face marks",
      armHoleFacePick,
      "plane-pick-face-",
      "data-face-pick-hover",
    );
    await expectNoLostProxies(page, rows, { toggles: false });
  });

  test("on the SHELLED housing, an inner wall's mark does not answer for the outer wall", async ({
    page,
  }) => {
    test.setTimeout(600_000);
    const rows = await censusLeg(
      page,
      "hole / plane-pick face marks, SHELLED housing",
      armHoleFacePick,
      "plane-pick-face-",
      "data-face-pick-hover",
      { shelled: true, shot: "plane-pick-face-shelled" },
    );
    // The audit's measured pair: an inner wall's mark within a few pixels of
    // its outer twin. Report the closest pair of LIVE marks so the separation
    // is on the record, and require that no two live marks overlap — a pair
    // closer than one 24 px target is a pair where the user picks one by
    // accident, whichever z-index wins.
    const live = rows.filter((r) => !r.buried);
    let closest = Number.POSITIVE_INFINITY;
    let pair = "";
    for (let i = 0; i < live.length; i += 1) {
      for (let j = i + 1; j < live.length; j += 1) {
        const a = live[i] as CensusRow;
        const b = live[j] as CensusRow;
        const d = Math.hypot(a.cx - b.cx, a.cy - b.cy);
        if (d < closest) {
          closest = d;
          pair = `${a.id}~${b.id}`;
        }
      }
    }
    console.log(
      `    [shelled] ${rows.length} face marks, ${live.length} live; closest ` +
        `live pair ${pair} at ${closest.toFixed(1)} px`,
    );
    expect(
      closest,
      `two LIVE face marks overlap (${pair}) — one of them answers for a face ` +
        `the user is not pointing at`,
    ).toBeGreaterThanOrEqual(24);
    await expectNoLostProxies(page, rows, { toggles: false });
  });
});

/**
 * THE GATE. Every proxy must land in one of exactly two honest states, and the
 * failure message names the offenders rather than reporting a count.
 *
 *  · it reaches its own subject under a real pointer; or
 *  · it is BURIED, it says so with a hidden-line ghost, and the pixel it stands
 *    on goes to whatever is in front of it — which is the face the modeller can
 *    actually see.
 *
 * Anything else is the defect the board item is about: a proxy that is drawn,
 * is not marked buried, and answers with something other than its own subject —
 * i.e. the user aims at a mark and gets a different entity, or nothing.
 */
async function expectNoLostProxies(
  page: Page,
  rows: readonly CensusRow[],
  options: { toggles: boolean; settle?: (page: Page) => Promise<unknown> },
): Promise<void> {
  const lost = rows.filter((r) => !r.reaches && !r.yields);
  expect(
    lost.map(
      (r) =>
        `${r.id}@(${r.cx},${r.cy}) buried=${r.buried} top=${r.topId} ` +
        `live=${r.live ?? "-"} body=${r.body ?? "-"}`,
    ),
    "every drawn proxy must either answer with its own subject or be a buried " +
      "ghost handing its pixel to the face in front of it",
  ).toEqual([]);

  // NO LIVE MARK MAY TAKE A PIXEL THAT VISIBLY BELONGS TO ANOTHER FACE. This
  // is the audit's `shell-face-1`: the bottom face's mark drawn on the front
  // wall, so clicking the front wall opened the bottom. It "reaches" its own
  // subject, which is exactly why the lost-proxy gate above cannot see it —
  // measured: the solid-housing hole leg PASSED that gate with three such
  // marks on screen until this assertion existed.
  expect(
    rows
      .filter((r) => r.steals)
      .map(
        (r) =>
          `${r.id}@(${r.cx},${r.cy}) answers for itself; body says ${r.body}`,
      ),
    "a live mark stands on a pixel the body gives to a different face",
  ).toEqual([]);

  // WHAT IS DRAWN AT REST MUST BE WHAT THE POINTER FINDS. The root cause of
  // the seven "self-erasing" edge marks was a seat pass that computed their
  // burial and never published it, so they were drawn live until a hover
  // happened to re-render the overlay — then vanished from under the pointer.
  // Nothing about the scene changes between the snapshot and the hover here,
  // so any difference is the drawn state lying.
  expect(
    rows
      .filter((r) => r.restBuried !== r.buried)
      .map((r) => `${r.id}: drawn buried=${r.restBuried}, finds ${r.buried}`),
    "a mark's drawn state changed merely because the pointer arrived",
  ).toEqual([]);

  // A GHOST MUST NOT LIE. A mark drawn as a hidden line claims its subject is
  // behind the part; if pointing at the ghost reaches that very subject, the
  // subject is in plain view and the claim is false. Found by mutation: with
  // every face mark forced buried, the pointer fell through to the surface,
  // which answered the three visible faces for themselves, and no other gate
  // objected.
  expect(
    rows
      .filter((r) => r.buried && r.reaches)
      .map(
        (r) => `${r.id}@(${r.cx},${r.cy}) drawn buried, yet answers for itself`,
      ),
    "a hidden-line ghost stands on its own visible subject",
  ).toEqual([]);

  // A buried proxy must SAY it is buried. Without this the suite would pass
  // just as happily if every ghost were deleted again, which is the state that
  // shipped an asymmetric housing.
  for (const row of rows.filter((r) => r.buried)) {
    expect(row.ghost, `${row.id} is buried and draws no hidden-line cue`).toBe(
      true,
    );
  }

  // COMPANION TO THE ABOVE, because a guard whose locator can never resolve is
  // vacuous and an all-buried page would satisfy every assertion so far: prove
  // a real click at a proxy's own centre PICKS it, read back through the app's
  // own selection state (`aria-pressed`) rather than through a hover stamp.
  const reachable = rows.filter((r) => r.reaches);
  expect(
    reachable.length,
    "no proxy on this page was reachable at all — every assertion above would " +
      "then be satisfied by a page with no working picks",
  ).toBeGreaterThan(0);
  // A single-select picker COMMITS on click and tears its overlay down, so
  // only the multi-select overlays can be driven proxy by proxy; for the
  // others one proxy is proof that a real click reaches a real handler.
  const drive = options.toggles ? reachable : reachable.slice(0, 1);
  for (const proxy of drive) {
    const node = page.getByTestId(proxy.id);
    const before = await node.getAttribute("aria-pressed");
    // Park off the model first: a click at the position the pointer already
    // occupies fires no boundary events, so the app would never learn the
    // pointer had arrived.
    await page.mouse.move(4, 4);
    await waitForFrames(page, 1);
    await page.mouse.click(proxy.cx, proxy.cy);
    if (!options.toggles) {
      await expect(
        page.getByTestId("hole-face"),
        `a real click at ${proxy.id}'s own centre must seat the hole on a face`,
      ).toBeVisible({ timeout: 15_000 });
      break;
    }
    await expect(
      node,
      `a real click at ${proxy.id}'s own centre must select ${proxy.id}`,
    ).toHaveAttribute("aria-pressed", before === "true" ? "false" : "true", {
      timeout: 15_000,
    });
    // Put it back, so the next proxy is measured from the same state — by
    // clicking the mark where it is NOW. A pick can mount a gauge, and a
    // gauge can make a mark re-seat itself out from under it; a user clicks
    // the mark they can see, not the pixel it used to occupy. What sits on
    // top of that centre is read first, so a failure names its occluder
    // rather than reporting a bare count.
    // NAMED SETTLES before reading where the mark is now: the pick can mount
    // a gauge (and a gauge can re-frame the camera), and the seat pass then
    // re-owes every mark — so the camera by position, then that pass.
    await waitForChromeStill(page);
    await waitForCameraStill(page);
    await options.settle?.(page);
    await waitForCameraStill(page);
    const now = await node.boundingBox();
    expect(now, `${proxy.id} vanished after it was picked`).not.toBeNull();
    if (now === null) break;
    const nx = now.x + now.width / 2;
    const ny = now.y + now.height / 2;
    const onTop = await page.evaluate(
      ([x, y, id]: [number, number, string]) => {
        const top = document.elementFromPoint(x, y);
        const name =
          top?.closest("[data-testid]")?.getAttribute("data-testid") ??
          top?.tagName ??
          "(none)";
        const mark = document.querySelector(`[data-testid="${id}"]`);
        const seats =
          document
            .querySelector('[data-testid="viewport"]')
            ?.getAttribute("data-edge-mark-seats") ?? "-";
        const chrome = [
          ...document.querySelectorAll(
            '[data-gauge], [data-testid$="-readout"]',
          ),
        ]
          .map((el) => {
            const r = el.getBoundingClientRect();
            return `${el.getAttribute("data-testid")}[${Math.round(r.left)},${Math.round(r.top)} ${Math.round(r.width)}x${Math.round(r.height)}]`;
          })
          .join(" ");
        return `${name} (mark buried=${mark?.getAttribute("data-buried")}, seats=${seats}; chrome ${chrome})`;
      },
      [nx, ny, proxy.id] as [number, number, string],
    );
    await page.mouse.move(4, 4);
    await waitForFrames(page, 1);
    await page.mouse.click(nx, ny);
    await expect(
      node,
      `a real click on ${proxy.id} where it now sits (${Math.round(nx)},` +
        `${Math.round(ny)}) must UN-pick it — on top there: ${onTop}`,
    ).toHaveAttribute("aria-pressed", before ?? "false", { timeout: 15_000 });
  }
}

/** One edge mark, and whether a piece of a GAUGE is what sits on its centre. */
interface GaugeCover {
  id: string;
  cx: number;
  cy: number;
  buried: boolean;
  /** `data-gauge` of the element on top of the mark's centre, or null. */
  gauge: string | null;
}

async function gaugeCovers(page: Page): Promise<GaugeCover[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll('[data-testid^="edge-pick-"]')].map((el) => {
      const r = el.getBoundingClientRect();
      const cx = Math.round((r.left + r.right) / 2);
      const cy = Math.round((r.top + r.bottom) / 2);
      const top = document.elementFromPoint(cx, cy);
      return {
        id: el.getAttribute("data-testid") ?? "?",
        cx,
        cy,
        buried: el.getAttribute("data-buried") === "true",
        // Gauge chrome: the grip and sleeve carry `data-gauge`; the value
        // readout is a live control that carries only its test id, and is a
        // GAUGE's readout only if a `data-gauge` element names its prefix —
        // `measure-readout` and `selection-readout` are HUD, not gauges.
        gauge: (() => {
          const tagged = top?.closest("[data-gauge]");
          if (tagged !== null && tagged !== undefined) {
            return tagged.getAttribute("data-gauge");
          }
          const readout = top?.closest('[data-testid$="-readout"]');
          const id = readout?.getAttribute("data-testid") ?? null;
          if (id === null) return null;
          const owner = id.slice(0, -"-readout".length);
          return document.querySelector(
            `[data-gauge="${CSS.escape(owner)}"]`,
          ) === null
            ? null
            : id;
        })(),
      };
    }),
  );
}

/** Total on-screen area of the gauge's own DOM — proves the gauge EXISTS. */
async function gaugeArea(page: Page, gaugeId: string): Promise<number> {
  return page.evaluate(
    (id: string) =>
      [...document.querySelectorAll(`[data-gauge="${id}"]`)].reduce(
        (sum, el) => {
          const r = el.getBoundingClientRect();
          return sum + r.width * r.height;
        },
        0,
      ),
    gaugeId,
  );
}

test.describe("board #76 — a gauge does not cover the mark that spawned it", () => {
  test("a picked edge can be UN-picked by a real click on its own mark", async ({
    page,
  }) => {
    test.setTimeout(600_000);
    await openHousing(page);
    await armFillet(page);

    // Pick the first live mark whose pick mounts the radius gauge — through a
    // REAL click, confirmed by the app's own selection state.
    const marks = (await censusProxies(page, ["edge-pick-"])).filter(
      (m) => !m.buried,
    );
    let picked: Proxy | undefined;
    for (const mark of marks) {
      await page.mouse.move(4, 4);
      await waitForFrames(page, 1);
      await page.mouse.click(mark.cx, mark.cy);
      const node = page.getByTestId(mark.id);
      // NAMED SETTLE, not a frame count: the pick lands through a React
      // state update and the gauge mounts a render later, so wait on the
      // app's own answers — the mark's pressed state, then the grip.
      const pressed = await expect
        .poll(() => node.getAttribute("aria-pressed"), { timeout: 3_000 })
        .toBe("true")
        .then(
          () => true,
          () => false,
        );
      if (!pressed) continue;
      const mounted = await expect
        .poll(() => page.getByTestId("fillet-radius-handle").count(), {
          timeout: 5_000,
        })
        .toBeGreaterThan(0)
        .then(
          () => true,
          () => false,
        );
      if (mounted) {
        picked = mark;
        break;
      }
      await page.mouse.move(4, 4);
      await page.mouse.click(mark.cx, mark.cy);
      await expect(node).toHaveAttribute("aria-pressed", "false");
    }
    expect(picked, "no live edge mark mounted the radius gauge").toBeDefined();
    if (picked === undefined) return;
    await expect(page.getByTestId("fillet-radius-handle")).toBeVisible({
      timeout: 15_000,
    });

    // NAMED SETTLES: the gauge's chrome until it stops arriving and moving; a
    // gauge mounting can re-frame the camera, and a re-frame re-owes every
    // seat — so the camera by POSITION, then the seat pass, then the camera
    // once more in case the seat pass's own frames moved it.
    await waitForChromeStill(page);
    await waitForCameraStill(page);
    await expectSeatsSettled(page, "radius gauge mounted");
    await waitForCameraStill(page);

    // COMPANION: the gauge is really there, with area, so the "nothing is
    // covered by it" assertion below cannot pass because it never mounted.
    expect(await gaugeArea(page, "fillet-radius")).toBeGreaterThan(0);

    const covers = await gaugeCovers(page);
    const stolen = covers.filter((c) => c.gauge !== null);
    await captureEvidence(page, "fillet-gauge-picked");
    console.log(
      `    [gauge] picked ${picked.id}; marks with a piece of a gauge on ` +
        `their centre: ${
          stolen.length === 0
            ? "none"
            : stolen
                .map((c) => `${c.id}@(${c.cx},${c.cy})<-${c.gauge}`)
                .join(" ")
        }`,
    );
    expect(
      stolen.map((c) => `${c.id}<-${c.gauge}`),
      "no edge mark may sit under a gauge — a picked edge whose mark the gauge " +
        "covers can only be dropped by clearing every pick",
    ).toEqual([]);

    // And the property that matters to the user: the picked edge can be
    // un-picked by a real click on its own mark, wherever it now sits.
    const box = await page.getByTestId(picked.id).boundingBox();
    expect(box).not.toBeNull();
    if (box === null) return;
    await page.mouse.move(4, 4);
    await waitForFrames(page, 1);
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await expect(
      page.getByTestId(picked.id),
      `a real click on ${picked.id}'s own mark must un-pick it`,
    ).toHaveAttribute("aria-pressed", "false", { timeout: 15_000 });
  });
});
