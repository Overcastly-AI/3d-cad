"""HTTP plumbing: one authenticated gateway client, one error translation.

Everything above this module speaks in pydantic models and :mod:`loft.errors`;
nothing above it knows a URL, a status code or a header. That is deliberate —
it is the seam that keeps the library a CLIENT rather than a second
implementation of the product.

Two guarantees live here, and both are enforced rather than documented:

1. **Only declared operations, only declared payloads.** Every call names an
   :class:`~loft._operation.Operation` out of the generated table, and the
   request is checked against the committed contract on all THREE axes the
   contract declares: the body model's class name against ``request_model``,
   the path parameters against ``path_params`` (strict both ways, in
   :meth:`Operation.url`), and the query against ``required_query``. A payload
   the gateway does not declare cannot be sent, so the library structurally
   cannot reach something the browser cannot.

   The query axis was missing until 2026-09-15, and the gap was not theoretical:
   ``required_query`` was generated for all 86 operations and read by NOTHING,
   so ``Part.delete_feature`` omitted the ``expected_tree_version`` the route
   requires and **422'd on every call, for every input**. A guarantee that
   covers bodies and paths reads as a total one — that is what made a whole
   public method unusable without any gate objecting — so the axis that is
   enforced and the axis that is merely emitted must not drift apart again.
   NOTE the asymmetry with the other two: only REQUIRED query parameters are
   checked, and extras are allowed, because optional query is how a route
   legitimately varies (``format`` on export). Missing-required is the failure
   that produces a 422; unexpected-extra is one FastAPI ignores.
2. **Every non-2xx becomes a typed error with the server's own code.** No
   response body reaches a caller unexamined, and no status is swallowed.
"""

from __future__ import annotations

import contextlib
import json
from types import TracebackType
from typing import Any, Self, TypeVar

import httpx2 as httpx
from pydantic import BaseModel, SecretStr

from loft._operation import Operation
from loft.errors import LoftError, RateLimited, UpstreamError

ModelT = TypeVar("ModelT", bound=BaseModel)

#: Default per-request timeout (seconds). Generous because a geometry evaluate
#: of a heavy tree is real OCCT work on the far side of two hops, and a client
#: timeout that fires mid-solve looks exactly like a broken server.
DEFAULT_TIMEOUT = 120.0

#: Sent on every request so gateway logs can tell scripted traffic from the
#: browser — the cheapest possible answer to "who did this?" in an audit.
USER_AGENT = "loft-script"


def json_payload(model: BaseModel) -> dict[str, Any]:
    """A JSON-ready dict for a request body, with ``SecretStr`` fields unmasked.

    ``model_dump(mode="json")`` renders a :class:`~pydantic.SecretStr` as
    ``"**********"``, which is right for logs and catastrophic for a request
    body: ``RegisterRequest`` would create an account whose password is ten
    asterisks, the call would return **201**, and the very next login would
    fail. That is the repo's "assert on the result, not the status" trap in its
    purest form — the request parsed, and meant something else.

    The models are the server's own DTOs (``loft_wire.auth``), which are
    written to be PARSED by a server and so have no client-side serializer for
    their secrets; unmasking here, at the one place bodies are encoded, is the
    alternative to either duplicating those models or hand-building auth dicts.
    Covered by ``test_register_payload_carries_the_real_password`` in
    ``tests/test_transport.py``, which asserts on the BYTES, not on a status.
    """
    data = model.model_dump(mode="json")
    for name, value in model:
        if isinstance(value, SecretStr):
            data[name] = value.get_secret_value()
    return data


