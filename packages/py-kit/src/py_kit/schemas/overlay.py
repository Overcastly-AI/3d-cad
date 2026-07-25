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
from uuid import UUID

from pydantic import BaseModel, Field

from py_kit.schemas.features import (
    EdgeSignature,
    EvaluateTreeRequest,
    PlanarFaceSignature,
)
from py_kit.schemas.geometry import Vec3

# --- Per-request work bound (engineering audit 2026-07-25 H4) --------------------
#
# Same posture as the G2 bounds in py_kit.schemas.features: the rate limiter caps
# request FREQUENCY, these cap the WORK one authenticated request can demand.
# Unlike the G2 bounds this one cannot be a parse-time ceiling — the face count is
# an OUTPUT of evaluation, not an input — so it is enforced where the work happens
# and DEGRADES rather than rejects (below).

#: Ceiling on the face fingerprints ONE per-face provenance pass may compute:
#: ``len(final faces) + sum(len(snapshot faces))``. Each fingerprint is an exact-
#: B-rep GProp (area + area centroid), measured at ~186 us/face (2026-07-25,
#: build123d 0.11.1 / OCCT 7.9), so this bounds the pass at ~1.5 s — inside the
#: RESEARCH §9 2 s rebuild ceiling — where the UNBOUNDED pass took 8.8 s at 4800
#: faces and grew super-linearly (a 20k-face STEP import ran for minutes) on the
#: interactive selection route (audit H4). An authored part is nowhere near the
#: bound (tens of body-affecting features x tens-to-low-hundreds of faces each),
#: so a working engineer never feels it.
#:
#: Over-bound DEGRADES, never errors: :func:`geometry.kernel.attribute_faces`
#: returns all-``None`` attribution, so ``OverlayFace.feature_id`` is null and the
#: frontend falls back to whole-body selection — exactly the behaviour before
#: per-face provenance existed. A 422 would be strictly worse: it would take the
#: whole overlay (vertex/edge/face picking, measure, sketch-on-face) away from
#: large imported bodies that work fine today, to protect a RENDERING nicety.
MAX_PROVENANCE_FACES = 8_000

#: Edge curve family, enough for the client to pick a hover/label style. Exact
#: nearest-distance still comes from the B-rep via ``/measure`` — this tag is a
#: rendering hint, not a measurement input.
OverlayEdgeKind = Literal["line", "circle", "other"]


class OverlayEdge(BaseModel):
    """One pickable B-rep edge of the evaluated body (transient index).

    The list position of this edge in :attr:`OverlayResult.edges` is its
    transient 0-based index — the SAME ordinal ``body.edges()`` yields, so
    passing it as :class:`~py_kit.schemas.measure.EdgeTarget` ``index`` measures
    THIS edge. The transient index is for MEASUREMENT; the STABLE, rebuild-
    surviving reference is :attr:`signature` (topological naming) — echo it into
    an ``EdgeSubshapeRef`` to fillet/chamfer exactly this edge.
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
    signature: EdgeSignature = Field(
        description="Stage-1 edge signature (curve/endpoints/midpoint/length) — "
        "the SAME fingerprint the fillet/chamfer picked-edge resolver matches "
        "against (one enumeration: pick side == resolve side, an order-equality "
        "gate proves it). Echo it into an EdgeSubshapeRef to round THIS edge. "
        "Unlike the transient index, it survives rebuilds (best-effort, stage 1)."
    )


class OverlayFace(BaseModel):
    """One face of the evaluated body — pickable for a sketch datum-on-a-face.

    A PLANAR face carries a stage-1
    :class:`~py_kit.schemas.features.PlanarFaceSignature` — the SAME fingerprint
    a datum-on-face ``SubshapeRef`` stores and the geometry resolver matches
    against (one enumeration: the pick side and the resolve side share
    ``geometry.kernel.faces.planar_faces``; an order-equality gate proves it). To
    place a sketch on a face, echo its ``signature`` into a ``SubshapeRef`` — the
    same round-trip a vertex makes into a ``PointTarget``. A NON-planar face has
    ``signature = null`` and is not sketchable in v1 (topological naming's face
    signatures are planar-only until edge/curved-surface support lands).

    ``index`` is TRANSIENT — the ``body.faces()`` position for THIS tree only,
    not stable across edits (the persisted reference is the signature, never the
    index — topological naming, feature-tree design §2.4).
    """

    index: int = Field(
        description="Transient 0-based body.faces() index (this tree only; NOT "
        "stable across edits — the stored reference is the signature)"
    )
    planar: bool = Field(
        description="True if the face is planar (sketchable — carries a signature)"
    )
    signature: PlanarFaceSignature | None = Field(
        default=None,
        description="Stage-1 face signature (normal/centroid/area) for a planar "
        "face; null for a non-planar face. Echo it into a SubshapeRef to place a "
        "datum-on-a-face sketch here.",
    )
    feature_id: UUID | None = Field(
        default=None,
        description="Feature that OWNS this face (created it, or last modified it "
        "into its current form) — the tree feature id (FeatureResult.feature_id / "
        "the evaluate request's feature.id), for feature-localized selection "
        "highlighting (FINDINGS #9). Map a selected feature id to its faces by "
        "collecting every OverlayFace whose feature_id equals it; each face's "
        "`index` is its body.faces() ordinal (== the GLB primitive ordinal, one "
        "glTF primitive per B-rep face), so those indices are the mesh face set to "
        "highlight. Best-effort provenance for RENDERING (a cylindrical hole wall "
        "attributes to the hole, the untouched base faces to the extrude); NOT a "
        "rebuild-surviving reference (that is the signature). Null when the server "
        "did not compute attribution: an older payload, a body with no "
        "body-affecting feature, or a body past MAX_PROVENANCE_FACES (work bound, "
        "audit H4 — attribution degrades to null rather than pinning a worker; "
        "clients must handle null and fall back to whole-body selection).",
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
    faces: list[OverlayFace] = Field(
        description="Faces in body.faces() order; each planar face carries the "
        "SAME stage-1 signature the datum-on-face resolver matches against — echo "
        "a planar face's signature into a SubshapeRef to sketch on it"
    )
