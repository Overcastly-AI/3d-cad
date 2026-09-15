"""The ``Operation`` record the generated route table is made of.

Hand-written on purpose: ``_operations.py`` is generated and should stay dumb
data, so anything with behaviour (and therefore with bugs worth reviewing and
testing) lives here instead.
"""

from __future__ import annotations

from typing import NamedTuple
from urllib.parse import quote


class UnknownPathParameter(KeyError):
    """A path parameter was supplied that the route does not declare."""


class MissingPathParameter(KeyError):
    """A path parameter the route declares was not supplied."""


class Operation(NamedTuple):
    """One gateway route, as the committed OpenAPI contract declares it.

    ``request_model`` / ``response_model`` are the COMPONENT NAMES the contract
    names for the JSON body (``"FeatureCreate"``, ``"EvaluateTreeResult"``, ...),
    or ``None`` where the operation has no JSON body on that side (an export
    returns file bytes; an evaluate takes none). FastAPI names components after
    the pydantic class, so these are exactly the class names in
    ``py_kit.schemas`` — which is what makes the contract-parity test possible:
    it can check that the class the library SENDS is the class the contract
    declares, a property a 2xx status cannot establish.
    """

    operation_id: str
    method: str
    path: str
    request_model: str | None
    response_model: str | None
    path_params: tuple[str, ...]
    required_query: tuple[str, ...]

    def url(self, **params: object) -> str:
        """Substitute path parameters, refusing anything the route does not declare.

        Strict in BOTH directions, which is the whole value over an f-string: a
        missing parameter would otherwise leave a literal ``{part_id}`` in the
        URL (a 404 whose message says nothing about the cause), and a misspelled
        one would be silently dropped. Both raise here instead, with the route
        and the declared names in the message — the machine-readable-reason rule
        applied to the library's own programming errors, not just the server's.
        """
        declared = set(self.path_params)
        supplied = set(params)
        if unknown := sorted(supplied - declared):
            raise UnknownPathParameter(
                f"{self.method} {self.path} declares path parameters "
                f"{sorted(declared)}; got unexpected {unknown}"
            )
        if missing := sorted(declared - supplied):
            raise MissingPathParameter(
                f"{self.method} {self.path} requires path parameters {missing}"
            )
        url = self.path
        for name, value in params.items():
            url = url.replace("{" + name + "}", quote(str(value), safe=""))
        return url
