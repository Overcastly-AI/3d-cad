"""The client address behind a trusted reverse proxy (the trusted-proxy rule).

Behind the bundled nginx every request's socket peer is nginx, so anything
keyed on ``request.client.host`` (the auth rate limiter) puts every user in
one bucket, and one attacker locks every user out. The proxy's
``X-Forwarded-For`` names the real client, but the header is attacker-written
whenever the request did NOT come through the proxy, so it is trusted only
when the connecting peer is a configured proxy (``TRUSTED_PROXIES``).

The rule is the standard one (nginx ``real_ip_recursive``, uvicorn
``--forwarded-allow-ips``, Rails ``remote_ip``): append the socket peer to
the ``X-Forwarded-For`` chain and walk it from the right, skipping trusted
proxies; the first untrusted address is the client. Entries left of it were
written by the client and can never choose the key. A malformed entry stops
the walk at the trusted hop that forwarded it (conservative: that proxy's
own bucket, never an attacker-chosen one).

``TRUSTED_PROXIES`` is a comma-separated list of IP addresses, CIDRs and
hostnames. A hostname is resolved through DNS and cached for
:data:`RESOLVE_TTL_S`; compose sets ``web``, the bundled nginx service,
because its container address changes when it is recreated. The compose
subnet is NOT the default: the gateway's port is published, and Docker's
userland proxy (hairpin and rootless setups) presents outside clients with
the bridge gateway address, which lies inside that subnet, so trusting the
subnet would let a direct caller forge the header. Unset means no proxy is
trusted and every key is the socket address.

IPv6 clients are keyed by their /64, the smallest block an ISP hands out,
so one host cannot step to a fresh bucket per address.
"""

import ipaddress
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

import anyio
from fastapi import Request

type IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
type IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

#: How long a resolved proxy hostname is trusted before it is looked up again.
RESOLVE_TTL_S = 30.0

#: At most this many ``X-Forwarded-For`` hops are examined (input limit). A
#: real chain is one hop for the bundled nginx and a handful behind a CDN.
MAX_FORWARDED_HOPS = 16

#: The prefix an IPv6 client is keyed by.
IPV6_KEY_PREFIX = 64

_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)

Resolver = Callable[[str], Awaitable[Sequence[str]]]


async def _resolve(host: str) -> list[str]:
    """Every address *host* resolves to (empty when it does not resolve)."""
    try:
        infos = await anyio.getaddrinfo(host, None)
    except OSError:
        return []
    return [str(info[4][0]) for info in infos]


def parse_address(raw: str) -> IPAddress | None:
    """One address as a proxy or socket reports it, or ``None`` if malformed.

    Accepts a bare IPv4/IPv6 address, ``[v6]``, ``[v6]:port`` and
    ``v4:port`` (some proxies append ports). An IPv4-mapped IPv6 address is
    the IPv4 address it maps, so a dual-stack socket keys like an IPv4 one.
    """
    text = raw.strip().strip('"')
    if text.startswith("["):
        end = text.find("]")
        if end == -1 or (end + 1 < len(text) and text[end + 1] != ":"):
            return None
        text = text[1:end]
    elif text.count(":") == 1:
        text = text.split(":", 1)[0]
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def address_key(address: IPAddress) -> str:
    """The rate-limit key of *address*: itself, or its /64 for IPv6."""
    if isinstance(address, ipaddress.IPv4Address):
        return str(address)
    network = ipaddress.IPv6Network((int(address), IPV6_KEY_PREFIX), strict=False)
    return str(network)


@dataclass
class TrustedProxies:
    """The configured proxies: fixed networks plus DNS names resolved lazily."""

    networks: tuple[IPNetwork, ...] = ()
    hostnames: tuple[str, ...] = ()
    resolver: Resolver = _resolve
    clock: Callable[[], float] = time.monotonic
    _resolved: dict[str, tuple[float, frozenset[IPAddress]]] = field(
        default_factory=dict[str, tuple[float, frozenset[IPAddress]]]
    )

    @classmethod
    def parse(
        cls, spec: str | None, *, resolver: Resolver = _resolve
    ) -> "TrustedProxies":
        """Parse ``TRUSTED_PROXIES``; raise :class:`RuntimeError` on a bad entry.

        A typo must stop the boot rather than silently trust nothing (every
        user in one bucket again) or the wrong thing.
        """
        networks: list[IPNetwork] = []
        hostnames: list[str] = []
        for entry in (spec or "").split(","):
            entry = entry.strip()
            if not entry:
                continue
            try:
                networks.append(ipaddress.ip_network(entry, strict=False))
                continue
            except ValueError:
                pass
            if not _HOSTNAME.match(entry):
                raise RuntimeError(
                    f"TRUSTED_PROXIES entry {entry!r} is not an IP address, "
                    "CIDR or hostname."
                )
            hostnames.append(entry.lower())
        return cls(tuple(networks), tuple(hostnames), resolver=resolver)

    @property
    def empty(self) -> bool:
        return not self.networks and not self.hostnames

    async def _addresses_of(self, host: str) -> frozenset[IPAddress]:
        now = self.clock()
        cached = self._resolved.get(host)
        if cached is not None and cached[0] > now:
            return cached[1]
        parsed = (parse_address(raw) for raw in await self.resolver(host))
        addresses = frozenset(a for a in parsed if a is not None)
        self._resolved[host] = (now + RESOLVE_TTL_S, addresses)
        return addresses

    async def contains(self, address: IPAddress) -> bool:
        if any(address in network for network in self.networks):
            return True
        for host in self.hostnames:
            if address in await self._addresses_of(host):
                return True
        return False


def _forwarded_hops(request: Request) -> list[str]:
    """Every ``X-Forwarded-For`` entry, left to right, across repeated headers."""
    hops: list[str] = []
    for value in request.headers.getlist("x-forwarded-for"):
        hops.extend(value.split(","))
    return hops


async def client_address(request: Request) -> str:
    """The key for "this client": its address, per the trusted-proxy rule.

    Every limiter and log line that means the client's address uses this,
    never ``request.client.host``. Reads the proxy list from
    ``app.state.trusted_proxies`` (installed by ``build_app``).
    """
    peer_raw = request.client.host if request.client is not None else "unknown"
    peer = parse_address(peer_raw)
    if peer is None:
        return peer_raw  # not an IP socket (a test client, a unix socket)
    trusted: TrustedProxies | None = getattr(request.app.state, "trusted_proxies", None)
    if trusted is None or trusted.empty or not await trusted.contains(peer):
        return address_key(peer)
    client = peer
    for raw in reversed(_forwarded_hops(request)[-MAX_FORWARDED_HOPS:]):
        hop = parse_address(raw)
        if hop is None:
            break
        client = hop
        if not await trusted.contains(hop):
            break
    return address_key(client)
