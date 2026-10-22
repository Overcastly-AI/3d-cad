"""py_kit.loopback: the port is held from construction, and boot failure is loud."""

import errno
import json
import socket
import urllib.request

import pytest
from fastapi import FastAPI
from py_kit.loopback import LoopbackServer


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"pong": "yes"}

    return app


def test_port_is_held_before_start_and_served_after() -> None:
    server = LoopbackServer(_app())
    try:
        # The TOCTOU this replaces: between choosing and serving, another
        # socket could take the number. Here it cannot.
        with (
            socket.socket(socket.AF_INET, socket.SOCK_STREAM) as squatter,
            pytest.raises(OSError) as taken,
        ):
            squatter.bind(("127.0.0.1", server.port))
        assert taken.value.errno == errno.EADDRINUSE
        server.start()
        with urllib.request.urlopen(f"{server.url}/ping", timeout=10) as response:
            assert json.load(response) == {"pong": "yes"}
    finally:
        server.stop()


def test_boot_failure_raises_with_the_cause() -> None:
    class _Exploding:
        async def __aenter__(self) -> None:
            raise RuntimeError("lifespan exploded")

        async def __aexit__(self, *_: object) -> None:
            return None

    def lifespan(_: FastAPI) -> _Exploding:
        return _Exploding()

    server = LoopbackServer(FastAPI(lifespan=lifespan))
    try:
        with pytest.raises(RuntimeError, match="lifespan exploded"):
            server.start()
    finally:
        server.stop()


def test_stop_without_start_releases_the_port() -> None:
    server = LoopbackServer(_app())
    server.stop()  # the old fixture raised "cannot join thread before it is started"
    server.stop()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as rebind:
        rebind.bind(("127.0.0.1", server.port))
