"""The gateway asks upstreams for ``identity`` (docs/PERF.md PERF-4).

py-kit gzips every service's responses, and httpx advertises ``gzip, deflate``
by default — so without this the gateway would make geometry compress a
1 MiB mesh, inflate it here, and re-compress it for the browser. Measured on
the PERF-4 N=200 tray: 20.6 ms to compress upstream plus 3.6 ms to inflate,
to save 2.6 ms of internal transfer; removing it cut the end-to-end gateway
mesh fetch from 57.8 ms to 31.4 ms. The browser still gets gzip — the
gateway's OWN response is compressed by py-kit's middleware.
"""

from __future__ import annotations

import asyncio

import httpx2 as httpx
from gateway.upstream import create_upstream_client


def test_upstream_client_requests_identity() -> None:
    """The default header is set on the client, so every forward carries it."""
    client = create_upstream_client("http://geometry:8002", timeout_s=5.0)
    assert client.headers["accept-encoding"] == "identity"


def test_upstream_client_sends_identity_on_the_wire() -> None:
    """Behaviour, not configuration: what the upstream actually receives.

    ``forward`` builds its own per-request header dict (request id, principal,
    content-type); this pins that those do NOT displace the client default,
    which is the way this regresses.
    """
    seen: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return httpx.Response(200, content=b"ok")

    async def fetch() -> httpx.Response:
        client = create_upstream_client(
            "http://geometry:8002",
            timeout_s=5.0,
            transport=httpx.MockTransport(handler),
        )
        async with client:
            return await client.get(
                "/api/v1/meshes/sha256:abc", headers={"X-Request-ID": "r1"}
            )

    response = asyncio.run(fetch())

    assert response.status_code == 200
    assert seen[0]["accept-encoding"] == "identity"
    assert "gzip" not in seen[0]["accept-encoding"]
    assert seen[0]["x-request-id"] == "r1"
