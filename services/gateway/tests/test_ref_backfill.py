"""gateway orchestration of DESIGN-INTENT-BACKFILL: on open, and the sweep CLI.

Mock transports per upstream, real auth over SQLite (the harness of
tests/test_evaluate_proxy.py). Pinned here: a non-preview evaluate of a tree
holding an unnamed pick runs the three hops AFTER the response and after the
verdict is recorded; a preview or a fully named tree never does; a geometry
error writes nothing (so the part stays pending); and no backfill failure can
reach the user's evaluate. The CLI is driven through the same mocks.
"""

import asyncio
import contextlib
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from gateway.ref_backfill import Upstreams, revert, sweep
from loft_wire.features import (
    EvaluateTreeRequest,
    EvaluateTreeResult,
    FeatureResult,
)
from loft_wire.parts import PRINCIPAL_HEADER
from loft_wire.ref_names import (
    RefBackfillPart,
    RefBackfillPartList,
    RefNamesApplyRequest,
    RefNamesApplyResult,
    RefNamesFailure,
    RefNamesFailureResult,
    RefNamesReport,
    RefNamesRequestResponse,
    RefNamesRevertResult,
)
from py_kit.db import async_dsn
from py_kit.metrics import REGISTRY
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"
Handler = Callable[[httpx.Request], httpx.Response]

PART = uuid.UUID("00000000-0000-0000-0000-0000000000fb")
EXTRUDE = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
FILLET = uuid.UUID("00000000-0000-0000-0000-0000000000b3")
OWNER = uuid.UUID("6f3f6b64-0000-4000-8000-0000000000d1")


def _fillet(name: str | None) -> dict[str, Any]:
    signature: dict[str, Any] = {
        "curve": "line",
        "end_a": {"x": 0, "y": 0, "z": 0},
        "end_b": {"x": 0, "y": 0, "z": 10},
        "midpoint": {"x": 0, "y": 0, "z": 5},
        "length_mm": 10.0,
    }
    if name is not None:
        signature["topo_name"] = name
    return {
        "type": "fillet",
        "version": 1,
        "params": {
            "edges": {
                "kind": "edges",
                "refs": [
                    {
                        "kind": "subshape",
                        "feature_id": str(EXTRUDE),
                        "subshape_type": "edge",
                        "selector": {"selector_version": 1, "signature": signature},
                    }
                ],
            },
            "radius_mm": 1.0,
        },
    }


def _tree(name: str | None = None, version: int = 4) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate(
        {
            "part_id": str(PART),
            "tree_version": version,
            "features": [{"id": str(FILLET), "feature": _fillet(name)}],
        }
    )


def _result() -> EvaluateTreeResult:
    return EvaluateTreeResult(
        part_id=PART,
        tree_version=4,
        features=[FeatureResult(feature_id=FILLET, status="ok")],
        mesh_glb_id=None,
        properties=None,
        last_good_feature_id=FILLET,
    )


def _report(version: int = 4) -> RefNamesReport:
    return RefNamesReport.model_validate(
        {
            "tree_version": version,
            "kernel": "k",
            "outcomes": [
                {
                    "feature_id": str(FILLET),
                    "path": "/edges/refs/0",
                    "kind": "edge",
                    "signature_sha256": "0" * 64,
                    "outcome": "named",
                    "topo_name": "a|b",
                }
            ],
        }
    )


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path}/gateway.db"
    asyncio.run(_create_schema(url))
    return url


