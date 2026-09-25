# Loft: Operations

For the person running Loft: backup, restore, upgrade, sizing and metrics.
The numbers were measured on a 4-core, 15.7 GiB Linux container. The full
measurements are in git: `git show 5b6fd28:docs/OPERATIONS.md`,
`git show 5b6fd28:docs/PERF.md` and `git show 5b6fd28:docs/OBSERVABILITY.md`.

## TL;DR

```bash
just backup                      # -> backups/loft-<UTC timestamp>/
just restore backups/loft-...    # fresh volumes -> live stack
just backup-drill                # prove the whole cycle on your own machine
```

Back up **both Postgres databases**. Do not back up the object store. Keep a
copy off the machine. Run `just backup-drill` once on your own hardware before
you trust any of it.

## 1. What is stateful

| Component                  | Holds                                                                                          | Backed up |
| -------------------------- | ---------------------------------------------------------------------------------------------- | --------- |
| Postgres `loft_gateway`    | users, password hashes                                                                         | **yes**   |
| Postgres `loft_documents`  | parts, feature trees, assemblies, drawings, undo snapshots, materials, inline STEP of imports | **yes**   |
| MinIO / S3 bucket          | content-addressed meshes and drawing artifacts                                                 | no        |
| Redis                      | rate-limit counters, job queue                                                                 | no        |

The object store holds only artifacts derived from Postgres. Evaluation is
deterministic, so a restored part re-derives a bit-identical mesh with the same
address. The cost is one cold rebuild the first time each part is opened
(0.6 s at 25 features, 6.9 s at 100, 27 s at 200). The drill asserts this.
The two databases are deliberately separate: both alembic trees start at
`0001`.

## 2. Backup

`just backup [dest]` (or `scripts/backup.sh`) works against a **running**
stack through `docker compose exec db`. It is online, with one transaction per
database. It writes `gateway.dump` and `documents.dump` (`pg_dump -Fc`), a
`manifest.json` (Loft commit, alembic revision, exact per-table row counts,
checksums) and `SHA256SUMS`. It fails at backup time if a dump cannot be
listed or lacks the product's tables, or if a database is unmigrated.
`backups/` is git-ignored because it holds user data.

Keep a copy off the machine, for example with nightly cron plus `rsync` and
14 days of retention.

## 3. Restore

```bash
just restore backups/loft-20260731T120000Z
scripts/restore.sh <dir> --force    # target databases are not empty
```

It works from nothing: a new machine, the repo at the same or a newer commit,
then `docker compose up -d db` and restore. The steps are:

1. Verify the checksums.
2. Compare each database's alembic revision with this image's migrations
   (§4).
3. Refuse a non-empty target unless `--force` is given.
4. Stop gateway and documents, then run `pg_restore --single-transaction`
   (all or nothing).
5. Verify the revision and the exact row counts against the manifest.
6. Migrate forward if the backup is older.
7. Re-create the empty bucket and start the stack.

Exit codes: `0` restored, `1` usage, `2` target not empty, `3` version skew
(nothing changed), `4` verification failed (**do not use that install**).

## 4. Version skew

| Backup's revision                         | Result                                                                    |
| ----------------------------------------- | ------------------------------------------------------------------------- |
| equal to head                             | restore only                                                              |
| older (an ancestor of head)               | restore, then `alembic upgrade head` inside the service image, loudly    |
| unknown (from a newer Loft, or a fork)    | **refused, exit 3.** Restore with a Loft at least as new as the backup.  |

Downgrades are not supported.

## 5. Upgrading

```bash
just backup /srv/loft/pre-upgrade      # always first
git pull && docker compose build
docker compose up -d --wait db redis minio
for s in gateway documents; do
  docker compose run --rm --no-deps "$s" alembic -c /app/migrations/alembic.ini upgrade head
done
docker compose up -d
scripts/smoke-healthz.sh 8000
```

Migrations only go forward, and run from the images. To roll back, restore the
pre-upgrade backup with the old tag's images.

## 6. Sizing

Three facts drive sizing:

- **Geometry is CPU-bound, and one worker uses one core.** OCP does not
  release the GIL, so each extra modeller on a worker multiplies everyone's
  latency. A 50-feature edit takes 2.1 s for one user, 4.6 s for two and
  9.7 s for four.
- **The rebuild cache is a per-process LRU of 8 entries**
  (`REBUILD_CACHE_CAPACITY`). A modeller uses two, so one worker serves about
  four modellers before hit rates collapse.
