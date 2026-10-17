"""The trusted-proxy rule for the client address (AUTH-RATE-LIMIT-PROXY).

Unit level: parsing, IPv6 keying, the right-to-left walk, malformed input and
hostname resolution. The end-to-end bucket tests (two clients behind the
proxy, a forged header straight to the gateway) are in
``test_rate_limit_proxy.py``.
"""

import asyncio
from collections.abc import Sequence
from types import SimpleNamespace

import pytest
from gateway.client_ip import (
    MAX_FORWARDED_HOPS,
    RESOLVE_TTL_S,
    TrustedProxies,
    client_address,
    parse_address,
)
from starlette.requests import Request

PROXY = "172.18.0.5"


def _request(
    peer: str | None, xff: Sequence[str] = (), trusted: TrustedProxies | None = None
) -> Request:
    app = SimpleNamespace(state=SimpleNamespace(trusted_proxies=trusted))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "headers": [(b"x-forwarded-for", v.encode("latin-1")) for v in xff],
        "client": (peer, 40000) if peer is not None else None,
        "app": app,
    }
    return Request(scope)


def _key(peer: str | None, xff: Sequence[str] = (), trusted: str | None = PROXY) -> str:
    proxies = TrustedProxies.parse(trusted) if trusted is not None else None
    return asyncio.run(client_address(_request(peer, xff, proxies)))


def test_no_proxy_configured_keys_on_socket_and_ignores_header() -> None:
    assert _key("203.0.113.7", ["198.51.100.1"], trusted=None) == "203.0.113.7"
    assert _key("203.0.113.7", ["198.51.100.1"], trusted="") == "203.0.113.7"


def test_forged_header_from_untrusted_peer_is_ignored() -> None:
    assert _key("203.0.113.7", ["198.51.100.1"]) == "203.0.113.7"


def test_trusted_proxy_peer_yields_forwarded_client() -> None:
    assert _key(PROXY, ["198.51.100.1"]) == "198.51.100.1"
    assert _key(PROXY, ["198.51.100.2"]) == "198.51.100.2"


def test_spoofed_left_most_entry_cannot_choose_the_key() -> None:
    # An appending proxy: the client sent "1.2.3.4", the proxy added the real
    # peer. The right-most untrusted entry wins, whatever the client wrote.
    assert _key(PROXY, ["1.2.3.4, 198.51.100.1"]) == "198.51.100.1"
    assert _key(PROXY, ["1.2.3.4", "198.51.100.1"]) == "198.51.100.1"


def test_chain_of_trusted_proxies_is_skipped() -> None:
    key = _key(
        PROXY, ["6.6.6.6, 198.51.100.1, 10.0.0.2"], trusted=f"{PROXY},10.0.0.0/8"
    )
    assert key == "198.51.100.1"


def test_all_hops_trusted_keys_on_left_most_trusted() -> None:
    assert _key(PROXY, ["10.0.0.2"], trusted=f"{PROXY},10.0.0.0/8") == "10.0.0.2"


def test_trusted_peer_without_header_keys_on_peer() -> None:
    assert _key(PROXY) == PROXY


@pytest.mark.parametrize(
    "xff",
    ["", "not-an-ip", "1.2.3.4, garbage", "999.1.1.1", "[2001:db8::1", "a,,b", " , "],
)
def test_malformed_header_falls_back_to_the_proxy(xff: str) -> None:
    # The walk stops at the trusted hop that forwarded garbage: its own
    # bucket, never an attacker-chosen one.
    assert _key(PROXY, [xff]) == PROXY


def test_ipv6_clients_key_on_their_64() -> None:
    a = _key(PROXY, ["2001:db8:1:2::a"])
    b = _key(PROXY, ["2001:db8:1:2:ffff::b"])
    c = _key(PROXY, ["2001:db8:1:3::a"])
    assert a == b == "2001:db8:1:2::/64"
    assert c == "2001:db8:1:3::/64"


def test_ipv6_proxy_and_peer() -> None:
    assert _key("fd00::5", ["198.51.100.1"], trusted="fd00::/64") == "198.51.100.1"
    assert _key("2001:db8::7", ["198.51.100.1"], trusted="fd00::/64") == (
        "2001:db8::/64"
    )


def test_bracketed_ported_and_mapped_forms() -> None:
    assert _key(PROXY, ["[2001:db8::1]:443"]) == "2001:db8::/64"
    assert _key(PROXY, ["198.51.100.1:5555"]) == "198.51.100.1"
    assert _key(PROXY, ["::ffff:198.51.100.1"]) == "198.51.100.1"
    assert _key("::ffff:172.18.0.5", ["198.51.100.1"]) == "198.51.100.1"


def test_non_ip_peer_is_used_verbatim() -> None:
    assert _key("testclient", ["198.51.100.1"]) == "testclient"
    assert _key(None, ["198.51.100.1"]) == "unknown"


def test_hop_walk_is_bounded() -> None:
    hops = ", ".join(["10.0.0.9"] * (MAX_FORWARDED_HOPS + 50))
    key = _key(PROXY, [f"198.51.100.1, {hops}"], trusted=f"{PROXY},10.0.0.0/8")
    assert key == "10.0.0.9"  # never walked as far as the client-written entry


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.2.3.4", "1.2.3.4"),
        (" 1.2.3.4 ", "1.2.3.4"),
        ('"1.2.3.4"', "1.2.3.4"),
        ("[::1]", "::1"),
        ("::1", "::1"),
        ("1.2.3.4:80:90", None),
        ("[::1]x", None),
        ("unknown", None),
    ],
)
def test_parse_address(raw: str, expected: str | None) -> None:
    parsed = parse_address(raw)
    assert (str(parsed) if parsed is not None else None) == expected


def test_bad_trusted_proxies_entry_refuses_boot() -> None:
    with pytest.raises(RuntimeError, match="TRUSTED_PROXIES"):
        TrustedProxies.parse("web, 10.0.0.0/33x")
    with pytest.raises(RuntimeError, match="TRUSTED_PROXIES"):
        TrustedProxies.parse("http://web")


def test_hostname_entry_resolves_and_is_cached() -> None:
    lookups: list[str] = []
    answer = ["172.18.0.9"]

    async def resolver(host: str) -> list[str]:
        lookups.append(host)
        return answer

    now = [0.0]
    proxies = TrustedProxies.parse("Web", resolver=resolver)
    proxies.clock = lambda: now[0]

    def key(peer: str) -> str:
        return asyncio.run(client_address(_request(peer, ["198.51.100.1"], proxies)))

    assert key("172.18.0.9") == "198.51.100.1"
    assert key("172.18.0.1") == "172.18.0.1"  # the bridge gateway: not trusted
    assert lookups == ["web"]  # cached between requests
    answer[:] = ["172.18.0.10"]  # nginx recreated with a new address
    now[0] = RESOLVE_TTL_S + 1
    assert key("172.18.0.10") == "198.51.100.1"
    assert key("172.18.0.9") == "172.18.0.9"
    assert lookups == ["web", "web"]


def test_unresolvable_hostname_trusts_nothing() -> None:
    async def resolver(host: str) -> list[str]:
        return []

    proxies = TrustedProxies.parse("web", resolver=resolver)
    request = _request(PROXY, ["198.51.100.1"], proxies)
    assert asyncio.run(client_address(request)) == PROXY
