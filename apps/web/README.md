# @loft/web

The Loft SPA: TanStack Router/Query shell around a react-three-fiber CAD
viewport. Talks ONLY to the gateway, ONLY through the generated
`@loft/ts-client` (CLAUDE.md DRY rule). All styling comes from
`@loft/design` — tokens, primitives, fonts; zero hex literals in this app.

## Run it

```bash
pnpm --filter @loft/web dev     # Vite dev server on :5173
```

The dev server proxies `/api` to the gateway on `127.0.0.1:8000`. For the
full pipe (dimension edit → gateway → OCCT tessellation → GLB → viewport)
run the stack (`just dev`), or bare-uvicorn for a lightweight loop:

```bash
uv run uvicorn geometry.main:app --port 8002   # geometry (OCCT)
LOFT_ENV=dev uv run uvicorn gateway.main:app --port 8000    # gateway
pnpm --filter @loft/web dev
```

## Checks

```bash
pnpm --filter @loft/web test        # vitest unit tests
pnpm --filter @loft/web typecheck
pnpm --filter @loft/web e2e         # Playwright (needs gateway + geometry up)
```

The e2e suite (`e2e/first-light.spec.ts`) drives the real stack in Chromium,
asserts real mass properties (6 000 mm³ for the 10×20×30 reference box),
verifies the canvas actually rendered, and captures the founder screenshots
into `docs/screenshots/`.
