# Agent operating protocol

**Every agent that touches this repo reads this before its first tool call.**
It holds what every orchestrator brief used to restate — ~40 lines per brief,
six briefs a wave. Your brief now carries only three things: the **task**, your
**territory**, and your **ports**. Everything else is here.

`CLAUDE.md` holds the repo-wide rules (and is auto-loaded); this file holds
the per-agent ones, and neither repeats the other. Long-form evidence for each
rule lives in `docs/LESSONS.md`, under a stable anchor. Read it when you need
to know *why*; you do not need it to follow the rule.

---

## 1. Start

1. **Confirm you are in a worktree.** `git rev-parse --show-toplevel` must NOT be
   `/home/user/3d-cad`. A builder or QA agent in the shared checkout stops and
   says so in its first message — the shared checkout is where overwrites,
   index sweeps and swallowed commits happen. (Read-only reviewers may read it.)
2. **Reset to the branch tip before reading any source.**
   `git fetch origin <branch>`, then `git rev-list --count HEAD..origin/<branch>`.
   Nonzero — which it is ~100% of the time; worktrees seed at the last merge into
   `main` — means `git reset --hard origin/<branch>` first.
3. `pnpm install --frozen-lockfile` before any lint or typecheck. A failure in a
   file you did not touch, before this runs, is your environment — not a
   colleague's regression.
4. Scratch files go in `$SCRATCHPAD/<your-slug>/`, **never the scratchpad root**
   (a stdlib-shadowing `inspect.py` lives there and breaks imports in a way that
   reads like a broken venv).

## 2. Territory

- **Edit only the paths your brief grants.** If the fix needs a file outside
  them, stop and report — do not cross. Overlapping edits are the root of every
  overwrite in this repo.
- **Territory limits EDITS, not RUNS.** Run the e2e specs that exercise the code
  you change, even when you may not edit them. On 2026-09-16 a camera change
  broke three specs owned by another agent because its builder was told e2e was
  not its territory, and never ran them. If a spec you may not edit goes red
  because of your change, report it with the failure text — that is part of
  your deliverable.
- **Builders never edit `docs/ROADMAP.md` or `docs/BACKLOG.md`.** Put
  `Doc-tick: groomer` in the commit; the `backlog-groomer` owns the board.
- **Never mint a board ID.** Use the ID your brief names, or none. On
  2026-09-24 a builder titled its commits "PERF-REAL-3" for a new defect while
  that ID already named a different open item, and the groomer had to untangle
  the two. New work gets its ID from the groomer.

## 3. Commit

- One logical item per commit, conventional-commit message.
- **Never `git add` and `git commit` in the same shell command.** Two calls, and
  read `git diff --cached` IN FULL in between. Never `git add -A`.
- **Never `git stash`** — the stash list is shared across worktrees, so a pop can
  hand you a sibling's work and send yours to them, exit 0. Use
  `git diff > $SCRATCHPAD/<slug>/wip.patch` and `git apply`.
- Trailers: `Doc-tick: groomer` (builders), then the attribution lines your brief
  gives you. No model names anywhere in commits, code or comments.

## 4. Push — after every gated fix, and verify by value

- **Push after EACH gated fix, not at the end of your task.** Session limits kill
  a whole wave at once; anything unpushed dies with you. Twice in one week
  finished, gated commits were stranded in worktrees this way.
- `git push origin HEAD:<branch>`. The `-u origin <branch>` form, run from a
  worktree, pushes the *shared* checkout's branch and truthfully prints
  "Everything up-to-date" while your commit goes nowhere.
- **Verify:** `git ls-remote origin <branch>` must equal `git rev-parse HEAD`.
  Exit code 0 is not evidence.
- Rejected → `git pull --rebase origin <branch>`, re-run your gates, push again.
- Push each commit separately — a commit in the middle of a multi-commit push
  gets no CI run at all.

## 5. CI

**You cannot read CI** — `api.github.com` is policy-denied for every subagent;
do not try to route around it. Push, stop, and report your SHAs. The
orchestrator reads all three workflows (`ci`, `e2e`, `deploy-path`) and relays
any failure text back to you.