class Transport:
    """An authenticated, contract-checked HTTP client for one gateway."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        #: An injected client is how the unit suite drives a real gateway app
        #: over an ASGI transport with no sockets — the same object the library
        #: uses in production, pointed at the app instead of at a port.
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Release the connection pool (only if this object opened it)."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- request path ------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": USER_AGENT}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _send(
        self,
        operation: Operation,
        *,
        path_params: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        body: BaseModel | None = None,
    ) -> httpx.Response:
        """Issue one request, or raise a typed error. Never returns a non-2xx."""
        _check_request_model(operation, body)
        _check_required_query(operation, query)
        url = self.base_url + operation.url(**(path_params or {}))
        try:
            response = self._client.request(
                operation.method,
                url,
                params=query,
                json=json_payload(body) if body is not None else None,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            # A connection refused / DNS failure / read timeout is the same
            # KIND of thing to a caller as a 502 — the gateway did not answer —
            # so it gets the same class and a code that says which.
            raise UpstreamError(
                f"{operation.method} {operation.path}: {exc}",
                code="gateway_unreachable",
                details={"url": url},
            ) from exc
        if response.is_success:
            return response
        raise _error_for(operation, response)

    def call(
        self,
        operation: Operation,
        model: type[ModelT],
        *,
        path_params: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        body: BaseModel | None = None,
    ) -> ModelT:
        """Call an operation and parse its JSON body into ``model``.

        ``model`` is passed in rather than looked up from
        ``operation.response_model`` on purpose: a name is not a class, and
        resolving one by string would be a second, weaker type system beside
        pyright's. The contract-parity test closes the loop by asserting the
        two agree for every call site.
        """
        response = self._send(
            operation, path_params=path_params, query=query, body=body
        )
        return model.model_validate_json(response.content)

    def call_none(
        self,
        operation: Operation,
        *,
        path_params: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        body: BaseModel | None = None,
    ) -> None:
        """Call an operation whose success carries nothing worth reading."""
        self._send(operation, path_params=path_params, query=query, body=body)

    def call_bytes(
        self,
        operation: Operation,
        *,
        path_params: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        body: BaseModel | None = None,
    ) -> bytes:
        """Call an operation that returns a file, and hand back its bytes.

        Deliberately unparsed and unvalidated here: an exported STEP/STL is
        proxied byte-exact from the geometry service, and anything this layer
        did to it would make the library's output differ from the browser's
        download, which is the one thing it must not do.
        """
        return self._send(
            operation, path_params=path_params, query=query, body=body
        ).content


def _check_request_model(operation: Operation, body: BaseModel | None) -> None:
    """Refuse a body whose class is not the one the contract declares here."""
    declared = operation.request_model
    supplied = type(body).__name__ if body is not None else None
    if declared == supplied:
        return
    from loft.errors import ContractMismatch

    raise ContractMismatch(
        f"{operation.method} {operation.path} declares request body "
        f"{declared or 'none'}; got {supplied or 'none'}",
        details={
            "operation_id": operation.operation_id,
            "declared": declared,
            "supplied": supplied,
        },
    )


def _check_required_query(operation: Operation, query: dict[str, Any] | None) -> None:
    """Refuse a request missing a query parameter the contract marks required.

    Required-only, and extras are deliberately allowed: an optional query
    parameter is how a route varies legitimately, and the failure this closes is
    the one that produces a 422 before the handler ever runs.

    ``None`` counts as ABSENT, not as supplied. A version guard serialised as
    ``?expected_tree_version=None`` is a 422 with a more confusing message than
    omitting it, so the two cases get the same refusal.
    """
    supplied = {name for name, value in (query or {}).items() if value is not None}
    missing = sorted(set(operation.required_query) - supplied)
    if not missing:
        return
    from loft.errors import ContractMismatch

    raise ContractMismatch(
        f"{operation.method} {operation.path} requires query parameter(s) "
        f"{missing}; got {sorted(supplied)}",
        details={
            "operation_id": operation.operation_id,
            "required": list(operation.required_query),
            "supplied": sorted(supplied),
            "missing": missing,
        },
    )


def _error_for(operation: Operation, response: httpx.Response) -> LoftError:
    """Translate a non-2xx response into the right :class:`LoftError`."""
    try:
        body: Any = response.json()
    except (json.JSONDecodeError, ValueError):
        # An intermediary answering with HTML, or a truncated body. Keep the
        # text — it is the only evidence there is — but do not pretend it
        # parsed.
        body = response.text
    error = LoftError.from_response(
        response.status_code,
        body,
        fallback=f"{operation.method} {operation.path} failed ({response.status_code})",
    )
    retry_after = response.headers.get("retry-after")
    if retry_after is not None and isinstance(error, RateLimited):
        # RFC 9110 also allows an HTTP-date here. Suppressed rather than parsed:
        # a missing `retry_after` is a caller backing off on its own judgement,
        # which is survivable — raising a ValueError out of the ERROR PATH would
        # replace the server's actual refusal with a parsing complaint about it.
        with contextlib.suppress(ValueError):
            error.retry_after = float(retry_after)
    return error
