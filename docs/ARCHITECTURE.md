# Architecture

The system layout at Phase 0. For rationale and design decisions, see
`docs/RESEARCH.md`.

## Components

```
apps/web            React 19 + Vite SPA (viewport + UI)
services/gateway    FastAPI: REST aggregation, geometry proxy
services/geometry   OCCT workers (OCP + build123d): evaluate, tessellate
services/documents  Parts/assemblies, feature trees, versioning (Postgres) [Phase 1+]
packages/py-kit     Shared service kit (config, logging, health, errors, queue)
packages/contracts  Generated OpenAPI schemas (pydantic → committed)
packages/ts-client  Generated TypeScript client (never hand-edited)
packages/design     Design tokens + primitives + fonts (source-only workspace)
deploy/docker       Dockerfile + compose assets
docs/               VISION, RESEARCH, ROADMAP, BACKLOG, QA reports
.claude/            AI agent team: agents, skills, workflows
```

## Service boundaries (enforced)

- Only `services/geometry` imports OCP/build123d. No kernel types cross
  service boundaries.
- `services/geometry` never touches Postgres; `services/documents` never
  imports the kernel.
- `apps/web` talks only to the gateway.
- Types flow one way: pydantic models → OpenAPI → generated TS client.

## Data flows — Phase 0 tessellation pipeline

**User input → Server tessellation → GLB → Viewport**

1. **Browser (apps/web):** user edits x/y/z dimensions in title-block inspector
2. **Gateway** (services/gateway): `POST /api/v1/geometry/tessellate`
   - Passes dimensions as JSON to geometry service
   - Returns GLB buffer + X-Loft-Properties metadata header
3. **Geometry service** (services/geometry): `POST /api/v1/tessellate`
   - Evaluates parametric box via OCCT/build123d B-rep kernel
   - Tessellates to byte-deterministic GLB (identical across runs)
   - Computes mass properties (volume, area, centroid) + topology counts
   - Returns GLB + properties header
4. **Viewport** (apps/web): r3f scene
   - Renders three.js mesh from GLB buffers
   - Displays mass properties parsed from X-Loft-Properties header
   - On dimension edit, loop back to step 1

**Today:** pipeline is synchronous (HTTP request → OCCT evaluation → response);
geometry evaluates in-request. **Future:** async queue (Redis + arq) feeds
geometry workers.

## Datastore footprint — Phase 0

- **Postgres 16:** unused in Phase 0; documents service wired for future
- **Redis 7:** unused in Phase 0; queue client in py-kit ready for Phase 1
- **MinIO (S3-compat):** unused in Phase 0; storage client reserved in py-kit
- **In-memory state:** viewport state (zustand), geometry results (per-request)

## DRY enforcement

- **One source of truth for types:** pydantic models in service code →
  generated OpenAPI schemas → generated TS client. Hand-written type duplicates
  are rejected in review.
- **Cross-service boilerplate:** config, logging, health endpoints, error
  envelopes, queue plumbing live in `py-kit` exactly once.
- **Design tokens:** `packages/design` constants drive both Tailwind preset
  (DOM) and r3f scene (WebGL); no hex values duplicated.

## Test coverage — Phase 0

- **Unit tests:** 76 pytest (Python services + py-kit), 13 vitest (web + design)
- **Geometry QA:** golden-model suite (data-driven; mass properties, topology,
  determinism), STEP round-trip fidelity test
- **Web E2E:** Playwright against live geometry+gateway stack (tessellation,
  dimension edits, mass properties assertion)
- **CI gates:** lint, typecheck, unit tests, contract drift check, compose
  config validation

## Dependency licensing

- **App:** MIT (Overcastly AI)
- **Allowed:** MIT/BSD/Apache, LGPL (dynamic linking)
- **Forbidden:** GPL/AGPL
- **Kernel:** OCCT is LGPL-2.1 with exception (safe for MIT)
