"""The connected session: credentials in, documents out."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from types import TracebackType
from typing import Self

import httpx2 as httpx
from py_kit.schemas.auth import (
    AuthTokenResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from py_kit.schemas.units import LengthUnit
from pydantic import SecretStr

from loft import _operations as ops
from loft.errors import AuthenticationError
from loft.part import Part, create_part, list_parts
from loft.transport import DEFAULT_TIMEOUT, Transport

__all__ = ["Session", "connect", "register"]


class Session:
    """An authenticated connection to one Loft gateway.

    A context manager, because it owns a connection pool::

        with loft.connect(url, token=token) as session:
            ...

    Everything a script does goes through here, and everything it does is an
    ordinary gateway call — the session holds no privilege the browser's session
    does not have.
    """

    def __init__(self, transport: Transport, *, user: UserResponse | None = None):
        self.transport = transport
        self._user = user

    def __repr__(self) -> str:
        who = self._user.email if self._user else "unknown"
        return f"Session(url={self.transport.base_url!r}, user={who!r})"

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Close the underlying connection pool."""
        self.transport.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- identity ----------------------------------------------------------

    @property
    def user(self) -> UserResponse:
        """Who this session is, asking the gateway if it was not told.

        A token is opaque to a client, so "who am I" is a server question. It is
        also the cheapest possible liveness probe for an agent resuming with a
        token it did not mint.
        """
        if self._user is None:
            self._user = self.transport.call(ops.GET_AUTH_ME, UserResponse)
        return self._user

    @property
    def token(self) -> str:
        """The bearer token this session presents.

        Exposed so a long-lived agent can persist it and reconnect without
        re-sending credentials — the reconstruction path an MCP server wants.
        """
        if self.transport.token is None:
            raise AuthenticationError(
                "this session has no token", code="no_credentials"
            )
        return self.transport.token

    # -- documents ---------------------------------------------------------

    def new_part(
        self,
        name: str,
        *,
        folder_id: uuid.UUID | None = None,
        length_unit: LengthUnit = "mm",
    ) -> Part:
        """Create a part and return a handle to it."""
        return create_part(self, name, folder_id=folder_id, length_unit=length_unit)

    def part(self, part_id: uuid.UUID | str) -> Part:
        """A handle to an existing part, from its id alone.

        No request is made: the handle is a pair of (session, id), and every
        method on it fetches what it needs. That is what lets one agent tool
        call hand an id to the next with nothing else attached.
        """
        return Part(
            self, part_id if isinstance(part_id, uuid.UUID) else uuid.UUID(part_id)
        )

    def parts(self) -> Sequence[Part]:
        """The caller's parts, oldest first."""
        return list_parts(self)


def _session_from_token(
    base_url: str,
    response: AuthTokenResponse,
    transport: Transport,
) -> Session:
    transport.token = response.access_token
    return Session(transport, user=response.user)


def connect(
    url: str,
    *,
    token: str | None = None,
    email: str | None = None,
    password: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    client: httpx.Client | None = None,
) -> Session:
    """Connect to a Loft gateway, with a bearer token or with credentials.

        with loft.connect("http://localhost:8000", token=os.environ["LOFT_TOKEN"]) as s:
            ...

    Exactly one of ``token`` or (``email``, ``password``) is required, and that
    is checked here rather than by letting an empty ``Authorization`` header
    reach the server: an argument mistake should not look like a rejected
    credential.
    """
    has_password = email is not None and password is not None
    if (token is None) == (not has_password):
        raise ValueError(
            "connect() needs either token= or both email= and password=, not "
            "neither and not both"
        )
    transport = Transport(url, token=token, timeout=timeout, client=client)
    if token is not None:
        return Session(transport)
    assert email is not None and password is not None
    response = transport.call(
        ops.POST_AUTH_LOGIN,
        AuthTokenResponse,
        body=LoginRequest(email=email, password=SecretStr(password)),
    )
    return _session_from_token(url, response, transport)


def register(
    url: str,
    *,
    email: str,
    password: str,
    timeout: float = DEFAULT_TIMEOUT,
    client: httpx.Client | None = None,
) -> Session:
    """Create an account and return a session already signed in to it.

    Separate from :func:`connect` on purpose: creating an account is a
    different intention from using one, and a ``create=True`` flag on connect
    is how a typo'd email quietly becomes a second empty account.
    """
    transport = Transport(url, timeout=timeout, client=client)
    response = transport.call(
        ops.POST_AUTH_REGISTER,
        AuthTokenResponse,
        body=RegisterRequest(email=email, password=SecretStr(password)),
    )
    return _session_from_token(url, response, transport)
