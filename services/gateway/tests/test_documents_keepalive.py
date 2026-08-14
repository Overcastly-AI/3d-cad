"""CI-3 — a dropped keep-alive to documents must not become a user 502.

The defect this pins is a PRODUCT one that the test suite happened to catch:
commit aea990a (a diff over scripts/stage-doc-hunks.py and CLAUDE.md only, so
it cannot reach the app) went red in ``sketch-drag-draw.spec.ts`` inside
``createPartViaApi`` with::

    502 {"code":"upstream_unavailable",
         "message":"Documents service is unreachable",
         "details":{"reason":"ReadError"}}

That is the idle keep-alive race. The gateway pools its connection to
documents; uvicorn closes an idle connection after 5 s (its default, and both
services run it unflagged); httpx's pool also considers a connection reusable
for 5.0 s. When those two clocks agree, the gateway can put a request on a
connection the server is closing at that instant, and the modeler is told a
healthy service is unreachable.

The fix is :data:`~gateway.upstream.UPSTREAM_KEEPALIVE_EXPIRY_S`: retire
pooled connections well before the server can. Not a retry — see that
constant's docstring for why documents specifically must not get the geometry
failover treatment.

The stand-in upstream here serves ONE request per connection and answers a
second one with a reset rather than a response. That is the transport shape of
the race (a request written onto a connection the peer is tearing down, unread
bytes answered with RST → ``ReadError``) made deterministic; it deliberately
does not model uvicorn's *timing*, which is unreproducible on demand.
"""

from __future__ import annotations

import asyncio
import inspect
import socket
import struct
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from gateway.upstream import UPSTREAM_KEEPALIVE_EXPIRY_S, UPSTREAM_LIMITS
from py_kit.db import async_dsn
from py_kit.schemas.materials import EMPTY_MATERIAL_ASSIGNMENT
from py_kit.schemas.parts import PartResponse
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "keepalive-test-jwt-secret-0123456789ab"

#: How long a handler waits for a second request on the same connection before
#: giving up. Only a teardown bound — the client's close ends the wait at once.
SECOND_REQUEST_WAIT_S = 30.0

#: Socket read budget for one request. Generous; loopback, tiny bodies.
READ_TIMEOUT_S = 10.0

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)


def _part_json() -> bytes:
    """A canned documents 201 body (the gateway validates what it relays)."""
    return (
        PartResponse(
            id=uuid.uuid4(),
            name="Bracket",
            owner_id=uuid.uuid4(),
            length_unit="mm",
            materials=EMPTY_MATERIAL_ASSIGNMENT,
            tree_version=0,
            eval_state="never",
            last_eval_status=None,
            last_eval_at=None,
            last_eval_tree_version=None,
            created_at=NOW,
            updated_at=NOW,
        )
        .model_dump_json()
        .encode()
    )


