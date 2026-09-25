---
name: run-stack
description: Bring the Loft stack up (natively in the sandbox, or via compose where Docker works) on your own ports and verify it, so a change can be seen working in the real app. Use before QA, for screenshots, or to reproduce a user-facing bug.
---

# Run the Loft stack

Read `docs/ENVIRONMENT.md` first if you are in the Claude Code sandbox.

## Just run e2e specs

`scripts/e2e.sh` boots geometry, documents and gateway on SQLite, runs
Playwright, and tears everything down:

```bash
GATEWAY_PORT=8300 DOCUMENTS_PORT=8301 GEOMETRY_PORT=8302 \
  scripts/e2e.sh --web-only -- e2e/<spec>.ts
```

Playwright starts Vite on :5173 and reuses anything already listening there,
so check that port first.

## A stack you can drive by hand

Follow QUICKSTART Option B (container-free) with your own ports. Start each
service with `setsid nohup ... < /dev/null &`, then poll until healthy:

```bash
scripts/smoke-healthz.sh <gateway_port>   # /healthz + /readyz on all three
```

Point Vite at your gateway with `GATEWAY_ORIGIN=http://127.0.0.1:<port>`.

## Where Docker works

`just dev` runs the full stack with hot reload, and `scripts/dev-instance.sh <N>`
runs an isolated copy with ports offset by N*100. `just compose-smoke` proves
the self-host path.

## Teardown

Stop only what you started, by port:
`kill $(lsof -ti tcp:<port> -sTCP:LISTEN)`. Remove your own SQLite files.
