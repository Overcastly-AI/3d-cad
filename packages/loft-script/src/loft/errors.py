"""Errors that carry a MACHINE-READABLE reason, never a stack trace.

Designed for the MCP server that sits on top of this library next: an agent
calling one tool at a time needs to branch on WHAT went wrong, and a formatted
traceback is the worst possible channel for that. So every failure here is a
:class:`LoftError` with a stable :attr:`~LoftError.code`, the same code the
gateway's ``py_kit.errors`` envelope puts on the wire, plus enough structure
(:meth:`LoftError.as_dict`) to hand straight back to a tool caller.

Three families, and the split matters because the remedies differ:

* **Transport/envelope failures** — the gateway refused (401, 404, 409, 422,
  429, 5xx). :meth:`LoftError.from_response` maps the status to the subclass
  and lifts ``error.code`` verbatim out of the envelope.
* **Modelling refusals** — the request SUCCEEDED and the model did not build: a
  feature errored during evaluate (:class:`FeatureFailed`), a sketch did not
  solve (:class:`SketchNotSolved`), a tree evaluated to no body
  (:class:`NoBody`). These are 200 responses in the protocol (feature failures
  are per-feature statuses, never envelopes — feature-tree.md §4.3) and they
  are exactly the states where the UI DISABLES the next action. A library that
  returned them as ordinary values would let a script sail past a refusal the
  UI would have stopped a person at.
* **Programming errors** — a path parameter that does not exist, a payload
  whose model the contract does not declare for the route
  (:class:`ContractMismatch`). Raised before anything leaves the process.
"""

from __future__ import annotations

from typing import Any, cast

__all__ = [
    "AuthenticationError",
    "Conflict",
    "ContractMismatch",
    "FeatureFailed",
    "InvalidRequest",
    "LoftError",
    "NoBody",
    "NotFound",
    "PermissionDenied",
    "RateLimited",
    "SketchNotSolved",
    "StaleDocument",
    "UpstreamError",
]


class LoftError(Exception):
    """Base of every failure this library raises.

    ``code`` is the contract: a short, stable, machine-readable string. For a
    server refusal it is the gateway envelope's own ``error.code``; for a
    modelling refusal it is the code the geometry service put on the failing
    feature, or one of this module's own (``sketch_not_solved``,
    ``tree_has_no_body``). Never parse ``message`` — it is for humans and it
    changes.
    """

    #: Fallback when neither the envelope nor the caller names one.
    default_code = "loft_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int | None = None,
        details: Any = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        #: HTTP status, when the failure came from a response. ``None`` for a
        #: modelling refusal (which arrives on a 200) or a programming error.
        self.status = status
        self.details = details
        #: The gateway's correlation id, when it sent one — the single most
        #: useful thing to hand back to an operator reading service logs.
        self.request_id = request_id

    def as_dict(self) -> dict[str, Any]:
        """The failure as plain JSON-ready data (what an MCP tool returns)."""
        return {
            "code": self.code,
            "message": self.message,
            "status": self.status,
            "details": self.details,
            "request_id": self.request_id,
        }

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"

    @staticmethod
    def from_response(status: int, body: Any, *, fallback: str) -> LoftError:
        """Build the right subclass from an HTTP status and a decoded body.

        ``body`` is whatever the response decoded to — the ``{"error": {...}}``
        envelope every Loft service renders (``py_kit.errors``), or anything at
        all when an intermediary (a proxy, a crashed worker) answered instead.
        The non-envelope case is handled rather than assumed: a client that
        assumes the shape turns "the load balancer returned HTML" into a
        ``KeyError`` with no status in it, which is strictly less informative
        than the response it was given.
        """
        # An OpenAPI-shaped body is `dict[str, Any]` all the way down, and
        # pyright-strict will not let that `Any` spread implicitly — rightly,
        # since this function's entire premise is that the body might not be
        # the shape it claims. Narrow ONCE, to empty rather than to an
        # exception: a proxy's HTML is a normal thing to receive here.
        decoded: dict[str, Any] = (
            cast(dict[str, Any], body) if isinstance(body, dict) else {}
        )
        raw = decoded.get("error")
        envelope: dict[str, Any] = (
            cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
        )
        if envelope:
            message = str(envelope.get("message") or fallback)
            code: Any = envelope.get("code")
            details: Any = envelope.get("details")
            request_id: Any = envelope.get("request_id")
        else:
            message = fallback
            code = None
            details = cast(Any, body) if body not in (None, "") else None
            request_id = None

        cls = _CODE_ERRORS.get(str(code)) or _STATUS_ERRORS.get(status)
        if cls is None:
            cls = UpstreamError if status >= 500 else LoftError
        return cls(
            message,
            code=str(code) if code else None,
            status=status,
            details=details,
            request_id=str(request_id) if request_id else None,
        )


class AuthenticationError(LoftError):
    """No credentials, or credentials the gateway would not accept (401)."""

    default_code = "unauthorized"


class PermissionDenied(LoftError):
    """Authenticated, but not allowed to touch this (403)."""

    default_code = "forbidden"


class NotFound(LoftError):
    """No such document — or one owned by somebody else (404).

    The gateway deliberately does not distinguish those two, and neither does
    this: telling a caller that a part exists but is not theirs is an
    enumeration oracle.
    """

    default_code = "not_found"


