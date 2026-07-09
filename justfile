set shell := ["bash", "-cu"]

# List recipes
default:
    @just --list

# Full dev stack (db/redis/minio + services + web, hot reload)
dev:
    @echo "just dev: not implemented yet — the compose stack lands with the 'Service skeletons + compose' backlog item (docs/BACKLOG.md)."
    @exit 1

# Lint + typecheck: ruff (lint + format), pyright strict, eslint + prettier
lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    pnpm run lint

# Unit tests: pytest across the uv workspace + vitest via pnpm (recursive)
test:
    uv run pytest || [ $? -eq 5 ]  # pytest exit 5 = no tests collected; fine until the first suites land
    pnpm run test

# Regenerate OpenAPI contracts + TS client
gen:
    @echo "just gen: placeholder — lands with the 'Contract pipeline' backlog item (docs/BACKLOG.md)."

# Playwright e2e + geometry golden suite
e2e:
    @echo "just e2e: placeholder — lands with the web-shell and golden-harness backlog items (docs/BACKLOG.md)."
