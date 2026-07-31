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

### The two facts you cannot discover from the outside

**(a) Geometry is CPU-bound OCCT work.** Rebuild time is dominated by
whole-body B-rep operations; it grows as roughly **N^1.8 in feature count** and
much more gently (~faces^1.2-1.4) in face count. Sketch solving, tessellation
and the face matcher are all noise by comparison. More cores let you serve more
*concurrent* modelers; they do not make one part rebuild faster.

**(b) The rebuild cache is a PER-PROCESS LRU of 8 entries**
(`REBUILD_CACHE_CAPACITY` in `services/geometry/src/geometry/rebuild_cache.py`).
It is what turns a 27 s rebuild into a 1 s append and a 0.16 s re-export, and it
is **in-process memory, not Redis and not S3**. Two consequences that decide how
you size:

* Raising `WEB_CONCURRENCY` / `--scale geometry=N` **divides the cache hit rate
  rather than multiplying throughput**: nothing routes a modeler back to the
  process holding their part (uvicorn workers share one listening socket;
  compose DNS round-robins replicas), so with N processes their next click has
  roughly a 1/N chance of landing on the checkpoint it wants. The other N-1 times they
  pay the full cold rebuild. There is **no session affinity** in the stack today
  — say it plainly, because it is the difference between a 1 s and a 27 s click
  on a big part.
* The cache holds **one checkpoint per lineage** (the frontier), so 8 entries
  covers a modeler working on one part, a couple of parts side by side, or a
  small assembly (one tree per unique part). It does not cover 8 users.

**Practical rule: prefer ONE geometry worker per host, sized to the cores you
have, until the number of concurrent modelers exceeds the number of cores.**
Scale out only then, and expect the interactive numbers to degrade toward the
cold column until affinity exists.

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

| use | cores | RAM | notes |
| --- | ---: | ---: | --- |
| **Single engineer, parts to ~50 features** | 2 | 4 GiB | 1 geometry worker. Everything under ~2 s. |
| **Single engineer, real parts (to ~100 features)** | 4 | 8 GiB | 1 geometry worker. Cold opens 7 s, edits 0.4 s. |
| **Small team, 3-5 concurrent modelers** | 8 | 16 GiB | `--scale geometry=4`, ~1 GiB each; read the cache caveat above. |
| **Team with big parts / heavy STEP import** | 16 | 32 GiB | STEP import is a bounded subprocess with `RLIMIT_CPU`; give it real cores. |

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

Two other bounds worth knowing before you promise anything:

* **STEP import**: bounded by a 20 CPU-second ceiling and a 16 MiB upload cap.
  Measured cost is ~1.0 s fixed + 0.23-0.36 CPU s per MiB, so a file at the full
  upload cap costs ~6-7 CPU s — the upload cap binds first.
* **Per-face selection highlighting** degrades to whole-body selection past
  ~207 features (`MAX_PROVENANCE_FACES`).

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