## 6. Gates before every commit

- **`just lint`** — not `ruff check` alone; it also runs `prettier --check .` and
  `ruff format --check`. Use `uv run ruff`, never a bare PATH `ruff`.
- Typecheck and unit tests, scoped to your **whole diff** — a signature change
  breaks its callers and their tests, not just the file you were editing.
- The e2e specs covering your change, on your own isolated stack (§2).
- Schema change → `just gen`, then **`just gen-verify`** (reads the index; `gen-check`
  reads the working tree and can bless a commit CI rejects).
- Kernel-adjacent → the geometry pytest suite and the goldens.

## 7. Stack and processes

- **Native boot only** — the Docker registry is 403 here. SQLite schema via
  SQLAlchemy `metadata.create_all` (not alembic); geometry with `--workers 1` and
  `S3_URL` unset; `LOFT_ENV=dev` on the gateway. Recipe: `CLAUDE.md` →
  "Environment recipes" (schema step copied from `scripts/e2e.sh`).
- `rm -f` your own SQLite files before a boot: `create_all` does not migrate,
  so an old file is silently reused at its old schema.
- Never put scratch files in `apps/web/test-results/` (Playwright wipes it) or
  the repo root (`prettier --check .` walks the filesystem and fails everyone).
- Use the **ports in your brief**; prefix SQLite files with your slug and
  `rm -f` only your own. **Never touch 8000/8001/8002/5173** (the shared stack).
- Boot with `setsid nohup … < /dev/null &` plus a health-poll loop. **Never
  `Bash(run_in_background)`** for a stack — the harness reaps the listener.
- **Kill by port, LISTENERS only:** `lsof -ti tcp:<port> -sTCP:LISTEN`. Plain
  `lsof -ti :<port>` also returns processes merely CONNECTED to the port — our
  gateway holds sockets to documents, so it can kill the wrong service and leave
  one running on a deleted DB. **Never `pkill -f`** and never a process-name
  grep — both kill other agents' stacks. (`ss` resolves nothing in this
  container; a teardown built on it silently does nothing.)
- `pnpm run <script> -- <args>` **drops the `--`**. Never write it; check the
  port Vite actually printed.
- **Restart Vite** after touching `packages/design`, `tailwind-preset.ts`,
  `tokens.ts` or `vite.config.ts`, and between mutation legs — then confirm the
  SERVED bytes. A stale transform makes a mutation check pass when it must fail.
- Playwright reporting line numbers that don't match the file →
  `rm -rf /tmp/playwright-transform-cache-0` and re-run cold.
- A native uvicorn returning `attempt to write a readonly database` after ~10 min
  is a stale handle, not a regression — bounce your own three services.
- **Tear down your whole stack, by port, before you report.**

## 8. Evidence

- **Every new assertion must have been seen to fail.** Mutate the code, watch it
  redden, revert, and say so. An assertion you have never seen fail is not a gate.
- **Assert the property, not a stand-in for it.** A screen position cannot tell
  "the thing moved" from "the camera moved". `toBeVisible()` passes for clipped
  and `sr-only` elements. A 2xx proves a request parsed, not that it meant
  anything (params models are `extra="ignore"`).
- **No `click({ force: true })`** outside the `clickRefusedControl` helper.
- A DOM wait followed by a canvas assertion needs a **named** settle. For the
  camera, settle on **position** (`waitForCameraStill`); `waitForCameraRest`
  checks direction only and is blind to a re-frame.
- Before/after pairs must be taken in the same state, with the settle named.
  Prefer **attribution** (what is on top of each item) to subtraction.
- Census the **call** (`toHaveCount(`), not the argument. Test ids are often
  template-assembled — prove an id is absent in the running DOM, not by grep.
- A visible change ships **before/after screenshots** at 1280×800 and a
  small-laptop width, and you look at them — the screenshot is the only check
  that asks whether the thing is legible.

## 9. Report

Evidence, not narration:
- what you changed, and the root cause (not the symptom);
- every gate you ran, with counts;
- which assertion you saw redden;
- anything you did NOT do, and why;
- the pushed SHAs, each verified with `git ls-remote`.
