"""Durable dimension anchors — the resolver unit gates (audit N1).

:mod:`geometry.drawings.anchor` adds the EDGE tier that picked faces have had since
FINDINGS #3: the strict stage-1 signature first, then a re-match on the
rebuild-invariant of the edge's curve kind. These tests pin the predicate itself —
what it accepts, what it refuses, and that it refuses rather than guesses — on real
kernel bodies. The end-to-end "widen the plate, the dimension re-measures" gate lives
in ``test_drawings_resize.py``.
"""

from __future__ import annotations

import math

import pytest
from build123d import Axis, Box, Cylinder, Pos
from geometry.drawings.anchor import resolve_anchor_edge
from geometry.kernel.edges import edge_signature_dto, enumerate_edges
from geometry.kernel.faces import SubshapeAmbiguousError, SubshapeUnresolvedError
from geometry.kernel.types import BodyShape
from py_kit.schemas.features import EdgeSignature
from py_kit.schemas.geometry import Vec3

#: Signature-value comparison bound (mm). The bodies below are exact prisms/cylinders,
#: so a re-anchored edge's endpoints are exact rationals; this absorbs float
#: representation only. Documented, not ad-hoc (docs/GEOMETRY-QA.md posture).
_TOL = 1e-9


def _vec(x: float, y: float, z: float) -> Vec3:
    return Vec3(x=x, y=y, z=z)


