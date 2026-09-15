"""Transport unit tests: what goes on the wire, and what comes back off it.

No network — an ``httpx.MockTransport`` records the actual request the library
built, which is the only thing that can settle questions about encoding.
"""

from __future__ import annotations

import json
from typing import Any

import httpx2 as httpx
import pytest
from loft import _operations as ops
from loft._operation import (
    MissingPathParameter,
    Operation,
    UnknownPathParameter,
)
from loft.errors import (
    AuthenticationError,
    Conflict,
    ContractMismatch,
    InvalidRequest,
    LoftError,
    NotFound,
    RateLimited,
    StaleDocument,
    UpstreamError,
)
from loft.transport import Transport
from py_kit.schemas.auth import RegisterRequest
from py_kit.schemas.parts import PartCreate
from pydantic import SecretStr

PASSWORD = "correct-horse-battery"


def _recorder(
    status: int = 200, body: Any = None, headers: dict[str, str] | None = None
) -> tuple[list[httpx.Request], httpx.MockTransport]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            status, json=body if body is not None else {}, headers=headers
        )

    return seen, httpx.MockTransport(handler)


def _transport(
    status: int = 200, body: Any = None, headers: dict[str, str] | None = None
) -> tuple[list[httpx.Request], Transport]:
    seen, mock = _recorder(status, body, headers)
    return seen, Transport(
        "http://gateway.test", token="tok", client=httpx.Client(transport=mock)
    )


# --- the SecretStr trap -----------------------------------------------------


def test_register_payload_carries_the_real_password() -> None:
    """The bytes must contain the password, not pydantic's ``**********`` mask.

    THE assertion this module exists for. ``model_dump(mode="json")`` masks a
    ``SecretStr``, and a masked register would have been a **201** followed by
    a login that fails for reasons nobody could see — a request that parsed and
    meant something else. Asserting on the status here would prove nothing, so
    this reads the body off the wire.
    """
    seen, transport = _transport(
        201,
        {
            "user": {
                "id": "00000000-0000-0000-0000-000000000001",
                "email": "e@example.com",
                "created_at": "2026-01-01T00:00:00Z",
            },
            "access_token": "jwt",
            "token_type": "bearer",
            "expires_in": 3600,
        },
    )
    transport.call(
        ops.POST_AUTH_REGISTER,
        __import__("py_kit.schemas.auth", fromlist=["x"]).AuthTokenResponse,
        body=RegisterRequest(email="e@example.com", password=SecretStr(PASSWORD)),
    )
    payload = json.loads(seen[0].content)
    assert payload["password"] == PASSWORD
    assert "*" not in payload["password"]


# --- contract enforcement ---------------------------------------------------


def test_a_body_the_contract_does_not_declare_is_refused() -> None:
    """The negative control for the "only declared payloads" guarantee.

    Without it, ``_check_request_model`` is an assertion nobody has ever seen
    fire, which is not yet a gate.
    """
    seen, transport = _transport(201, {})
    with pytest.raises(ContractMismatch) as caught:
        transport.call(
            ops.POST_PARTS,
            PartCreate,
            body=RegisterRequest(email="e@example.com", password=SecretStr(PASSWORD)),
        )
    assert caught.value.code == "contract_mismatch"
    assert caught.value.details == {
        "operation_id": ops.POST_PARTS.operation_id,
        "declared": "PartCreate",
        "supplied": "RegisterRequest",
    }
    assert seen == [], "nothing may reach the network once the check refuses"


def test_a_body_on_a_bodyless_operation_is_refused() -> None:
    """Evaluate declares no JSON body; sending one is a programming error."""
    _, transport = _transport(200, {})
    with pytest.raises(ContractMismatch):
        transport.call_none(
            ops.POST_PARTS_PART_ID_EVALUATE,
            path_params={"part_id": "p"},
            body=PartCreate(name="x"),
        )


# --- URL building -----------------------------------------------------------


def test_url_substitutes_and_escapes_path_parameters() -> None:
    assert (
        ops.GET_PARTS_PART_ID_FEATURES_FEATURE_ID.url(part_id="a/b", feature_id="c")
        == "/api/v1/parts/a%2Fb/features/c"
    )


