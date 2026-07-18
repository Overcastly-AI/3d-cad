"""gateway.step_import — STEP upload: auth, size cap, validation, forwarding.

Same harness as tests/test_features_proxy.py: the documents upstream is an
``httpx.MockTransport``; auth runs for real (register → bearer token) over the
SQLite test DB posture. The upload endpoint takes the STEP file as the RAW
request body (streamed, size-capped) with ``name`` / ``expected_tree_version``
as query params, and maps it to an ``import`` feature persisted through the
ordinary documents feature-append path.
"""

import asyncio
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from py_kit.db import async_dsn
from py_kit.schemas.features import (
    FeatureCreate,
    FeatureMutationResponse,
    FeatureResponse,
    ImportFeature,
    ImportParamsV1,
)
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=UTC)

#: A minimal STEP part-21 file: carries the ISO-10303-21 header the gateway
#: guard checks. The gateway never parses geometry (that is the geometry
#: service's job), so this need not be OCCT-loadable — only STEP-shaped.
STEP_TEXT = (
    "ISO-10303-21;\n"
    "HEADER;\n"
    "FILE_DESCRIPTION((''),'2;1');\n"
    "FILE_NAME('box.step','2026-07-13T00:00:00',(''),(''),'','','');\n"
    "FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
    "ENDSEC;\n"
    "DATA;\n"
    "#1=CARTESIAN_POINT('',(0.,0.,0.));\n"
    "ENDSEC;\n"
    "END-ISO-10303-21;\n"
)