def _client(db_url: str, documents: Handler, geometry: Handler) -> TestClient:
    settings = GatewaySettings(
        geometry_url="http://geometry.internal:8002",
        documents_url="http://documents.internal:8001",
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(
        settings,
        geometry_transport=httpx.MockTransport(geometry),
        documents_transport=httpx.MockTransport(documents),
    )
    return TestClient(app, raise_server_exceptions=False)


def _bearer(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "bf@example.com", "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _documents(
    seen: list[httpx.Request],
    tree: EvaluateTreeRequest,
    *,
    request_status: int = 200,
    needed: bool = True,
    backoff: bool = False,
) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/evaluation-request"):
            return httpx.Response(200, content=tree.model_dump_json())
        if path.endswith("/last-evaluation"):
            return httpx.Response(200, json={})
        if path.endswith("/ref-names-request"):
            body = RefNamesRequestResponse(
                needed=needed and not backoff,
                tree_version=tree.tree_version,
                ref_names_checked_version=None,
                backoff_until=datetime(2026, 10, 8, 12, tzinfo=UTC)
                if backoff
                else None,
                request=tree if needed and not backoff else None,
            )
            return httpx.Response(request_status, content=body.model_dump_json())
        if path.endswith("/ref-names/failure"):
            failure = RefNamesFailure.model_validate_json(request.content)
            result = RefNamesFailureResult(result="backoff", attempts=1)
            assert failure.tree_version == tree.tree_version
            return httpx.Response(200, content=result.model_dump_json())
        if path.endswith("/ref-names"):
            applied = RefNamesApplyRequest.model_validate_json(request.content)
            result = RefNamesApplyResult(
                result="dry_run" if applied.dry_run else "written",
                tree_version=tree.tree_version + (0 if applied.dry_run else 1),
                refs_written=len(applied.report.outcomes),
            )
            return httpx.Response(200, content=result.model_dump_json())
        return httpx.Response(404, json={})

    return handler


def _geometry(
    seen: list[httpx.Request], *, names_status: int = 200, timeout: bool = False
) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/ref-names":
            if timeout:
                raise httpx.ReadTimeout("cold rebuild too slow", request=request)
            if names_status != 200:
                return httpx.Response(names_status, json={"error": {}})
            tree = EvaluateTreeRequest.model_validate_json(request.content)
            return httpx.Response(
                200, content=_report(tree.tree_version).model_dump_json()
            )
        return httpx.Response(200, content=_result().model_dump_json())

    return handler


def _paths(seen: list[httpx.Request]) -> list[str]:
    return [f"{r.method} {r.url.path.rsplit('/', 1)[-1]}" for r in seen]


def _runs(trigger: str, result: str) -> float:
    value = REGISTRY.get_sample_value(
        "loft_ref_backfill_runs_total", {"trigger": trigger, "result": result}
    )
    return 0.0 if value is None else value


def test_an_open_of_an_unnamed_tree_backfills_after_the_verdict(db_url: str) -> None:
    docs: list[httpx.Request] = []
    geo: list[httpx.Request] = []
    before = _runs("open", "written")
    with _client(db_url, _documents(docs, _tree()), _geometry(geo)) as client:
        response = client.post(
            f"/api/v1/parts/{PART}/evaluate", headers=_bearer(client)
        )
    assert response.status_code == 200, response.text
    assert _paths(docs) == [
        "GET evaluation-request",
        "PUT last-evaluation",
        "GET ref-names-request",
        "POST ref-names",
    ]
    assert _paths(geo) == ["POST evaluate", "POST ref-names"]
    # An open never bypasses documents' backoff.
    assert "ignore_backoff" not in docs[2].url.params
    applied = RefNamesApplyRequest.model_validate_json(docs[-1].content)
    assert applied.tree_version == 4
    assert applied.trigger == "open"
    assert not applied.dry_run
    assert docs[-1].headers[PRINCIPAL_HEADER] == docs[0].headers[PRINCIPAL_HEADER]
    assert _runs("open", "written") - before == 1


def test_a_named_tree_never_asks(db_url: str) -> None:
    docs: list[httpx.Request] = []
    geo: list[httpx.Request] = []
    with _client(db_url, _documents(docs, _tree("a|b")), _geometry(geo)) as client:
        response = client.post(
            f"/api/v1/parts/{PART}/evaluate", headers=_bearer(client)
        )
    assert response.status_code == 200
    assert _paths(docs) == ["GET evaluation-request", "PUT last-evaluation"]
    assert _paths(geo) == ["POST evaluate"]


def test_a_preview_never_triggers_it(db_url: str) -> None:
    docs: list[httpx.Request] = []
    geo: list[httpx.Request] = []
    with _client(db_url, _documents(docs, _tree()), _geometry(geo)) as client:
        response = client.post(
            f"/api/v1/parts/{PART}/evaluate",
            params={"before": str(FILLET)},
            headers=_bearer(client),
        )
    assert response.status_code == 200
    assert _paths(docs) == ["GET evaluation-request"]
    assert _paths(geo) == ["POST evaluate"]


def test_a_geometry_error_writes_nothing(db_url: str) -> None:
    docs: list[httpx.Request] = []
    geo: list[httpx.Request] = []
    before = _runs("open", "failed")
    with _client(
        db_url, _documents(docs, _tree()), _geometry(geo, names_status=503)
    ) as client:
        response = client.post(
            f"/api/v1/parts/{PART}/evaluate", headers=_bearer(client)
        )
    assert response.status_code == 200
    assert "POST ref-names" not in _paths(docs)
    assert _paths(geo) == ["POST evaluate", "POST ref-names"]
    assert _runs("open", "failed") - before == 1


@pytest.mark.parametrize("request_status", [500, 404])
def test_a_documents_failure_is_swallowed(db_url: str, request_status: int) -> None:
    docs: list[httpx.Request] = []
    geo: list[httpx.Request] = []
    with _client(
        db_url, _documents(docs, _tree(), request_status=request_status), _geometry(geo)
    ) as client:
        response = client.post(
            f"/api/v1/parts/{PART}/evaluate", headers=_bearer(client)
        )
    assert response.status_code == 200
    assert EvaluateTreeResult.model_validate(response.json()) == _result()
    assert _paths(geo) == ["POST evaluate"]


def test_an_unreachable_documents_is_swallowed(db_url: str) -> None:
    calls = {"n": 0}
    tree = _tree()

    def documents(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.url.path.endswith("/ref-names-request"):
            raise httpx.ConnectError("down", request=request)
        return _documents([], tree)(request)

    with _client(db_url, documents, _geometry([])) as client:
        response = client.post(
            f"/api/v1/parts/{PART}/evaluate", headers=_bearer(client)
        )
    assert response.status_code == 200
    assert calls["n"] == 3


# --- the CLI -----------------------------------------------------------------------


def _sweep_documents(
    seen: list[httpx.Request], parts: list[RefBackfillPart], needed: set[uuid.UUID]
) -> Handler:
    trees = {p.part_id: _tree(version=p.tree_version) for p in parts}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path == "/api/v1/ref-backfill/parts":
            wanted = request.url.params.get("part_id")
            rows = [p for p in parts if wanted is None or str(p.part_id) == wanted]
            return httpx.Response(
                200, content=RefBackfillPartList(parts=rows).model_dump_json()
            )
        part_id = uuid.UUID(path.split("/")[4])
        if path.endswith("/revert"):
            result = (
                RefNamesRevertResult(
                    result="reverted", tree_version=9, features_restored=1
                )
                if part_id != _P1.part_id or request.url.params.get("force")
                else RefNamesRevertResult(
                    result="refused", tree_version=9, detail="edited after"
                )
            )
            return httpx.Response(200, content=result.model_dump_json())
        return _documents([], trees[part_id], needed=part_id in needed)(request)

    return handler


def _upstreams(documents: Handler, geometry: Handler) -> Upstreams:
    return Upstreams(
        documents=httpx.AsyncClient(
            base_url="http://documents", transport=httpx.MockTransport(documents)
        ),
        geometry=httpx.AsyncClient(
            base_url="http://geometry", transport=httpx.MockTransport(geometry)
        ),
    )


_P1 = RefBackfillPart(
    part_id=uuid.UUID(int=1),
    owner_id=OWNER,
    tree_version=4,
    ref_names_checked_version=None,
)
_P2 = RefBackfillPart(
    part_id=uuid.UUID(int=2),
    owner_id=uuid.UUID(int=7),
    tree_version=6,
    ref_names_checked_version=None,
)


@pytest.mark.parametrize("dry_run", [False, True])
def test_the_sweep_backfills_each_pending_part_as_its_owner(dry_run: bool) -> None:
    docs: list[httpx.Request] = []
    geo: list[httpx.Request] = []
    lines: list[str] = []
    upstreams = _upstreams(
        _sweep_documents(docs, [_P1, _P2], {_P1.part_id}), _geometry(geo)
    )
    code = asyncio.run(sweep(upstreams, dry_run=dry_run, out=lines.append))
    assert code == 0
    applies = [
        (
            r.headers[PRINCIPAL_HEADER],
            RefNamesApplyRequest.model_validate_json(r.content),
        )
        for r in docs
        if r.method == "POST"
    ]
    if dry_run:
        # P2 needs nothing and a dry run marks nothing.
        assert [(owner, a.dry_run, a.trigger) for owner, a in applies] == [
            (str(OWNER), True, "sweep")
        ]
    else:
        # P2 needs nothing: an empty report marks it checked, as its owner.
        assert [(owner, len(a.report.outcomes)) for owner, a in applies] == [
            (str(OWNER), 1),
            (str(_P2.owner_id), 0),
        ]
    assert len(geo) == 1
    assert lines[0].startswith(
        f"part {_P1.part_id}: {'dry_run' if dry_run else 'written'}"
    )
    assert "named=1" in lines[0]
    assert lines[1].startswith(f"part {_P2.part_id}: not_needed")
    assert lines[-1].startswith("2 part(s), 0 failed")


def test_the_sweep_fails_loudly_per_part_and_carries_on() -> None:
    lines: list[str] = []
    upstreams = _upstreams(
        _sweep_documents([], [_P1, _P2], {_P1.part_id, _P2.part_id}),
        _geometry([], names_status=500),
    )
    assert asyncio.run(sweep(upstreams, out=lines.append)) == 1
    assert [line.split(":")[1].split()[0] for line in lines[:2]] == ["failed", "failed"]
    assert lines[-1].startswith("2 part(s), 2 failed")


def test_one_part_is_forced_and_reverted_as_its_owner() -> None:
    docs: list[httpx.Request] = []
    lines: list[str] = []
    upstreams = _upstreams(
        _sweep_documents(docs, [_P1, _P2], {_P2.part_id}), _geometry([])
    )
    assert asyncio.run(sweep(upstreams, part=_P2.part_id, out=lines.append)) == 0
    asked = next(r for r in docs if r.url.path.endswith("/ref-names-request"))
    assert asked.url.params.get("force") == "true"
    assert asyncio.run(revert(upstreams, _P2.part_id, out=lines.append)) == 0
    reverted = docs[-1]
    assert reverted.url.path == f"/api/v1/parts/{_P2.part_id}/ref-names/revert"
    assert reverted.headers[PRINCIPAL_HEADER] == str(_P2.owner_id)
    assert (
        lines[-1] == f"part {_P2.part_id}: reverted restored=1 skipped=0 tree_version=9"
    )
    assert asyncio.run(revert(upstreams, uuid.UUID(int=99), out=lines.append)) == 1


# --- retry storm (review of 9d87478) -------------------------------------------------


def _failures(seen: list[httpx.Request]) -> list[str]:
    return [
        RefNamesFailure.model_validate_json(r.content).reason
        for r in seen
        if r.url.path.endswith("/ref-names/failure")
    ]


def test_a_geometry_error_is_reported_so_documents_backs_off(db_url: str) -> None:
    docs: list[httpx.Request] = []
    with _client(
        db_url, _documents(docs, _tree()), _geometry([], names_status=500)
    ) as client:
        client.post(f"/api/v1/parts/{PART}/evaluate", headers=_bearer(client))
    assert _failures(docs) == ["geometry_error"]


def test_a_timeout_is_reported_and_the_evaluate_still_answers(db_url: str) -> None:
    docs: list[httpx.Request] = []
    before = _runs("open", "failed")
    with _client(db_url, _documents(docs, _tree()), _geometry([], timeout=True)) as (
        client
    ):
        response = client.post(
            f"/api/v1/parts/{PART}/evaluate", headers=_bearer(client)
        )
    assert response.status_code == 200
    assert _failures(docs) == ["timeout"]
    assert "POST ref-names" not in _paths(docs)
    assert _runs("open", "failed") - before == 1


def test_a_part_backing_off_starts_no_rebuild(db_url: str) -> None:
    docs: list[httpx.Request] = []
    geo: list[httpx.Request] = []
    before = _runs("open", "backing_off")
    with _client(db_url, _documents(docs, _tree(), backoff=True), _geometry(geo)) as (
        client
    ):
        response = client.post(
            f"/api/v1/parts/{PART}/evaluate", headers=_bearer(client)
        )
    assert response.status_code == 200
    assert _paths(geo) == ["POST evaluate"]
    assert _paths(docs)[-1] == "GET ref-names-request"
    assert _runs("open", "backing_off") - before == 1


@contextlib.asynccontextmanager
async def _async_gateway(tmp_path: Path, documents: Handler, geometry: Any):
    url = f"sqlite:///{tmp_path}/gateway-async.db"
    await _create_schema(url)
    app = build_app(
        GatewaySettings(
            geometry_url="http://geometry.internal:8002",
            documents_url="http://documents.internal:8001",
            postgres_url=url,
            loft_env="dev",
            jwt_secret=TEST_JWT_SECRET,
        ),
        geometry_transport=httpx.MockTransport(geometry),
        documents_transport=httpx.MockTransport(documents),
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://gateway.test"
        ) as client,
    ):
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "bf2@example.com", "password": "hunter2-passphrase"},
        )
        assert response.status_code == 201, response.text
        client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        yield client


