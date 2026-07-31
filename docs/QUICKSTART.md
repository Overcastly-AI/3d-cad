# Quickstart

Get Loft running and model something. Two paths:

- **[Option A — Docker Compose](#option-a--docker-compose-self-hosting)**: the
  self-hosting path. Datastores included. Start here if you want to *use* Loft.
- **[Option B — container-free](#option-b--container-free-development)**: no
  Docker, no Postgres, no MinIO. Start here if you want to *develop* Loft.

Both end at the same place: a browser at a modeling viewport with a part in it.

> **Pre-release.** There are no tagged releases and no published images yet —
> you build from source either way. See
> [`docs/LICENSING.md`](./LICENSING.md) for why images aren't published yet and
> what has to be true before they are.

---

## Option A — Docker Compose (self-hosting)

### Prerequisites

- **Docker** with the Compose plugin (`docker compose version` ≥ 2.20)
- ~6 GB of disk. The geometry image carries the OCCT kernel (~95 MB of shared
  libraries before Python), so the first build is slow. Later builds cache on
  `uv.lock`.
- No host Python or Node needed. Migrations run from inside the images.

### Bring it up

```bash
git clone https://github.com/Overcastly-AI/3d-cad.git
cd 3d-cad

cp .env.example .env      # optional but recommended — read the comments in it
docker compose up -d --build
```

`.env` is optional: every value has the same default inside
`docker-compose.yml`, so the stack runs without one. **Those defaults are
published in this repository**, so they only work for a local deployment.
`.env.example` explains the guard in detail — the short version is that unless
`LOFT_ENV` is exactly `dev`, any service whose datastore URL embeds a
publicly-known default password refuses to boot and names the variable to fix.

### Create the schemas

Once per database. Re-running is a no-op.

```bash
docker compose run --rm gateway   alembic -c /app/migrations/alembic.ini upgrade head
docker compose run --rm documents alembic -c /app/migrations/alembic.ini upgrade head
```

The gateway and documents services own separate databases (`loft_gateway`,
`loft_documents`), created on the volume's first boot. They must stay separate:
both alembic trees start at revision `0001`.

### Check it

```bash
curl -fsS http://127.0.0.1:8000/healthz    # gateway
curl -fsS http://127.0.0.1:8000/readyz     # gateway + its upstreams
```

Only the gateway is published (`:8000`). `documents` and `geometry` are
reachable only from inside the compose network, on purpose — the smoke test
asserts they are *not* reachable from the host.

For the full proof — build, boot, migrate, and a real modeling round-trip over
the published port — run:

```bash
just compose-smoke
```

That is the same script CI runs on every push
([`deploy-path.yml`](../.github/workflows/deploy-path.yml)).

### Tear down

```bash
docker compose down          # keeps your data
docker compose down -v       # deletes the volumes too
```

---

## Option B — container-free development

No Docker required. Documents and gateway use SQLite; geometry keeps meshes in
an in-process LRU cache; the rate limiter no-ops without Redis. This is how the
project is developed day to day.

### Prerequisites

- **Python 3.12** (see `.python-version`)
- **Node 22** + **pnpm 10** (pinned in `package.json` → `packageManager`)
- **[uv](https://docs.astral.sh/uv/)**
- **[just](https://just.systems/)** — `uv tool install rust-just`

### Install

```bash
git clone https://github.com/Overcastly-AI/3d-cad.git
cd 3d-cad
uv sync          # Python workspace (services + py-kit)
pnpm install     # TS workspace (web app + design + ts-client)
```

`uv sync` downloads the OCCT wheel. It is large; be patient the first time.

### Create the schemas

**Do not run alembic against SQLite** — the migrations render Postgres DDL
verbatim (`DEFAULT (now())`), which SQLite rejects at insert time. Use
SQLAlchemy's `create_all`, which renders dialect-correct DDL:

The database files live outside the repo so they can never dirty your working
tree (`scripts/e2e.sh` uses a `mktemp` directory for the same reason):

```bash
export LOFT_LOCAL="$HOME/.loft-local"
mkdir -p "$LOFT_LOCAL" && rm -f "$LOFT_LOCAL"/documents.db "$LOFT_LOCAL"/gateway.db

DOC_DSN="sqlite+aiosqlite:///$LOFT_LOCAL/documents.db" \
GW_DSN="sqlite+aiosqlite:///$LOFT_LOCAL/gateway.db" \
uv run python - <<'EOF'
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
from documents.db import Base as D
from gateway.db import Base as G
from py_kit.db import async_dsn

async def main():
    for url, base in ((os.environ["DOC_DSN"], D), (os.environ["GW_DSN"], G)):
        engine = create_async_engine(async_dsn(url))
        async with engine.begin() as conn:
            await conn.run_sync(base.metadata.create_all)
        await engine.dispose()
        print("schema created:", url.rsplit("/", 1)[-1])

asyncio.run(main())
EOF
```

`create_all` does **not** migrate. If you pulled changes and something fails
with `no such column`, delete the two `.db` files and re-run the block above.
Keep `LOFT_LOCAL` exported for the next step, or substitute the path inline.

### Start the three services

All three are required. The gateway proxies parts and feature trees to
`documents` and geometry work to `geometry`; without `documents` you get a
`503` on the very first request.

```bash
# geometry — keep --workers 1: the mesh LRU is per-process
uv run uvicorn geometry.main:app --host 127.0.0.1 --port 8002 --workers 1 &

POSTGRES_URL="sqlite+aiosqlite:///$LOFT_LOCAL/documents.db" \
  uv run uvicorn documents.main:app --host 127.0.0.1 --port 8001 &

LOFT_ENV=dev \
POSTGRES_URL="sqlite+aiosqlite:///$LOFT_LOCAL/gateway.db" \
GEOMETRY_URL=http://127.0.0.1:8002 \
DOCUMENTS_URL=http://127.0.0.1:8001 \
  uv run uvicorn gateway.main:app --host 127.0.0.1 --port 8000 &
```

`LOFT_ENV=dev` is required — the gateway fails closed on JWT posture
otherwise, and it is what permits the publicly-known dev fallback secret.
Expect two startup warnings (`jwt_dev_fallback_secret_in_use`,
`rate_limit_disabled_no_redis`); both are correct for a local run.

Verify:

```bash
just smoke        # /healthz + /readyz on all three
```

### Start the web app

```bash
pnpm --filter @loft/web dev
```

Open **<http://localhost:5173>**. Vite proxies `/api` to the gateway on
`:8000` (override with `GATEWAY_ORIGIN`).

> **Running a second stack on other ports? Do not write `--`.**
> pnpm 10 **silently discards** the npm-idiomatic `--` separator, so
> `pnpm --filter @loft/web dev -- --port 5199` starts Vite on **5173**, not
> 5199 — no error, no warning. Measured on pnpm 10.33.0. Use one of:
>
> ```bash
> pnpm --filter @loft/web dev --port 5199        # no `--`
> pnpm --filter @loft/web exec vite --port 5199  # equivalent
> ```
>
> This matters more than it looks. `apps/web/playwright.config.ts` sets
> `reuseExistingServer: true`, so a stray Vite on 5173 gets **reused** by the
> next `just e2e` — and if its `/api` proxy points at a gateway you have since
> torn down, every spec fails at `seedSession` with a 500 that looks like a
> code regression. Always confirm the port Vite actually printed, and kill
> your own Vite in teardown, not just your uvicorns.

### Prove the whole path without a browser

```bash
python3 scripts/compose-roundtrip.py --base-url http://127.0.0.1:8000
```

Nine checks — register, create a part, author a sketch and an extrude,
evaluate, fetch the GLB from the mesh store, reject an unauthenticated fetch,
export STEP, and confirm the internal services aren't exposed. Stdlib only.

---

## Your first part

1. **Register.** The landing page takes an email and password. There is no
   email verification; this is a local account in your own database.
2. **New part.** You get an empty feature tree, three origin planes, and the
   viewport.
3. **Sketch.** Pick a plane, draw a rectangle. Dimension it — dimensions accept
   expressions, and you can mark them driving or driven. The solver status
   ("Solved" / "Under-constrained") sits under the tree.
4. **Extrude.** Finish the sketch, choose Extrude, give it a depth. The
   geometry service evaluates the B-rep with OCCT and streams back a
   deterministic GLB.
5. **Read the numbers.** The inspector shows volume, surface area, centroid,
   bounding box and topology counts read back from the evaluated B-rep — not
   estimated from the mesh. Assign a material to get mass; until you do, mass
   is `null` rather than a made-up default.
6. **Export.** STEP (B-rep) or STL (mesh) from the same panel.

### Check the numbers yourself

The mass properties are read back from the evaluated B-rep, so they should
agree with arithmetic you can do on paper. A worked example you can rebuild in
four features — sketch a 120 × 80 rectangle, extrude 40, shell 3 mm with the
top face open, break the edges at R1:

```
outer block        120 × 80 × 40   = 384 000 mm³
less the cavity    114 × 74 × 37   = 312 132 mm³
                                   ---------------
                                     71 868 mm³
less the R1 edge breaks                 173.52 mm³
                                   ---------------
Loft reports                         71 694.48 mm³
```

That part is `docs/screenshots/part-enclosure-1600.png`. If your numbers don't
reconcile, that's a bug worth filing — wrong geometry is a first-class bug
here, not a rounding complaint.

### Expectations before you scale up

Parts up to ~50 features feel fine, ~100 is painful cold, and a first rebuild
of a 200-feature tree takes ~26 s. [`docs/PERF.md`](./PERF.md) has the measured
tables and says plainly where the wall is.

---

## Troubleshooting

**`database_unavailable: Database is not configured; set POSTGRES_URL.`**
The gateway booted without a database. In Option B, `POSTGRES_URL` must be set
on both the gateway and documents processes; see the block above.

**`503` on `/api/v1/parts` but `/healthz` is `200`.**
The `documents` service isn't running or `DOCUMENTS_URL` is wrong. Health is
per-service; `/readyz` on the gateway is what checks upstreams.

**`no such column: …` in Option B.**
Your SQLite file predates a schema change. `create_all` never migrates —
delete `$LOFT_LOCAL/*.db` and re-create.

**`attempt to write a readonly database` after a long session (Option B).**
A long-lived uvicorn's SQLite handle goes bad after ~10 minutes of idle. It is
not a code regression. Restart the three services.

**The viewport is blank but the feature tree says `ok`.**
The mesh didn't come back. Check the geometry service's log: with `S3_URL` set
but no credentials, every mesh `put`/`get` 403s while the config stays valid.
Unset `S3_URL` to use the in-process store.

**Vite ignored my `--port` and started on 5173.**
You wrote `--`. pnpm 10 discards it silently — see the note above. Vite's
config has no `strictPort`, so a dropped port argument falls back to 5173
rather than failing.

**Every e2e spec fails at registration with a 500, but curl to the gateway works.**
A stale Vite on 5173 is being reused, and its `/api` proxy points at a dead
gateway. `ps -eo pid,args | grep vite/bin/vite`, kill it, re-run.

**The first `docker compose up --build` takes forever.**
The geometry image installs the OCCT wheel. Subsequent builds cache on
`uv.lock`.

---

## What to run before you open a PR

```bash
just lint        # ruff + ruff format + pyright strict + eslint + prettier + tsc
just test        # pytest + vitest
just e2e         # geometry gates + Playwright (local gate; not a CI job yet)
```

[`CONTRIBUTING.md`](../CONTRIBUTING.md) has the full expectations.
