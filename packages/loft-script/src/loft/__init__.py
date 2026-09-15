"""Loft's public Python scripting API — model parts from code.

    import loft

    with loft.connect("http://localhost:8000", token=TOKEN) as session:
        part = session.new_part("Bracket")
        sk = part.sketch(on="XY")
        sk.rect(40, 25)
        sk.solve()
        part.extrude(sk, 10)
        print(part.mass_properties().volume)   # 10000.0
        part.export("bracket.step")

**This library is another client of the gateway, exactly like the web app.**
That is the whole design and it is worth stating before anything else, because
the alternative is so tempting and so expensive: a scripting API that talked to
the kernel directly, or wrote to Postgres, would be a SECOND PRODUCT — it would
drift, grow its own bugs, and make every future feature something we have to
build twice. So:

* it imports no kernel (only ``services/geometry`` may import OCP/build123d),
* it touches no database,
* it reaches nothing the browser cannot reach — every call is a route declared
  in ``packages/contracts/gateway.openapi.json``, and the transport refuses to
  send a body whose model that contract does not name for that route,
* and it refuses what the UI refuses: an unsolved sketch, a bodiless export, a
  non-positive extrude distance.

Where the types come from
-------------------------
The DTOs are ``loft_wire.*`` — the very pydantic models the services
serve. They are imported, not regenerated: Python can read a pydantic model, so
deriving a second set of Python classes from an OpenAPI document that was
itself derived from those classes would lose information and add a drift
surface for nothing. ``packages/ts-client`` is generated precisely because
TypeScript has no such option. What a Python client genuinely cannot import is
the ROUTING, so that — and only that — is generated, into
:mod:`loft._operations` by ``just gen``, with ``just gen-check`` failing CI on
drift.

Designed for the MCP server that comes next
-------------------------------------------
Errors carry a machine-readable :attr:`~loft.errors.LoftError.code` and an
:meth:`~loft.errors.LoftError.as_dict`, never a stack trace. Every object is
addressable by id, and every handle can be rebuilt from one
(:meth:`Session.part`, :meth:`Part.sketch_by_id`), so an agent calling one tool
at a time never depends on state it cannot reconstruct.
"""

from __future__ import annotations

from loft_wire.geometry import ExportFormat, ShapeProperties
from loft_wire.sketch import Point2D, SolvedSketch

from loft._operation import Operation
from loft.errors import (
    AuthenticationError,
    Conflict,
    ContractMismatch,
    FeatureFailed,
    InvalidRequest,
    LoftError,
    NoBody,
    NotFound,
    PermissionDenied,
    RateLimited,
    SketchNotSolved,
    StaleDocument,
    UpstreamError,
)
from loft.part import Evaluation, Part
from loft.session import Session, connect, register
from loft.sketch import XY, XZ, YZ, Rect, Sketch

__version__ = "0.1.0"

__all__ = [
    "XY",
    "XZ",
    "YZ",
    "AuthenticationError",
    "Conflict",
    "ContractMismatch",
    "Evaluation",
    "ExportFormat",
    "FeatureFailed",
    "InvalidRequest",
    "LoftError",
    "NoBody",
    "NotFound",
    "Operation",
    "Part",
    "PermissionDenied",
    "Point2D",
    "RateLimited",
    "Rect",
    "Session",
    "ShapeProperties",
    "Sketch",
    "SketchNotSolved",
    "SolvedSketch",
    "StaleDocument",
    "UpstreamError",
    "__version__",
    "connect",
    "register",
]