def _read_one_request(conn: socket.socket) -> bool:
    """Consume exactly one HTTP/1.1 request. False on a clean client close."""
    buffer = b""
    while b"\r\n\r\n" not in buffer:
        chunk = conn.recv(65536)
        if not chunk:
            return False
        buffer += chunk
    head, _, body = buffer.partition(b"\r\n\r\n")
    length = 0
    for line in head.split(b"\r\n")[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            length = int(value.strip())
    while len(body) < length:
        chunk = conn.recv(65536)
        if not chunk:
            return False
        body += chunk
    return True


class ServeOnceThenReset:
    """A documents stand-in that keeps a connection alive and then drops it.

    Per connection: serve the first request normally (HTTP/1.1, no
    ``Connection: close``, so the client pools it), then — if a second request
    ever arrives on it — close WITHOUT reading those bytes and with
    ``SO_LINGER 0``, so the kernel answers with RST exactly as it does when a
    request lands on a connection the server has just timed out.
    """

    def __init__(self, body: bytes) -> None:
        self._response = (
            b"HTTP/1.1 201 Created\r\n"
            b"content-type: application/json\r\n"
            b"content-length: " + str(len(body)).encode() + b"\r\n"
            b"\r\n" + body
        )
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(8)
        self.port: int = self._listener.getsockname()[1]
        #: Connections accepted, i.e. how many times the client had to dial.
        self.connections = 0
        #: Second requests refused with a reset — the failure under test.
        self.resets = 0
        self._workers: list[threading.Thread] = []
        self._accepting = threading.Thread(target=self._accept_loop, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _accept_loop(self) -> None:
        while True:
            try:
                conn, _ = self._listener.accept()
            except OSError:  # listener closed by __exit__
                return
            self.connections += 1
            worker = threading.Thread(target=self._serve, args=(conn,), daemon=True)
            self._workers.append(worker)
            worker.start()

    def _serve(self, conn: socket.socket) -> None:
        with conn:
            try:
                conn.settimeout(READ_TIMEOUT_S)
                if not _read_one_request(conn):
                    return
                conn.sendall(self._response)
                conn.settimeout(SECOND_REQUEST_WAIT_S)
                # MSG_PEEK leaves the bytes unread on purpose: unread data in
                # the receive queue is itself enough for Linux to answer the
                # close with RST, and SO_LINGER 0 makes that unconditional.
                if conn.recv(1, socket.MSG_PEEK):
                    conn.setsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_LINGER,
                        struct.pack("ii", 1, 0),
                    )
                    self.resets += 1
            except OSError:
                return

    def __enter__(self) -> ServeOnceThenReset:
        self._accepting.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._listener.close()
        self._accepting.join(timeout=5.0)


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


@pytest.fixture
def upstream() -> Iterator[ServeOnceThenReset]:
    with ServeOnceThenReset(_part_json()) as server:
        yield server


def _gateway(db_url: str, documents_url: str) -> TestClient:
    """The real gateway over a REAL socket to *documents_url* (no mock
    transport — connection pooling is the subject, and a MockTransport has no
    pool at all)."""
    settings = GatewaySettings(
        geometry_url="http://127.0.0.1:9",  # nothing listens; unused here
        documents_url=documents_url,
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    return TestClient(build_app(settings), raise_server_exceptions=False)


def _bearer(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_idle_pooled_connection_is_retired_before_documents_drops_it(
    db_url: str, upstream: ServeOnceThenReset
) -> None:
    """The acceptance gate: no 502 when the upstream drops the pooled socket.

    The sleep is longer than the pool's expiry and the stand-in resets any
    second request on a connection, so the ONLY way through is for the gateway
    to have retired the first connection and dialled again.
    """
    with _gateway(db_url, upstream.url) as client:
        bearer = _bearer(client)
        first = client.post("/api/v1/parts", json={"name": "Bracket"}, headers=bearer)
        assert first.status_code == 201, first.text

        time.sleep(UPSTREAM_KEEPALIVE_EXPIRY_S + 0.25)

        second = client.post("/api/v1/parts", json={"name": "Flange"}, headers=bearer)

    assert second.status_code == 201, second.text
    assert upstream.resets == 0
    assert upstream.connections == 2


def test_upstream_expiry_undercuts_the_uvicorn_keep_alive_default() -> None:
    """The margin is the fix, so both ends of it are asserted, not assumed.

    Read from the libraries rather than restated: if uvicorn lowers its
    keep-alive default under ours, or httpx changes the pool ceilings we
    inherit, this fails instead of the race quietly reopening in production.
    """
    import uvicorn

    uvicorn_keep_alive_s = (
        inspect.signature(uvicorn.Config.__init__)
        .parameters["timeout_keep_alive"]
        .default
    )
    assert isinstance(uvicorn_keep_alive_s, (int, float))
    assert uvicorn_keep_alive_s > UPSTREAM_KEEPALIVE_EXPIRY_S

    httpx_defaults = (
        inspect.signature(httpx.AsyncClient.__init__).parameters["limits"].default
    )
    assert isinstance(httpx_defaults, httpx.Limits)
    # The race is httpx's default expiry meeting uvicorn's: same number.
    assert httpx_defaults.keepalive_expiry == uvicorn_keep_alive_s
    # Only the expiry is ours; the ceilings stay httpx's documented defaults.
    assert UPSTREAM_LIMITS.max_connections == httpx_defaults.max_connections
    assert (
        UPSTREAM_LIMITS.max_keepalive_connections
        == httpx_defaults.max_keepalive_connections
    )
    assert UPSTREAM_LIMITS.keepalive_expiry == UPSTREAM_KEEPALIVE_EXPIRY_S
