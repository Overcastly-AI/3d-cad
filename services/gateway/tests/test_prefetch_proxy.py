"""gateway ``POST /api/v1/geometry/prefetch`` — intent in, a warm ticket out.

The browser knows the INTENT (this feature's editor is open; the travel stop is
being dragged here) and documents knows the evaluation-ready feature list. This
route is where they meet, and the tests pin the three things that make it worth
having:

* it forwards a warm that lands on the key a LATER REAL EVALUATE will probe —
  same principal-scoped ``/evaluation-request`` hop, so a `feature_edit` keeps
  the tree whole and names a prefix, while a `travel_stop` sends the SHORTER TREE
  (they hash differently, and only the right one is ever a hit);
* nothing geometric comes back, ever — the reply is a ticket and a boolean;
* it is auth-gated and per-user namespaced, so speculation cannot be started for
  somebody else's part or cancelled out from under another user.

Same harness as tests/test_evaluate_proxy.py: mock transports per upstream, real
auth over SQLite.
"""

import asyncio
import json
import uuid
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from py_kit.db import async_dsn
from py_kit.schemas.features import (
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExtrudeFeature,
    SketchFeature,
    WarmTreeRequest,
)
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

PART = uuid.UUID("00000000-0000-0000-0000-0000000000fa")
SKETCH = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
EXTRUDE = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
SKETCH_2 = uuid.UUID("00000000-0000-0000-0000-0000000000a3")
MISSING = uuid.UUID("00000000-0000-0000-0000-0000000000ff")

SKETCH_ENVELOPE: dict[str, Any] = {
    "type": "sketch",
    "version": 1,
    "params": {
        "plane": {"kind": "datum_plane", "plane": "XY"},
        "entities": [
            {
                "id": "e1",
                "kind": "line",
                "start": {"x": 0.0, "y": 0.0},
                "end": {"x": 40.0, "y": 0.0},
            }
        ],
        "constraints": [{"kind": "fixed", "point": {"entity": "e1", "point": "start"}}],
    },
}

EXTRUDE_ENVELOPE: dict[str, Any] = {
    "type": "extrude",
    "version": 1,
    "params": {
        "profile": {"kind": "feature", "feature_id": str(SKETCH)},
        "distance_mm": 10.0,
        "operation": "add",
    },
}


