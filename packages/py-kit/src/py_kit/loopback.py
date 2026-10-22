"""A real uvicorn server on a loopback port, in a daemon thread, for tests.

The listening socket is bound ONCE, here, and handed to uvicorn
(``Server.run(sockets=[...])``). The pattern this replaces probed a "free"
port (bind to 0, read the number, close) and let uvicorn bind it again later:
between the close and the re-bind any other process, or any outbound
connection drawing an ephemeral source port, can take the number. CI hit
exactly that (``[Errno 98] address already in use``) once shard rebalancing
put several stack-booting suites on one runner.

Startup failure is loud: :meth:`LoopbackServer.start` raises with the errors
uvicorn logged (a lifespan failure, say) instead of letting a dead thread
surface later as an opaque ``cannot join thread before it is started``.
"""

from __future__ import annotations

import logging
import socket
import threading
import time

import uvicorn
from fastapi import FastAPI

#: Loopback uvicorn boots in well under a second; this is a hang budget.
BOOT_TIMEOUT_S = 30.0


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(self.format(record))


class LoopbackServer:
    """One uvicorn server on ``127.0.0.1``; its port is reserved at construction.

    ``url`` is valid as soon as the object exists, so a later server can be
    configured to call an earlier one before either has started.
    """

    def __init__(self, app: FastAPI, *, boot_timeout_s: float = BOOT_TIMEOUT_S) -> None:
        self._boot_timeout_s = boot_timeout_s
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._socket.bind(("127.0.0.1", 0))
            # Listen now: the port is held from here on, and a client that
            # races the boot queues in the backlog rather than being refused.
            self._socket.listen()
        except BaseException:
            self._socket.close()
            raise
        self.port: int = self._socket.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        self._error: BaseException | None = None
        self._thread = threading.Thread(
            target=self._run, name=f"uvicorn-{self.port}", daemon=True
        )

    def _run(self) -> None:
        try:
            self.server.run(sockets=[self._socket])
        except BaseException as exc:  # SystemExit included: uvicorn exits on failure
            self._error = exc

    def start(self) -> None:
        """Boot and wait until uvicorn reports ``started``; raise if it cannot."""
        collect = _Collect()
        uvicorn_error = logging.getLogger("uvicorn.error")
        uvicorn_error.addHandler(collect)
        try:
            self._thread.start()
            deadline = time.monotonic() + self._boot_timeout_s
            while not self.server.started:
                if not self._thread.is_alive():
                    self._raise_boot_failure("exited during startup", collect)
                if time.monotonic() > deadline:
                    self._raise_boot_failure(
                        f"did not start within {self._boot_timeout_s:g} s", collect
                    )
                time.sleep(0.01)
        finally:
            uvicorn_error.removeHandler(collect)

    def _raise_boot_failure(self, what: str, collect: _Collect) -> None:
        detail = "; ".join(collect.messages) or "no error logged by uvicorn"
        if self._error is not None:
            detail += f"; thread raised {self._error!r}"
        raise RuntimeError(f"uvicorn on {self.url} {what}: {detail}") from self._error

    def stop(self) -> None:
        """Shut down if started; always release the socket. Safe to call twice."""
        if self._thread.ident is not None:
            self.server.should_exit = True
            self._thread.join(timeout=self._boot_timeout_s)
        self._socket.close()