- **Session affinity is built in.** `GEOMETRY_URL` takes a comma-separated
  list, and the gateway pins each user to one worker by rendezvous hash. Use
  `docker compose -f docker-compose.yml -f docker-compose.scale.yml up -d`
  with `S3_URL` set. Bare `--scale geometry=N` has no affinity.

**Rule: one geometry worker per concurrent modeller, one core and about 1 GiB
of RAM per worker.** An idle worker's floor is about 500 MiB. Gateway and
documents need tens of MiB, and Postgres 0.5 to 1 GiB. Size the Postgres disk
for imported STEP stored inline, which can reach 16 MiB per import.

| Use                               | Cores | RAM    | Geometry workers |
| --------------------------------- | ----: | -----: | ---------------: |
| One engineer, parts up to ~50 features | 2 | 4 GiB  | 1 |
| One engineer, up to ~100 features | 4     | 8 GiB  | 2                |
| Four concurrent modellers         | 8     | 16 GiB | 4 (scale overlay) |
| Eight concurrent modellers        | 16    | 32 GiB | 8                |

**Comfortable part sizes (one user, first open / add a feature):** 25 features
0.6 s / 0.14 s; 50 features 2.0 s / 0.22 s; 100 features 6.9 s / 0.43 s;
200 features 27 s / 1.0 s. Feature count sets the limit, not face count. An
edit near the start of the tree costs as much as a first open.

**Overload behaviour.** Each geometry worker admits `ADMISSION_CONCURRENCY`
(1) request at a time, queues up to `ADMISSION_QUEUE_DEPTH` (8), and waits at
most `ADMISSION_MAX_WAIT_S` (20 s). Past that, it answers
**503 `service_overloaded`** with `Retry-After`. The gateway waits
`GEOMETRY_TIMEOUT_S` (90 s) and then answers **504 `upstream_timeout`**; the
work is not cancelled, so a retry is cheaper. A **502** means something really
is down. STEP import is capped at 20 CPU-seconds and a 16 MiB upload.

## 7. Security notes

- **Never publish `documents` (:8001) or `geometry` (:8002).** Documents
  trusts the gateway's `X-Loft-User` header. `scripts/check-compose.py`
  gates this.
- Set `LOFT_ENV=production`, a real `JWT_SECRET` (at least 32 characters),
  `POSTGRES_PASSWORD` and `MINIO_ROOT_PASSWORD`. Outside dev, the services
  refuse to boot on the dev defaults.
- Session limits: `SESSION_IDLE_TTL_S` (24 h, sliding), `SESSION_MAX_AGE_S`
  (7 d) and `JWT_TTL_S` (1 h), checked at boot. The refresh cookie is
  `Secure`, so run TLS, or sessions on a host other than localhost are capped
  at 1 h (RESEARCH §13).
- Backups hold password hashes and every part. Protect them like the
  database.

## 8. Proving it on your own hardware

`just backup-drill` seeds a user, part, assembly and drawing; backs up;
destroys every volume; boots from nothing; restores; and demands the same
volume and the same `mesh_glb_id`. CI runs it on every push (`deploy-path`).

## 9. Metrics

Every service exposes the same Prometheus metrics at `/metrics`
(`packages/py-kit/src/py_kit/metrics.py`). With `LOFT_ENV=dev` the endpoint is
open. Otherwise it returns 404 unless the request carries
`Authorization: Bearer $METRICS_TOKEN`. That applies on the internal network
too, because it is not an authentication boundary. `METRICS_ENABLED=false`
removes the endpoint entirely. Scrape `gateway:8000`, `documents:8001` and
`geometry:8002` from a Prometheus on the compose network:

```yaml
scrape_configs:
  - job_name: loft
    authorization:
      type: Bearer
      credentials_file: /etc/prometheus/loft-metrics-token
    static_configs:
      - targets: ["gateway:8000", "documents:8001", "geometry:8002"]
```

**Is it broken, or is it a big part?**

- `loft_rebuild_duration_seconds{cache,tree_size}` shows rebuild time, with
  the cache (`hit`, `partial`, `miss`) and the tree-size band as labels.
- `loft_rebuild_cache_hits_total` and `loft_rebuild_cache_misses_total`: a
  falling hit rate means too few workers, or no affinity.
- `loft_admission_queued` and `loft_admission_in_flight`: a queue that stays
  above zero, or in-flight pinned at the bound, means you need more workers.
  `loft_admission_rejected_total{reason}` counts the 503s.
- `loft_feature_errors_total{code}` counts modelling failures by error code.
- `loft_step_import_duration_seconds{outcome}` and
  `loft_step_import_refusals_total{reason}`: a refusal means a resource
  limit was hit, not that the input was bad.
