# Loft — Operations

**For the person running Loft.** Self-hosting makes you your own ops team, so
this file covers the four things that decide whether that goes well: **backup**,
**restore**, **upgrade**, and **sizing**.

Every number in the sizing section is measured, in this repo, on the machine
named there. Nothing here is estimated. The companion documents are
`docs/PERF.md` (where the measurements come from) and `README.md` (install).

---

## TL;DR

```bash
just backup                      # -> backups/loft-<UTC timestamp>/
just restore backups/loft-...    # from nothing: fresh volumes -> live stack
just backup-drill                # prove the whole cycle on your own machine
```

Back up **both Postgres databases**. Do not bother backing up MinIO. Keep a
backup off the machine that runs Loft. Run `just backup-drill` once on your own
hardware before you trust any of it — that is the only way you learn your
restore works while it does not matter yet.

---

## 1. What is stateful, and what is not

| Component | Holds | Backed up | Why |
| --- | --- | --- | --- |
| Postgres `loft_gateway` | users, password hashes | **yes** | the only copy |
| Postgres `loft_documents` | parts, **feature trees**, assemblies, instances, mates, drawings, sheets, views, dimensions, undo snapshots, materials, and the inline STEP text of imported bodies | **yes** | **this is the product** |
| MinIO / S3 bucket | `meshes/sha256/*.glb`, composed drawing artifacts | **no** | derived — see below |
| Redis | rate-limit counters, job queue | no | cache; empty is a valid state |
| Container images | code | no | rebuild from the repo at a tagged commit |

The two databases are deliberately separate: both alembic trees start at
revision `0001` in the default `alembic_version` table, so one shared database
would make the second service's first migration a silent no-op
(`deploy/docker/postgres-init` explains it at length).

### What is not backed up, and what that costs

The object store holds **only content-addressed derived artifacts**. A mesh's
key *is* the SHA-256 of its own bytes (`geometry/s3_store.py`), and a composed
drawing artifact's key is the SHA-256 of the compose request. Both are pure
functions of data that lives in Postgres, and evaluation is required to be
deterministic (RESEARCH §9) — so a restored feature tree re-derives a
**bit-identical** mesh, with the same content address.

That is not a claim, it is the drill's final assertion: `just backup-drill`
destroys the bucket along with everything else and then demands the same
`mesh_glb_id` back out of a rebuild.

**Restore-time cost** — one cold rebuild the first time each part is opened,
paid once per part, and it is the same cost a cold worker or a page reload would
pay anyway (measured, 4-core container, `docs/PERF.md`):

| part | first open after a restore |
| --- | ---: |
| 10 features | 0.23 s |
| 25 features | 0.63 s |
| 50 features | 2.0 s |
| 100 features | 6.9 s |
| 200 features | 27 s |
| 6 features / 2 006 faces | 9.8 s |

Copying the bucket would buy back exactly that, at the price of storing ~1 MiB
per tessellated body forever and having to keep it consistent with the database
it was derived from. It is not worth it. If you want it anyway — a very large
part corpus and an SLA on the first click after a restore — mirror the bucket
yourself; nothing in Loft needs to know:

```bash
docker compose run --rm --entrypoint /bin/sh minio-init -c \
  'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" \
   && mc mirror --overwrite local/"$S3_BUCKET" /mirror'    # mount /mirror yourself
```

A mirrored bucket is safe to restore into: keys are content addresses, so a
stale object is either byte-identical to what would be re-derived or
unreferenced.

---

## 2. Backup

```bash
just backup                       # backups/loft-<UTC timestamp>/
scripts/backup.sh /srv/loft/nightly
```

Requires a **running stack** (it works through `docker compose exec db`, so
there is no host Postgres client to install and the dump is always taken by the
same major version that wrote the data). It is **online** — each database is
dumped in one transaction; no downtime, no read-only window.

What lands in the destination:

```
manifest.json    format, timestamp, Loft commit, postgres version, and per
                 database: the alembic revision, EXACT per-table row counts,
                 dump size and sha256
gateway.dump     pg_dump -Fc --no-owner --no-privileges
documents.dump   pg_dump -Fc --no-owner --no-privileges
SHA256SUMS       sha256sum -c-verifiable
```