def test_url_refuses_a_missing_or_unknown_path_parameter() -> None:
    """Both directions, because each leaves a DIFFERENT kind of broken URL."""
    with pytest.raises(MissingPathParameter):
        ops.GET_PARTS_PART_ID.url()
    with pytest.raises(UnknownPathParameter):
        ops.GET_PARTS_PART_ID.url(part_id="p", prt_id="typo")


def test_url_of_a_parameterless_operation() -> None:
    assert ops.GET_PARTS.url() == "/api/v1/parts"


# --- error translation ------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, AuthenticationError),
        (404, NotFound),
        (409, Conflict),
        (422, InvalidRequest),
        (429, RateLimited),
        (500, UpstreamError),
        (503, UpstreamError),
    ],
)
def test_status_maps_to_the_typed_error(status: int, expected: type[LoftError]) -> None:
    _, transport = _transport(
        status,
        {
            "error": {
                "code": "some_code",
                "message": "nope",
                "details": {"field": "x"},
                "request_id": "req-1",
            }
        },
    )
    with pytest.raises(expected) as caught:
        transport.call(ops.GET_PARTS, PartCreate)
    error = caught.value
    assert error.code == "some_code"
    assert error.message == "nope"
    assert error.status == status
    assert error.request_id == "req-1"
    assert error.as_dict()["details"] == {"field": "x"}


def test_a_stale_tree_version_is_its_own_class_not_a_plain_422() -> None:
    """The code, not the status, decides — a 422 is too coarse to retry on."""
    _, transport = _transport(
        422, {"error": {"code": "stale_tree_version", "message": "stale"}}
    )
    with pytest.raises(StaleDocument):
        transport.call(ops.GET_PARTS, PartCreate)


def test_a_non_envelope_body_still_produces_a_typed_error() -> None:
    """An intermediary answering HTML must not become a ``KeyError``."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>bad gateway</html>")

    transport = Transport(
        "http://gateway.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(UpstreamError) as caught:
        transport.call(ops.GET_PARTS, PartCreate)
    assert caught.value.status == 502
    assert caught.value.code == "upstream_error"
    assert "bad gateway" in str(caught.value.details)


def test_retry_after_is_lifted_off_the_header() -> None:
    _, transport = _transport(
        429,
        {"error": {"code": "rate_limited", "message": "slow down"}},
        headers={"Retry-After": "12"},
    )
    with pytest.raises(RateLimited) as caught:
        transport.call(ops.GET_PARTS, PartCreate)
    assert caught.value.retry_after == 12.0
    assert caught.value.as_dict()["retry_after"] == 12.0


def test_an_unreachable_gateway_is_an_upstream_error_not_an_httpx_error() -> None:
    """A caller should never have to catch the HTTP library's own exceptions."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = Transport(
        "http://gateway.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(UpstreamError) as caught:
        transport.call(ops.GET_PARTS, PartCreate)
    assert caught.value.code == "gateway_unreachable"


# --- headers ----------------------------------------------------------------


def test_the_bearer_token_and_user_agent_are_sent() -> None:
    seen, transport = _transport(200, {"parts": []})
    transport.call_none(ops.GET_PARTS)
    assert seen[0].headers["authorization"] == "Bearer tok"
    assert seen[0].headers["user-agent"] == "loft-script"


def test_no_authorization_header_without_a_token() -> None:
    """An anonymous client must send NO header, not an empty one — the gateway
    must be able to tell "did not authenticate" from "sent a bad token"."""
    seen, mock = _recorder(401, {"error": {"code": "unauthorized", "message": "no"}})
    transport = Transport("http://gateway.test", client=httpx.Client(transport=mock))
    with pytest.raises(AuthenticationError):
        transport.call_none(ops.GET_PARTS)
    assert "authorization" not in seen[0].headers


def test_an_operation_record_is_immutable() -> None:
    """The generated table is shared global state; it must not be writable."""
    with pytest.raises(AttributeError):
        ops.GET_PARTS.path = "/elsewhere"  # type: ignore[misc]
    assert isinstance(ops.GET_PARTS, Operation)
