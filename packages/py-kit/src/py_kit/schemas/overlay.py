"""Selection-overlay boundary DTOs — pickable geometry of an evaluated body.

Single source of truth (CLAUDE.md DRY rule) for the stateless overlay query
the geometry service serves at ``POST /api/v1/overlay`` and the gateway proxies
at ``POST /api/v1/geometry/overlay``. Pure pydantic only — kernel types never
appear here (CLAUDE.md service boundaries). Units are millimetres; coordinates
are in the SAME world space as :mod:`py_kit.schemas.measure` (OCCT-native mm,
Z-up), so a vertex snapped from an overlay can be sent straight back as a
:class:`py_kit.schemas.measure.PointTarget`.

Why this endpoint exists (feature-tree measurement pickability, BACKLOG #6b):
the measurement UI needs (a) EXACT vertex coordinates to snap to and (b) each
edge's transient index — and that index MUST equal the ``body.edges()``
position the measure endpoint resolves an :class:`~py_kit.schemas.measure.
EdgeTarget` against, or an edge measurement would silently target the wrong
edge. Both the overlay and the measure endpoint enumerate the SAME
``body.edges()`` list of the SAME recomputed body, so ``edges[i]`` here IS the
edge ``EdgeTarget(index=i)`` measures (proven by an order-equality gate).

**Transient contract (the KEY design decision, documented here + endpoint
docstring + docs/GEOMETRY-QA.md):** the vertex and edge indices are transient
— valid for THIS tree/request only, NOT stable across edits. They are ordinals
into the recomputed body's deterministic ``.vertices()`` / ``.edges()`` lists
(OCCT exploration order), exactly the same non-persistent selector as measure's
edge index. Stable named references that survive rebuilds are topological
naming (Phase 2, feature-tree design §2.4) — this is deliberately NOT that.
"""

from typing import Literal

from pydantic import BaseModel, Field

from py_kit.schemas.features import EvaluateTreeRequest
from py_kit.schemas.geometry import Vec3

#: Edge curve family, enough for the client to pick a hover/label style. Exact
#: nearest-distance still comes from the B-rep via ``/measure`` — this tag is a
#: rendering hint, not a measurement input.
OverlayEdgeKind = Literal["line", "circle", "other"]


class OverlayEdge(BaseModel):
    """One pickable B-rep edge of the evaluated body (transient index).

    The list position of this edge in :attr:`OverlayResult.edges` is its
    transient 0-based index — the SAME ordinal ``body.edges()`` yields, so
    passing it as :class:`~py_kit.schemas.measure.EdgeTarget` ``index`` measures
    THIS edge. Not stable across edits (topological naming is Phase 2).
    """

    kind: OverlayEdgeKind = Field(
        description="Curve family (line/circle/other) — a rendering hint only; "
        "measurement reads the exact B-rep, never this tag"
    )
    start: Vec3 = Field(description="Edge start vertex, world mm (curve param 0)")
    end: Vec3 = Field(
        description="Edge end vertex, world mm (curve param 1); equals start "
        "for a closed edge such as a full circle"
    )
    polyline: list[Vec3] = Field(
        description="Ordered world-mm points to draw the edge as a polyline "
        "(>= 2 points, start..end inclusive). A straight edge is exactly "
        "[start, end]; a curved edge is sampled to the request tree's "
        "linear_deflection — the SAME tolerance policy as the mesh, no new "
        "epsilon."
    )


class OverlayRequest(BaseModel):
    """Request the pickable selection geometry of an evaluated feature tree.

    ``tree`` is recomputed with the SAME ordered dispatch + strict-prefix rule
    as ``POST /api/v1/evaluate`` / ``/measure`` (reusing ``evaluate_tree``); the
    overlay is built from the last-good body. Its ``linear_deflection`` also
    fixes the curved-edge polyline sampling (one tolerance, no ad-hoc epsilon).
    A tree that recomputes to no body is a clean 422 ``tree_overlay_failed``.
    """

    tree: EvaluateTreeRequest = Field(
        description="Feature tree to recompute; the overlay describes its "
        "last-good body"
    )


class OverlayResult(BaseModel):
    """Pickable selection geometry of the evaluated body (all coords world mm).

    ``vertices`` and ``edges`` are index-aligned with the recomputed body's
    deterministic ``.vertices()`` / ``.edges()`` lists. A client snaps to a
    vertex (exact point-point / point-edge) by echoing its coordinates as a
    ``PointTarget``, and measures an edge by sending its list index as an
    ``EdgeTarget``. Both index spaces are TRANSIENT — this request/tree only.
    """

    vertices: list[Vec3] = Field(
        description="Exact world-mm snap points in body.vertices() order; echo "
        "one back as a measure PointTarget for an exact point measurement"
    )
    edges: list[OverlayEdge] = Field(
        description="Pickable edges in body.edges() order — the SAME "
        "enumeration measure resolves EdgeTarget.index against"
    )