def test_evaluates_during_an_in_flight_backfill_start_one_rebuild(
    tmp_path: Path,
) -> None:
    """Three evaluates of one pending part while its cold rebuild is still
    running: exactly one rebuild, and the others are counted ``in_flight``."""
    docs: list[httpx.Request] = []
    rebuilds: list[httpx.Request] = []
    release = asyncio.Event()
    plain = _geometry([])

    async def geometry(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/ref-names":
            rebuilds.append(request)
            await release.wait()
        return plain(request)

    before = _runs("open", "in_flight")

    async def scenario() -> None:
        async with _async_gateway(
            tmp_path, _documents(docs, _tree()), geometry
        ) as client:
            first = asyncio.create_task(client.post(f"/api/v1/parts/{PART}/evaluate"))
            while not rebuilds:
                await asyncio.sleep(0.01)
            others = await asyncio.gather(
                client.post(f"/api/v1/parts/{PART}/evaluate"),
                client.post(f"/api/v1/parts/{PART}/evaluate"),
            )
            assert [r.status_code for r in others] == [200, 200]
            release.set()
            assert (await first).status_code == 200

    asyncio.run(scenario())
    assert len(rebuilds) == 1
    assert _runs("open", "in_flight") - before == 2
    # Once it is done, the next open may run again (dedupe, not a latch).
    assert [r.url.path.rsplit("/", 1)[-1] for r in docs].count("ref-names") == 1


def test_the_sweep_ignores_the_backoff() -> None:
    docs: list[httpx.Request] = []
    upstreams = _upstreams(_sweep_documents(docs, [_P1], {_P1.part_id}), _geometry([]))
    assert asyncio.run(sweep(upstreams, out=lambda _line: None)) == 0
    asked = next(r for r in docs if r.url.path.endswith("/ref-names-request"))
    assert asked.url.params.get("ignore_backoff") == "true"


# --- unsafe revert (review of 9d87478) ----------------------------------------------


def test_a_refused_revert_fails_and_force_warns_loudly() -> None:
    docs: list[httpx.Request] = []
    lines: list[str] = []
    upstreams = _upstreams(_sweep_documents(docs, [_P1], set()), _geometry([]))
    assert asyncio.run(revert(upstreams, _P1.part_id, out=lines.append)) == 1
    assert lines[-1] == (
        f"part {_P1.part_id}: revert refused: edited after (use --force)"
    )
    assert docs[-1].url.params.get("force") is None
    assert (
        asyncio.run(revert(upstreams, _P1.part_id, out=lines.append, force=True)) == 0
    )
    assert lines[-2].startswith(f"WARNING part {_P1.part_id}: forcing a revert")
    assert docs[-1].url.params.get("force") == "true"
    assert lines[-1].startswith(f"part {_P1.part_id}: reverted")