Before it declares success, `backup.sh` reads back each archive's table of
contents with `pg_restore -l` and requires the tables that hold the product's
value to be in it (`users`; `parts`, `features`, `assemblies`, `drawings`). A
dump that cannot be listed, or a valid dump of the *wrong* database, fails at
backup time rather than at restore time.

It refuses to back up a database with no `alembic_version` row: an unmigrated
database cannot be restored honestly, so that is a loud failure and not a file.

**Off-machine.** A backup on the disk that dies with the server is not a backup:

```bash
just backup /srv/loft/nightly && \
  rsync -a --delete /srv/loft/nightly backup-host:/srv/loft-backups/
```

`backups/` is git-ignored: dumps hold real user data and password hashes, and
must never be committed.

**Scheduling** (cron on the Docker host; keep 14 days):

```cron
17 3 * * *  cd /srv/loft && /usr/bin/env just backup /srv/loft/backups/$(date -u +\%Y\%m\%d) \
              >> /var/log/loft-backup.log 2>&1
41 4 * * *  find /srv/loft/backups -maxdepth 1 -mtime +14 -type d -exec rm -rf {} +
```

---

## 3. Restore

```bash
just restore backups/loft-20260731T120000Z
scripts/restore.sh <dir> --force    # target databases are NOT empty
```

**It works from nothing.** The intended disaster path is: new machine, clone the
repo at the same (or a newer) commit, `docker compose up -d db`, restore, done.

What it does, in order — and everything before step 4 is a **refusal point**, so
a restore that cannot be completed correctly changes nothing:

1. verifies `SHA256SUMS`;
2. reads each database's alembic revision out of the manifest and compares it
   with the migration tree **inside this deployment's service image** (§4);
3. refuses a non-empty target database without `--force`;
4. stops `gateway` and `documents` (a half-restored install must not serve),
   drops and recreates each database, and runs `pg_restore --single-transaction`
   — **all-or-nothing**. Without that flag pg_restore logs errors, keeps going,
   and **exits 0**: a half-populated database reported as success, which is the
   exact defect class this script exists to make impossible;
5. **verifies before believing**: the restored `alembic_version` must equal the
   manifest's, and the exact per-table row counts must equal the manifest's,
   table for table. A mismatch is exit code 4 with the differing tables printed;
6. migrates forward if the backup is older than this Loft (§4), loudly;
7. re-creates the (empty) object-storage bucket and brings the stack back up.

Exit codes: `0` restored · `1` usage/environment · `2` target not empty (use
`--force`) · `3` version skew, nothing changed · `4` post-restore verification
failed — **do not put that install into service**.

Then check it the way the drill does:

```bash
scripts/smoke-healthz.sh 8000     # /healthz + /readyz
# open a part in the browser: the first evaluate re-derives its mesh
```

---

## 4. Version skew — restoring an old backup onto a new Loft

This is the question restore tooling usually leaves unanswered. Loft answers it
before touching a database, per schema-owning service:

| backup's alembic revision | what happens |
| --- | --- |
| **equal to this image's head** | restore, nothing else. Printed: `backup is at head (0014) — no migration needed`. |
| **an ancestor of head** (older Loft) | restore, then `alembic upgrade head` inside the service image. Printed: `MIGRATING documents: 0011 -> 0014`, then `MIGRATED documents: 0011 -> 0014`. Your data is migrated forward by the same migrations a live upgrade would run. |
| **unknown to this image's tree** (backup from a NEWER Loft, or a fork) | **REFUSED, exit 3, nothing changed.** Rolling a schema backwards drops columns and the data in them; Loft will not do that silently. Fix: restore with a Loft at least as new as the one that took the backup — the manifest records its commit. |

The row-count check in step 5 runs **before** any migration, so "the restore was
complete" and "the migration then changed things" stay separate facts.

**Downgrades are not supported.** There are no `downgrade()` paths worth
trusting across a schema this young; the honest answer is "restore with the
newer version", and that is what the tool says.

---

## 5. Upgrading

```bash
just backup /srv/loft/pre-upgrade      # ALWAYS first
git pull && docker compose build
docker compose up -d --wait db redis minio
for s in gateway documents; do
  docker compose run --rm --no-deps "$s" alembic -c /app/migrations/alembic.ini upgrade head
done
docker compose up -d
scripts/smoke-healthz.sh 8000
```

