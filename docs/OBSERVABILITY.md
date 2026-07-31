# Loft — Observability

**For one person running one stack.** Not an SRE runbook: no alert routing, no
federation, no multi-tenant conventions. The question this file answers is the
one a self-hoster actually has at 11pm — *is Loft broken, or is that just a big
part?* — because in a CAD tool those look identical from the outside. A
legitimate rebuild of a 200-feature part takes **26 seconds** (`docs/PERF.md`),
and the UI during those 26 seconds is indistinguishable from a hung service.

Everything here is exported by `packages/py-kit/src/py_kit/metrics.py`, wired
once in the app factory, so **all three services expose the same metrics under
the same names**.

---

## 1. Turn it on

`/metrics` is served by each service and is **not public by default**. It
follows the same fail-closed posture as `JWT_SECRET` and the datastore
credentials, off the same one variable:

| `LOFT_ENV` | `METRICS_TOKEN` | `GET /metrics` |
| --- | --- | --- |
| `dev` | anything | **200** — open, so a localhost stack just works |
| anything else | unset | **404** |
| anything else | set | **404**, unless the request carries `Authorization: Bearer <token>` |

So for a real deployment:

```bash
# .env
LOFT_ENV=production
METRICS_TOKEN=$(openssl rand -hex 32)   # same value in the scrape config below
```

Two deliberate choices worth knowing:

* **404, not 403.** An unauthorized probe gets exactly the response a stack with
  `METRICS_ENABLED=false` gives, so it cannot even learn that there are metrics
  here to attack.
* **A shared secret, not an IP allowlist.** "Allow loopback" is the tempting
  version and it is actively dangerous: behind the reverse proxy you terminate
  TLS with, *every* request arrives from `127.0.0.1`, so an IP check would serve
  `/metrics` to the whole internet while looking careful.

`METRICS_ENABLED=false` removes the endpoint **and** the per-request
instrumentation — not merely an unread counter.

### Which ports to scrape

In the shipped compose file the gateway is the only service that publishes a
host port; `documents` and `geometry` are reachable only on the compose network,
and the datastores bind loopback. So:

* a Prometheus **container on the compose network** scrapes
  `gateway:8000`, `documents:8001`, `geometry:8002` by service name;
* a Prometheus **on the host** can reach only the gateway unless you publish
  more ports — and the metric you most want (rebuild time) lives in *geometry*,
  so the container is the better shape.

Either way the token is required outside dev, including on the internal network.
That is intentional: an internal network is not an authentication boundary.

### Example scrape config

```yaml
# prometheus.yml — one stack, one Prometheus, 15 s resolution.
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: loft
    authorization:
      type: Bearer
      # Prometheus reads the secret from a file so it is not in this config.
      credentials_file: /etc/prometheus/loft-metrics-token
    static_configs:
      - targets: ["gateway:8000"]
        labels: { service: gateway }
      - targets: ["documents:8001"]
        labels: { service: documents }
      - targets: ["geometry:8002"]
        labels: { service: geometry }
```

