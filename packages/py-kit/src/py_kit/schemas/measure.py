"""Measurement boundary DTOs — transient point/edge distance (BACKLOG #6a).

Single source of truth (CLAUDE.md DRY rule) for the stateless distance query
the geometry service serves at ``POST /api/v1/measure`` and the gateway proxies
at ``POST /api/v1/geometry/measure``. Pure pydantic only — kernel types never
appear here (CLAUDE.md service boundaries). Units are millimetres (lengths) and
degrees (angles), fixed per field exactly as :mod:`py_kit.schemas.geometry`.

Stateless contract (the KEY design decision, documented here and in the
endpoint docstring + docs/GEOMETRY-QA.md): a measurement is a one-shot query,
never persisted. The caller sends the geometry it picked in the viewport and
geometry answers the EXACT nearest distance. A measurement *target* is one of:

* a **point** — explicit world coordinates (mm). The viewport already holds
  exact coordinates for a picked vertex/snap point, so a point target needs no
  server-side geometry and is exact on its own.
* an **edge** — a B-rep edge of a body geometry recomputes from a supplied
  feature ``tree``. Because v1 has no topological naming (that is the Phase-2
  ``SubshapeRef``, feature-tree design §2.4), an edge is named by its 0-based
  INDEX into the body's deterministic edge list — the OCCT exploration order
  build123d's ``.edges()`` yields, the same order the B-rep edge overlay
  enumerates. This is a **transient** selector: valid only for this single
  measurement against this exact ``tree``, NOT a reference that survives edits.

**Fidelity — chosen for exactness, honestly stated:** every supported case is
EXACT, straight or curved, because edge targets are measured against the
recomputed B-rep with OCCT's exact nearest-distance solver
(``BRepExtrema_DistShapeShape``), never against the tessellation. The
alternative "client sends picked coordinates for edges too" contract was
rejected precisely because curved-edge nearest distance would then be a
mesh approximation; recomputing the body keeps point-edge and edge-edge exact.
The cost is that an edge target must carry the ``tree`` to recompute (point
targets need nothing) — a deliberate trade for correctness.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from py_kit.schemas.features import EvaluateTreeRequest
from py_kit.schemas.geometry import Vec3


class PointTarget(BaseModel):
    """A measurement endpoint given by explicit world coordinates (mm).

    Exact on its own — a picked vertex/snap point already has exact world
    coordinates, so no body recomputation is needed for a point target.
    """

    kind: Literal["point"] = "point"
    position: Vec3 = Field(description="World-space coordinates of the point (mm)")


class EdgeTarget(BaseModel):
    """A measurement endpoint that is a B-rep edge of the recomputed body.

    ``index`` is a TRANSIENT 0-based index into the recomputed body's
    deterministic edge list (build123d ``.edges()`` / OCCT exploration order —
    the same order the B-rep edge overlay enumerates). It is meaningful only
    against the ``tree`` sent in the SAME request and is NOT stable across
    edits (stable named references are topological naming, Phase 2 —
    feature-tree design §2.4). Requires :attr:`MeasureRequest.tree`.
    """

    kind: Literal["edge"] = "edge"
    index: int = Field(
        ge=0,
        description="0-based index into the recomputed body's deterministic "
        "edge list (transient — valid for this request/tree only, not stable "
        "across edits)",
    )


#: A measurement endpoint: an explicit point or a transient edge reference.
MeasureTarget = Annotated[PointTarget | EdgeTarget, Field(discriminator="kind")]


class MeasureRequest(BaseModel):
    """Measure the nearest distance between two targets (stateless, one-shot).

    ``tree`` is required iff either target is an edge — geometry recomputes
    that feature tree (reusing the ``POST /api/v1/evaluate`` machinery, so the
    same ordered dispatch + strict-prefix rule applies) and measures the exact
    B-rep edge. For point-point, ``tree`` is omitted and no body is built.
    """

    a: MeasureTarget = Field(description="First measurement target")
    b: MeasureTarget = Field(description="Second measurement target")
    tree: EvaluateTreeRequest | None = Field(
        default=None,
        description="Feature tree to recompute for edge targets (required iff a "
        "or b is an edge); ignored for point-point. Its linear_deflection is "
        "unused — measurement reads the exact B-rep, never the mesh.",
    )

    @model_validator(mode="after")
    def _tree_required_for_edges(self) -> Self:
        """An edge target has no meaning without a body to resolve it against."""
        needs_body = self.a.kind == "edge" or self.b.kind == "edge"
        if needs_body and self.tree is None:
            raise ValueError(
                "an edge target requires 'tree' (the feature tree to recompute "
                "and measure the exact B-rep edge against)"
            )
        return self


class MeasureResult(BaseModel):
    """Nearest distance between the two targets plus its components.

    ``distance`` is the exact minimum distance; ``delta`` are the signed
    component distances from the nearest point on A to the nearest point on B
    (its magnitude equals ``distance``). ``point_on_a``/``point_on_b`` are the
    witness points (what a UI draws the measurement line between). ``angle_deg``
    is the acute angle between the two targets, reported only for edge-edge
    where BOTH edges are straight lines (else null — no single direction).
    """

    kind: Literal["point_point", "point_edge", "edge_edge"] = Field(
        description="Which pair of target flavours was measured"
    )
    distance: float = Field(
        description="Exact nearest (minimum) distance between the targets (mm)"
    )
    delta: Vec3 = Field(
        description="Component distances from the nearest point on A to the "
        "nearest point on B (mm): (dx, dy, dz); |delta| == distance"
    )
    point_on_a: Vec3 = Field(description="Nearest point on target A (mm)")
    point_on_b: Vec3 = Field(description="Nearest point on target B (mm)")
    angle_deg: float | None = Field(
        default=None,
        description="Acute angle between the two targets in degrees [0, 90], "
        "reported only for edge-edge where both edges are straight lines; null "
        "otherwise (a point or a curved edge has no single direction)",
    )
