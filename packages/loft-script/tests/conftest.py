"""A real three-service stack on loopback, for the scripting client to drive.

Real uvicorn servers, real sockets, real OCCT, SQLite stores — no mock
transports anywhere. That is the point: this package's whole claim is that a
script travels the SAME path as the browser, and a test that stubbed the
gateway would be asserting the claim rather than exercising it.

DUPLICATION, ACKNOWLEDGED: ``services/gateway/tests/test_evaluate_e2e.py``
boots the same stack the same way. It is not shared because a test module in
another distribution is not importable from here (pytest's ``importlib``
import-mode gives each suite its own namespace, and ``services/gateway/tests``
is not a package). The honest fix is to lift the boot into a root ``conftest.py``
fixture both suites use; that touches a live test file in another territory and
is filed rather than done here.
"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
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

import pytest
import uvicorn
from documents.main import DocumentsSettings
from documents.main import build_app as build_documents_app
from fastapi import FastAPI
from gateway.db import Base as GatewayBase
from gateway.main import GatewaySettings
from gateway.main import build_app as build_gateway_app
from geometry.main import build_app as build_geometry_app
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "loft-script-test-jwt-secret-0123456789"
BOOT_TIMEOUT_S = 30.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


class _Server:
    """One uvicorn server on a loopback port, run in a daemon thread."""

    def __init__(self, app: FastAPI, port: int) -> None:
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self.thread.start()
        deadline = time.monotonic() + BOOT_TIMEOUT_S
        while not self.server.started:
            if time.monotonic() > deadline or not self.thread.is_alive():
                raise RuntimeError("uvicorn server failed to boot")
            time.sleep(0.01)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=BOOT_TIMEOUT_S)


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

    documents_port, geometry_port, gateway_port = (
        _free_port(),
        _free_port(),
        _free_port(),
    )
    servers = [
        _Server(
            build_documents_app(DocumentsSettings(postgres_url=documents_db)),
            documents_port,
        ),
        _Server(build_geometry_app(), geometry_port),
        _Server(
            build_gateway_app(
                GatewaySettings(
                    geometry_url=f"http://127.0.0.1:{geometry_port}",
                    documents_url=f"http://127.0.0.1:{documents_port}",
                    postgres_url=gateway_db,
                    loft_env="dev",
                    jwt_secret=TEST_JWT_SECRET,
                )
            ),
            gateway_port,
        ),
    ]
    try:
        for server in servers:
            server.start()
        yield Stack(gateway_url=f"http://127.0.0.1:{gateway_port}")
    finally:
        for server in reversed(servers):
            server.stop()