Migrations are forward-only and are run **from the service images**, so no
Python toolchain is needed on the host. Both services must be migrated; each
owns its own database.

If an upgrade goes wrong, the recovery path is the one you already tested:
restore the pre-upgrade backup with the **old** images (`git checkout` the
previous tag, `docker compose build`) — restoring an old dump onto new code is
supported (it migrates forward); restoring it onto *older* code than it came
from is refused, which is why you check out the old tag rather than fighting it.

Note the object store survives an upgrade untouched and needs no attention:
its keys are content addresses, so a changed tessellator simply produces new
keys and the old objects become unreferenced.

---

## 6. Sizing

Machine for every number below: **Linux container, nproc = 4, 15.7 GiB RAM**,
OCCT via OCP as shipped. Full method and raw tables in `docs/PERF.md`.

### The three facts you cannot discover from the outside

> **Corrected 2026-08-01 against measurement.** Until that date this section
> reasoned its way to "prefer ONE geometry worker per host." The reasoning about
> the cache was right; the conclusion was wrong, and it was wrong in the
> expensive direction — it told operators to run a configuration that uses a
> quarter of their machine. `docs/PERF.md` §"CONCURRENCY" has the run.

**(a) Geometry is CPU-bound OCCT work.** Rebuild time is dominated by
whole-body B-rep operations; it grows as roughly **N^1.8 in feature count** and
much more gently (~faces^1.2-1.4) in face count. Sketch solving, tessellation
and the face matcher are all noise by comparison. **More cores do not make one
part rebuild faster, and — see (b) — they do not let one worker serve more
modelers either.**

**(b) ONE GEOMETRY WORKER USES ONE CORE, whatever you throw at it.** Measured:
a worker held at **1.05-1.15 cores** with 1, 2, 4 and 8 concurrent requests in
flight and 11-18 OS threads live. OCP/pybind11 does not release the GIL around
OCCT calls, so the FastAPI threadpool is concurrency in name only. The
consequences are arithmetic:

* **The second modeler on a worker doubles everyone's latency**, the fourth
  quadruples it. Measured on the 50-feature tray: an edit costs 2.1 s with one
  user, 4.6 s with two, 9.7 s with four, 19.4 s with eight.
* **A 4-core host running one geometry worker is running at 25 % of the
  machine, permanently.** Nothing about load changes that.

**(c) The rebuild cache is a PER-PROCESS LRU of 8 entries**
(`REBUILD_CACHE_CAPACITY` in `services/geometry/src/geometry/rebuild_cache.py`).
It is what turns a 27 s rebuild into a 1 s append and a 0.16 s re-export, and it
is **in-process memory, not Redis and not S3**. Three consequences:

* A working modeler occupies **two** lineages (their evaluate lineage and the
  `record_history` lineage a face pick uses), so 8 entries is **exactly four
  concurrent modelers per worker**. Measured: hit rate holds at 0.40 up to four
  users and falls to 0.28 / 0.15 / 0.125 at five / six / eight — and `/measure`,
  the cheapest thing in the product, goes from **244 ms to 19 s**.
* Raising `WEB_CONCURRENCY` / `--scale geometry=N` really does **divide the
  cache hit rate** roughly 1/N (measured 0.40 → 0.225 at two workers → 0.075 at
  four), because nothing routes a modeler back to the process holding their
  part: uvicorn workers share one listening socket and compose DNS round-robins
  replicas. There is **no session affinity in the stack today.**
* **But fan-out still wins, in every routing policy measured** — this is the
  part the old text got wrong. Four users on a 4-core host, against one worker
  as the baseline: **3.75x** with per-user affinity, 2.06x with balanced
  round-robin, **1.21x** with the random dispatch you get today. Losing affinity
  costs 1.8x to cache dilution and another 1.7x to arrival imbalance (a worker
  with no internal parallelism cannot absorb two simultaneous requests), but the
  floor is still faster than one worker.

**Practical rule: run ONE GEOMETRY WORKER PER CORE.** With `S3_URL` set, so the
mesh store is shared — the in-process LRU deliberately refuses multi-worker
without it. Expect roughly:

| what you run on a 4-core box | comfortable simultaneous modelers |
| --- | ---: |
| 1 geometry worker | **1** |
| 4 workers, no affinity (what compose `--scale` gives you today) | **1-2** |
| 4 workers + sticky routing (**not shipped** — see below) | **4** |

Four users on four workers **with** affinity paid 2 559 ms per edit against
2 113 ms for a lone user on an idle machine — i.e. no measurable degradation at
all. Session affinity is the single highest-value thing missing from this
stack's operations story (filed as CONC-1); until it lands, a consistent-hash
reverse proxy on part id in front of the geometry replicas buys most of it.

### What breaks first, and what it looks like

Not memory, and not the rate limiter. **The gateway's 30-second upstream read
timeout** (`GEOMETRY_TIMEOUT_S`, `services/gateway/src/gateway/geometry.py`).

A 200-feature part's first face pick takes 40 s on an **idle** machine with
**one** user, so the browser gets a `502 upstream_unavailable` saying *"Geometry
service is unreachable"* — which is false, the service is fine and the finished
answer is thrown away. Measured: the same click had to be made **three times**
(two 502s, then a 22.7 s success once the abandoned rebuild's checkpoint reached
the cache). At eight users the same thing happens on a **50-feature** part.

There is also **no admission control** anywhere in the stack: the gateway's HTTP
client allows httpx's default 100 connections and the geometry threadpool 40
workers, all sharing one effective core. Overload therefore degrades by
*processor sharing*, which under a fixed client timeout is the worst possible
policy — 16 simultaneous requests all finished within 0.4 s of each other at
~40 s, so **1 of 16 landed inside a 30 s ceiling where a plain FIFO queue would
have delivered 11.**

Operator takeaways until CONC-2/CONC-3 land: keep parts under ~100 features,
prefer more workers over more users per worker, and read a burst of
`upstream_unavailable` as *"geometry is saturated"*, not as *"geometry is
down"* — check `loft_rebuild_cache_*` and the request histogram
(`docs/OBSERVABILITY.md`) before restarting anything.

### Memory

| item | measured |
| --- | ---: |
| OCCT baseline per geometry worker | **~500 MiB RSS** |
| a 442-face part resident | 619 MiB |
| a 2 006-face part resident | 829 MiB |
| each retained rebuild checkpoint | **+2 MiB** (219 faces) to ~4 MiB (442 faces) |
| a full 8-entry cache | tens of MiB |

So **budget ~1 GiB per geometry worker** and treat 500 MiB as the floor a worker
occupies while idle. RSS does not fall when the cache is cleared (glibc keeps
the arena), so plan for the peak, not the average.

Gateway and documents are thin async services — tens of MiB each. Postgres is
comfortable in 512 MiB-1 GiB at this data size; MinIO in 256-512 MiB.

### Recommended configurations

**Size on one rule: one geometry worker per concurrent modeler, one core per
worker, ~1 GiB per worker.** (Measured 2026-08-01; the pre-2026-08-01 version of
this table recommended one worker for a whole small team and was wrong by 4x.)

| use | cores | RAM | geometry workers | notes |
| --- | ---: | ---: | ---: | --- |
| **Single engineer, parts to ~50 features** | 2 | 4 GiB | **1** | Everything under ~2 s. One worker genuinely is enough for one person. |
| **Single engineer, real parts (to ~100 features)** | 4 | 8 GiB | **2** | Cold opens 7 s, edits 0.4 s. The second worker is for the background rebuild an open editor prefetches (PERF-1b) so it stops competing with your click. |
| **Small team, 4 concurrent modelers** | 8 | 16 GiB | **4** | `--scale geometry=4` with `S3_URL` set. **Without affinity expect ~1.2-2x, not 4x** — put a consistent-hash proxy on part id in front of the replicas if you can. |
| **Small team, 8 concurrent modelers** | 16 | 32 GiB | **8** | Same rule. Do not try to serve 8 people from 4 workers: the 5th user per worker also breaks the rebuild cache (fact (c) above). |
| **Team with big parts / heavy STEP import** | 16+ | 32 GiB | **8** | STEP import is a bounded subprocess with `RLIMIT_CPU`; give it real cores. Parts over ~150 features hit the gateway timeout — see "What breaks first". |

