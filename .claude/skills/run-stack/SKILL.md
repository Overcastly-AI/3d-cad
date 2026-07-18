---
name: run-stack
description: Bring the Loft stack up locally (or as an isolated per-agent instance) and verify it end-to-end. Use before any QA pass, after infra changes, or whenever a change needs to be seen working in the real app.
---

# Run the Loft stack

## Default (single instance)

```bash
just dev          # db + redis + minio (compose) + services + web, hot reload
```

Verify before declaring it up — never assume:

```bash
curl -sf localhost:8000/healthz   # gateway
curl -sf localhost:8001/healthz   # documents
curl -sf localhost:8002/healthz   # geometry worker health
curl -sf localhost:5173           # web (dev server)
```

All four must pass. If a service is unhealthy, read its logs
(`docker compose logs <svc>` or the foreground process output) and
root-cause — do not restart-and-hope.

## Isolated instance (parallel agents)

Each parallel agent runs its own stack from its own worktree:

```bash
scripts/dev-instance.sh <N>   # compose project loft-<N>, ports offset by N*100
```

Never kill processes by name pattern — sibling agents' instances match too.
Check `ps`/port ownership and kill by PID only, or just use your own instance.

## Full-artifact mode (release-ish QA)

```bash
docker compose up -d --build
```

This is what a self-hoster gets; QA verdicts about "works for the user" must
come from this mode, not the dev server, when the item is release-facing.

## Teardown

`just dev-down` / `docker compose down` (add `-v` to wipe volumes — never in
a shared instance you don't own).
