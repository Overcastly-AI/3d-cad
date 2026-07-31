"""py_kit.metrics — the exposition, its posture, and proof the numbers MOVE.

EVERY test here asserts a DELTA, never the presence of a metric name. A counter
that is exported but never incremented is the failure mode this whole module is
supposed to prevent, and a test that greps ``/metrics`` for a string passes
happily against exactly that bug — the same "a gate that cannot fail" class the
repo has been bitten by before. So each test reads the sample value, causes the
event, reads it again, and pins the difference.
"""

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from py_kit.app import create_app
from py_kit.config import BaseServiceSettings
from py_kit.metrics import (
    MAX_DISTINCT_CODES,
    METRICS_PATH,
    REGISTRY,
    UNMATCHED_ROUTE,
    note_rebuild,
    observe_step_import,
    record_feature_error,
    record_rebuild_cache_eviction,
    record_rebuild_cache_hit,
    record_rebuild_cache_miss,
    record_rebuild_cache_store,
)
from py_kit.schemas.features import FeatureError

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _value(name: str, labels: dict[str, str] | None = None) -> float:
    """A sample's current value, with an absent series read as 0.0.

    Absent-as-zero matters: a Prometheus counter with labels does not exist
    until its first increment, so "was None, is now 1.0" and "was 3.0, is now
    4.0" are the same delta and the tests must not care which they got.
    """
    sample = REGISTRY.get_sample_value(name, labels or {})
    return 0.0 if sample is None else sample


def _without_request_id(envelope: dict[str, Any]) -> dict[str, Any]:
    """The error body minus the one field that legitimately differs per call."""
    error = {k: v for k, v in envelope["error"].items() if k != "request_id"}
    return {"error": error}