**Disk**: the databases are small — feature trees are JSON text — with one
exception: an **imported STEP body is stored inline in the feature tree**, up to
`MAX_INLINE_STEP_CHARS` = **16 MiB per import feature**. Size the Postgres
volume from that, not from part count. The object store is ~30 bytes per
triangle plus ~425 bytes per B-rep face (a 2 000-face body is ~1 MiB), it
deduplicates by content address, and it can be deleted at any time.

### What part sizes are comfortable

Cold rebuild is what you pay on a first open; append and repeat are what you pay
while working (both cache-warm, same machine):

| part | first open | add a feature | measure / export / re-tessellate | verdict |
| --- | ---: | ---: | ---: | --- |
| 10 features | 0.23 s | 0.07 s | 0.006 s | instant |
| 25 features | 0.63 s | 0.14 s | 0.018 s | **comfortable** |
| 50 features | 2.0 s | 0.22 s | 0.04 s | **comfortable while working**; first open is at the 2 s ceiling |
| 100 features | 6.9 s | 0.43 s | 0.06 s | usable, but every cold open is a coffee sip |
| 200 features | 27 s | 1.0 s | 0.16 s | **first open is painful**; editing is fine |
| 2 006 faces / 6 features | 9.8 s | — | 0.52 s tessellate | face count is not the wall |

Read that honestly: **Loft is comfortable up to about 50-100 features per part
today, and face count is not the limit — feature count is.** A machined bracket
(40-80 features) is fine; a 150-400-feature housing is not, and the cold-open
cost is the reason. `docs/PERF.md` has the ranked fix list.

**Two caveats on that table, both measured 2026-08-01:**

* **"add a feature" is not "change a dimension."** Appending is the case the
  rebuild cache serves; an *edit* re-runs the tree from feature 0 unless an open
  feature editor prefetched it first (PERF-1b). Measured over HTTP on the
  50-feature tray: append **0.25 s**, edit **2.4 s** — the same as a cold open.
  Most of a modelling day is edits.
* **Every number in that table is for ONE user.** Multiply by the number of
  concurrent modelers sharing a worker (fact (b)). Four people on one worker
  turn the 50-feature row's 2.0 s open into 9.7 s.

Two other bounds worth knowing before you promise anything:

* **STEP import**: bounded by a 20 CPU-second ceiling and a 16 MiB upload cap.
  Measured cost is ~1.0 s fixed + 0.23-0.36 CPU s per MiB, so a file at the full
  upload cap costs ~6-7 CPU s — the upload cap binds first.
* **Per-face selection highlighting** degrades to whole-body selection past
  ~207 features (`MAX_PROVENANCE_FACES`).
* **The gateway gives up at 30 s** and reports it as *"Geometry service is
  unreachable"*. A 200-feature face pick costs 40 s idle with one user, so parts
  that size are not merely slow today — they error. See "What breaks first".

---

## 7. Security notes that interact with ops

* **Never publish `documents` (:8001) or `geometry` (:8002).** The base compose
  file publishes only the gateway; documents trusts the gateway-verified
  `X-Loft-User` header with no signature check, so exposing it is
  forged-header cross-tenant access. `scripts/check-compose.py` gates this, and
  `scripts/compose-roundtrip.py` re-checks it at runtime.
* **Set `LOFT_ENV=production` and a real `JWT_SECRET`** (>= 32 chars,
  `openssl rand -hex 32`), plus real `POSTGRES_PASSWORD` and
  `MINIO_ROOT_PASSWORD`. The services **refuse to boot** on the repo-public dev
  defaults outside `LOFT_ENV=dev` — deliberately.
* Backups contain password hashes and every part your users own. Treat a backup
  directory like the database itself: restricted permissions, encrypted at rest
  if it leaves the host.

---

## 8. Proving it on your own hardware

```bash
just backup-drill
```

Seeds a user, a part with a feature tree, an assembly and a drawing through the
real API; backs up; runs `docker compose down -v` and **asserts the volumes are
gone**; boots from nothing and asserts the seeded user **cannot** log in;
restores; then logs in as that user again, re-reads every document, confirms the
old mesh is a 404, and re-evaluates the part demanding the **same volume and the
same `mesh_glb_id`**.

CI runs this same script on every push (`.github/workflows/deploy-path.yml`,
job `backup-restore-drill`). Run it yourself anyway — on your hardware, with
your data volumes, before you need it.
