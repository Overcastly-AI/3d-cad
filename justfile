set shell := ["bash", "-cu"]

# List recipes
default:
    @just --list

# Full dev stack via docker compose — needs a running docker daemon.
# db/redis/minio + gateway/documents/geometry with hot reload (web joins the
# stack with the web-shell backlog item). Foreground; Ctrl-C then `just dev-down`.
dev:
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Tear down the dev stack (keeps named volumes; add -v manually to wipe data)
dev-down:
    docker compose -f docker-compose.yml -f docker-compose.dev.yml down

# Probe /healthz + /readyz on all three services (compose or bare uvicorn).
# Usage: just smoke [base_port]
smoke base_port="8000":
    scripts/smoke-healthz.sh {{base_port}}

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