def _import_feature_response(part_id: uuid.UUID, data: str) -> FeatureResponse:
    return FeatureResponse(
        id=uuid.uuid4(),
        part_id=part_id,
        order_index=0,
        name="Imported STEP",
        feature=ImportFeature(
            type="import",
            version=1,
            params=ImportParamsV1(kind="inline", format="step", data=data),
        ),
        rolled_back=False,
        created_at=NOW,
        updated_at=NOW,
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


def make_client(db_url: str, handler: Handler) -> TestClient:
    settings = GatewaySettings(
        geometry_url="http://127.0.0.1:9",  # nothing listens; irrelevant here
        documents_url="http://documents.internal:8001",
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(settings, documents_transport=httpx.MockTransport(handler))
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def seen() -> list[httpx.Request]:
    return []


def _echo_documents(seen: list[httpx.Request]) -> Handler:
    """A canned documents upstream that echoes back the persisted import."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        part_id = uuid.UUID(request.url.path.split("/")[4])
        body = FeatureCreate.model_validate_json(request.content)
        assert isinstance(body.feature, ImportFeature)
        payload = FeatureMutationResponse(
            feature=_import_feature_response(part_id, body.feature.params.data),
            tree_version=body.expected_tree_version + 1,
        )
        return httpx.Response(201, content=payload.model_dump_json())

    return handler


def _register(client: TestClient) -> tuple[str, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["user"]["id"], {"Authorization": f"Bearer {body['access_token']}"}


def _envelope(body: dict[str, Any]) -> dict[str, Any]:
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    return error


PART = uuid.uuid4()
_IMPORT_URL = f"/api/v1/parts/{PART}/features/import?expected_tree_version=0"


# --- auth gating -----------------------------------------------------------------


def test_unauthenticated_401_and_nothing_forwarded(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        response = client.post(_IMPORT_URL, content=STEP_TEXT.encode())
    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert seen == []


# --- happy path ------------------------------------------------------------------


def test_valid_upload_creates_import_feature(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        user_id, bearer = _register(client)
        response = client.post(
            f"/api/v1/parts/{PART}/features/import",
            params={"expected_tree_version": 3, "name": "Bracket"},
            content=STEP_TEXT.encode(),
            headers=bearer,
        )

    assert response.status_code == 201, response.text
    body = FeatureMutationResponse.model_validate(response.json())
    assert body.tree_version == 4
    assert isinstance(body.feature.feature, ImportFeature)

    [upstream] = seen
    assert upstream.method == "POST"
    assert upstream.url.path == f"/api/v1/parts/{PART}/features"
    assert upstream.headers[PRINCIPAL_HEADER] == user_id
    # The uploaded bytes are persisted verbatim as the inline STEP text, under
    # an `import` feature with the requested name and concurrency token.
    parsed = FeatureCreate.model_validate_json(upstream.content)
    assert parsed.name == "Bracket"
    assert parsed.expected_tree_version == 3
    assert isinstance(parsed.feature, ImportFeature)
    assert parsed.feature.params.kind == "inline"
    assert parsed.feature.params.format == "step"
    assert parsed.feature.params.data == STEP_TEXT


def test_default_feature_name_when_omitted(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.post(_IMPORT_URL, content=STEP_TEXT.encode(), headers=bearer)
    assert response.status_code == 201, response.text
    parsed = FeatureCreate.model_validate_json(seen[0].content)
    assert parsed.name == "Imported STEP"


# --- size cap (before anything goes upstream) ------------------------------------


def test_oversize_declared_length_is_422_before_forwarding(
    db_url: str, seen: list[httpx.Request], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A declared Content-Length over the cap is rejected before any parse."""
    monkeypatch.setattr("gateway.step_import.MAX_STEP_UPLOAD_BYTES", 64)
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.post(
            _IMPORT_URL, content=b"ISO-10303-21;" + b"x" * 200, headers=bearer
        )
    assert response.status_code == 422
    error = _envelope(response.json())
    assert error["code"] == "import_too_large"
    assert error["details"]["max_bytes"] == 64
    assert seen == []  # never reached documents


def test_streaming_guard_rejects_chunked_without_content_length(
    db_url: str, seen: list[httpx.Request], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A chunked upload (no Content-Length) is still bounded, chunk-by-chunk.

    Passing an iterator body makes httpx send ``Transfer-Encoding: chunked``
    with NO ``Content-Length``, so the declared-length guard cannot fire — the
    stream loop's running-total guard is what rejects it (422), still before
    anything reaches documents.
    """
    monkeypatch.setattr("gateway.step_import.MAX_STEP_UPLOAD_BYTES", 64)

    def oversize_chunks() -> Iterator[bytes]:
        yield b"ISO-10303-21;"
        yield b"y" * 40
        yield b"z" * 40

    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.post(_IMPORT_URL, content=oversize_chunks(), headers=bearer)
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "import_too_large"
    assert seen == []


def test_chunked_upload_within_cap_is_accepted(
    db_url: str, seen: list[httpx.Request]
) -> None:
    """A chunked (Content-Length-free) STEP upload within the cap round-trips."""

    def step_chunks() -> Iterator[bytes]:
        yield STEP_TEXT[:20].encode()
        yield STEP_TEXT[20:].encode()

    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.post(_IMPORT_URL, content=step_chunks(), headers=bearer)
    assert response.status_code == 201, response.text
    parsed = FeatureCreate.model_validate_json(seen[0].content)
    assert isinstance(parsed.feature, ImportFeature)
    assert parsed.feature.params.data == STEP_TEXT


# --- empty / non-STEP (clean 4xx here, nothing forwarded) ------------------------


def test_empty_upload_is_422(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.post(_IMPORT_URL, content=b"   \n  ", headers=bearer)
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "import_empty"
    assert seen == []


def test_non_step_text_is_422(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.post(
            _IMPORT_URL, content=b"this is not a STEP file at all", headers=bearer
        )
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "import_not_step"
    assert seen == []


def test_non_utf8_bytes_is_422(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.post(
            _IMPORT_URL, content=b"\xff\xfe\x00\x01binary-garbage", headers=bearer
        )
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "import_not_step"
    assert seen == []


# --- import onto a part that already has a body ----------------------------------


def test_import_with_prior_body_envelope_is_resurfaced(db_url: str) -> None:
    """Documents' 422 import_with_prior_body passes through verbatim."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": "import_with_prior_body",
                    "message": "An import cannot follow another body-producing "
                    "feature.",
                    "details": {"prior_feature_type": "extrude"},
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, handler) as client:
        _, bearer = _register(client)
        response = client.post(_IMPORT_URL, content=STEP_TEXT.encode(), headers=bearer)

    assert response.status_code == 422
    error = _envelope(response.json())
    assert error["code"] == "import_with_prior_body"
    assert error["details"] == {"prior_feature_type": "extrude"}