A scrape costs about **12 KB** (2.2 KB gzipped — Prometheus asks for gzip and
py-kit's compression middleware provides it) and a few milliseconds of CPU.
At 15 s that is negligible next to one rebuild.

---

## 2. What is exported

`{}` marks a label. Counters carry the usual `_total` suffix; histograms expose
`_bucket` / `_sum` / `_count`.

### The four that are about *this* product

| Metric | Type | Labels | What it means |
| --- | --- | --- | --- |
| `loft_rebuild_duration_seconds` | histogram | `cache`, `tree_size` | Wall time of a request that evaluated at least one feature tree. |
| `loft_rebuild_features_evaluated_total` | counter | — | Features the kernel actually evaluated. |
| `loft_rebuild_features_resumed_total` | counter | — | Features supplied by the prefix cache instead. |
| `loft_rebuild_cache_hits_total` | counter | — | Rebuilds that resumed from a cached prefix. |
| `loft_rebuild_cache_misses_total` | counter | — | Rebuilds that started from feature 0. |
| `loft_rebuild_cache_stores_total` | counter | — | Checkpoints entering the LRU. |
| `loft_rebuild_cache_evictions_total` | counter | — | Checkpoints dropped because the LRU was full. |
| `loft_feature_errors_total` | counter | `code` | Feature evaluations that failed, by error code. |
| `loft_step_import_duration_seconds` | histogram | `outcome` | Wall time of the bounded, killable STEP parse worker. |
| `loft_step_import_refusals_total` | counter | `reason` | Imports refused by a **resource bound**, not by bad input. |

Label values, all bounded and all fixed:

* `cache` ∈ `hit` (nothing had to be evaluated — a `/measure`, `/export` or
  re-tessellate of a tree just evaluated), `partial` (an append: one new feature
  on a long cached prefix), `miss` (a cold rebuild from feature 0).
* `tree_size` ∈ `1-10`, `11-25`, `26-50`, `51-100`, `101-200`, `201+` — bands
  chosen to straddle the wall `docs/PERF.md` measured, not to be round.
* `outcome` ∈ `ok`, `cpu_timeout`, `wall_timeout`, `too_many_products`,
  `parse_failed`, `error`.
* `reason` ∈ `cpu_timeout`, `wall_timeout`, `too_many_products`. **A malformed
  file is not a refusal** — bad input is the user's problem, a resource bound is
  yours, and sharing a counter would make "are my users hitting the ceiling?"
  unanswerable.
* `code` — the ~85 feature error codes (`invalid_body`,
  `shell_thickness_too_large`, `import_parse_timeout`, `boolean_failed`, …).

### The ordinary floor

| Metric | Type | Labels |
| --- | --- | --- |
| `loft_http_requests_total` | counter | `method`, `route`, `status` |
| `loft_http_request_duration_seconds` | histogram | `method`, `route` |
| `loft_http_requests_in_flight` | gauge | — |
| `loft_service_info` | info | `service`, `version` |
| `process_*`, `python_gc_*`, `python_info` | — | from `prometheus_client` |

`route` is always the **route template** (`/api/v1/parts/{part_id}`), never the
requested path, and anything that matched no route is the single series
`route="<unmatched>"`.

### Histogram buckets (why they are not the defaults)

Latency buckets run **5 ms … 60 s**. Prometheus' default top bucket is 10 s,
which would put a 7.5 s rebuild, a 26 s rebuild and a hung request in the same
terminal bucket — precisely the three things you need to tell apart. Two
boundaries are deliberate:

* **2 s** on the latency histograms — the interactive ceiling from
  `docs/RESEARCH.md` §9, so "what fraction felt like a tool" is one expression;
* **20 s** on the STEP import histogram — the CPU ceiling
  (`STEP_IMPORT_TIMEOUT_SECONDS`), so you can see imports *approaching* the wall
  before they start being refused by it.

---

## 3. What healthy looks like, and what struggling looks like

Numbers below come from `docs/PERF.md` (measured, same machine class as a
typical self-host box: 4 cores, 16 GB).

### Rebuild time

```promql
# median rebuild
histogram_quantile(0.5, sum by (le) (rate(loft_rebuild_duration_seconds_bucket[5m])))

# the one that matters: fraction of rebuilds under the 2 s interactive ceiling
sum(rate(loft_rebuild_duration_seconds_bucket{le="2.0"}[5m]))
  / sum(rate(loft_rebuild_duration_seconds_count[5m]))
```

| Reading | Verdict |
| --- | --- |
| p50 < 0.5 s, >90 % under 2 s | **Healthy.** Ordinary parts, warm cache. |
| p95 2–8 s, concentrated in `tree_size="51-100"` | **Working as designed, and your users can feel it.** This is Loft's known wall (`docs/PERF.md`: rebuild grows as N^1.8 in feature count), not a fault. Nothing to fix in ops. |
| p50 jumps with `cache="miss"` climbing | Workers are restarting, or the working set outgrew the cache — see below. |
| p95 climbing at *constant* `tree_size` | A real regression, or the box is saturated. Cross-check `process_cpu_seconds_total` and `loft_http_requests_in_flight`. |

Always read this metric **by `tree_size`**. Aggregated across bands it is
meaningless: a fleet of 25-feature parts and one 200-feature part average out to
a number describing no request that ever happened.

### Rebuild cache — the metric that tells you your worker count is wrong

```promql
sum(rate(loft_rebuild_cache_hits_total[5m]))
  / sum(rate(loft_rebuild_cache_hits_total[5m]) + rate(loft_rebuild_cache_misses_total[5m]))
```

| Reading | Verdict |
| --- | --- |
| hit rate > 0.7, evictions ≈ 0 | **Healthy.** Appends and repeats are being served warm; this is the difference between a 1.0 s append and a 26 s one on a 200-feature part. |
| hit rate < 0.3 with steady traffic | The cache is not helping. Most likely cause is below. |
| evictions rising steadily | The working set exceeds the LRU (8 checkpoints per process). More concurrent parts than the cache holds. |

**The per-process trap, in one paragraph.** The prefix cache is an in-process
LRU — `geometry.rebuild_cache`. Raising `WEB_CONCURRENCY` to N gives you N
independent caches, and a user's second request lands on whichever worker the
kernel picks, so the *expected* hit rate falls roughly as 1/N even though every
individual cache is behaving perfectly. If you raised the worker count and
latency got *worse*, this metric is the proof. Geometry is CPU-bound on OCCT
(`docs/PERF.md`), so more workers than cores buys nothing anyway; the honest
tuning is workers ≈ cores, and watch the hit rate when you change it.

`loft_rebuild_features_resumed_total / (resumed + evaluated)` is the same story
in units of work saved — how much of the kernel's job the cache is deleting.

### Feature errors — three very different pages

```promql
topk(5, sum by (code) (rate(loft_feature_errors_total[15m])))
```

| Spiking code | What it actually means |
| --- | --- |
| `shell_thickness_too_large`, `no_fillet_edges`, `hole_off_body`, `profile_not_closed` | **A user is learning the tool.** Not an incident. Expected background rate. |
| `invalid_body`, `boolean_failed` | **Investigate.** The kernel refused to publish a body. Worth a bug report with the part. |
| `import_parse_timeout` | Users are hitting the STEP DoS ceiling — see below. |
| `reference_unresolved`, `subshape_unresolved` | Usually a part edited upstream of a selection; a burst after a revision is normal, a sustained rate is not. |

Read these on the **geometry** job. The gateway re-validates geometry's response
into the same contract model, so a proxied failure appears on the gateway job
too — the same event, one hop later. Do not sum across jobs.

### STEP import

```promql
sum by (reason) (rate(loft_step_import_refusals_total[1h]))
histogram_quantile(0.95, sum by (le) (rate(loft_step_import_duration_seconds_bucket{outcome="ok"}[1h])))
```

| Reading | Verdict |
| --- | --- |
| p95 under ~4 s, no refusals | **Healthy.** Measured: 3.5 CPU s for the largest part Loft itself can export (2 006 faces, 7 MiB), ~5 s at the 16 MiB upload cap. |
| `reason="cpu_timeout"` non-zero | A file is burning the 20 s CPU ceiling. The ceiling was re-derived in `docs/PERF.md` (PERF-3) to sit at ~3x the worst file the upload cap admits, so this should be **unreachable by any accepted file** at the measured rate — a hit means either a topologically pathological file (which is what the bound is for) or a real regression. Raise `STEP_IMPORT_TIMEOUT_SECONDS` only after looking at the file. |
| `reason="wall_timeout"` non-zero | Different problem: the parse is *wedged*, not burning CPU. Usually the box is thrashing. Check `process_resident_memory_bytes`. |
| `reason="too_many_products"` | An assembly STEP with more occurrences than the import ceiling. A user-facing limit, not a fault. |

### Is the box the problem?

```promql
rate(process_cpu_seconds_total[5m])          # ~1.0 per core saturated
process_resident_memory_bytes                # OCCT baseline is ~500 MiB before any part
loft_http_requests_in_flight                 # sustained ≈ worker count means queueing
rate(python_gc_collections_total[5m])
```

A geometry worker sitting at ~500–800 MiB RSS is normal — that is OCCT's
baseline plus a few cached checkpoints (~2–4 MiB each, capped at 8). Sustained
`in_flight` at or above the worker count means requests are queueing behind the
CPU, which on a rebuild-heavy workload is the expected failure mode and the
signal to add cores, not workers.

---

## 4. Cost and cardinality

**Instrumentation overhead.** Measured on this repo, 4-core container, A/B
between `METRICS_ENABLED=true` and `false` (which removes the middleware
entirely, so it is a genuine A/B), interleaved samples, median:

| Where | Route | metrics off | metrics on | added |
| --- | --- | ---: | ---: | ---: |
| in-process (ASGI, no sockets) | `GET /healthz` | 641.8 µs | 672.1 µs | **+30.3 µs** |
| in-process | `GET /api/v1/parts/{part_id}` | 694.9 µs | 726.2 µs | **+31.3 µs** |
| in-process | `POST /api/v1/evaluate` (also records a rebuild) | 647.4 µs | 681.1 µs | **+33.7 µs** |
| loopback HTTP, real geometry service | `GET /healthz` | 1.164 ms | 1.211 ms | +46.4 µs |
| loopback HTTP, real geometry service | `POST /api/v1/evaluate` (2 features) | 4.476 ms | 4.510 ms | +34.3 µs |

So: **~30 µs per request.** Against the numbers this product actually produces
that is 0.0001 % of a 26 s rebuild and 0.0008 % of a 4 ms warm evaluate. The
middleware is pure ASGI rather than Starlette's `BaseHTTPMiddleware` precisely
to keep it there — no task group, no streaming bridge, just a `perf_counter`
pair and two metric updates. Scraping costs ~12 KB and a few ms.

**Cardinality.** No label is ever a part id, user id, feature id, request id or
raw URL path. Worst case, with every route in the product exercised:

| Series | gateway | documents | geometry |
| --- | ---: | ---: | ---: |
| `loft_http_request_duration_seconds` (pairs × 17) | ~1 380 | ~1 020 | ~510 |
| `loft_http_requests_total` (pairs × statuses seen) | ~500 | ~360 | ~180 |
| `loft_rebuild_duration_seconds` (3 × 6 × 17) | — | — | 306 |
| `loft_step_import_duration_seconds` (6 × 13) | — | — | 78 |
| `loft_feature_errors_total` | ≤129 | — | ≤129 |
| everything else (cache, gauges, process, GC) | ~30 | ~30 | ~30 |
| **total** | **~2 000** | **~1 400** | **~1 200** |

≈ **4 600 series for the whole stack**, a few tens of MB in Prometheus. Two
guards keep it there and both are unit-tested:

* an unmatched path collapses to one `route="<unmatched>"` series, so a
  vulnerability scanner spraying URLs costs one series, not thousands;
* the one free-form label in the product (`code`, a plain `str` on the contract
  DTO) is capped at 128 distinct values per process, with the overflow folded
  into `code="other"` — the total stays true even if the breakdown stops being
  complete. Today every code is a literal constant; the cap guards the future
  interpolated one.

---

## 5. Honest limits

Things this does **not** do, stated so nobody reads a flat line as good news:

* **Rebuild timing is per HTTP request.** `loft_rebuild_duration_seconds` is the
  wall time of a request that evaluated at least one tree — what a modeller
  waits, including tessellation and response encoding — not an isolated kernel
  timing. A rebuild performed outside a request (a future queue worker, a CLI)
  moves the feature counters but is not timed.
* **A request that rebuilds several trees** (an assembly evaluating one tree per
  unique part) contributes **one** observation, labelled by the largest tree and
  by the aggregate cache outcome.
* **The cache counters are per process.** With multiple workers, each exports
  its own; that is a feature (see the per-process trap above), but it means you
  must aggregate across `instance` to get a fleet hit rate.
* **No tracing, no exemplars, no per-part attribution.** Deliberate: per-part
  labels are exactly the cardinality explosion this document refuses.
* **No alerting rules ship with this.** One person running one stack does not
  need a paging tree; the tables above are meant to be read, not routed.

## 6. Where the code is

| Thing | File |
| --- | --- |
| Metric definitions, middleware, `/metrics` route, posture | `packages/py-kit/src/py_kit/metrics.py` |
| Config (`METRICS_ENABLED`, `METRICS_TOKEN`) | `packages/py-kit/src/py_kit/config.py`, `.env.example` |
| Rebuild + cache seam | `services/geometry/src/geometry/rebuild_cache.py` (`PrefixCache.take` / `.store`) |
| STEP import seam | `services/geometry/src/geometry/kernel/imports.py` (`run_bounded_parse_worker`) |
| Feature-error seam | `packages/py-kit/src/py_kit/schemas/features.py` (`FeatureError.model_post_init`) |
| Proof every counter moves | `packages/py-kit/tests/test_metrics.py`, `services/geometry/tests/test_metrics_seams.py` |

Every seam above was chosen because it **cannot be bypassed** — the DTO every
feature failure is rendered through, the cache `evaluate_tree` consults as its
second statement, the one bounded worker both STEP readers run through. A
counter placed at call sites instead would silently stop incrementing the day
someone adds a call site, and a flat line reads as good news. Correspondingly,
every test asserts that a number **moves** by a specific amount, never that a
metric name appears in the exposition.