def _line_sig(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> EdgeSignature:
    """A straight-edge signature spanning *a* → *b* (canonically ordered)."""
    lo, hi = sorted((a, b))
    return EdgeSignature(
        curve="line",
        end_a=_vec(*lo),
        end_b=_vec(*hi),
        midpoint=_vec((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2),
        length_mm=math.dist(lo, hi),
    )


def _plate(width: float, depth: float = 60.0, height: float = 10.0) -> BodyShape:
    """A width x depth x height box with its min corner at the origin."""
    return Pos(width / 2, depth / 2, height / 2) * Box(width, depth, height)


def _bottom_front_edge(body: BodyShape, width: float) -> EdgeSignature:
    """The plate's y=0, z=0 edge — the 'overall length' edge a print dimensions."""
    return _line_sig((0.0, 0.0, 0.0), (width, 0.0, 0.0))


def test_clean_rebuild_resolves_on_the_exact_tier() -> None:
    """An unchanged edge still matches the STRICT stage-1 signature — the durable tier
    is a fallback, never the default (so every clean rebuild is byte-identical)."""
    body = _plate(100.0)
    resolved = resolve_anchor_edge(body, _bottom_front_edge(body, 100.0))
    assert resolved.tier == "exact"
    assert resolved.signature.length_mm == pytest.approx(100.0, abs=_TOL)


def test_widened_plate_re_anchors_the_overall_length_edge() -> None:
    """THE audit N1 case at the resolver: the dimensioned edge grew 100 → 120 along
    itself, so the strict signature is dead and the durable tier re-anchors onto the
    SAME edge — the one on the same supporting line overlapping the stored span."""
    stored = _bottom_front_edge(_plate(100.0), 100.0)
    resolved = resolve_anchor_edge(_plate(120.0), stored)
    assert resolved.tier == "durable"
    assert resolved.signature.length_mm == pytest.approx(120.0, abs=_TOL)
    # And it is the SAME edge (same supporting line: y = 0, z = 0, along +x), not some
    # other 120 mm edge of the widened plate.
    assert (resolved.signature.end_a.y, resolved.signature.end_a.z) == (0.0, 0.0)
    assert (resolved.signature.end_b.y, resolved.signature.end_b.z) == (0.0, 0.0)
    assert resolved.signature.end_b.x == pytest.approx(120.0, abs=_TOL)


def test_symmetric_growth_re_anchors_too() -> None:
    """A plate that grows about its CENTRE moves BOTH endpoints (the midpoint stays) —
    the case an endpoint-sharing rule would miss. Collinearity + span overlap does not
    care which end moved."""
    stored = _line_sig((-50.0, 0.0, 0.0), (50.0, 0.0, 0.0))
    body = Pos(0.0, 30.0, 5.0) * Box(120.0, 60.0, 10.0)
    resolved = resolve_anchor_edge(body, stored)
    assert resolved.tier == "durable"
    assert resolved.signature.length_mm == pytest.approx(120.0, abs=_TOL)


def test_shrunken_edge_re_anchors() -> None:
    """Shrinking is the same invariant as growing (a narrowed plate, a bigger corner
    round eating into the edge)."""
    stored = _bottom_front_edge(_plate(100.0), 100.0)
    resolved = resolve_anchor_edge(_plate(80.0), stored)
    assert resolved.tier == "durable"
    assert resolved.signature.length_mm == pytest.approx(80.0, abs=_TOL)


def test_a_parallel_but_not_collinear_edge_is_not_accepted() -> None:
    """The plate's DEPTH changed, so the dimensioned edge moved sideways onto a
    DIFFERENT supporting line. A parallel-only rule would grab the far edge and stamp a
    plausible wrong number; requiring the same supporting line refuses instead."""
    # Stored: the y = 60 (back) edge of a 60-deep plate. New plate is 40 deep, so
    # nothing lies on y = 60 any more; the y = 40 back edge is parallel, not collinear.
    stored = _line_sig((0.0, 60.0, 0.0), (100.0, 60.0, 0.0))
    with pytest.raises(SubshapeUnresolvedError):
        resolve_anchor_edge(_plate(100.0, depth=40.0), stored)


def test_two_collinear_segments_are_an_honest_ambiguity() -> None:
    """A slot cut through the middle of the dimensioned edge leaves TWO collinear
    segments overlapping the stored span. Refuse to guess which one the dimension
    meant (topological-naming §5) rather than pick the first."""
    body = _plate(100.0) - (Pos(50.0, 0.0, 5.0) * Box(20.0, 20.0, 10.0))
    stored = _bottom_front_edge(body, 100.0)
    with pytest.raises(SubshapeAmbiguousError):
        resolve_anchor_edge(body, stored)


def test_resized_hole_re_anchors_its_rim_circle() -> None:
    """A hole's Ø changed: the rim's endpoints, midpoint and length all moved, but its
    CENTRE, plane and angular station did not. The durable tier re-anchors and the
    radius is the NEW one, measured off the current B-rep."""
    plate = _plate(100.0)
    small = plate - (Pos(50.0, 30.0, 5.0) * Cylinder(5.0, 10.0))
    stored = _rim_signature(small, radius=5.0)
    grown = plate - (Pos(50.0, 30.0, 5.0) * Cylinder(7.0, 10.0))
    resolved = resolve_anchor_edge(grown, stored)
    assert resolved.tier == "durable"
    assert resolved.edge.radius == pytest.approx(7.0, abs=1e-7)


def test_moved_hole_is_unresolved_not_a_wrong_circle() -> None:
    """A hole that MOVED breaks the centre invariant, so its diameter dimension fails
    honestly instead of re-anchoring onto the hole at its new place (which would stamp
    a number against geometry the user never picked)."""
    plate = _plate(100.0)
    stored = _rim_signature(plate - (Pos(50.0, 30.0, 5.0) * Cylinder(5.0, 10.0)), 5.0)
    moved = plate - (Pos(70.0, 30.0, 5.0) * Cylinder(5.0, 10.0))
    with pytest.raises(SubshapeUnresolvedError):
        resolve_anchor_edge(moved, stored)


def test_free_form_curve_has_no_durable_tier() -> None:
    """A spline/ellipse edge has no invariant we can state honestly, so it stays an
    honest unresolved — the message says so instead of inventing a match."""
    stored = EdgeSignature(
        curve="other",
        end_a=_vec(0.0, 0.0, 0.0),
        end_b=_vec(10.0, 0.0, 0.0),
        midpoint=_vec(5.0, 1.0, 0.0),
        length_mm=10.5,
    )
    with pytest.raises(SubshapeUnresolvedError, match="no rebuild-invariant"):
        resolve_anchor_edge(_plate(100.0), stored)


def _notch(radius: float) -> BodyShape:
    """A 100 x 60 x 10 plate with a semicircular notch cut in its y = 0 face, centred
    at x = 50 — so the notch's rim is a genuine ARC whose centre is the sketch point
    (50, 0), fixed under a radius change."""
    return _plate(100.0) - (Pos(50.0, 0.0, 5.0) * Cylinder(radius, 10.0))


def _top_arc(body: BodyShape) -> EdgeSignature:
    """The notch's top-face rim ARC (z = 10, endpoints distinct — not a full circle)."""
    arcs = [
        record.signature
        for record in enumerate_edges(body)
        if record.signature.curve == "circle"
        and abs(record.signature.end_a.z - 10.0) < _TOL
        and math.dist(
            (record.signature.end_a.x, record.signature.end_a.y),
            (record.signature.end_b.x, record.signature.end_b.y),
        )
        > _TOL
    ]
    assert len(arcs) == 1, f"expected exactly one top-face arc, got {len(arcs)}"
    return arcs[0]


def test_arc_centre_is_derived_from_the_stored_signature() -> None:
    """The circular tier derives centre + angular station from the three stored points
    alone (no new persisted state) — proven on a genuine ARC, not a full circle: a
    semicircular notch widened R8 → R12 re-anchors, and the measured radius is the NEW
    one. This is the case a centre-from-two-seam-points shortcut would get wrong."""
    stored = _top_arc(_notch(8.0))
    # The unchanged body resolves on the exact tier.
    assert resolve_anchor_edge(_notch(8.0), stored).tier == "exact"
    resolved = resolve_anchor_edge(_notch(12.0), stored)
    assert resolved.tier == "durable"
    assert resolved.edge.radius == pytest.approx(12.0, abs=1e-6)
    # Same arc: still on the top face, still centred on the notch's sketch point.
    assert resolved.signature.end_a.z == pytest.approx(10.0, abs=_TOL)


def test_a_re_radiused_FILLET_arc_is_an_honest_error_not_a_guess() -> None:
    """A corner round's arc is the documented LIMIT of the circular invariant: changing
    R4 → R6 moves the arc's CENTRE (it sits R in from the corner), so there is no
    invariant to re-anchor on and the dimension fails honestly rather than re-measuring
    a differently-placed arc. A dimension that silently resolves to the wrong geometry
    is worse than one that errors (topological-naming §11; the adjacency-based fix is
    stage-2 provenance)."""
    body = _plate(40.0, depth=40.0)
    filleted = body.fillet(4.0, body.edges().filter_by(Axis.Z))  # type: ignore[union-attr]
    arcs = [
        record.signature
        for record in enumerate_edges(filleted)
        if record.signature.curve == "circle" and abs(record.signature.end_a.z) < _TOL
    ]
    assert arcs, "the filleted plate should have corner arcs on its bottom face"
    stored = arcs[0]
    assert resolve_anchor_edge(filleted, stored).tier == "exact"
    bigger = body.fillet(6.0, body.edges().filter_by(Axis.Z))  # type: ignore[union-attr]
    with pytest.raises(SubshapeUnresolvedError):
        resolve_anchor_edge(bigger, stored)


def _rim_signature(body: BodyShape, radius: float) -> EdgeSignature:
    """The signature of a bored hole's rim edge on the TOP face (z = 10) of a plate."""
    candidates = [
        record.signature
        for record in enumerate_edges(body)
        if record.signature.curve == "circle"
        and abs(record.signature.end_a.z - 10.0) < _TOL
    ]
    assert candidates, "expected a circular rim edge on the top face"
    # Sanity: the rim really has the radius the caller says it does.
    edge = next(
        record.edge
        for record in enumerate_edges(body)
        if edge_signature_dto(record.edge) == candidates[0]
    )
    assert edge.radius == pytest.approx(radius, abs=1e-7)
    return candidates[0]