class Conflict(LoftError):
    """The write is refused because something depends on it (409)."""

    default_code = "conflict"


class InvalidRequest(LoftError):
    """The gateway rejected the request body or a parameter (422).

    Covers both an ill-formed payload and a well-formed one the server refuses
    on its own rules (a non-positive extrude distance, an unresolvable profile
    reference). :class:`StaleDocument` is the one 422 split out, because it is
    the only one with an automatic remedy.
    """

    default_code = "validation_error"


class StaleDocument(LoftError):
    """An optimistic-concurrency guard rejected the write (422).

    The ``expected_tree_version`` sent did not match the document's current
    one, so somebody (or something) edited the part in between. The library
    refetches and retries a write once on this; it reaches a caller only when
    the retry also lost, which means a genuinely concurrent editor.
    """

    default_code = "stale_tree_version"


class RateLimited(LoftError):
    """Too many requests (429). ``retry_after`` is seconds, when the server said."""

    default_code = "rate_limited"

    def __init__(self, *args: Any, retry_after: float | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.retry_after = retry_after

    def as_dict(self) -> dict[str, Any]:
        return {**super().as_dict(), "retry_after": self.retry_after}


class UpstreamError(LoftError):
    """The gateway or a service behind it failed (5xx), or was unreachable."""

    default_code = "upstream_error"


class ContractMismatch(LoftError):
    """The library tried to send a model the contract does not declare here.

    Raised before the request leaves the process. This is the runtime half of
    the "another client of the gateway, not a second product" guarantee: the
    transport refuses to post a body whose class is not the one
    ``packages/contracts`` names for that operation, so the library cannot
    grow a private payload shape the browser never sends.
    """

    default_code = "contract_mismatch"


class FeatureFailed(LoftError):
    """A feature errored while the part was being evaluated.

    Arrives on a **200** — a feature failure is a per-feature status, not an
    envelope (feature-tree.md §4.3) — so this is the library turning a value
    the UI renders as a red feature row into a refusal a script cannot walk
    past. ``code`` is the geometry service's own feature-error code
    (``profile_not_closed``, ``extrude_failed``, ...).
    """

    default_code = "feature_failed"

    def __init__(
        self,
        message: str,
        *,
        feature_id: str,
        feature_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.feature_id = feature_id
        self.feature_name = feature_name

    def as_dict(self) -> dict[str, Any]:
        return {
            **super().as_dict(),
            "feature_id": self.feature_id,
            "feature_name": self.feature_name,
        }


class SketchNotSolved(LoftError):
    """The constraint solver could not satisfy the sketch.

    ``status`` on the wire is ``conflicting`` (mutually contradictory
    constraints) or ``diverged`` (numeric failure); both leave the UI's extrude
    disabled, so both are a refusal here. ``conflicting_constraints`` /
    ``redundant_constraints`` are indices into the constraint list as authored,
    which is what lets a caller name the offending constraint rather than
    re-derive it.
    """

    default_code = "sketch_not_solved"

    def __init__(
        self,
        message: str,
        *,
        solve_status: str,
        conflicting_constraints: tuple[int, ...] = (),
        redundant_constraints: tuple[int, ...] = (),
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.solve_status = solve_status
        self.conflicting_constraints = conflicting_constraints
        self.redundant_constraints = redundant_constraints

    def as_dict(self) -> dict[str, Any]:
        return {
            **super().as_dict(),
            "solve_status": self.solve_status,
            "conflicting_constraints": list(self.conflicting_constraints),
            "redundant_constraints": list(self.redundant_constraints),
        }


class NoBody(LoftError):
    """The tree evaluated cleanly but produced no solid.

    A sketch-only part is the common case, and it is not an error in the
    protocol — ``mesh_glb_id`` and ``properties`` are simply ``null``. It IS a
    refusal for anything that needs a body: the UI shows "No body" and disables
    the export button, so :meth:`loft.Part.export` and
    :meth:`loft.Part.mass_properties` raise this rather than return ``None``
    and let a script write a zero-byte STEP.
    """

    default_code = "tree_has_no_body"


#: Envelope CODE -> error class, consulted before the status map because a
#: status is coarser than a code: every optimistic-concurrency rejection is a
#: 422, and so is a malformed payload, but only one of them is worth retrying.
#: Keyed on the codes the services actually emit
#: (``documents/features.py``, ``documents/parts.py``).
_CODE_ERRORS: dict[str, type[LoftError]] = {
    "stale_tree_version": StaleDocument,
    # An export of a tree that evaluates to no solid. The geometry service's
    # own 422, re-surfaced verbatim by the gateway, so the library's refusal is
    # the server's verdict rather than a client-side second opinion.
    "tree_export_failed": NoBody,
}

#: Status -> error class. 4xx codes the gateway actually uses; anything else
#: falls back in :meth:`LoftError.from_response` (5xx -> UpstreamError).
_STATUS_ERRORS: dict[int, type[LoftError]] = {
    401: AuthenticationError,
    403: PermissionDenied,
    404: NotFound,
    409: Conflict,
    422: InvalidRequest,
    429: RateLimited,
}
