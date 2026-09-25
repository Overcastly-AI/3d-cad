# Environment (the Claude Code sandbox)

Read this before booting a stack or chasing a failure that looks like the
environment. Each item here has cost real time before.

## Booting

- **No Docker images.** The Docker registry's blob CDN returns 403, so
  `just dev` and `docker compose` cannot run here. Boot natively instead:
  [QUICKSTART Option B](./QUICKSTART.md#option-b--container-free-development),
  or let `scripts/e2e.sh` boot and tear down its own stack
  (`GATEWAY_PORT` / `DOCUMENTS_PORT` / `GEOMETRY_PORT` pick the ports).
- **SQLite, not Postgres,** for a native boot. Create the schema with
  `metadata.create_all` exactly as `scripts/e2e.sh` does, never with alembic
  (the migrations emit Postgres-only SQL). `create_all` does not migrate, so
  run `rm -f` on your old `.db` files first.
- Geometry: `--workers 1` with `S3_URL` unset. Gateway: `LOFT_ENV=dev` with
  `REDIS_URL` unset.
- **Bind to `127.0.0.1`,** not `localhost`. There is no IPv6 loopback here,
  but CI is dual-stack.
- **Start a long-lived stack with `setsid nohup ... < /dev/null &`** and a
  health-poll loop (`scripts/smoke-healthz.sh <port>`). The harness kills
  anything started with `Bash(run_in_background)`.
- **Use your own ports.** Stop only your own listeners, by port:
  `lsof -ti tcp:<port> -sTCP:LISTEN`. Never `pkill -f`, because it also kills
  other agents' stacks.
- **Playwright reuses any server on :5173,** even one serving another
  worktree's code. Check the port before running e2e.

## Tools

- `uv python install` returns 403. Use the system Python
  (`uv sync` picks 3.12). Install `just` with `uv tool install rust-just`.
- Use `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` for Playwright.
- The disk is small. Do not create extra worktrees or `node_modules`
  trees you do not need, and clean up your scratch files.
- Never leave scratch files in the repo root (`prettier --check .` walks it)
  or in `apps/web/test-results/` (Playwright wipes it).
- If Playwright reports line numbers that do not match the file, clear its
  cache with `rm -rf /tmp/playwright-transform-cache-0`.
- vitest loads a second copy of three.js, so use the `isMesh` /
  `isPerspectiveCamera` flags rather than `instanceof` against three.js
  classes.

## Network

`api.github.com` is blocked for subagents; only the orchestrator reads CI.
GitHub release assets are also blocked. `git clone` over HTTPS,
raw.githubusercontent.com, PyPI and npm all work.