def _evaluation_request() -> EvaluateTreeRequest:
    """Three features, so a prefix, a whole tree and a truncation all differ."""
    return EvaluateTreeRequest(
        part_id=PART,
        tree_version=4,
        features=[
            EvaluatedFeatureInput(
                id=SKETCH, feature=SketchFeature.model_validate(SKETCH_ENVELOPE)
            ),
            EvaluatedFeatureInput(
                id=EXTRUDE, feature=ExtrudeFeature.model_validate(EXTRUDE_ENVELOPE)
            ),
            EvaluatedFeatureInput(
                id=SKETCH_2, feature=SketchFeature.model_validate(SKETCH_ENVELOPE)
            ),
        ],
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


#: Open lifespans for the clients a test built. The gateway starts its DB and
#: both upstream clients in the LIFESPAN, so an un-entered ``TestClient`` answers
#: `503 database_unavailable` to everything — including registration, which reads
#: like an auth bug and is not one.
_LIFESPANS: list[ExitStack] = []


@pytest.fixture(autouse=True)
def _client_lifespans() -> Iterator[None]:
    with ExitStack() as stack:
        _LIFESPANS.append(stack)
        try:
            yield
        finally:
            _LIFESPANS.pop()


def make_client(
    db_url: str, documents_handler: Handler, geometry_handler: Handler
) -> TestClient:
    """A gateway TestClient with both upstreams mocked, lifespan already run."""
    settings = GatewaySettings(
        geometry_url="http://geometry.internal:8002",
        documents_url="http://documents.internal:8001",
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(
        settings,
        geometry_transport=httpx.MockTransport(geometry_handler),
        documents_transport=httpx.MockTransport(documents_handler),
    )
    return _LIFESPANS[-1].enter_context(TestClient(app, raise_server_exceptions=False))


def _register(
    client: TestClient, email: str = "alice@example.com"
) -> tuple[str, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["user"]["id"], {"Authorization": f"Bearer {body['access_token']}"}


def _documents_ok(seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_evaluation_request().model_dump_json())

    return handler


def _geometry_ok(seen: list[httpx.Request], *, accepted: bool = True) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        ticket = json.loads(request.content)["ticket"]
        return httpx.Response(200, json={"ticket": ticket, "accepted": accepted})

    return handler


def _warm(seen: list[httpx.Request]) -> WarmTreeRequest:
    """The single warm request the gateway forwarded."""
    warms = [r for r in seen if r.url.path == "/api/v1/warm"]
    assert len(warms) == 1
    return WarmTreeRequest.model_validate_json(warms[0].content)


def test_an_open_editor_warms_the_features_before_it(db_url: str) -> None:
    """`feature_edit` on feature index 2 → the whole tree, prefix_length 2, and
    BOTH lineages: the commit reads the plain one, the first face pick after it
    reads provenance (the 29 s the user actually sees on a big part)."""
    documents: list[httpx.Request] = []
    geometry: list[httpx.Request] = []
    client = make_client(db_url, _documents_ok(documents), _geometry_ok(geometry))
    user_id, auth = _register(client)

    response = client.post(
        "/api/v1/geometry/prefetch",
        json={
            "ticket": "editor",
            "part_id": str(PART),
            "kind": "feature_edit",
            "feature_id": str(SKETCH_2),
        },
        headers=auth,
    )

    assert response.status_code == 200
    assert response.json() == {"ticket": "editor", "accepted": True}
    warm = _warm(geometry)
    assert warm.prefix_length == 2
    assert [item.id for item in warm.tree.features] == [SKETCH, EXTRUDE, SKETCH_2]
    assert warm.lineages == ["evaluate", "provenance"]
    # Namespaced per user: one client can never cancel another's speculation.
    assert warm.ticket == f"{user_id}:editor"
    # The principal reaches documents and NEVER geometry (RESEARCH §3).
    assert documents[0].headers[PRINCIPAL_HEADER] == user_id
    assert PRINCIPAL_HEADER not in [h.lower() for h in geometry[0].headers]


def test_a_travel_stop_warms_the_shorter_tree_not_a_prefix(db_url: str) -> None:
    """The distinction that makes the warm usable at all: a rolled-back evaluate
    sends a SHORTER TREE, and a shorter tree hashes differently from a prefix of
    the long one (the mirror capture scope in the key header is computed over the
    whole feature list). So the gateway truncates rather than passing a length."""
    geometry: list[httpx.Request] = []
    client = make_client(db_url, _documents_ok([]), _geometry_ok(geometry))
    _user_id, auth = _register(client)

    response = client.post(
        "/api/v1/geometry/prefetch",
        json={
            "ticket": "travel",
            "part_id": str(PART),
            "kind": "travel_stop",
            "feature_id": str(EXTRUDE),
        },
        headers=auth,
    )

    assert response.status_code == 200
    warm = _warm(geometry)
    assert warm.prefix_length is None
    assert [item.id for item in warm.tree.features] == [SKETCH, EXTRUDE]
    # A stop is a body to LOOK at; provenance waits for a pick that may not come.
    assert warm.lineages == ["evaluate"]


def test_a_target_outside_the_evaluation_prefix_is_a_quiet_no(db_url: str) -> None:
    """Rolled back past, or deleted between render and click. Prefetch is
    best-effort: nothing to warm is a 200 with `accepted: false`, never an error
    the user could see, and nothing is forwarded to geometry."""
    geometry: list[httpx.Request] = []
    client = make_client(db_url, _documents_ok([]), _geometry_ok(geometry))
    _user_id, auth = _register(client)

    response = client.post(
        "/api/v1/geometry/prefetch",
        json={
            "ticket": "editor",
            "part_id": str(PART),
            "kind": "feature_edit",
            "feature_id": str(MISSING),
        },
        headers=auth,
    )

    assert response.status_code == 200
    assert response.json() == {"ticket": "editor", "accepted": False}
    assert geometry == []


def test_editing_the_first_feature_settles_nothing(db_url: str) -> None:
    """There is no prefix before feature 0, so there is nothing to speculate on
    — and speculation that cannot help must not be started."""
    geometry: list[httpx.Request] = []
    client = make_client(db_url, _documents_ok([]), _geometry_ok(geometry))
    _user_id, auth = _register(client)

    response = client.post(
        "/api/v1/geometry/prefetch",
        json={
            "ticket": "editor",
            "part_id": str(PART),
            "kind": "feature_edit",
            "feature_id": str(SKETCH),
        },
        headers=auth,
    )

    assert response.json() == {"ticket": "editor", "accepted": False}
    assert geometry == []


def test_the_reply_can_never_carry_geometry(db_url: str) -> None:
    """Structural: even if the geometry service answered with a body, this
    route's response model has nowhere to put it."""

    def geometry_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ticket": json.loads(request.content)["ticket"],
                "accepted": True,
                "mesh_glb_id": "sha256:deadbeef",
                "properties": {"volume": 1.0},
            },
        )

    client = make_client(db_url, _documents_ok([]), geometry_handler)
    _user_id, auth = _register(client)

    response = client.post(
        "/api/v1/geometry/prefetch",
        json={
            "ticket": "editor",
            "part_id": str(PART),
            "kind": "feature_edit",
            "feature_id": str(SKETCH_2),
        },
        headers=auth,
    )
    assert response.status_code == 200
    assert set(response.json()) == {"ticket", "accepted"}


def test_cancel_namespaces_the_ticket_and_echoes_the_client_one(db_url: str) -> None:
    """Closing the editor. The gateway scopes the ticket upstream and hands the
    client back the ticket the CLIENT chose — the namespace is not its business."""
    geometry: list[httpx.Request] = []
    client = make_client(db_url, _documents_ok([]), _geometry_ok(geometry))
    user_id, auth = _register(client)

    response = client.post(
        "/api/v1/geometry/prefetch/cancel",
        json={"ticket": "editor"},
        headers=auth,
    )

    assert response.status_code == 200
    assert response.json() == {"ticket": "editor", "accepted": True}
    assert json.loads(geometry[0].content) == {"ticket": f"{user_id}:editor"}


def test_a_part_the_caller_does_not_own_never_reaches_geometry(db_url: str) -> None:
    """Authorization rides on the documents hop, exactly as it does for evaluate:
    a 404 there is re-surfaced and no warm is issued."""
    geometry: list[httpx.Request] = []

    def documents_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "error": {
                    "code": "not_found",
                    "message": "No such part",
                    "details": {},
                    "request_id": "r",
                }
            },
        )

    client = make_client(db_url, documents_handler, _geometry_ok(geometry))
    _user_id, auth = _register(client)

    response = client.post(
        "/api/v1/geometry/prefetch",
        json={
            "ticket": "editor",
            "part_id": str(PART),
            "kind": "feature_edit",
            "feature_id": str(SKETCH_2),
        },
        headers=auth,
    )

    assert response.status_code == 404
    assert geometry == []


@pytest.mark.parametrize(
    "path", ["/api/v1/geometry/prefetch", "/api/v1/geometry/prefetch/cancel"]
)
def test_unauthenticated_401_and_nothing_forwarded(db_url: str, path: str) -> None:
    """A warm is real geometry CPU even though it produces nothing, so the route
    carries the same auth posture as tessellate/export (audit F7)."""
    touched: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        touched.append(request)
        return httpx.Response(200, json={})

    client = make_client(db_url, handler, handler)
    response = client.post(
        path,
        json={
            "ticket": "editor",
            "part_id": str(PART),
            "kind": "feature_edit",
            "feature_id": str(SKETCH_2),
        },
    )
    assert response.status_code == 401
    assert touched == []
