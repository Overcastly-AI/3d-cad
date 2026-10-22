"""A real three-service stack on loopback, for the scripting client to drive.

Real uvicorn servers, real sockets, real OCCT, SQLite stores — no mock
transports anywhere. That is the point: this package's whole claim is that a
script travels the SAME path as the browser, and a test that stubbed the
gateway would be asserting the claim rather than exercising it.

``services/gateway/tests/test_evaluate_e2e.py`` boots the same stack. The
per-server mechanics (port held from bind to serve, loud boot failure) live in
``py_kit.loopback`` so the two cannot drift; the three-service wiring is still
written out in each, because a test module in another distribution is not
importable from here (pytest's ``importlib`` import-mode).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

# `gateway.main` builds a module-level `app` at import time and fail-closes on
# the JWT posture, so importing it needs an explicit dev opt-in — the same
# `setdefault` `services/gateway/tests/conftest.py` does, repeated here so this
# suite runs standalone. `setdefault`, not `setenv`: in a whole-repo run the
# gateway conftest has already set it, and a test whose subject is LOFT_ENV must
# monkeypatch explicitly rather than inherit either way (CLAUDE.md).
os.environ.setdefault("LOFT_ENV", "dev")
# `geometry.main` builds its app at import, and the blend server is prewarmed
# by default (~0.5 GiB, several seconds). Nothing here needs it up front: a
# blend, if any, starts it on first use.
os.environ.setdefault("BLEND_SERVER_PREWARM", "false")

import pytest
from documents.main import DocumentsSettings
from documents.main import build_app as build_documents_app
from gateway.db import Base as GatewayBase
from gateway.main import GatewaySettings
from gateway.main import build_app as build_gateway_app
from geometry.main import build_app as build_geometry_app
from py_kit.db import async_dsn
from py_kit.loopback import LoopbackServer
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "loft-script-test-jwt-secret-0123456789"


async def _create_schema(url: str, base: type) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(base.metadata.create_all)  # type: ignore[attr-defined]
    await engine.dispose()


class Stack(NamedTuple):
    """Where the booted stack lives."""

    gateway_url: str


@pytest.fixture(scope="session")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    """The booted three-service stack (real uvicorn servers on loopback)."""
    from documents.db import Base as DocumentsBase

    tmp_path: Path = tmp_path_factory.mktemp("loft-script")
    documents_db = f"sqlite:///{tmp_path}/documents.db"
    gateway_db = f"sqlite:///{tmp_path}/gateway.db"
    asyncio.run(_create_schema(documents_db, DocumentsBase))
    asyncio.run(_create_schema(gateway_db, GatewayBase))

    # Each server holds its port from construction on (see py_kit.loopback):
    # no probe-then-rebind window for another process to take it.
    documents = LoopbackServer(
        build_documents_app(DocumentsSettings(postgres_url=documents_db))
    )
    geometry = LoopbackServer(build_geometry_app())
    gateway = LoopbackServer(
        build_gateway_app(
            GatewaySettings(
                geometry_url=geometry.url,
                documents_url=documents.url,
                postgres_url=gateway_db,
                loft_env="dev",
                jwt_secret=TEST_JWT_SECRET,
            )
        )
    )
    servers = [documents, geometry, gateway]
    try:
        for server in servers:
            server.start()
        yield Stack(gateway_url=gateway.url)
    finally:
        for server in reversed(servers):
            server.stop()