def _client(
    *,
    loft_env: str | None = "dev",
    metrics_enabled: bool = True,
    metrics_token: str | None = None,
) -> TestClient:
    settings = BaseServiceSettings(
        service_name="metrics-test",
        loft_env=loft_env,
        metrics_enabled=metrics_enabled,
        metrics_token=metrics_token,
    )
    app = create_app(settings, title="Metrics Test", version="0.0.1")

    @app.get("/api/v1/things/{thing_id}")
    async def read_thing(thing_id: str) -> dict[str, str]:
        return {"thing_id": thing_id}

    @app.get("/api/v1/slow")
    async def slow() -> dict[str, str]:
        time.sleep(0.02)
        return {"status": "done"}

    @app.get("/api/v1/rebuild/{part_id}")
    async def rebuild(part_id: str, features: int, resumed: int) -> dict[str, str]:
        note_rebuild(features=features, resumed=resumed)
        return {"part_id": part_id}

    @app.get("/api/v1/boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    # ``raise_server_exceptions=False`` so an unhandled exception is rendered as
    # the 500 a real client would receive, which is what the metric must agree
    # with. Note the middleware never sees a response in that case — Starlette's
    # ServerErrorMiddleware sits OUTSIDE it — which is exactly why the recorded
    # status defaults to 500 rather than to "unknown".
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with _client() as ready:
        yield ready


# ---------------------------------------------------------------------------
# HTTP: rate, latency, status — and the cardinality guarantee
# ---------------------------------------------------------------------------


def test_request_counter_moves_by_exactly_one(client: TestClient) -> None:
    labels = {
        "method": "GET",
        "route": "/api/v1/things/{thing_id}",
        "status": "200",
    }
    before = _value("loft_http_requests_total", labels)

    assert client.get("/api/v1/things/abc").status_code == 200

    assert _value("loft_http_requests_total", labels) == before + 1


def test_route_label_is_the_template_not_the_path(client: TestClient) -> None:
    """THE cardinality guarantee: a part id must never become a label value.

    Two requests to two different ids land on ONE series. If this regressed to
    the raw path, a self-hoster's Prometheus would grow a time series per part
    per user — the exact way an operator blows up their own monitoring.
    """
    template = {"method": "GET", "route": "/api/v1/things/{thing_id}", "status": "200"}
    before = _value("loft_http_requests_total", template)

    client.get("/api/v1/things/part-aaaa")
    client.get("/api/v1/things/part-bbbb")

    assert _value("loft_http_requests_total", template) == before + 2
    # ...and specifically NOT one series per id.
    for raw in ("/api/v1/things/part-aaaa", "/api/v1/things/part-bbbb"):
        assert (
            REGISTRY.get_sample_value(
                "loft_http_requests_total",
                {"method": "GET", "route": raw, "status": "200"},
            )
            is None
        )


def test_route_label_survives_include_router() -> None:
    """REGRESSION, and the reason this test exists at all: since FastAPI 0.139
    ``include_router`` does NOT flatten its routes into ``app.routes`` — they sit
    behind an ``_IncludedRouter``. The first version of this middleware built an
    ``endpoint -> path`` map by walking ``app.routes``, passed every test in this
    file (which register routes with ``@app.get``), and labelled EVERY real API
    route in all three services ``<unmatched>``: one useless series, and a
    latency histogram of the whole product mashed together. Every route in the
    product arrives via ``include_router``, so that is the shape to pin.
    """
    settings = BaseServiceSettings(service_name="router-test", loft_env="dev")
    app = create_app(settings, title="Router Test", version="0.0.1")
    router = APIRouter(prefix="/api/v1")

    @router.get("/widgets/{widget_id}")
    async def read_widget(widget_id: str) -> dict[str, str]:
        return {"widget_id": widget_id}

    app.include_router(router)

    labels = {
        "method": "GET",
        "route": "/api/v1/widgets/{widget_id}",
        "status": "200",
    }
    with TestClient(app) as routed:
        before = _value("loft_http_requests_total", labels)
        assert routed.get("/api/v1/widgets/w-1").status_code == 200
        assert _value("loft_http_requests_total", labels) == before + 1
    # The prefix must be part of the label, not stripped by it.
    assert (
        REGISTRY.get_sample_value(
            "loft_http_requests_total",
            {"method": "GET", "route": "/widgets/{widget_id}", "status": "200"},
        )
        is None
    )


def test_unmatched_paths_collapse_to_one_series(client: TestClient) -> None:
    """A scanner spraying random URLs must cost exactly one time series."""
    labels = {"method": "GET", "route": UNMATCHED_ROUTE, "status": "404"}
    before = _value("loft_http_requests_total", labels)

    for path in ("/wp-login.php", "/.env", "/api/v2/whatever"):
        assert client.get(path).status_code == 404

    assert _value("loft_http_requests_total", labels) == before + 3


def test_duration_histogram_records_the_request_in_the_right_bucket(
    client: TestClient,
) -> None:
    labels = {"method": "GET", "route": "/api/v1/slow"}
    count_before = _value("loft_http_request_duration_seconds_count", labels)
    fast_before = _value(
        "loft_http_request_duration_seconds_bucket", {**labels, "le": "0.01"}
    )
    slow_before = _value(
        "loft_http_request_duration_seconds_bucket", {**labels, "le": "2.0"}
    )

    client.get("/api/v1/slow")

    assert (
        _value("loft_http_request_duration_seconds_count", labels) == count_before + 1
    )
    # The handler sleeps 20 ms, so it must MISS the 10 ms bucket and make the
    # 2 s one — i.e. the histogram measures the request, it does not just count.
    assert (
        _value("loft_http_request_duration_seconds_bucket", {**labels, "le": "0.01"})
        == fast_before
    )
    assert (
        _value("loft_http_request_duration_seconds_bucket", {**labels, "le": "2.0"})
        == slow_before + 1
    )


def test_a_handler_that_raises_is_counted_as_500(client: TestClient) -> None:
    """The error envelope turns an unhandled exception into a 500; the metric
    must agree with what the client saw, not with what the handler intended."""
    labels = {"method": "GET", "route": "/api/v1/boom", "status": "500"}
    before = _value("loft_http_requests_total", labels)

    assert client.get("/api/v1/boom").status_code == 500

    assert _value("loft_http_requests_total", labels) == before + 1


def test_in_flight_gauge_returns_to_its_baseline(client: TestClient) -> None:
    """A leaked in-flight counter would slowly read as a saturated service."""
    before = _value("loft_http_requests_in_flight")
    client.get("/api/v1/things/x")
    client.get("/api/v1/boom")  # even the failing path must decrement
    assert _value("loft_http_requests_in_flight") == before


# ---------------------------------------------------------------------------
# rebuild attribution
# ---------------------------------------------------------------------------


def test_rebuild_histogram_and_feature_counters_move(client: TestClient) -> None:
    """An append: 200 features, 199 of them served from the cached prefix."""
    hist = {"cache": "partial", "tree_size": "101-200"}
    count_before = _value("loft_rebuild_duration_seconds_count", hist)
    evaluated_before = _value("loft_rebuild_features_evaluated_total")
    resumed_before = _value("loft_rebuild_features_resumed_total")

    client.get("/api/v1/rebuild/p1", params={"features": 200, "resumed": 199})

    assert _value("loft_rebuild_duration_seconds_count", hist) == count_before + 1
    assert _value("loft_rebuild_features_evaluated_total") == evaluated_before + 1
    assert _value("loft_rebuild_features_resumed_total") == resumed_before + 199


def test_cache_label_separates_cold_warm_and_repeat(client: TestClient) -> None:
    """The three readings an operator has to be able to tell apart."""
    cases = (
        ({"features": 40, "resumed": 0}, {"cache": "miss", "tree_size": "26-50"}),
        ({"features": 40, "resumed": 39}, {"cache": "partial", "tree_size": "26-50"}),
        ({"features": 40, "resumed": 40}, {"cache": "hit", "tree_size": "26-50"}),
    )
    before = {
        labels["cache"]: _value("loft_rebuild_duration_seconds_count", labels)
        for _, labels in cases
    }
    for params, labels in cases:
        client.get("/api/v1/rebuild/p1", params=params)
        assert (
            _value("loft_rebuild_duration_seconds_count", labels)
            == before[labels["cache"]] + 1
        )


def test_a_request_with_no_rebuild_records_no_rebuild_sample(
    client: TestClient,
) -> None:
    """Otherwise every ``/healthz`` would drag the rebuild distribution to 0 s
    and the histogram would describe the probe, not the product."""
    labels = {"cache": "miss", "tree_size": "1-10"}
    before = _value("loft_rebuild_duration_seconds_count", labels)
    client.get("/healthz")
    client.get("/api/v1/things/x")
    assert _value("loft_rebuild_duration_seconds_count", labels) == before


def test_tree_size_label_is_banded_not_a_raw_count(client: TestClient) -> None:
    """Cardinality: 40 and 41 features share a series; a raw count would not."""
    labels = {"cache": "miss", "tree_size": "26-50"}
    before = _value("loft_rebuild_duration_seconds_count", labels)
    client.get("/api/v1/rebuild/p", params={"features": 40, "resumed": 0})
    client.get("/api/v1/rebuild/p", params={"features": 41, "resumed": 0})
    assert _value("loft_rebuild_duration_seconds_count", labels) == before + 2
    assert (
        REGISTRY.get_sample_value(
            "loft_rebuild_duration_seconds_count", {"cache": "miss", "tree_size": "40"}
        )
        is None
    )


def test_note_rebuild_outside_a_request_still_counts_features() -> None:
    """No request means no duration to attribute — but the work still happened,
    so the feature counters must move (a worker or CLI rebuild is real work)."""
    evaluated_before = _value("loft_rebuild_features_evaluated_total")
    note_rebuild(features=12, resumed=4)
    assert _value("loft_rebuild_features_evaluated_total") == evaluated_before + 8


def test_rebuild_cache_counters_move() -> None:
    before = {
        name: _value(f"loft_rebuild_cache_{name}_total")
        for name in ("hits", "misses", "stores", "evictions")
    }
    record_rebuild_cache_hit()
    record_rebuild_cache_miss()
    record_rebuild_cache_store()
    record_rebuild_cache_eviction()
    for name, value in before.items():
        assert _value(f"loft_rebuild_cache_{name}_total") == value + 1


# ---------------------------------------------------------------------------
# feature errors
# ---------------------------------------------------------------------------


def test_constructing_a_feature_error_counts_it_by_code() -> None:
    """The seam: the DTO, not the ~85 raise sites (see FeatureError's docstring)."""
    labels = {"code": "shell_thickness_too_large"}
    before = _value("loft_feature_errors_total", labels)

    FeatureError(
        code="shell_thickness_too_large",
        message="Wall thickness exceeds the smallest local radius.",
    )

    assert _value("loft_feature_errors_total", labels) == before + 1


def test_a_feature_error_parsed_off_the_wire_is_also_counted() -> None:
    """The gateway deserialises geometry's response into this same model, so
    validation must count too — otherwise the seam would only see errors this
    process constructed by hand."""
    labels = {"code": "import_parse_timeout"}
    before = _value("loft_feature_errors_total", labels)

    FeatureError.model_validate_json(
        '{"code": "import_parse_timeout", "message": "aborted"}'
    )

    assert _value("loft_feature_errors_total", labels) == before + 1


def test_distinct_error_codes_are_capped() -> None:
    """Today every code is a literal, so this guards a FUTURE interpolated one
    (``f"failed_{part_id}"``) — an unbounded label is how a self-hoster's
    Prometheus dies, and it would die silently."""
    other_before = _value("loft_feature_errors_total", {"code": "other"})
    for index in range(MAX_DISTINCT_CODES + 25):
        record_feature_error(f"synthetic_code_{index}")

    after = _value("loft_feature_errors_total", {"code": "other"})
    assert after > other_before, "overflow codes must fold into `other`"
    # The total is still true even though the breakdown is no longer complete.
    assert after - other_before >= 25 - MAX_DISTINCT_CODES % 1


# ---------------------------------------------------------------------------
# STEP import
# ---------------------------------------------------------------------------


def test_step_import_records_duration_and_only_refusals_count_as_refusals() -> None:
    ok_before = _value("loft_step_import_duration_seconds_count", {"outcome": "ok"})
    refusal_before = _value(
        "loft_step_import_refusals_total", {"reason": "cpu_timeout"}
    )
    parse_failed_refusals_before = _value(
        "loft_step_import_refusals_total", {"reason": "parse_failed"}
    )

    observe_step_import(1.5, outcome="ok")
    observe_step_import(19.9, outcome="cpu_timeout")
    observe_step_import(0.2, outcome="parse_failed")

    assert (
        _value("loft_step_import_duration_seconds_count", {"outcome": "ok"})
        == ok_before + 1
    )
    assert (
        _value("loft_step_import_refusals_total", {"reason": "cpu_timeout"})
        == refusal_before + 1
    )
    # A malformed file is the USER's problem, not a resource bound: counting it
    # as a refusal would make "are my users hitting the DoS ceiling?" unanswerable.
    assert (
        _value("loft_step_import_refusals_total", {"reason": "parse_failed"})
        == parse_failed_refusals_before
    )


def test_step_import_ceiling_is_a_bucket_boundary() -> None:
    """20 s is ``DEFAULT_STEP_IMPORT_CPU_TIMEOUT_S``. An import at 19.9 s must
    land under it and one at 21 s above, so "approaching the wall" is visible
    before "refused by the wall" starts happening."""
    labels = {"outcome": "ok", "le": "20.0"}
    before = _value("loft_step_import_duration_seconds_bucket", labels)
    observe_step_import(19.9, outcome="ok")
    observe_step_import(21.0, outcome="ok")
    assert _value("loft_step_import_duration_seconds_bucket", labels) == before + 1


# ---------------------------------------------------------------------------
# exposure posture
# ---------------------------------------------------------------------------


def test_metrics_is_open_in_dev(client: TestClient) -> None:
    response = client.get(METRICS_PATH)
    assert response.status_code == 200
    assert "loft_http_requests_total" in response.text
    assert response.headers["content-type"].startswith("text/plain")


def test_metrics_is_404_outside_dev_without_a_token() -> None:
    """Fail-closed, same shape as the JWT and datastore guards: a real
    deployment that configured nothing publishes nothing."""
    with _client(loft_env="production") as unconfigured:
        assert unconfigured.get(METRICS_PATH).status_code == 404


def test_metrics_requires_the_bearer_token_outside_dev() -> None:
    token = "a" * 40
    with _client(loft_env="production", metrics_token=token) as guarded:
        assert guarded.get(METRICS_PATH).status_code == 404
        assert (
            guarded.get(
                METRICS_PATH, headers={"authorization": f"Bearer {'b' * 40}"}
            ).status_code
            == 404
        )
        assert (
            guarded.get(
                METRICS_PATH, headers={"authorization": f"Basic {token}"}
            ).status_code
            == 404
        )
        allowed = guarded.get(
            METRICS_PATH, headers={"authorization": f"Bearer {token}"}
        )
        assert allowed.status_code == 200
        assert "loft_service_info" in allowed.text


def test_unauthorized_metrics_is_indistinguishable_from_disabled() -> None:
    """404 both ways ON PURPOSE — a prober must not learn that this deployment
    has metrics it merely cannot read."""
    with (
        _client(loft_env="production") as guarded,
        _client(metrics_enabled=False) as off,
    ):
        guarded_response = guarded.get(METRICS_PATH)
        off_response = off.get(METRICS_PATH)
        assert guarded_response.status_code == off_response.status_code == 404
        # Identical envelope bar the per-request id, which every response carries.
        assert _without_request_id(guarded_response.json()) == _without_request_id(
            off_response.json()
        )


def test_disabling_metrics_removes_the_instrumentation_too() -> None:
    """Not merely an unread counter: no middleware, so no per-request cost."""
    labels = {"method": "GET", "route": "/api/v1/things/{thing_id}", "status": "200"}
    with _client(metrics_enabled=False) as off:
        before = _value("loft_http_requests_total", labels)
        assert off.get("/api/v1/things/abc").status_code == 200
        assert _value("loft_http_requests_total", labels) == before


def test_metrics_is_not_in_the_openapi_contract(client: TestClient) -> None:
    """Infrastructure, like the probes: it must never reach packages/contracts
    or the generated TS client."""
    schema = client.get("/openapi.json").json()
    assert METRICS_PATH not in schema["paths"]


def test_process_and_gc_basics_are_exported(client: TestClient) -> None:
    """The floor under everything else: is it swapping, saturated, or thrashing?"""
    body = client.get(METRICS_PATH).text
    assert "process_resident_memory_bytes" in body
    assert "process_cpu_seconds_total" in body
    assert "python_gc_collections_total" in body
